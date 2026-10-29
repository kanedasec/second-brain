# Second Brain unified atlas ingestion task

Transform the source material I provide after this instruction into **only one valid JSON object** that conforms exactly to the supplied JSON Schema. The result must populate the complete Second Brain: memories, chronology, topics, search, tasks, knowledge gaps, recommendations, and the relationship graph. Do not wrap the result in Markdown and do not add commentary outside the JSON.

## Grounding rules — do not invent information

1. Treat the supplied material as the only source of truth for events, decisions, people, dates, ownership, commitments, facts, and relationships.
2. Never fabricate a missing name, date, deadline, owner, decision, quotation, status, configuration, or relationship. Preserve uncertainty instead of resolving it.
3. Every fact and action must contain a short `evidence` excerpt or close paraphrase directly supported by the source.
4. Use `confidence: "explicit"` when the source states a fact directly, `"strong"` only when its wording makes the fact unambiguous, and `"uncertain"` when the source itself is uncertain.
5. Create an action only for a commitment, request, obligation, or task actually present in the source. Put your suggested next steps in `recommendations`, never in `actions`.
6. If an action has no stated deadline, set `due_at` to `null`. If it has no stated owner, set `owner` to `null`.
7. All known timestamps must be RFC 3339 with an explicit timezone offset. If a date or timezone cannot be determined from the source or context I explicitly supplied, use `null` and capture the ambiguity as a knowledge gap. Never substitute the generation time for an event time.

## Editorial memories

- Split unrelated events into separate `memories` and give each one a stable lowercase ID such as `2026-10-28-project-briefing-01`.
- Keep titles concise, summaries self-contained, topics reusable, and topic context specific to the memory.
- Put unanswered questions, missing decisions, unclear ownership, and information needed to proceed in `knowledge_gaps`.
- Use empty arrays when a memory has no supported facts, entities, actions, gaps, or recommendations.

## Careful enrichment

- Add an `entities` item only when the person, organization, software, device, architecture, place, or concept is actually mentioned.
- Explain each mentioned entity in plain language so the memory remains useful later.
- If the explanation is stated in the source, use `explanation_source: "source"`.
- You may use established, non-controversial general knowledge only to explain what a mentioned entity is. Mark it `explanation_source: "general_knowledge"`. Do not infer how it was configured or used beyond what the source states.
- Recommendations are your advice, not source facts or commitments. Set `ai_generated` to `true` and give a clear rationale without inventing deadlines or obligations.

## Knowledge graph

- Create exactly one graph node for every editorial memory. Its ID must be `mem:` followed by the exact memory ID, for example `mem:2026-10-28-project-briefing-01`; its category must be `memory`, and its label, description, and `occurred_at` must stay consistent with that memory.
- Do not create a `memory` category or `mem:` graph node unless it has a matching editorial memory in the same bundle.
- Use the remaining `nodes` and `edges` for first-class entities and meaningful relationships that make the source easier to navigate: people, organizations, projects, concepts, events, technologies, places, and topics.
- Every node needs a stable, unique, lowercase `id`. Use canonical IDs where possible: `person:ada-chen`, `topic:environmental-monitoring`, or `entity:technology:lorawan`. Reuse the same ID for the same real entity across files and do not create another ID for an entity already represented in the bundle.
- Create a node only for something present in the source. Give it `provenance: "source"`. If its description contains only general background rather than source-specific information, use `provenance: "ai_inferred"` and keep the description clearly general.
- Every edge must reference nodes defined in this same bundle. Create an edge only when the source supports the relationship. Include a short `evidence` excerpt and use `provenance: "source"`.
- A relationship added from established general knowledge or reasonable inference must use `provenance: "ai_inferred"` and explain the inference in `description`. Never present it as source-stated.
- Use short, lowercase, reusable edge labels such as `leads`, `member of`, `uses`, `depends on`, `located at`, or `part of`. Keep edges directional unless the relationship is genuinely symmetric.

## Output quality

- Preserve the source language unless a translation is explicitly requested.
- Deduplicate repeated memories, facts, nodes, and relationships within the bundle.
- Set `schema_version` to `3.0`. Identify your provider and model when known.
- Before responding, validate the complete object against the supplied schema. Correct every missing, extra, or mistyped field and every edge that references an undefined node.

Source material begins after this line:

---
