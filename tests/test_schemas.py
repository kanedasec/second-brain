from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas import AtlasBundle, KnowledgeBundle


def test_example_bundle_is_valid(example_bundle):
    bundle = KnowledgeBundle.model_validate(example_bundle)
    assert bundle.schema_version == "1.0"
    assert bundle.memories[0].recommendations[0].ai_generated is True


def test_naive_timestamp_is_rejected(example_bundle):
    payload = deepcopy(example_bundle)
    payload["memories"][0]["occurred_at"] = "2026-10-28T14:30:00"
    with pytest.raises(ValidationError, match="timezone"):
        KnowledgeBundle.model_validate(payload)


def test_unknown_memory_date_can_remain_unknown(example_bundle):
    payload = deepcopy(example_bundle)
    payload["memories"][0]["occurred_at"] = None
    bundle = KnowledgeBundle.model_validate(payload)
    assert bundle.memories[0].occurred_at is None


def test_unknown_fields_are_rejected(example_bundle):
    payload = deepcopy(example_bundle)
    payload["memories"][0]["invented"] = "not allowed"
    with pytest.raises(ValidationError, match="Extra inputs"):
        KnowledgeBundle.model_validate(payload)


def test_ai_advice_cannot_masquerade_as_source_content(example_bundle):
    payload = deepcopy(example_bundle)
    payload["memories"][0]["recommendations"][0]["ai_generated"] = False
    with pytest.raises(ValidationError):
        KnowledgeBundle.model_validate(payload)


def test_duplicate_memory_ids_are_rejected(example_bundle):
    payload = deepcopy(example_bundle)
    payload["memories"].append(deepcopy(payload["memories"][0]))
    with pytest.raises(ValidationError, match="unique"):
        KnowledgeBundle.model_validate(payload)


def test_example_graph_is_valid(example_graph):
    from app.schemas import GraphBundle

    bundle = GraphBundle.model_validate(example_graph)
    assert bundle.schema_version == "2.0"
    assert len(bundle.nodes) == 9
    assert any(edge.provenance == "ai_inferred" for edge in bundle.edges)


def test_graph_edge_must_reference_existing_node(example_graph):
    from app.schemas import GraphBundle

    payload = deepcopy(example_graph)
    payload["edges"].append({"source": "person.ada-chen", "target": "missing.node", "label": "x"})
    with pytest.raises(ValidationError, match="unknown node id"):
        GraphBundle.model_validate(payload)


def test_graph_rejects_duplicate_node_ids(example_graph):
    from app.schemas import GraphBundle

    payload = deepcopy(example_graph)
    payload["nodes"].append(dict(payload["nodes"][0]))
    with pytest.raises(ValidationError, match="unique"):
        GraphBundle.model_validate(payload)


def test_graph_rejects_self_loop(example_graph):
    from app.schemas import GraphBundle

    payload = deepcopy(example_graph)
    payload["edges"].append(
        {"source": "person.ada-chen", "target": "person.ada-chen", "label": "self"}
    )
    with pytest.raises(ValidationError, match="different nodes"):
        GraphBundle.model_validate(payload)


def test_graph_rejects_unknown_field(example_graph):
    from app.schemas import GraphBundle

    payload = deepcopy(example_graph)
    payload["nodes"][0]["unexpected"] = "x"
    with pytest.raises(ValidationError):
        GraphBundle.model_validate(payload)


def test_example_atlas_is_valid(example_atlas):
    bundle = AtlasBundle.model_validate(example_atlas)
    assert bundle.schema_version == "3.0"
    assert bundle.nodes[0].id.startswith("mem:")
    assert bundle.memories[0].actions[0].evidence


def test_atlas_requires_a_graph_node_for_every_memory(example_atlas):
    payload = deepcopy(example_atlas)
    payload["nodes"] = [node for node in payload["nodes"] if node["category"] != "memory"]
    payload["edges"] = [
        edge
        for edge in payload["edges"]
        if not edge["source"].startswith("mem:") and not edge["target"].startswith("mem:")
    ]
    with pytest.raises(ValidationError, match="every memory must have a graph node"):
        AtlasBundle.model_validate(payload)


def test_atlas_memory_graph_node_must_use_memory_category(example_atlas):
    payload = deepcopy(example_atlas)
    node = next(node for node in payload["nodes"] if node["id"].startswith("mem:"))
    node["category"] = "event"
    with pytest.raises(ValidationError, match="category 'memory'"):
        AtlasBundle.model_validate(payload)


def test_atlas_rejects_graph_only_memory_nodes(example_atlas):
    payload = deepcopy(example_atlas)
    extra = deepcopy(payload["nodes"][0])
    extra["id"] = "mem:2026-10-28-graph-only-memory-01"
    extra["label"] = "Graph-only memory"
    extra["description"] = "This node has no matching editorial memory."
    payload["nodes"].append(extra)
    with pytest.raises(ValidationError, match="must correspond to an editorial memory"):
        AtlasBundle.model_validate(payload)


def test_atlas_memory_graph_node_must_match_editorial_memory(example_atlas):
    payload = deepcopy(example_atlas)
    node = next(node for node in payload["nodes"] if node["id"].startswith("mem:"))
    node["label"] = "Conflicting title"
    with pytest.raises(ValidationError, match="must match title"):
        AtlasBundle.model_validate(payload)


def test_atlas_source_graph_edges_require_evidence(example_atlas):
    payload = deepcopy(example_atlas)
    edge = next(edge for edge in payload["edges"] if edge.get("provenance") == "source")
    edge.pop("evidence", None)
    with pytest.raises(ValidationError, match="requires evidence"):
        AtlasBundle.model_validate(payload)
