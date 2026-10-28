from __future__ import annotations

import json
from pathlib import Path

from app.schemas import GraphBundle, KnowledgeBundle


CONTENT_DIR = Path(__file__).with_name("content")
PROMPT_PATH = CONTENT_DIR / "ai-ingestion-prompt.md"
GRAPH_PROMPT_PATH = CONTENT_DIR / "graph-ingestion-prompt.md"


def json_schema() -> dict:
    return KnowledgeBundle.model_json_schema()


def graph_json_schema() -> dict:
    return GraphBundle.model_json_schema()


def _read(name: str) -> str:
    return (CONTENT_DIR / name).read_text(encoding="utf-8").strip() + "\n"


def _complete(instructions_path: Path, schema: dict) -> str:
    instructions = instructions_path.read_text(encoding="utf-8").strip()
    rendered = json.dumps(schema, indent=2, ensure_ascii=False)
    return f"{instructions}\n\n## Required JSON Schema\n\n```json\n{rendered}\n```\n"


def complete_prompt() -> str:
    return _complete(PROMPT_PATH, json_schema())


def complete_graph_prompt() -> str:
    return _complete(GRAPH_PROMPT_PATH, graph_json_schema())


# --- Prompt library ------------------------------------------------------
#
# Two tiers: source-preparation prompts that emit a written report, and the
# schema generator that turns a prepared report (or raw source) into graph JSON.
# `title`/`description` are English source strings translated in the template.

PROMPT_LIBRARY = [
    {
        "id": "email",
        "group": "prep",
        "output": "report",
        "title": "Email day review",
        "description": (
            "Review a day of email: important messages, tasks, who wrote, whether you "
            "replied, and what is still missing — with context."
        ),
        "getter": lambda: _read("email-review-prompt.md"),
    },
    {
        "id": "meeting",
        "group": "prep",
        "output": "report",
        "title": "Meeting transcript review",
        "description": (
            "Review a meeting recording transcript into decisions, actions, owners, "
            "and open questions."
        ),
        "getter": lambda: _read("meeting-review-prompt.md"),
    },
    {
        "id": "daily",
        "group": "prep",
        "output": "report",
        "title": "Interactive daily report",
        "description": (
            "Give it your day's notes and messages; it asks you focused questions, "
            "then writes a detailed daily report."
        ),
        "getter": lambda: _read("daily-report-prompt.md"),
    },
    {
        "id": "graph",
        "group": "schema",
        "output": "graph",
        "title": "Graph schema generator",
        "description": (
            "Turns a prepared report (or raw source) into the graph JSON the app imports."
        ),
        "getter": complete_graph_prompt,
        "schema_url": "/graph-schema.json",
    },
]

_PROMPTS_BY_ID = {item["id"]: item for item in PROMPT_LIBRARY}


def prompt_catalog() -> list[dict]:
    """Library metadata for the page — without the prompt bodies."""
    return [{k: v for k, v in item.items() if k != "getter"} for item in PROMPT_LIBRARY]


def prompt_text(prompt_id: str) -> str | None:
    item = _PROMPTS_BY_ID.get(prompt_id)
    return item["getter"]() if item else None
