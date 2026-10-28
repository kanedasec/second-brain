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
