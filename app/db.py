from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from app.schemas import GraphBundle, KnowledgeBundle


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checksum TEXT NOT NULL UNIQUE,
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    generator_provider TEXT NOT NULL,
    generator_model TEXT,
    generated_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    memory_count INTEGER NOT NULL CHECK (memory_count > 0)
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    occurred_at TEXT,
    context TEXT NOT NULL,
    people_json TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS memories_occurred_at_idx ON memories(occurred_at DESC);
CREATE INDEX IF NOT EXISTS memories_source_type_idx ON memories(source_type);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE
);

CREATE TABLE IF NOT EXISTS memory_topics (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    context TEXT NOT NULL,
    PRIMARY KEY (memory_id, topic_id)
);

CREATE INDEX IF NOT EXISTS memory_topics_topic_idx ON memory_topics(topic_id, memory_id);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    statement TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('explicit', 'strong', 'uncertain'))
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    mentioned_as TEXT NOT NULL,
    evidence TEXT NOT NULL,
    explanation TEXT NOT NULL,
    explanation_source TEXT NOT NULL CHECK (explanation_source IN ('source', 'general_knowledge'))
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'done', 'cancelled')),
    due_at TEXT,
    owner TEXT,
    evidence TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS actions_status_due_idx ON actions(status, due_at);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    evidence TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    advice TEXT NOT NULL,
    rationale TEXT NOT NULL,
    related_topic TEXT,
    ai_generated INTEGER NOT NULL DEFAULT 1 CHECK (ai_generated = 1)
);

-- Graph schema (version 2.0): first-class nodes and directional edges.
-- Nodes and edges upsert across imports so the graph accumulates; an
-- identical uploaded file is still rejected by its checksum.

CREATE TABLE IF NOT EXISTS graph_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checksum TEXT NOT NULL UNIQUE,
    source_filename TEXT NOT NULL,
    generator_provider TEXT NOT NULL,
    generator_model TEXT,
    generated_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    node_count INTEGER NOT NULL CHECK (node_count > 0),
    edge_count INTEGER NOT NULL CHECK (edge_count >= 0)
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    occurred_at TEXT,
    source_type TEXT,
    source_label TEXT,
    source_excerpt TEXT,
    provenance TEXT NOT NULL DEFAULT 'source'
        CHECK (provenance IN ('source', 'ai_inferred')),
    metadata_json TEXT,
    import_id INTEGER REFERENCES graph_imports(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS graph_nodes_category_idx ON graph_nodes(category);

CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_key TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    directed INTEGER NOT NULL DEFAULT 1 CHECK (directed IN (0, 1)),
    description TEXT,
    evidence TEXT,
    provenance TEXT NOT NULL DEFAULT 'source'
        CHECK (provenance IN ('source', 'ai_inferred')),
    metadata_json TEXT,
    import_id INTEGER REFERENCES graph_imports(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS graph_edges_source_idx ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS graph_edges_target_idx ON graph_edges(target_id);
"""

MEMORY_CHILD_QUERIES = {
    "facts": "SELECT * FROM facts WHERE memory_id = ? ORDER BY id",
    "entities": "SELECT * FROM entities WHERE memory_id = ? ORDER BY id",
    "actions": "SELECT * FROM actions WHERE memory_id = ? ORDER BY id",
    "knowledge_gaps": "SELECT * FROM knowledge_gaps WHERE memory_id = ? ORDER BY id",
    "recommendations": "SELECT * FROM recommendations WHERE memory_id = ? ORDER BY id",
}

OPEN_ACTIONS_SQL = """
SELECT a.*, m.title AS memory_title, m.occurred_at
FROM actions a JOIN memories m ON m.id = a.memory_id
WHERE a.status = 'open'
ORDER BY CASE a.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
         a.due_at, m.occurred_at DESC
"""


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if slug:
        return slug[:72]
    return "topic-" + hashlib.sha256(value.casefold().encode()).hexdigest()[:10]


class DuplicateBundleError(ValueError):
    pass


class DuplicateMemoryError(ValueError):
    pass


class Repository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(SCHEMA)
            connection.commit()

    def ready(self) -> bool:
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def import_bundle(self, bundle: KnowledgeBundle, filename: str, raw_data: bytes) -> int:
        checksum = hashlib.sha256(raw_data).hexdigest()
        now = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    "SELECT 1 FROM imports WHERE checksum = ?", (checksum,)
                ).fetchone():
                    raise DuplicateBundleError("this exact JSON file has already been imported")

                existing = []
                for memory in bundle.memories:
                    row = connection.execute(
                        "SELECT id FROM memories WHERE id = ?", (memory.id,)
                    ).fetchone()
                    if row:
                        existing.append(row)
                if existing:
                    ids = ", ".join(row["id"] for row in existing)
                    raise DuplicateMemoryError(f"memory id already exists: {ids}")

                cursor = connection.execute(
                    """
                    INSERT INTO imports (
                        checksum, source_filename, source_type, source_label,
                        generator_provider, generator_model, generated_at, imported_at, memory_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checksum,
                        filename,
                        bundle.source.type,
                        bundle.source.label,
                        bundle.generator.provider,
                        bundle.generator.model,
                        utc_iso(bundle.generated_at),
                        now,
                        len(bundle.memories),
                    ),
                )
                import_id = cursor.lastrowid

                for memory in bundle.memories:
                    connection.execute(
                        """
                        INSERT INTO memories (
                            id, import_id, title, summary, occurred_at, context, people_json,
                            source_type, source_label, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            memory.id,
                            import_id,
                            memory.title,
                            memory.summary,
                            utc_iso(memory.occurred_at) if memory.occurred_at else None,
                            memory.context,
                            json.dumps(memory.people, ensure_ascii=False),
                            bundle.source.type,
                            bundle.source.label,
                            now,
                        ),
                    )
                    self._insert_children(connection, memory)
                connection.commit()
                return len(bundle.memories)
            except Exception:
                connection.rollback()
                raise

    def _insert_children(self, connection: sqlite3.Connection, memory: Any) -> None:
        for topic in memory.topics:
            topic_id = self._topic_id(connection, topic.name)
            connection.execute(
                "INSERT INTO memory_topics (memory_id, topic_id, context) VALUES (?, ?, ?)",
                (memory.id, topic_id, topic.context),
            )
        connection.executemany(
            "INSERT INTO facts (memory_id, statement, evidence, confidence) VALUES (?, ?, ?, ?)",
            [(memory.id, item.statement, item.evidence, item.confidence) for item in memory.facts],
        )
        connection.executemany(
            """
            INSERT INTO entities (
                memory_id, name, type, mentioned_as, evidence, explanation, explanation_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    memory.id,
                    item.name,
                    item.type,
                    item.mentioned_as,
                    item.evidence,
                    item.explanation,
                    item.explanation_source,
                )
                for item in memory.entities
            ],
        )
        connection.executemany(
            """
            INSERT INTO actions (memory_id, title, status, due_at, owner, evidence, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    memory.id,
                    item.title,
                    item.status,
                    utc_iso(item.due_at) if item.due_at else None,
                    item.owner,
                    item.evidence,
                    item.priority,
                )
                for item in memory.actions
            ],
        )
        connection.executemany(
            """
            INSERT INTO knowledge_gaps (memory_id, question, why_it_matters, evidence)
            VALUES (?, ?, ?, ?)
            """,
            [
                (memory.id, item.question, item.why_it_matters, item.evidence)
                for item in memory.knowledge_gaps
            ],
        )
        connection.executemany(
            """
            INSERT INTO recommendations (memory_id, advice, rationale, related_topic, ai_generated)
            VALUES (?, ?, ?, ?, 1)
            """,
            [
                (memory.id, item.advice, item.rationale, item.related_topic)
                for item in memory.recommendations
            ],
        )

    def _topic_id(self, connection: sqlite3.Connection, name: str) -> int:
        existing = connection.execute(
            "SELECT id FROM topics WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            return existing["id"]

        base_slug = slugify(name)
        slug = base_slug
        suffix = 1
        while connection.execute("SELECT 1 FROM topics WHERE slug = ?", (slug,)).fetchone():
            suffix += 1
            slug = f"{base_slug[:64]}-{suffix}"
        cursor = connection.execute("INSERT INTO topics (slug, name) VALUES (?, ?)", (slug, name))
        return cursor.lastrowid

    def stats(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM memories) AS memories,
                    (SELECT COUNT(*) FROM topics) AS topics,
                    (SELECT COUNT(*) FROM actions WHERE status = 'open') AS open_actions,
                    (SELECT COUNT(*) FROM knowledge_gaps) AS gaps
                """
            ).fetchone()
            return dict(row)

    def list_topics(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.slug, t.name, COUNT(mt.memory_id) AS memory_count,
                       MAX(m.occurred_at) AS latest_at
                FROM topics t
                JOIN memory_topics mt ON mt.topic_id = t.id
                JOIN memories m ON m.id = mt.memory_id
                GROUP BY t.id
                ORDER BY memory_count DESC, latest_at DESC, t.name COLLATE NOCASE
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def search_memories(
        self,
        *,
        query: str = "",
        topic_slug: str = "",
        date_from: datetime | None = None,
        date_to_exclusive: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        query = query.strip()
        pattern = f"%{query}%" if query else None
        topic_filter = topic_slug or None
        date_from_filter = utc_iso(date_from) if date_from else None
        date_to_filter = utc_iso(date_to_exclusive) if date_to_exclusive else None
        params: list[Any] = [
            pattern,
            *([pattern] * 10),
            topic_filter,
            topic_filter,
            date_from_filter,
            date_from_filter,
            date_to_filter,
            date_to_filter,
        ]

        with self.connect() as connection:
            total = connection.execute(
                """
                SELECT COUNT(*) FROM memories m
                WHERE (
                    ? IS NULL OR m.title LIKE ? OR m.summary LIKE ? OR m.context LIKE ?
                    OR m.people_json LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM facts f
                        WHERE f.memory_id = m.id
                          AND (f.statement LIKE ? OR f.evidence LIKE ?)
                    )
                    OR EXISTS (
                        SELECT 1 FROM entities e
                        WHERE e.memory_id = m.id
                          AND (e.name LIKE ? OR e.explanation LIKE ?)
                    )
                    OR EXISTS (
                        SELECT 1 FROM memory_topics smt
                        JOIN topics st ON st.id = smt.topic_id
                        WHERE smt.memory_id = m.id
                          AND (st.name LIKE ? OR smt.context LIKE ?)
                    )
                )
                AND (
                    ? IS NULL OR EXISTS (
                        SELECT 1 FROM memory_topics fmt
                        JOIN topics ft ON ft.id = fmt.topic_id
                        WHERE fmt.memory_id = m.id AND ft.slug = ?
                    )
                )
                AND (? IS NULL OR m.occurred_at >= ?)
                AND (? IS NULL OR m.occurred_at < ?)
                """,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT m.*,
                    (SELECT COUNT(*) FROM actions a
                     WHERE a.memory_id = m.id AND a.status = 'open') AS open_actions,
                    (SELECT COUNT(*) FROM knowledge_gaps g
                     WHERE g.memory_id = m.id) AS gap_count
                FROM memories m
                WHERE (
                    ? IS NULL OR m.title LIKE ? OR m.summary LIKE ? OR m.context LIKE ?
                    OR m.people_json LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM facts f
                        WHERE f.memory_id = m.id
                          AND (f.statement LIKE ? OR f.evidence LIKE ?)
                    )
                    OR EXISTS (
                        SELECT 1 FROM entities e
                        WHERE e.memory_id = m.id
                          AND (e.name LIKE ? OR e.explanation LIKE ?)
                    )
                    OR EXISTS (
                        SELECT 1 FROM memory_topics smt
                        JOIN topics st ON st.id = smt.topic_id
                        WHERE smt.memory_id = m.id
                          AND (st.name LIKE ? OR smt.context LIKE ?)
                    )
                )
                AND (
                    ? IS NULL OR EXISTS (
                        SELECT 1 FROM memory_topics fmt
                        JOIN topics ft ON ft.id = fmt.topic_id
                        WHERE fmt.memory_id = m.id AND ft.slug = ?
                    )
                )
                AND (? IS NULL OR m.occurred_at >= ?)
                AND (? IS NULL OR m.occurred_at < ?)
                ORDER BY COALESCE(m.occurred_at, m.created_at) DESC, m.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
            memories = [dict(row) for row in rows]
            for memory in memories:
                memory["topics"] = self._memory_topics(connection, memory["id"])
                memory["people"] = json.loads(memory.pop("people_json"))
            return memories, total

    def _memory_topics(self, connection: sqlite3.Connection, memory_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT t.name, t.slug, mt.context
            FROM memory_topics mt JOIN topics t ON t.id = mt.topic_id
            WHERE mt.memory_id = ? ORDER BY t.name COLLATE NOCASE
            """,
            (memory_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return None
            memory = dict(row)
            memory["people"] = json.loads(memory.pop("people_json"))
            memory["topics"] = self._memory_topics(connection, memory_id)
            for table, query in MEMORY_CHILD_QUERIES.items():
                rows = connection.execute(query, (memory_id,)).fetchall()
                memory[table] = [dict(item) for item in rows]
            return memory

    def topic_detail(self, slug: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            topic_row = connection.execute(
                "SELECT id, slug, name FROM topics WHERE slug = ?", (slug,)
            ).fetchone()
            if not topic_row:
                return None
            topic = dict(topic_row)
            memories = connection.execute(
                """
                SELECT m.id, m.title, m.summary, m.occurred_at, mt.context
                FROM memory_topics mt JOIN memories m ON m.id = mt.memory_id
                WHERE mt.topic_id = ? ORDER BY m.occurred_at DESC
                """,
                (topic["id"],),
            ).fetchall()
            facts = connection.execute(
                """
                SELECT f.*, m.title AS memory_title
                FROM facts f JOIN memories m ON m.id = f.memory_id
                JOIN memory_topics mt ON mt.memory_id = m.id
                WHERE mt.topic_id = ? ORDER BY m.occurred_at DESC, f.id
                """,
                (topic["id"],),
            ).fetchall()
            gaps = connection.execute(
                """
                SELECT g.*, m.title AS memory_title
                FROM knowledge_gaps g JOIN memories m ON m.id = g.memory_id
                JOIN memory_topics mt ON mt.memory_id = m.id
                WHERE mt.topic_id = ? ORDER BY m.occurred_at DESC, g.id
                """,
                (topic["id"],),
            ).fetchall()
            recommendations = connection.execute(
                """
                SELECT r.*, m.title AS memory_title
                FROM recommendations r JOIN memories m ON m.id = r.memory_id
                JOIN memory_topics mt ON mt.memory_id = m.id
                WHERE mt.topic_id = ?
                  AND (r.related_topic IS NULL OR r.related_topic = ? COLLATE NOCASE)
                ORDER BY m.occurred_at DESC, r.id
                """,
                (topic["id"], topic["name"]),
            ).fetchall()
            topic["memories"] = [dict(row) for row in memories]
            topic["facts"] = [dict(row) for row in facts]
            topic["gaps"] = [dict(row) for row in gaps]
            topic["recommendations"] = [dict(row) for row in recommendations]
            return topic

    def task_board(self) -> dict[str, list[dict[str, Any]]]:
        now = utc_iso(datetime.now(UTC))
        soon = utc_iso(datetime.now(UTC) + timedelta(days=14))
        with self.connect() as connection:
            rows = connection.execute(OPEN_ACTIONS_SQL).fetchall()
        board: dict[str, list[dict[str, Any]]] = {
            "overdue": [],
            "upcoming": [],
            "later": [],
            "unscheduled": [],
        }
        for row in rows:
            action = dict(row)
            due_at = action["due_at"]
            if due_at is None:
                board["unscheduled"].append(action)
            elif due_at < now:
                board["overdue"].append(action)
            elif due_at <= soon:
                board["upcoming"].append(action)
            else:
                board["later"].append(action)
        return board

    # --- Graph (version 2.0) ---------------------------------------------

    def import_graph_bundle(self, bundle: GraphBundle, filename: str, raw_data: bytes) -> dict[str, int]:
        checksum = hashlib.sha256(raw_data).hexdigest()
        now = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    "SELECT 1 FROM graph_imports WHERE checksum = ?", (checksum,)
                ).fetchone():
                    raise DuplicateBundleError("this exact JSON file has already been imported")

                cursor = connection.execute(
                    """
                    INSERT INTO graph_imports (
                        checksum, source_filename, generator_provider, generator_model,
                        generated_at, imported_at, node_count, edge_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checksum,
                        filename,
                        bundle.generator.provider,
                        bundle.generator.model,
                        utc_iso(bundle.generated_at),
                        now,
                        len(bundle.nodes),
                        len(bundle.edges),
                    ),
                )
                import_id = cursor.lastrowid

                for node in bundle.nodes:
                    source = node.source
                    connection.execute(
                        """
                        INSERT INTO graph_nodes (
                            id, category, label, description, occurred_at,
                            source_type, source_label, source_excerpt, provenance,
                            metadata_json, import_id, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            category = excluded.category,
                            label = excluded.label,
                            description = excluded.description,
                            occurred_at = excluded.occurred_at,
                            source_type = excluded.source_type,
                            source_label = excluded.source_label,
                            source_excerpt = excluded.source_excerpt,
                            provenance = excluded.provenance,
                            metadata_json = excluded.metadata_json,
                            import_id = excluded.import_id,
                            updated_at = excluded.updated_at
                        """,
                        (
                            node.id,
                            node.category,
                            node.label,
                            node.description,
                            utc_iso(node.occurred_at) if node.occurred_at else None,
                            source.type if source else None,
                            source.label if source else None,
                            source.excerpt if source else None,
                            node.provenance,
                            json.dumps(node.metadata, ensure_ascii=False) if node.metadata else None,
                            import_id,
                            now,
                        ),
                    )

                for edge in bundle.edges:
                    edge_key = edge.id or f"{edge.source}|{edge.label}|{edge.target}"
                    connection.execute(
                        """
                        INSERT INTO graph_edges (
                            edge_key, source_id, target_id, label, directed,
                            description, evidence, provenance, metadata_json,
                            import_id, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(edge_key) DO UPDATE SET
                            source_id = excluded.source_id,
                            target_id = excluded.target_id,
                            label = excluded.label,
                            directed = excluded.directed,
                            description = excluded.description,
                            evidence = excluded.evidence,
                            provenance = excluded.provenance,
                            metadata_json = excluded.metadata_json,
                            import_id = excluded.import_id,
                            updated_at = excluded.updated_at
                        """,
                        (
                            edge_key,
                            edge.source,
                            edge.target,
                            edge.label,
                            1 if edge.directed else 0,
                            edge.description,
                            edge.evidence,
                            edge.provenance,
                            json.dumps(edge.metadata, ensure_ascii=False) if edge.metadata else None,
                            import_id,
                            now,
                        ),
                    )
                connection.commit()
                return {"nodes": len(bundle.nodes), "edges": len(bundle.edges)}
            except Exception:
                connection.rollback()
                raise

    def graph_stats(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM graph_nodes) AS graph_nodes,
                    (SELECT COUNT(*) FROM graph_edges) AS graph_edges
                """
            ).fetchone()
            return dict(row)

    def _stored_graph(self, connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        node_rows = connection.execute(
            """
            SELECT id, category, label, description, occurred_at, provenance,
                   source_type, source_label
            FROM graph_nodes ORDER BY id
            """
        ).fetchall()
        edge_rows = connection.execute(
            """
            SELECT edge_key AS id, source_id AS source, target_id AS target,
                   label, directed, provenance
            FROM graph_edges ORDER BY id
            """
        ).fetchall()
        nodes = [dict(row) | {"origin": "graph"} for row in node_rows]
        edges = [dict(row) | {"directed": bool(row["directed"]), "origin": "graph"} for row in edge_rows]
        return {"nodes": nodes, "edges": edges}

    def _projected_v1_graph(self, connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        """Project stored v1 memory records into graph nodes and edges so the
        existing record data appears in the graph view. Projected ids are
        namespaced (``mem:``/``topic:``/``entity:``/``person:``) to avoid
        colliding with author-provided graph node ids."""
        entity_category = {
            "person": "person",
            "organization": "organization",
            "software": "technology",
            "device": "technology",
            "architecture": "technology",
            "place": "place",
            "concept": "concept",
            "other": "other",
        }
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []

        memories = connection.execute(
            "SELECT id, title, summary, occurred_at, people_json FROM memories"
        ).fetchall()
        for memory in memories:
            mem_id = f"mem:{memory['id']}"
            nodes[mem_id] = {
                "id": mem_id,
                "category": "memory",
                "label": memory["title"],
                "description": memory["summary"],
                "occurred_at": memory["occurred_at"],
                "provenance": "source",
                "record_id": memory["id"],
                "origin": "memory",
            }
            for name in json.loads(memory["people_json"] or "[]"):
                person_id = f"person:{slugify(name)}"
                nodes.setdefault(
                    person_id,
                    {"id": person_id, "category": "person", "label": name,
                     "provenance": "source", "origin": "memory"},
                )
                edges.append({
                    "id": f"{mem_id}|involves|{person_id}", "source": mem_id,
                    "target": person_id, "label": "involves", "directed": True,
                    "provenance": "source", "origin": "memory",
                })

        for row in connection.execute(
            """
            SELECT mt.memory_id, t.slug, t.name
            FROM memory_topics mt JOIN topics t ON t.id = mt.topic_id
            """
        ).fetchall():
            topic_id = f"topic:{row['slug']}"
            nodes.setdefault(
                topic_id,
                {"id": topic_id, "category": "topic", "label": row["name"],
                 "provenance": "source", "origin": "memory"},
            )
            mem_id = f"mem:{row['memory_id']}"
            edges.append({
                "id": f"{mem_id}|about|{topic_id}", "source": mem_id, "target": topic_id,
                "label": "about", "directed": True, "provenance": "source", "origin": "memory",
            })

        for row in connection.execute(
            "SELECT memory_id, name, type FROM entities"
        ).fetchall():
            category = entity_category.get(row["type"], "other")
            entity_id = f"entity:{category}:{slugify(row['name'])}"
            nodes.setdefault(
                entity_id,
                {"id": entity_id, "category": category, "label": row["name"],
                 "provenance": "source", "origin": "memory"},
            )
            mem_id = f"mem:{row['memory_id']}"
            edges.append({
                "id": f"{mem_id}|mentions|{entity_id}", "source": mem_id, "target": entity_id,
                "label": "mentions", "directed": True, "provenance": "source", "origin": "memory",
            })

        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_payload(self) -> dict[str, list[dict[str, Any]]]:
        """Viewer payload: author-provided graph unified with the projection of
        v1 memory records. Stored graph nodes win id collisions."""
        with self.connect() as connection:
            stored = self._stored_graph(connection)
            projected = self._projected_v1_graph(connection)
        by_id = {node["id"]: node for node in projected["nodes"]}
        for node in stored["nodes"]:
            by_id[node["id"]] = node
        edges = {edge["id"]: edge for edge in projected["edges"]}
        for edge in stored["edges"]:
            edges[edge["id"]] = edge
        return {"nodes": list(by_id.values()), "edges": list(edges.values())}

    def node_detail(self, node_id: str) -> dict[str, Any] | None:
        payload = self.graph_payload()
        nodes = {node["id"]: node for node in payload["nodes"]}
        node = nodes.get(node_id)
        if node is None:
            return None
        neighbors = []
        for edge in payload["edges"]:
            if edge["source"] == node_id:
                other = nodes.get(edge["target"])
                neighbors.append({"edge": edge, "direction": "out", "node": other})
            elif edge["target"] == node_id:
                other = nodes.get(edge["source"])
                neighbors.append({"edge": edge, "direction": "in", "node": other})
        detail = dict(node)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT description, occurred_at, source_type, source_label,
                       source_excerpt, metadata_json
                FROM graph_nodes WHERE id = ?
                """,
                (node_id,),
            ).fetchone()
        if row:
            detail.update({k: row[k] for k in row.keys() if row[k] is not None})
            if detail.get("metadata_json"):
                detail["metadata"] = json.loads(detail.pop("metadata_json"))
        detail["neighbors"] = neighbors
        return detail

    def export_graph(
        self, seeds: list[str] | None = None, depth: int = 3
    ) -> dict[str, Any] | None:
        """Export the graph as a schema-2.0 GraphBundle that re-imports cleanly.

        With no seeds, exports the whole graph (stored v2 unified with the v1
        projection). With seeds, exports only those nodes plus everything within
        ``depth`` relationship hops (edges treated as undirected for reach), and
        the edges among the included nodes."""
        payload = self.graph_payload()
        all_nodes = {node["id"]: node for node in payload["nodes"]}
        if not all_nodes:
            return None
        edges = payload["edges"]

        if seeds:
            seed_ids = [s for s in seeds if s in all_nodes]
            if not seed_ids:
                return None
            adjacency: dict[str, set[str]] = {}
            for edge in edges:
                adjacency.setdefault(edge["source"], set()).add(edge["target"])
                adjacency.setdefault(edge["target"], set()).add(edge["source"])
            included = set(seed_ids)
            frontier = set(seed_ids)
            for _ in range(max(1, depth)):
                nxt = {
                    other
                    for nid in frontier
                    for other in adjacency.get(nid, ())
                    if other not in included
                }
                included |= nxt
                frontier = nxt
                if not frontier:
                    break
            node_payload = [all_nodes[i] for i in all_nodes if i in included]
            edge_payload = [
                e for e in edges if e["source"] in included and e["target"] in included
            ]
        else:
            node_payload = list(all_nodes.values())
            edge_payload = edges

        with self.connect() as connection:
            stored = {
                row["id"]: row
                for row in connection.execute(
                    "SELECT id, source_type, source_label, source_excerpt, metadata_json"
                    " FROM graph_nodes"
                ).fetchall()
            }
        nodes: list[dict[str, Any]] = []
        for item in node_payload:
            node: dict[str, Any] = {
                "id": item["id"],
                "category": item["category"],
                "label": item["label"],
                "provenance": item.get("provenance") or "source",
            }
            if item.get("description"):
                node["description"] = item["description"]
            if item.get("occurred_at"):
                node["occurred_at"] = item["occurred_at"]
            row = stored.get(item["id"])
            if row:
                if row["source_label"]:
                    source = {"type": row["source_type"] or "other", "label": row["source_label"]}
                    if row["source_excerpt"]:
                        source["excerpt"] = row["source_excerpt"]
                    node["source"] = source
                if row["metadata_json"]:
                    node["metadata"] = json.loads(row["metadata_json"])
            nodes.append(node)
        out_edges = [
            {
                "source": edge["source"],
                "target": edge["target"],
                "label": edge["label"],
                "directed": bool(edge.get("directed", True)),
                "provenance": edge.get("provenance") or "source",
            }
            for edge in edge_payload
        ]
        return {
            "schema_version": "2.0",
            "generated_at": utc_iso(datetime.now(UTC)),
            "generator": {"provider": "second-brain", "model": "export"},
            "nodes": nodes,
            "edges": out_edges,
        }
