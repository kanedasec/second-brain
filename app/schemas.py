from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


# --- Graph schema (version 2.0) ------------------------------------------
#
# A node-link knowledge graph. The external AI emits stable-id nodes and
# directional edges; every edge must reference existing node ids. Grounding is
# preserved: `provenance` distinguishes source-stated structure from AI
# inference, and `evidence`/`source` keep the original support.

GraphId = Annotated[
    str,
    Field(
        min_length=2,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9._:-]+$",
        description="Stable lowercase identifier, for example person.ada-lovelace",
    ),
]

NodeCategory = Literal[
    "person",
    "organization",
    "memory",
    "action",
    "project",
    "concept",
    "event",
    "technology",
    "place",
    "topic",
    "other",
]

Provenance = Literal["source", "ai_inferred"]


class GraphSource(StrictModel):
    type: Literal["note", "email", "briefing", "recording", "diary", "document", "other"]
    label: ShortText
    excerpt: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None


class Node(StrictModel):
    id: GraphId
    category: NodeCategory
    label: ShortText
    description: Annotated[str, Field(min_length=1, max_length=4_000)] | None = None
    occurred_at: datetime | None = None
    source: GraphSource | None = None
    provenance: Provenance = "source"
    metadata: dict[str, ShortText] | None = None

    _occurred_at_has_timezone = field_validator("occurred_at")(require_timezone)


class Edge(StrictModel):
    id: GraphId | None = None
    source: GraphId
    target: GraphId
    label: ShortText
    directed: bool = True
    description: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    evidence: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    provenance: Provenance = "source"
    metadata: dict[str, ShortText] | None = None


class GraphBundle(StrictModel):
    schema_version: Literal["2.0"]
    generated_at: datetime
    generator: Generator
    nodes: list[Node] = Field(min_length=1, max_length=5_000)
    edges: list[Edge] = Field(default_factory=list, max_length=20_000)

    _generated_at_has_timezone = field_validator("generated_at")(require_timezone)

    @model_validator(mode="after")
    def check_graph_integrity(self) -> "GraphBundle":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node ids must be unique within a bundle")
        known = set(node_ids)
        edge_ids = [edge.id for edge in self.edges if edge.id is not None]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge ids must be unique within a bundle")

        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"edge source references unknown node id: {edge.source}")
            if edge.target not in known:
                raise ValueError(f"edge target references unknown node id: {edge.target}")
            if edge.source == edge.target:
                raise ValueError(f"edge must connect two different nodes: {edge.source}")
        return self


class AtlasBundle(StrictModel):
    """Unified import format for every Second Brain surface.

    The editorial memories drive chronology, topics, tasks, search, grounded
    facts, gaps, and recommendations. Nodes and edges preserve richer graph
    relationships. Keeping both representations in one validated object lets
    the repository persist them atomically without inferring one from the
    other.
    """

    schema_version: Literal["3.0"]
    generated_at: datetime
    generator: Generator
    source: Source
    memories: list[Memory] = Field(min_length=1, max_length=500)
    nodes: list[Node] = Field(min_length=1, max_length=5_000)
    edges: list[Edge] = Field(default_factory=list, max_length=20_000)

    _generated_at_has_timezone = field_validator("generated_at")(require_timezone)

    @model_validator(mode="after")
    def check_atlas_integrity(self) -> "AtlasBundle":
        memory_ids = [memory.id for memory in self.memories]
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("memory ids must be unique within a bundle")

        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node ids must be unique within a bundle")
        known = set(node_ids)
        expected_memory_nodes = {f"mem:{memory_id}" for memory_id in memory_ids}
        missing_memory_nodes = sorted(expected_memory_nodes - known)
        if missing_memory_nodes:
            raise ValueError(
                "every memory must have a graph node named mem:<memory-id>; missing: "
                + ", ".join(missing_memory_nodes)
            )
        wrong_memory_nodes = sorted(
            node.id
            for node in self.nodes
            if node.id in expected_memory_nodes and node.category != "memory"
        )
        if wrong_memory_nodes:
            raise ValueError(
                "memory graph nodes must use category 'memory': "
                + ", ".join(wrong_memory_nodes)
            )
        unexpected_memory_nodes = sorted(
            node.id
            for node in self.nodes
            if (node.category == "memory" or node.id.startswith("mem:"))
            and node.id not in expected_memory_nodes
        )
        if unexpected_memory_nodes:
            raise ValueError(
                "memory graph nodes must correspond to an editorial memory: "
                + ", ".join(unexpected_memory_nodes)
            )
        nodes_by_id = {node.id: node for node in self.nodes}
        for memory in self.memories:
            node = nodes_by_id[f"mem:{memory.id}"]
            if (
                node.label != memory.title
                or node.description != memory.summary
                or node.occurred_at != memory.occurred_at
            ):
                raise ValueError(
                    f"memory graph node must match title, summary, and occurred_at: {node.id}"
                )

        unexplained_nodes = sorted(
            node.id
            for node in self.nodes
            if node.provenance == "ai_inferred" and not node.description
        )
        if unexplained_nodes:
            raise ValueError(
                "AI-inferred graph nodes require a description: "
                + ", ".join(unexplained_nodes)
            )

        edge_ids = [edge.id for edge in self.edges if edge.id is not None]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge ids must be unique within a bundle")

        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"edge source references unknown node id: {edge.source}")
            if edge.target not in known:
                raise ValueError(f"edge target references unknown node id: {edge.target}")
            if edge.source == edge.target:
                raise ValueError(f"edge must connect two different nodes: {edge.source}")
            if edge.provenance == "source" and not edge.evidence:
                raise ValueError(
                    f"source-grounded graph edge requires evidence: {edge.source} -> {edge.target}"
                )
            if edge.provenance == "ai_inferred" and not edge.description:
                raise ValueError(
                    f"AI-inferred graph edge requires a description: {edge.source} -> {edge.target}"
                )
        return self
