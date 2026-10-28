from __future__ import annotations

import base64
import json
from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app


def import_json(client, filename: str, content: str, headers: dict[str, str] | None = None):
    form = client.get("/import")
    assert form.status_code == 200
    csrf_token = client.cookies["second_brain_csrf"]
    return client.post(
        "/import",
        headers=headers or {},
        data={"csrf_token": csrf_token},
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
    assert "Imported graph" in response.text

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
