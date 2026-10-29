from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas import KnowledgeBundle


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
