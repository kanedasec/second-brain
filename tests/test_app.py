from __future__ import annotations

import base64
import copy
import json
import re
from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app


def import_json(
    client,
    filename: str,
    content: str,
    headers: dict[str, str] | None = None,
    form_data: dict[str, str] | None = None,
):
    form = client.get("/import")
    assert form.status_code == 200
    csrf_token = client.cookies["second_brain_csrf"]
    return client.post(
        "/import",
        headers=headers or {},
        data={"csrf_token": csrf_token} | (form_data or {}),
        files={"files": (filename, content, "application/json")},
    )


def test_ready_and_empty_dashboard(client):
    assert client.get("/ready").json() == {"status": "ready"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Your atlas starts empty" in response.text


def test_prompt_and_schema_are_retrievable(client):
    prompt = client.get("/prompt.txt")
    assert prompt.status_code == 200
    assert "do not invent information" in prompt.text
    schema = client.get("/schema.json")
    assert schema.status_code == 200
    assert schema.json()["title"] == "KnowledgeBundle"


def test_json_upload_imports_and_renders_memory(client, example_bundle):
    response = import_json(client, "memory.json", json.dumps(example_bundle))
    assert response.status_code == 200
    assert "Imported" in response.text
    dashboard = client.get("/")
    assert "Observatory sensor review" in dashboard.text
    assert "Observatory sensor review" in client.get(
        "/?date_from=2026-10-28&date_to=2026-10-28"
    ).text
    assert "Observatory sensor review" not in client.get(
        "/?date_from=2026-10-27&date_to=2026-10-27"
    ).text
    detail = client.get("/memories/2026-10-28-observatory-planning-01")
    assert "Mentioned, explained" in detail.text
    assert "generated advice" in detail.text


def test_invalid_upload_does_not_write_data(client):
    response = import_json(client, "broken.json", "{no")
    assert response.status_code == 422
    assert "Invalid JSON" in response.text
    assert "Your atlas starts empty" in client.get("/").text


def test_cross_origin_post_is_rejected(client, example_bundle):
    response = import_json(
        client,
        "memory.json",
        json.dumps(example_bundle),
        headers={"Origin": "https://attacker.invalid"},
    )
    assert response.status_code == 403


def test_same_origin_null_origin_is_allowed(client, example_bundle):
    # Chromium under a no-referrer policy sends "Origin: null" on same-origin
    # form POSTs; the Fetch Metadata signal still marks them same-origin.
    response = import_json(
        client,
        "memory.json",
        json.dumps(example_bundle),
        headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200
    assert "Imported" in response.text


def test_cross_site_fetch_metadata_is_rejected(client, example_bundle):
    response = import_json(
        client,
        "memory.json",
        json.dumps(example_bundle),
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert "Your atlas starts empty" in client.get("/").text


def test_import_requires_matching_csrf_token(client, example_bundle):
    response = client.post(
        "/import",
        data={"csrf_token": "attacker-token"},
        files={"files": ("memory.json", json.dumps(example_bundle), "application/json")},
    )
    assert response.status_code == 403
    assert "Your atlas starts empty" in client.get("/").text


def test_import_report_escapes_uploaded_filename(client):
    response = import_json(client, "<img src=x onerror=alert(1)>.json", "{no")
    assert response.status_code == 422
    assert "<img src=x onerror=alert(1)>" not in response.text
    assert "&lt;img src=x onerror=alert(1)&gt;.json" in response.text


def test_production_auth_protects_data_but_not_readiness(settings):
    protected = replace(
        settings,
        environment="production",
        username="owner",
        password="correct-horse-battery-staple",
    )
    token = base64.b64encode(b"owner:correct-horse-battery-staple").decode()
    with TestClient(create_app(protected)) as protected_client:
        assert protected_client.get("/ready").status_code == 200
        assert protected_client.get("/").status_code == 401
        assert protected_client.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200


def import_graph(client, example_graph):
    form = client.get("/import")
    assert form.status_code == 200
    csrf_token = client.cookies["second_brain_csrf"]
    return client.post(
        "/import",
        data={"csrf_token": csrf_token},
        files={"files": ("graph.json", json.dumps(example_graph), "application/json")},
    )


def test_graph_import_and_graph_json(client, example_graph):
    response = import_graph(client, example_graph)
    assert response.status_code == 200
    assert "Imported graph only" in response.text
    assert "does not create memories or tasks" in response.text
    assert "View imported memories" not in response.text
    assert "View graph" in response.text
    assert "Your atlas starts empty" in client.get("/").text

    graph = client.get("/graph.json").json()
    assert len(graph["nodes"]) == 9
    assert len(graph["edges"]) == 9

    detail = client.get("/nodes/project.sensor-array")
    assert detail.status_code == 200
    assert detail.json()["category"] == "project"
    assert client.get("/nodes/does.not-exist").status_code == 404


def test_graph_prompt_and_schema_are_retrievable(client):
    prompt = client.get("/graph-prompt.txt")
    assert prompt.status_code == 200
    assert "knowledge graph" in prompt.text.lower()
    schema = client.get("/graph-schema.json")
    assert schema.status_code == 200
    assert schema.json()["properties"]["schema_version"]["const"] == "2.0"


def test_unified_atlas_import_populates_all_views(client, example_atlas):
    response = import_json(client, "atlas.json", json.dumps(example_atlas))
    assert response.status_code == 200
    assert "Imported unified atlas (1 memory, 2 nodes, 1 edge)" in response.text
    assert "View imported memories" in response.text
    assert "View graph" in response.text

    title = example_atlas["memories"][0]["title"]
    memory_id = example_atlas["memories"][0]["id"]
    assert title in client.get("/").text
    assert "Review the observatory sensor inventory" in client.get("/tasks").text
    assert "Grounded facts" in client.get("/topics/observatory-project").text
    graph = client.get("/graph.json").json()
    assert f"mem:{memory_id}" in {node["id"] for node in graph["nodes"]}
    assert client.get(f"/nodes/mem:{memory_id}").json()["record_id"] == memory_id


def test_task_completion_route_archives_task_without_creating_graph_node(
    client, example_atlas
):
    import_json(client, "atlas.json", json.dumps(example_atlas))
    board = client.app.state.repository.task_board()
    task = next(
        item
        for key, items in board.items()
        if key != "completed"
        for item in items
        if item["title"] == "Review the observatory sensor inventory"
    )
    page = client.get("/tasks")
    assert page.status_code == 200
    csrf_token = client.cookies["second_brain_task_csrf"]

    rejected = client.post(
        f"/tasks/{task['id']}/complete",
        data={"csrf_token": "wrong-token"},
        follow_redirects=False,
    )
    assert rejected.status_code == 403

    completed = client.post(
        f"/tasks/{task['id']}/complete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert completed.status_code == 303
    assert completed.headers["location"] == "/tasks?updated=done#completed"
    archive = client.get(completed.headers["location"])
    assert "Task concluded" in archive.text
    assert task["title"] in archive.text
    assert f'/tasks/{task["id"]}/complete' not in archive.text
    assert not any(
        node.get("metadata", {}).get("task_status") == "done"
        for node in client.get("/graph.json").json()["nodes"]
    )


def test_task_completion_updates_matching_existing_graph_node(
    client, example_atlas
):
    atlas_data = copy.deepcopy(example_atlas)
    memory = atlas_data["memories"][0]
    action = memory["actions"][0]
    action_node_id = "action.review-observatory-sensor-inventory"
    atlas_data["nodes"].append(
        {
            "id": action_node_id,
            "category": "action",
            "label": action["title"],
            "provenance": "source",
            "metadata": {"memory_id": memory["id"], "task_status": "open"},
        }
    )
    atlas_data["edges"].append(
        {
            "source": f"mem:{memory['id']}",
            "target": action_node_id,
            "label": "commits to",
            "evidence": action["evidence"],
            "provenance": "source",
        }
    )
    imported = import_json(client, "atlas.json", json.dumps(atlas_data))
    assert imported.status_code == 200
    board = client.app.state.repository.task_board()
    task = next(
        item
        for key, items in board.items()
        if key != "completed"
        for item in items
        if item["title"] == action["title"]
    )
    client.get("/tasks")
    csrf_token = client.cookies["second_brain_task_csrf"]

    completed = client.post(
        f"/tasks/{task['id']}/complete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert completed.status_code == 303
    assert completed.headers["location"] == "/tasks?updated=done&graph=1#completed"
    node = client.get(f"/nodes/{action_node_id}").json()
    assert node["metadata"]["task_status"] == "done"
    assert node["metadata"]["task_completed_at"]


def test_unified_atlas_reconciliation_preflight_and_confirmation(
    client, example_atlas, overlapping_legacy_graph
):
    import_graph(client, overlapping_legacy_graph)

    preview = import_json(client, "atlas.json", json.dumps(example_atlas))
    assert preview.status_code == 200
    assert "Graph reconciliation preflight" in preview.text
    assert "Likely duplicate identities" in preview.text
    assert "No data was changed" in preview.text
    assert "Observatory sensor review" not in client.get("/").text
    fingerprint = re.search(
        r'name="reconciliation_fingerprint" type="hidden" value="([a-f0-9]{64})"',
        preview.text,
    )
    assert fingerprint is not None

    confirmed = import_json(
        client,
        "atlas.json",
        json.dumps(example_atlas),
        form_data={
            "reconciliation_fingerprint": fingerprint.group(1),
            "confirm_reconciliation": "yes",
        },
    )
    assert confirmed.status_code == 200
    assert "Imported reconciled unified atlas" in confirmed.text
    assert "Observatory sensor review" in client.get("/").text
    graph = client.get("/graph.json").json()
    ids = {node["id"] for node in graph["nodes"]}
    assert "memory.observatory-sensor-review" not in ids
    assert "entity:technology:lorawan" not in ids
    mentions = [edge for edge in graph["edges"] if edge["label"] == "mentions"]
    assert len(mentions) == 1
    assert "memory.observatory-sensor-review" not in mentions[0]["id"]


def test_unified_atlas_prompt_and_schema_are_retrievable(client):
    prompt = client.get("/atlas-prompt.txt")
    assert prompt.status_code == 200
    assert "complete Second Brain" in prompt.text
    assert '"schema_version"' in prompt.text
    schema = client.get("/atlas-schema.json")
    assert schema.status_code == 200
    assert schema.json()["properties"]["schema_version"]["const"] == "3.0"


def test_graph_page_loads_viewer(client):
    response = client.get("/graph")
    assert response.status_code == 200
    assert "/static/vendor/force-graph.min.js" in response.text
    assert "/static/graph.js" in response.text
    assert 'id="graph-canvas"' in response.text
    # Phase 3 exploration controls
    assert 'id="graph-search-input"' in response.text
    assert 'id="graph-ai-toggle"' in response.text
    assert 'id="graph-reset"' in response.text


def test_language_toggle_sets_cookie_and_translates(client, example_bundle):
    # default English
    assert "Memories" in client.get("/").text
    # switch to Brazilian Portuguese
    resp = client.get("/set-language", params={"lang": "pt-BR", "next": "/"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "lang=pt-BR" in resp.headers.get("set-cookie", "")
    body = client.get("/").text  # cookie now stored by the test client
    assert "Memórias" in body and "Cronologia" in body


def test_set_language_rejects_offsite_redirect(client):
    resp = client.get(
        "/set-language", params={"lang": "en", "next": "//evil.example"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_topic_page_renders(client, example_bundle):
    import_json(client, "memory.json", json.dumps(example_bundle))
    # the example bundle has an "Observatory project" topic
    page = client.get("/topics/observatory-project")
    assert page.status_code == 200
    assert "Grounded facts" in page.text


def test_prompt_library_page_and_downloads(client):
    page = client.get("/prompt")
    assert page.status_code == 200
    # cards are listed but the full prompt bodies are NOT inlined in the page
    assert 'data-prompt-id="email"' in page.text
    assert 'data-prompt-id="atlas"' in page.text
    assert "Email day review" in page.text
    assert "Source material begins after this line" not in page.text  # not fully exposed

    email = client.get("/prompts/email.txt")
    assert email.status_code == 200
    assert "Email day review" in email.text
    assert "Prepared for the Second Brain unified atlas generator" in email.text

    atlas = client.get("/prompts/atlas.txt")
    assert atlas.status_code == 200
    assert '"schema_version"' in atlas.text  # schema appended for the generator

    # The old graph-only prompt remains available for compatibility but is no
    # longer advertised as the primary ingestion path.
    graph = client.get("/prompts/graph.txt")
    assert graph.status_code == 200

    assert client.get("/prompts/nope.txt").status_code == 404


def test_export_graph_roundtrips(client, example_graph):
    import_graph(client, example_graph)
    resp = client.get("/export/graph.json")
    assert resp.status_code == 200
    assert 'filename="second-brain-graph.json"' in resp.headers["content-disposition"]
    data = resp.json()
    assert data["schema_version"] == "2.0"
    from app.schemas import GraphBundle
    GraphBundle.model_validate(data)  # the export must re-import cleanly


def test_export_graph_empty_is_404(client):
    assert client.get("/export/graph.json").status_code == 404


def test_presentation_prompt_available(client):
    page = client.get("/prompt")
    assert 'data-prompt-id="presentation"' in page.text
    assert "Presentation builder" in page.text
    txt = client.get("/prompts/presentation.txt")
    assert txt.status_code == 200
    assert "single-page html" in txt.text.lower()


def test_export_selection_subgraph(client, example_graph):
    import_graph(client, example_graph)
    # seed one node; depth 1 should be smaller than the whole graph
    whole = client.get("/export/graph.json").json()
    sub = client.get("/export/graph.json", params={"nodes": "project.sensor-array", "depth": 1}).json()
    from app.schemas import GraphBundle
    GraphBundle.model_validate(sub)  # re-importable
    ids = {n["id"] for n in sub["nodes"]}
    assert "project.sensor-array" in ids
    assert len(sub["nodes"]) < len(whole["nodes"])  # a neighbourhood, not everything
    # depth 3 reaches more than depth 1 from the same seed
    sub3 = client.get("/export/graph.json", params={"nodes": "project.sensor-array", "depth": 3}).json()
    assert len(sub3["nodes"]) >= len(sub["nodes"])
    # unknown seed -> 404
    assert client.get("/export/graph.json", params={"nodes": "nope.zzz"}).status_code == 404
