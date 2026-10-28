from __future__ import annotations

import base64
import json
from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app


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
    response = client.post(
        "/import",
        files={"files": ("memory.json", json.dumps(example_bundle), "application/json")},
    )
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
    response = client.post(
        "/import",
        files={"files": ("broken.json", "{no", "application/json")},
    )
    assert response.status_code == 422
    assert "Invalid JSON" in response.text
    assert "Your atlas starts empty" in client.get("/").text


def test_cross_origin_post_is_rejected(client, example_bundle):
    response = client.post(
        "/import",
        headers={"Origin": "https://attacker.invalid"},
        files={"files": ("memory.json", json.dumps(example_bundle), "application/json")},
    )
    assert response.status_code == 403


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
