from __future__ import annotations

import json
from pathlib import Path

from app.schemas import GraphBundle, KnowledgeBundle


CONTENT_DIR = Path(__file__).with_name("content")
PROMPT_PATH = CONTENT_DIR / "ai-ingestion-prompt.md"
GRAPH_PROMPT_PATH = CONTENT_DIR / "graph-ingestion-prompt.md"


def json_schema() -> dict:
    return KnowledgeBundle.model_json_schema()


def graph_json_schema() -> dict:
    return GraphBundle.model_json_schema()


def _complete(instructions_path: Path, schema: dict) -> str:
    instructions = instructions_path.read_text(encoding="utf-8").strip()
    rendered = json.dumps(schema, indent=2, ensure_ascii=False)
    return f"{instructions}\n\n## Required JSON Schema\n\n```json\n{rendered}\n```\n"


def complete_prompt() -> str:
    return _complete(PROMPT_PATH, json_schema())


def complete_graph_prompt() -> str:
    return _complete(GRAPH_PROMPT_PATH, graph_json_schema())
