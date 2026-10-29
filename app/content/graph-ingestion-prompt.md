# Second Brain graph ingestion task

Transform the source material I provide after this instruction into **only one valid JSON object** that conforms exactly to the supplied JSON Schema: a knowledge graph of `nodes` and directional `edges`. The source may be raw notes, email, or a transcript, or a report already prepared by one of the Second Brain review prompts — treat all of it as source material. Do not wrap the result in Markdown and do not add commentary outside the JSON.

## Grounding rules — do not invent information

1. Treat the supplied material as the only source of truth for people, organizations, projects, events, concepts, technologies, places, and the relationships between them.
2. Never fabricate a missing name, date, ownership, or relationship. Preserve uncertainty instead of resolving it.
3. Create a node only for something actually present in the source. Create an edge only for a relationship the source supports.
4. When a relationship is stated or clearly implied by the source, set `provenance: "source"` and include a short `evidence` excerpt. When you add a relationship from established general knowledge or reasonable inference, set `provenance: "ai_inferred"` and explain it in `description`. Never present an inference as if the source stated it.

## Nodes

- Every node needs a stable, unique, lowercase `id`, for example `person.ada-chen`, `project.sensor-array`, or `memory.2026-10-28-review`. Reuse the same `id` whenever the same real entity appears again, across files, so the graph accumulates instead of duplicating.
- Choose the most specific `category`: `person`, `organization`, `memory`, `project`, `concept`, `event`, `technology`, `place`, `topic`, or `other`.
- Give each node a concise human `label` and, when the source supports it, a `description`.
- Set `occurred_at` (RFC 3339 with an explicit timezone offset) only for time-anchored nodes such as events or memories. Never use the generation time as an event time.
- Record where a node came from in `source`, and put extra structured attributes in `metadata` as string values.

## Edges

- Every edge's `source` and `target` must be the `id` of a node defined in the same bundle. Do not reference a node you did not define.
- Use a short, lowercase, reusable `label` for the relationship, for example `leads`, `member of`, `about`, `mentions`, `uses`, `depends on`, `located at`, or `part of`.
- Keep edges directional (`directed: true`) unless the relationship is genuinely symmetric.
- Do not create an edge that connects a node to itself.

## Output quality

- Deduplicate: one node per real entity, one edge per real relationship.
- Prefer a connected graph — attach each node to at least one other node when the source supports it.
- Set `schema_version` to `2.0`. Identify your provider and model when known.
- Before responding, validate the object against the supplied schema and correct every missing, extra, or mistyped field, and every edge that references an undefined node.

Source material begins after this line:

---
