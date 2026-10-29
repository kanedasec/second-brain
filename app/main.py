from __future__ import annotations

import base64
import binascii
import json
import math
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import Settings
from app.db import (
    AmbiguousReconciliationError,
    DuplicateBundleError,
    DuplicateMemoryError,
    ReconciliationRequired,
    Repository,
)
from app.i18n import (
    LANG_COOKIE,
    LANG_LABELS,
    normalize_lang,
    other_lang,
    translator,
)
from app.prompt import (
    atlas_json_schema,
    complete_atlas_prompt,
    complete_graph_prompt,
    complete_prompt,
    graph_json_schema,
    json_schema,
    prompt_catalog,
    prompt_text,
)
from app.schemas import AtlasBundle, GraphBundle, KnowledgeBundle


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_PATHS = {"/ready", "/favicon.svg"}
CSRF_COOKIE_NAME = "second_brain_csrf"


def safe_filename(value: str | None) -> str:
    if not value:
        return "upload.json"
    return Path(value).name[:240]


def count_label(count: int, singular: str) -> str:
    return f"{count} {singular if count == 1 else singular + 's'}"


def parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"invalid date: {value}") from error


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    app_settings.prepare_directories()
    repository = Repository(app_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(
        title="Second Brain",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.repository = repository
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    templates.env.autoescape = True
    display_zone = ZoneInfo(app_settings.timezone)

    def display_datetime(value: str | datetime | None, date_only: bool = False) -> str:
        if not value:
            return "Date unknown"
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        local = parsed.astimezone(display_zone)
        return local.strftime("%d %b %Y" if date_only else "%d %b %Y · %H:%M")

    templates.env.filters["display_datetime"] = display_datetime
    templates.env.filters["display_due"] = lambda value: (
        display_datetime(value) if value else ""
    )

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):
        path = request.url.path
        is_public = path in PUBLIC_PATHS or path.startswith("/static/")
        if not is_public and app_settings.auth_enabled and not _valid_basic_auth(request, app_settings):
            return PlainTextResponse(
                "Authentication required",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Second Brain", charset="UTF-8"'},
            )

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not _is_same_origin_request(request):
                return PlainTextResponse("Cross-origin request denied", status_code=403)

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        return response

    def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
        lang = normalize_lang(request.cookies.get(LANG_COOKIE))
        values = {
            "request": request,
            "current_path": request.url.path,
            "t": translator(lang),
            "lang": lang,
            "other_lang": other_lang(lang),
            "lang_labels": LANG_LABELS,
        }
        if context:
            values.update(context)
        return templates.TemplateResponse(request, name, values, status_code=status_code)

    def render_import(
        request: Request,
        results: list[dict[str, Any]] | None = None,
        status_code: int = 200,
    ) -> Response:
        csrf_token = secrets.token_urlsafe(32)
        response = render(
            request,
            "import.jinja",
            {
                "csrf_token": csrf_token,
                "max_upload_mb": app_settings.max_upload_bytes // 1_048_576,
                "results": results or [],
            },
            status_code=status_code,
        )
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            max_age=3_600,
            httponly=True,
            secure=app_settings.environment == "production",
            samesite="strict",
            path="/import",
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        q: str = "",
        topic: str = "",
        date_from: str = "",
        date_to: str = "",
        page: int = 1,
    ):
        page = max(1, min(page, 10_000))
        parsed_date_from = parse_date(date_from)
        parsed_date_to = parse_date(date_to)
        start_at = (
            datetime.combine(parsed_date_from, time.min, tzinfo=display_zone)
            if parsed_date_from
            else None
        )
        end_at = (
            datetime.combine(parsed_date_to + timedelta(days=1), time.min, tzinfo=display_zone)
            if parsed_date_to
            else None
        )
        memories, total = repository.search_memories(
            query=q[:200],
            topic_slug=topic[:100],
            date_from=start_at,
            date_to_exclusive=end_at,
            page=page,
        )
        return render(
            request,
            "dashboard.html",
            {
                "stats": repository.stats(),
                "memories": memories,
                "topics": repository.list_topics(),
                "filters": {
                    "q": q[:200],
                    "topic": topic[:100],
                    "date_from": date_from,
                    "date_to": date_to,
                },
                "page": page,
                "pages": max(1, math.ceil(total / 20)),
                "total": total,
            },
        )

    @app.get("/memories/{memory_id}", response_class=HTMLResponse)
    async def memory_detail(request: Request, memory_id: str):
        memory = repository.get_memory(memory_id)
        if not memory:
            return render(request, "404.html", status_code=404)
        return render(request, "memory.html", {"memory": memory})

    @app.get("/topics/{slug}", response_class=HTMLResponse)
    async def topic_detail(request: Request, slug: str):
        topic = repository.topic_detail(slug)
        if not topic:
            return render(request, "404.html", status_code=404)
        return render(request, "topic.html", {"topic": topic})

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks(request: Request):
        return render(request, "tasks.html", {"board": repository.task_board()})

    @app.get("/import", response_class=HTMLResponse)
    async def import_page(request: Request):
        return render_import(request)

    @app.post("/import", response_class=HTMLResponse)
    async def import_files(
        request: Request,
        files: list[UploadFile] = File(...),
        csrf_token: str = Form(...),
        reconciliation_fingerprint: str = Form(""),
        confirm_reconciliation: str = Form(""),
    ):
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_token):
            raise HTTPException(status_code=403, detail="invalid CSRF token")

        results: list[dict[str, Any]] = []
        if len(files) > app_settings.max_upload_files:
            return render_import(
                request,
                [{"status": "error", "name": "Upload", "message": "too many files"}],
                status_code=422,
            )

        for uploaded in files:
            filename = safe_filename(uploaded.filename)
            try:
                if not filename.casefold().endswith(".json"):
                    raise ValueError("file must use the .json extension")
                raw_data = await uploaded.read(app_settings.max_upload_bytes + 1)
                if len(raw_data) > app_settings.max_upload_bytes:
                    raise ValueError("file exceeds the configured upload size")
                if not raw_data:
                    raise ValueError("file is empty")
                decoded = json.loads(raw_data)
                version = decoded.get("schema_version") if isinstance(decoded, dict) else None
                if version == "3.0":
                    atlas = AtlasBundle.model_validate(decoded)
                    confirmed_fingerprint = (
                        reconciliation_fingerprint
                        if confirm_reconciliation == "yes"
                        else None
                    )
                    counts = repository.import_atlas_bundle(
                        atlas,
                        filename,
                        raw_data,
                        reconciliation_fingerprint=confirmed_fingerprint,
                    )
                    results.append(
                        {
                            "status": "success",
                            "surface": "atlas",
                            "name": filename,
                            "message": (
                                (
                                    "Imported reconciled unified atlas ("
                                    if confirmed_fingerprint
                                    else "Imported unified atlas ("
                                )
                                + f"{count_label(counts['memories'], 'memory')}, "
                                f"{count_label(counts['nodes'], 'node')}, "
                                f"{count_label(counts['edges'], 'edge')})"
                            ),
                        }
                    )
                elif version == "2.0":
                    graph = GraphBundle.model_validate(decoded)
                    counts = repository.import_graph_bundle(graph, filename, raw_data)
                    results.append(
                        {
                            "status": "success",
                            "surface": "graph",
                            "name": filename,
                            "message": (
                                "Imported graph only ("
                                f"{count_label(counts['nodes'], 'node')}, "
                                f"{count_label(counts['edges'], 'edge')}). "
                                "It does not create memories or tasks."
                            ),
                        }
                    )
                else:
                    bundle = KnowledgeBundle.model_validate(decoded)
                    count = repository.import_bundle(bundle, filename, raw_data)
                    results.append(
                        {
                            "status": "success",
                            "surface": "memories",
                            "name": filename,
                            "message": f"Imported {count_label(count, 'memory')}",
                        }
                    )
            except ReconciliationRequired as error:
                results.append(
                    {
                        "status": "warning",
                        "surface": "reconciliation",
                        "name": filename,
                        "message": (
                            "No data was changed. Review the graph reconciliation plan "
                            "before confirming this import."
                        ),
                        "reconciliation": error.plan,
                        "confirmable": True,
                    }
                )
            except AmbiguousReconciliationError as error:
                results.append(
                    {
                        "status": "error",
                        "surface": "reconciliation",
                        "name": filename,
                        "message": (
                            "No data was changed. This file has ambiguous graph matches; "
                            "update its node IDs before importing."
                        ),
                        "reconciliation": error.plan,
                        "confirmable": False,
                    }
                )
            except json.JSONDecodeError as error:
                results.append(
                    {"status": "error", "name": filename, "message": f"Invalid JSON near line {error.lineno}"}
                )
            except ValidationError as error:
                first = error.errors(include_url=False)[0]
                location = ".".join(str(item) for item in first["loc"])
                results.append(
                    {"status": "error", "name": filename, "message": f"{location}: {first['msg']}"}
                )
            except (DuplicateBundleError, DuplicateMemoryError, ValueError) as error:
                results.append({"status": "error", "name": filename, "message": str(error)})
            finally:
                await uploaded.close()

        if any(item["status"] in {"success", "warning"} for item in results):
            status_code = 200
        else:
            status_code = 422
        return render_import(
            request,
            results,
            status_code=status_code,
        )

    @app.get("/prompt", response_class=HTMLResponse)
    async def prompt_page(request: Request):
        return render(request, "prompt.html", {"prompts": prompt_catalog()})

    @app.get("/prompts/{prompt_id}.txt", response_class=PlainTextResponse)
    async def prompt_library_download(prompt_id: str):
        text = prompt_text(prompt_id)
        if text is None:
            raise HTTPException(status_code=404, detail="unknown prompt")
        return PlainTextResponse(
            text,
            headers={
                "Content-Disposition": f'attachment; filename="second-brain-{prompt_id}-prompt.txt"'
            },
        )

    @app.get("/prompt.txt", response_class=PlainTextResponse)
    async def prompt_download():
        return PlainTextResponse(
            complete_prompt(),
            headers={"Content-Disposition": 'attachment; filename="second-brain-ingestion-prompt.txt"'},
        )

    @app.get("/schema.json", response_class=JSONResponse)
    async def schema_download():
        return JSONResponse(
            json_schema(),
            headers={"Content-Disposition": 'attachment; filename="second-brain-schema.json"'},
        )

    @app.get("/atlas-prompt.txt", response_class=PlainTextResponse)
    async def atlas_prompt_download():
        return PlainTextResponse(
            complete_atlas_prompt(),
            headers={
                "Content-Disposition": 'attachment; filename="second-brain-atlas-prompt.txt"'
            },
        )

    @app.get("/atlas-schema.json", response_class=JSONResponse)
    async def atlas_schema_download():
        return JSONResponse(
            atlas_json_schema(),
            headers={
                "Content-Disposition": 'attachment; filename="second-brain-atlas-schema.json"'
            },
        )

    @app.get("/graph", response_class=HTMLResponse)
    async def graph_page(request: Request):
        return render(request, "graph.html")

    @app.get("/graph.json", response_class=JSONResponse)
    async def graph_data():
        return JSONResponse(repository.graph_payload())

    @app.get("/export/graph.json")
    async def export_graph(nodes: str = "", depth: int = 3):
        seeds = [n for n in nodes.split(",") if n] or None
        depth = max(1, min(depth, 6))
        bundle = repository.export_graph(seeds=seeds, depth=depth)
        if bundle is None:
            raise HTTPException(status_code=404, detail="no graph to export")
        GraphBundle.model_validate(bundle)  # guard: the export must re-import
        filename = "second-brain-graph-selection.json" if seeds else "second-brain-graph.json"
        return Response(
            json.dumps(bundle, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/nodes/{node_id}", response_class=JSONResponse)
    async def node_data(node_id: str):
        detail = repository.node_detail(node_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="node not found")
        return JSONResponse(detail)

    @app.get("/graph-prompt.txt", response_class=PlainTextResponse)
    async def graph_prompt_download():
        return PlainTextResponse(
            complete_graph_prompt(),
            headers={
                "Content-Disposition": 'attachment; filename="second-brain-graph-prompt.txt"'
            },
        )

    @app.get("/graph-schema.json", response_class=JSONResponse)
    async def graph_schema_download():
        return JSONResponse(
            graph_json_schema(),
            headers={
                "Content-Disposition": 'attachment; filename="second-brain-graph-schema.json"'
            },
        )

    @app.get("/set-language")
    async def set_language(request: Request, lang: str = "en", next: str = "/"):
        code = normalize_lang(lang)
        # Only allow same-site relative redirect targets (no open redirect).
        target = next if next.startswith("/") and not next.startswith("//") else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            LANG_COOKIE, code, max_age=31_536_000, samesite="lax", path="/"
        )
        return response

    @app.get("/ready")
    async def ready():
        if repository.ready():
            return {"status": "ready"}
        return JSONResponse({"status": "not-ready"}, status_code=503)

    @app.get("/favicon.svg")
    async def favicon():
        return Response((BASE_DIR / "static" / "favicon.svg").read_bytes(), media_type="image/svg+xml")

    @app.exception_handler(404)
    async def not_found(request: Request, _: HTTPException):
        return render(request, "404.html", status_code=404)

    return app


def _valid_basic_auth(request: Request, settings: Settings) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return secrets.compare_digest(username, settings.username or "") and secrets.compare_digest(
        password, settings.password or ""
    )


def _is_same_origin_request(request: Request) -> bool:
    """Reject cross-site state-changing requests (CSRF defense).

    Prefer the Fetch Metadata ``Sec-Fetch-Site`` signal, which browsers set and
    page scripts cannot forge: only ``same-origin`` and ``none`` (a direct,
    user-initiated navigation) are allowed. When that header is absent (older
    clients), fall back to comparing the ``Origin`` host against ``Host``. A
    ``null`` Origin is not treated as a match here; same-origin browsers that
    send ``Origin: null`` (for example under a ``no-referrer`` policy) are
    admitted by the Fetch Metadata branch instead. The per-form double-submit
    CSRF token remains the second layer of defense.
    """
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site in {"same-origin", "none"}

    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return True
    return urlparse(origin).netloc.casefold() == request.headers.get("host", "").casefold()


app = create_app()
