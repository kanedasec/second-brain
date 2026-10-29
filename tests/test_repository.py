from __future__ import annotations

import json

import pytest

from app.db import DuplicateBundleError, Repository
from app.schemas import AtlasBundle, GraphBundle, KnowledgeBundle


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


def test_graph_import_payload_and_node_detail(settings, example_graph):
    from app.schemas import GraphBundle

    repository = Repository(settings.database_path)
    repository.initialize()
    raw = json.dumps(example_graph).encode()
    bundle = GraphBundle.model_validate(example_graph)

    counts = repository.import_graph_bundle(bundle, "graph.json", raw)
    assert counts == {"nodes": 9, "edges": 9}
    assert repository.graph_stats() == {"graph_nodes": 9, "graph_edges": 9}

    payload = repository.graph_payload()
    assert len(payload["nodes"]) == 9
    assert len(payload["edges"]) == 9

    detail = repository.node_detail("project.sensor-array")
    assert detail is not None
    assert detail["category"] == "project"
    # incoming edges from people, memory, event, concept; outgoing to tech and place
    labels = {n["edge"]["label"] for n in detail["neighbors"]}
    assert {"leads", "uses", "located at", "part of"} <= labels

    # re-importing the identical file is rejected by checksum
    with pytest.raises(DuplicateBundleError):
        repository.import_graph_bundle(bundle, "graph.json", raw)


def test_graph_nodes_upsert_across_imports(settings, example_graph):
    from app.schemas import GraphBundle

    repository = Repository(settings.database_path)
    repository.initialize()
    repository.import_graph_bundle(
        GraphBundle.model_validate(example_graph), "a.json", json.dumps(example_graph).encode()
    )

    second = {
        "schema_version": "2.0",
        "generated_at": "2026-10-29T10:00:00-03:00",
        "generator": {"provider": "example"},
        "nodes": [
            {"id": "person.ada-chen", "category": "person", "label": "Ada Chen (lead)"},
            {"id": "person.rui-silva", "category": "person", "label": "Rui Silva"},
        ],
        "edges": [
            {"source": "person.rui-silva", "target": "person.ada-chen", "label": "reports to"}
        ],
    }
    repository.import_graph_bundle(
        GraphBundle.model_validate(second), "b.json", json.dumps(second).encode()
    )

    stats = repository.graph_stats()
    assert stats["graph_nodes"] == 10  # 9 + 1 new; ada-chen merged, not duplicated
    detail = repository.node_detail("person.ada-chen")
    assert detail["label"] == "Ada Chen (lead)"  # updated by the second import


def test_graph_payload_projects_v1_memories(settings, example_bundle):
    repository = Repository(settings.database_path)
    repository.initialize()
    repository.import_bundle(
        KnowledgeBundle.model_validate(example_bundle),
        "mem.json",
        json.dumps(example_bundle).encode(),
    )
    payload = repository.graph_payload()
    categories = {node["category"] for node in payload["nodes"]}
    assert "memory" in categories and "topic" in categories
    assert any(edge["label"] == "about" for edge in payload["edges"])


def test_unified_atlas_populates_every_repository_surface(settings, example_atlas):
    repository = Repository(settings.database_path)
    repository.initialize()
    raw = json.dumps(example_atlas).encode()

    counts = repository.import_atlas_bundle(
        AtlasBundle.model_validate(example_atlas), "atlas.json", raw
    )

    assert counts == {"memories": 1, "nodes": 2, "edges": 1}
    assert repository.stats() == {"memories": 1, "topics": 2, "open_actions": 2, "gaps": 1}
    assert repository.graph_stats() == {"graph_nodes": 2, "graph_edges": 1}
    assert repository.search_memories(query="LoRaWAN")[1] == 1
    assert len(repository.list_topics()) == 2
    assert sum(len(items) for items in repository.task_board().values()) == 2

    memory_id = example_atlas["memories"][0]["id"]
    detail = repository.node_detail(f"mem:{memory_id}")
    assert detail is not None
    assert detail["record_id"] == memory_id


def test_unified_atlas_rolls_back_memories_when_graph_import_fails(
    settings, example_atlas, example_graph
):
    repository = Repository(settings.database_path)
    repository.initialize()
    raw = json.dumps(example_atlas).encode()

    # Reserve the atlas checksum only in graph_imports. The unified import then
    # reaches the graph duplicate after staging its memories; the transaction
    # must roll those memory writes back.
    repository.import_graph_bundle(
        GraphBundle.model_validate(example_graph), "existing-graph.json", raw
    )
    with pytest.raises(DuplicateBundleError):
        repository.import_atlas_bundle(
            AtlasBundle.model_validate(example_atlas), "atlas.json", raw
        )

    assert repository.stats() == {"memories": 0, "topics": 0, "open_actions": 0, "gaps": 0}
