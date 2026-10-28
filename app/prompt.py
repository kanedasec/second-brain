from __future__ import annotations

import json
from pathlib import Path

from app.schemas import KnowledgeBundle


PROMPT_PATH = Path(__file__).with_name("content") / "ai-ingestion-prompt.md"


def json_schema() -> dict:
    return KnowledgeBundle.model_json_schema()


def complete_prompt() -> str:
    instructions = PROMPT_PATH.read_text(encoding="utf-8").strip()
    schema = json.dumps(json_schema(), indent=2, ensure_ascii=False)
    return f"{instructions}\n\n## Required JSON Schema\n\n```json\n{schema}\n```\n"
