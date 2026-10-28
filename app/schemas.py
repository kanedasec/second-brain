from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ShortText = Annotated[str, Field(min_length=1, max_length=200)]
Paragraph = Annotated[str, Field(min_length=1, max_length=4_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def require_timezone(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone offset")
    return value


class Generator(StrictModel):
    provider: ShortText
    model: ShortText | None = None


class Source(StrictModel):
    type: Literal["note", "email", "briefing", "recording", "diary", "document", "other"]
    label: ShortText
    description: Annotated[str, Field(max_length=1_000)] | None = None


class Topic(StrictModel):
    name: ShortText
    context: Annotated[str, Field(min_length=1, max_length=1_000)]


class Fact(StrictModel):
    statement: Paragraph
    evidence: Annotated[str, Field(min_length=1, max_length=2_000)]
    confidence: Literal["explicit", "strong", "uncertain"]


class Entity(StrictModel):
    name: ShortText
    type: Literal[
        "person", "organization", "software", "device", "architecture", "place", "concept", "other"
    ]
    mentioned_as: Annotated[str, Field(min_length=1, max_length=1_000)]
    evidence: Annotated[str, Field(min_length=1, max_length=2_000)]
    explanation: Annotated[str, Field(min_length=1, max_length=2_000)]
    explanation_source: Literal["source", "general_knowledge"]


class Action(StrictModel):
    title: ShortText
    status: Literal["open", "done", "cancelled"]
    due_at: datetime | None = None
    owner: ShortText | None = None
    evidence: Annotated[str, Field(min_length=1, max_length=2_000)]
    priority: Literal["low", "medium", "high"]

    _due_at_has_timezone = field_validator("due_at")(require_timezone)


class KnowledgeGap(StrictModel):
    question: Paragraph
    why_it_matters: Paragraph
    evidence: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None


class Recommendation(StrictModel):
    advice: Paragraph
    rationale: Paragraph
    related_topic: ShortText | None = None
    ai_generated: Literal[True]


class Memory(StrictModel):
    id: Annotated[
        str,
        Field(
            min_length=8,
            max_length=120,
            pattern=r"^[a-z0-9][a-z0-9._-]+$",
            description="Stable lowercase identifier, for example 2026-10-28-project-briefing-01",
        ),
    ]
    title: ShortText
    summary: Paragraph
    occurred_at: datetime | None
    context: Paragraph
    people: list[ShortText] = Field(default_factory=list, max_length=100)
    topics: list[Topic] = Field(min_length=1, max_length=50)
    facts: list[Fact] = Field(default_factory=list, max_length=200)
    entities: list[Entity] = Field(default_factory=list, max_length=100)
    actions: list[Action] = Field(default_factory=list, max_length=100)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list, max_length=100)
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=100)

    _occurred_at_has_timezone = field_validator("occurred_at")(require_timezone)


class KnowledgeBundle(StrictModel):
    schema_version: Literal["1.0"]
    generated_at: datetime
    generator: Generator
    source: Source
    memories: list[Memory] = Field(min_length=1, max_length=500)

    _generated_at_has_timezone = field_validator("generated_at")(require_timezone)

    @field_validator("memories")
    @classmethod
    def memory_ids_are_unique(cls, memories: list[Memory]) -> list[Memory]:
        ids = [memory.id for memory in memories]
        if len(ids) != len(set(ids)):
            raise ValueError("memory ids must be unique within a bundle")
        return memories
