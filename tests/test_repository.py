from __future__ import annotations

import json

import pytest

from app.db import DuplicateBundleError, Repository
from app.schemas import KnowledgeBundle


def test_import_search_topic_and_task_views(settings, example_bundle):
    repository = Repository(settings.database_path)
    repository.initialize()
    raw = json.dumps(example_bundle).encode()
    bundle = KnowledgeBundle.model_validate(example_bundle)

    assert repository.import_bundle(bundle, "example.json", raw) == 1
    assert repository.stats() == {"memories": 1, "topics": 2, "open_actions": 2, "gaps": 1}

    memories, total = repository.search_memories(query="LoRaWAN")
    assert total == 1
    assert memories[0]["title"] == "Observatory sensor review"

    topics = repository.list_topics()
    project = next(item for item in topics if item["name"] == "Observatory project")
    detail = repository.topic_detail(project["slug"])
    assert detail is not None
    assert detail["facts"][0]["confidence"] == "explicit"
    assert detail["gaps"][0]["question"].startswith("Which firmware")

    board = repository.task_board()
    assert len(board["unscheduled"]) == 1
    assert sum(len(items) for items in board.values()) == 2


def test_exact_bundle_cannot_be_imported_twice(settings, example_bundle):
    repository = Repository(settings.database_path)
    repository.initialize()
    raw = json.dumps(example_bundle).encode()
    bundle = KnowledgeBundle.model_validate(example_bundle)
    repository.import_bundle(bundle, "example.json", raw)
    with pytest.raises(DuplicateBundleError):
        repository.import_bundle(bundle, "example.json", raw)
