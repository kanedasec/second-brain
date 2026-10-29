from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def example_bundle() -> dict:
    return json.loads((ROOT / "examples" / "example-memory.json").read_text(encoding="utf-8"))


@pytest.fixture
def example_graph() -> dict:
    return json.loads((ROOT / "examples" / "example-graph.json").read_text(encoding="utf-8"))


@pytest.fixture
def example_atlas() -> dict:
    return json.loads((ROOT / "examples" / "example-atlas.json").read_text(encoding="utf-8"))


@pytest.fixture
def overlapping_legacy_graph(example_atlas: dict) -> dict:
    memory = example_atlas["memories"][0]
    return {
        "schema_version": "2.0",
        "generated_at": "2026-10-28T18:00:00-03:00",
        "generator": {"provider": "legacy-example"},
        "nodes": [
            {
                "id": "memory.observatory-sensor-review",
                "category": "memory",
                "label": memory["title"],
                "description": "Legacy graph-only representation of the briefing.",
                "provenance": "source",
            },
            {
                "id": "tech.lorawan",
                "category": "technology",
                "label": "LoRaWAN",
                "description": "Legacy graph identity for LoRaWAN.",
                "provenance": "source",
            },
        ],
        "edges": [
            {
                "source": "memory.observatory-sensor-review",
                "target": "tech.lorawan",
                "label": "mentions",
                "directed": True,
                "evidence": "The note refers to the observatory's LoRaWAN gateway.",
                "provenance": "source",
            }
        ],
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "brain.sqlite3",
        backup_dir=tmp_path / "backups",
        environment="test",
        username=None,
        password=None,
        timezone="America/Sao_Paulo",
        max_upload_bytes=1_048_576,
        max_upload_files=5,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
