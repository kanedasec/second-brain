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

from app.schemas import AtlasBundle, GraphBundle, KnowledgeBundle


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
    completed_at TEXT,
    due_at TEXT,
    owner TEXT,
    evidence TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS actions_status_due_idx ON actions(status, due_at);

CREATE TABLE IF NOT EXISTS action_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    previous_status TEXT NOT NULL CHECK (previous_status IN ('open', 'done', 'cancelled')),
    new_status TEXT NOT NULL CHECK (new_status IN ('open', 'done', 'cancelled')),
    changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS action_status_events_action_idx
    ON action_status_events(action_id, changed_at DESC);

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

COMPLETED_ACTIONS_SQL = """
SELECT a.*, m.title AS memory_title, m.occurred_at
FROM actions a JOIN memories m ON m.id = a.memory_id
WHERE a.status = 'done'
ORDER BY a.completed_at DESC, a.id DESC
"""


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if slug:
        return slug[:72]
    return "topic-" + hashlib.sha256(value.casefold().encode()).hexdigest()[:10]


def normalized_label(value: str) -> str:
    """Normalize a label for exact identity matching without truncating it."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return key or unicodedata.normalize("NFKC", value).casefold().strip()


class DuplicateBundleError(ValueError):
    pass


class DuplicateMemoryError(ValueError):
    pass


class ReconciliationRequired(ValueError):
    def __init__(self, plan: dict[str, Any]):
        super().__init__("graph reconciliation requires confirmation")
        self.plan = plan


class AmbiguousReconciliationError(ValueError):
    def __init__(self, plan: dict[str, Any]):
        super().__init__("graph reconciliation is ambiguous")
        self.plan = plan


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
            self._migrate(connection)
            connection.commit()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """Apply small forward-only migrations to databases created in place."""

        action_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(actions)").fetchall()
        }
        if "completed_at" not in action_columns:
            connection.execute("ALTER TABLE actions ADD COLUMN completed_at TEXT")

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
                count = self._insert_memory_bundle(connection, bundle, filename, checksum, now)
                connection.commit()
                return count
            except Exception:
                connection.rollback()
                raise

    def _insert_memory_bundle(
        self,
        connection: sqlite3.Connection,
        bundle: KnowledgeBundle | AtlasBundle,
        filename: str,
        checksum: str,
        now: str,
    ) -> int:
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
        return len(bundle.memories)

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
            completed = connection.execute(COMPLETED_ACTIONS_SQL).fetchall()
        board: dict[str, list[dict[str, Any]]] = {
            "overdue": [],
            "upcoming": [],
            "later": [],
            "unscheduled": [],
            "completed": [dict(row) for row in completed],
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

    def complete_action(self, action_id: int) -> dict[str, Any] | None:
        """Mark one open action done and update one existing graph node, if unique."""

        completed_at = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT a.*, m.title AS memory_title
                    FROM actions a JOIN memories m ON m.id = a.memory_id
                    WHERE a.id = ?
                    """,
                    (action_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return None

                action = dict(row)
                if action["status"] != "open":
                    connection.commit()
                    return action | {"changed": False, "graph_node_id": None}

                connection.execute(
                    "UPDATE actions SET status = 'done', completed_at = ? WHERE id = ?",
                    (completed_at, action_id),
                )
                connection.execute(
                    """
                    INSERT INTO action_status_events (
                        action_id, previous_status, new_status, changed_at
                    ) VALUES (?, 'open', 'done', ?)
                    """,
                    (action_id, completed_at),
                )
                graph_node_id = self._sync_completed_action_node(
                    connection, action, completed_at
                )
                connection.commit()
                return action | {
                    "status": "done",
                    "completed_at": completed_at,
                    "changed": True,
                    "graph_node_id": graph_node_id,
                }
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _sync_completed_action_node(
        connection: sqlite3.Connection,
        action: dict[str, Any],
        completed_at: str,
    ) -> str | None:
        """Update a uniquely identifiable stored node without creating one."""

        candidates = []
        title_key = normalized_label(action["title"])
        for row in connection.execute(
            "SELECT id, category, label, metadata_json FROM graph_nodes ORDER BY id"
        ).fetchall():
            if normalized_label(row["label"]) != title_key:
                continue
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            task_like = (
                row["category"] in {"action", "event", "other"}
                or row["id"].startswith("action.")
                or metadata.get("kind") in {"action", "task"}
                or "task_status" in metadata
            )
            if not task_like:
                continue
            candidates.append((row, metadata))

        if not candidates:
            return None

        memory_id = action["memory_id"]
        explicit = [
            item
            for item in candidates
            if item[1].get("memory_id") == memory_id
            or item[1].get("action_id") == str(action["id"])
        ]
        if len(explicit) == 1:
            chosen = explicit[0]
        else:
            memory_node_id = f"mem:{memory_id}"
            connected_ids = {
                row["source_id"] if row["target_id"] == memory_node_id else row["target_id"]
                for row in connection.execute(
                    """
                    SELECT source_id, target_id FROM graph_edges
                    WHERE source_id = ? OR target_id = ?
                    """,
                    (memory_node_id, memory_node_id),
                ).fetchall()
            }
            connected = [item for item in candidates if item[0]["id"] in connected_ids]
            if len(connected) == 1:
                chosen = connected[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                return None

        row, metadata = chosen
        metadata |= {
            "task_status": "done",
            "task_completed_at": completed_at,
        }
        connection.execute(
            "UPDATE graph_nodes SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), completed_at, row["id"]),
        )
        return row["id"]

    # --- Graph (version 2.0) ---------------------------------------------

    def import_graph_bundle(self, bundle: GraphBundle, filename: str, raw_data: bytes) -> dict[str, int]:
        checksum = hashlib.sha256(raw_data).hexdigest()
        now = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                counts = self._insert_graph_bundle(connection, bundle, filename, checksum, now)
                connection.commit()
                return counts
            except Exception:
                connection.rollback()
                raise

    def import_atlas_bundle(
        self,
        bundle: AtlasBundle,
        filename: str,
        raw_data: bytes,
        reconciliation_fingerprint: str | None = None,
    ) -> dict[str, int]:
        """Persist editorial memories and graph structure in one transaction."""

        checksum = hashlib.sha256(raw_data).hexdigest()
        now = utc_iso(datetime.now(UTC))
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                plan = self._atlas_reconciliation(connection, bundle, checksum)
                if plan["ambiguities"]:
                    raise AmbiguousReconciliationError(plan)
                if (
                    plan["requires_confirmation"]
                    and reconciliation_fingerprint != plan["fingerprint"]
                ):
                    raise ReconciliationRequired(plan)
                memories = self._insert_memory_bundle(
                    connection, bundle, filename, checksum, now
                )
                graph = self._insert_graph_bundle(
                    connection, bundle, filename, checksum, now, plan
                )
                connection.commit()
                return {"memories": memories, **graph}
            except Exception:
                connection.rollback()
                raise

    def preflight_atlas_bundle(
        self, bundle: AtlasBundle, raw_data: bytes
    ) -> dict[str, Any]:
        checksum = hashlib.sha256(raw_data).hexdigest()
        with self.connect() as connection:
            return self._atlas_reconciliation(connection, bundle, checksum)

    def _atlas_reconciliation(
        self,
        connection: sqlite3.Connection,
        bundle: AtlasBundle,
        checksum: str,
    ) -> dict[str, Any]:
        stored_rows = connection.execute(
            """
            SELECT id, category, label, description, occurred_at,
                   source_type, source_label, source_excerpt, provenance,
                   metadata_json
            FROM graph_nodes ORDER BY id
            """
        ).fetchall()
        stored = {row["id"]: dict(row) | {"origin": "stored"} for row in stored_rows}
        projected = {
            node["id"]: node | {"origin": "projected"}
            for node in self._projected_v1_graph(connection)["nodes"]
            if node["id"] not in stored
        }
        existing = stored | projected

        by_label: dict[str, list[dict[str, Any]]] = {}
        for item in existing.values():
            by_label.setdefault(normalized_label(item["label"]), []).append(item)

        node_id_map: dict[str, str] = {}
        existing_replacements: dict[str, str] = {}
        node_inserts: list[dict[str, str]] = []
        node_updates: list[dict[str, str]] = []
        node_unchanged: list[str] = []
        node_merges: list[dict[str, str]] = []
        ambiguities: list[dict[str, Any]] = []

        for node in bundle.nodes:
            current = existing.get(node.id)
            if current is not None:
                if current["origin"] == "stored" and self._node_matches(current, node):
                    node_unchanged.append(node.id)
                elif current["origin"] == "projected":
                    node_merges.append(
                        {
                            "label": node.label,
                            "category": node.category,
                            "incoming_id": node.id,
                            "existing_id": node.id,
                            "final_id": node.id,
                            "action": "reuse projected identity",
                        }
                    )
                else:
                    node_updates.append(
                        {"id": node.id, "label": node.label, "category": node.category}
                    )
                continue

            compatible_categories = (
                {"memory", "event"} if node.category == "memory" else {node.category}
            )
            candidates = [
                item
                for item in by_label.get(normalized_label(node.label), [])
                if item["category"] in compatible_categories
                and not (node.category == "memory" and item["origin"] == "projected")
            ]
            if not candidates:
                node_inserts.append(
                    {"id": node.id, "label": node.label, "category": node.category}
                )
                continue
            if len(candidates) > 1:
                ambiguities.append(
                    {
                        "incoming_id": node.id,
                        "label": node.label,
                        "reason": "multiple existing nodes share this label and category",
                        "candidates": [item["id"] for item in candidates],
                    }
                )
                continue

            match = candidates[0]
            if node.category == "memory":
                claimed_by = existing_replacements.get(match["id"])
                if claimed_by is not None and claimed_by != node.id:
                    ambiguities.append(
                        {
                            "incoming_id": f"{claimed_by}, {node.id}",
                            "label": node.label,
                            "reason": (
                                "multiple incoming memories claim the same existing node"
                            ),
                            "candidates": [match["id"]],
                        }
                    )
                    continue
                existing_replacements[match["id"]] = node.id
                action = "fold existing node into memory identity"
                final_id = node.id
            else:
                node_id_map[node.id] = match["id"]
                action = "reuse existing identity"
                final_id = match["id"]
            node_merges.append(
                {
                    "label": node.label,
                    "category": node.category,
                    "incoming_id": node.id,
                    "existing_id": match["id"],
                    "final_id": final_id,
                    "action": action,
                }
            )

        final_ids: dict[str, list[str]] = {}
        for node in bundle.nodes:
            final_id = node_id_map.get(node.id, node.id)
            final_ids.setdefault(final_id, []).append(node.id)
        for final_id, incoming_ids in final_ids.items():
            if len(incoming_ids) > 1:
                ambiguities.append(
                    {
                        "incoming_id": ", ".join(incoming_ids),
                        "label": final_id,
                        "reason": "multiple incoming nodes would collapse into one identity",
                        "candidates": [final_id],
                    }
                )

        edge_rows = connection.execute(
            """
            SELECT edge_key, source_id, target_id, label, directed,
                   description, evidence, provenance, metadata_json
            FROM graph_edges ORDER BY id
            """
        ).fetchall()
        existing_edges: dict[str, dict[str, Any]] = {}
        semantic_edges: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
        for raw_row in edge_rows:
            row = dict(raw_row)
            source = existing_replacements.get(row["source_id"], row["source_id"])
            target = existing_replacements.get(row["target_id"], row["target_id"])
            derived_key = f"{row['source_id']}|{row['label']}|{row['target_id']}"
            effective_key = (
                f"{source}|{row['label']}|{target}"
                if row["edge_key"] == derived_key
                else row["edge_key"]
            )
            row |= {
                "edge_key": effective_key,
                "source_id": source,
                "target_id": target,
            }
            existing_edges[effective_key] = row
            semantic_edges.setdefault(
                (source, target, row["label"].casefold(), int(row["directed"])), []
            ).append(row)

        edge_keys: list[str] = []
        edge_inserts: list[dict[str, str]] = []
        edge_updates: list[dict[str, str]] = []
        edge_merges: list[dict[str, str]] = []
        edge_unchanged: list[str] = []
        for edge in bundle.edges:
            source = node_id_map.get(edge.source, edge.source)
            target = node_id_map.get(edge.target, edge.target)
            desired_key = edge.id or f"{source}|{edge.label}|{target}"
            matches = semantic_edges.get(
                (source, target, edge.label.casefold(), 1 if edge.directed else 0), []
            )
            if len(matches) > 1:
                ambiguities.append(
                    {
                        "incoming_id": str(edge.id or "derived"),
                        "label": edge.label,
                        "reason": (
                            "multiple existing edges share these endpoints and label"
                        ),
                        "candidates": [item["edge_key"] for item in matches],
                    }
                )
                edge_keys.append(desired_key)
                continue

            current = existing_edges.get(desired_key)
            if current is not None:
                edge_keys.append(desired_key)
                if self._edge_matches(current, edge, source, target):
                    edge_unchanged.append(desired_key)
                else:
                    edge_updates.append(
                        {
                            "id": desired_key,
                            "source": source,
                            "target": target,
                            "label": edge.label,
                        }
                    )
                continue

            if matches:
                existing_key = matches[0]["edge_key"]
                edge_keys.append(existing_key)
                edge_merges.append(
                    {
                        "incoming_id": str(edge.id or "derived"),
                        "existing_id": existing_key,
                        "label": edge.label,
                    }
                )
            else:
                edge_keys.append(desired_key)
                edge_inserts.append(
                    {"id": desired_key, "source": source, "target": target, "label": edge.label}
                )

        fingerprint_payload = {
            "checksum": checksum,
            "node_id_map": node_id_map,
            "existing_replacements": existing_replacements,
            "edge_keys": edge_keys,
            "node_updates": node_updates,
            "node_merges": node_merges,
            "edge_updates": edge_updates,
            "edge_merges": edge_merges,
            "ambiguities": ambiguities,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return fingerprint_payload | {
            "fingerprint": fingerprint,
            "node_inserts": node_inserts,
            "node_unchanged": node_unchanged,
            "edge_inserts": edge_inserts,
            "edge_unchanged": edge_unchanged,
            "requires_confirmation": bool(
                node_updates or node_merges or edge_updates or edge_merges
            ),
        }

    @staticmethod
    def _node_matches(row: dict[str, Any], node: Any) -> bool:
        source = node.source
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else None
        return (
            row["category"] == node.category
            and row["label"] == node.label
            and row["description"] == node.description
            and row["occurred_at"]
            == (utc_iso(node.occurred_at) if node.occurred_at else None)
            and row["source_type"] == (source.type if source else None)
            and row["source_label"] == (source.label if source else None)
            and row["source_excerpt"] == (source.excerpt if source else None)
            and row["provenance"] == node.provenance
            and metadata == node.metadata
        )

    @staticmethod
    def _edge_matches(
        row: dict[str, Any], edge: Any, source: str, target: str
    ) -> bool:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else None
        return (
            row["source_id"] == source
            and row["target_id"] == target
            and row["label"] == edge.label
            and bool(row["directed"]) == edge.directed
            and row["description"] == edge.description
            and row["evidence"] == edge.evidence
            and row["provenance"] == edge.provenance
            and metadata == edge.metadata
        )

    def _insert_graph_bundle(
        self,
        connection: sqlite3.Connection,
        bundle: GraphBundle | AtlasBundle,
        filename: str,
        checksum: str,
        now: str,
        reconciliation: dict[str, Any] | None = None,
    ) -> dict[str, int]:
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

        node_id_map = reconciliation["node_id_map"] if reconciliation else {}
        for node in bundle.nodes:
            source = node.source
            node_id = node_id_map.get(node.id, node.id)
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
                    node_id,
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

        if reconciliation:
            for old_id, new_id in reconciliation["existing_replacements"].items():
                self._merge_existing_graph_node(connection, old_id, new_id)

        for index, edge in enumerate(bundle.edges):
            source_id = node_id_map.get(edge.source, edge.source)
            target_id = node_id_map.get(edge.target, edge.target)
            edge_key = (
                reconciliation["edge_keys"][index]
                if reconciliation
                else edge.id or f"{source_id}|{edge.label}|{target_id}"
            )
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
                    source_id,
                    target_id,
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
        return {"nodes": len(bundle.nodes), "edges": len(bundle.edges)}

    @staticmethod
    def _merge_existing_graph_node(
        connection: sqlite3.Connection, old_id: str, new_id: str
    ) -> None:
        if old_id == new_id:
            return
        rows = connection.execute(
            "SELECT * FROM graph_edges WHERE source_id = ? OR target_id = ? ORDER BY id",
            (old_id, old_id),
        ).fetchall()
        for row in rows:
            source_id = new_id if row["source_id"] == old_id else row["source_id"]
            target_id = new_id if row["target_id"] == old_id else row["target_id"]
            if source_id == target_id:
                connection.execute("DELETE FROM graph_edges WHERE id = ?", (row["id"],))
                continue
            derived_key = f"{row['source_id']}|{row['label']}|{row['target_id']}"
            edge_key = (
                f"{source_id}|{row['label']}|{target_id}"
                if row["edge_key"] == derived_key
                else row["edge_key"]
            )
            duplicate = connection.execute(
                """
                SELECT id FROM graph_edges
                WHERE id != ? AND (
                    edge_key = ? OR (
                        source_id = ? AND target_id = ?
                        AND label = ? AND directed = ?
                    )
                )
                LIMIT 1
                """,
                (
                    row["id"],
                    edge_key,
                    source_id,
                    target_id,
                    row["label"],
                    row["directed"],
                ),
            ).fetchone()
            if duplicate:
                connection.execute("DELETE FROM graph_edges WHERE id = ?", (row["id"],))
            else:
                connection.execute(
                    """
                    UPDATE graph_edges
                    SET edge_key = ?, source_id = ?, target_id = ?
                    WHERE id = ?
                    """,
                    (edge_key, source_id, target_id, row["id"]),
                )
        connection.execute("DELETE FROM graph_nodes WHERE id = ?", (old_id,))

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
                   source_type, source_label, metadata_json
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
        nodes = []
        for row in node_rows:
            node = dict(row) | {"origin": "graph"}
            metadata_json = node.pop("metadata_json")
            if metadata_json:
                node["metadata"] = json.loads(metadata_json)
            nodes.append(node)
        edges = [dict(row) | {"directed": bool(row["directed"]), "origin": "graph"} for row in edge_rows]
        return {"nodes": nodes, "edges": edges}

    def _projected_v1_graph(self, connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        """Project stored v1 memory records into graph nodes and edges so the
        existing record data appears in the graph view. Projected ids are
        namespaced (``mem:``/``topic:``/``entity:``/``person:``). When one
        authored graph node has the same normalized label and category, the
        projection reuses that identity instead of drawing a duplicate."""
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
        authored_by_label: dict[tuple[str, str], list[str]] = {}
        for row in connection.execute(
            "SELECT id, category, label FROM graph_nodes ORDER BY id"
        ).fetchall():
            authored_by_label.setdefault(
                (row["category"], normalized_label(row["label"])), []
            ).append(row["id"])

        def projected_id(category: str, label: str, fallback: str) -> str:
            matches = authored_by_label.get((category, normalized_label(label)), [])
            return matches[0] if len(matches) == 1 else fallback

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
                person_id = projected_id(
                    "person", name, f"person:{slugify(name)}"
                )
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
            topic_id = projected_id(
                "topic", row["name"], f"topic:{row['slug']}"
            )
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
            entity_id = projected_id(
                category,
                row["name"],
                f"entity:{category}:{slugify(row['name'])}",
            )
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
            # A unified schema-3 import deliberately uses the projected
            # ``mem:<memory-id>`` identity. Preserve projection-only fields
            # such as ``record_id`` while allowing the authored graph node to
            # enrich its label, description, provenance, and source metadata.
            by_id[node["id"]] = by_id.get(node["id"], {}) | node
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
