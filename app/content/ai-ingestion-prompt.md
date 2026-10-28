# Second Brain ingestion task

Transform the source material I provide after this instruction into **only one valid JSON object** that conforms exactly to the supplied JSON Schema. Do not wrap the result in Markdown and do not add commentary outside the JSON.

## Grounding rules — do not invent information

1. Treat the supplied material as the only source of truth for events, decisions, people, dates, ownership, commitments, and facts.
2. Never fabricate a missing name, date, deadline, owner, decision, quotation, status, or relationship. Preserve uncertainty instead of resolving it.
3. Every fact and action must contain a short `evidence` excerpt or close paraphrase that is directly supported by the source.
4. Use `confidence: "explicit"` when the source states the fact directly, `"strong"` only when the wording makes it unambiguous, and `"uncertain"` when the source itself is uncertain. Do not turn a guess into a fact.
5. Create an action only for a commitment, request, obligation, or task actually present in the source. Put your own suggested next steps in `recommendations`, never in `actions`.
6. If an action has no stated deadline, set `due_at` to `null`. If it has no stated owner, set `owner` to `null`.
7. All known timestamps must be RFC 3339 with an explicit timezone offset. If the memory date or timezone cannot be determined from the source or from context I explicitly supplied, set `occurred_at` to `null` and describe the ambiguity in a knowledge gap. Never use the generation time as an event time.
8. Split unrelated events into separate memories. Give each memory a stable lowercase ID such as `2026-10-28-project-briefing-01`.

## Careful enrichment

- Add an `entities` item only when the person, organization, software, device, architecture, place, or concept is actually mentioned.
- Explain each mentioned entity in plain language so the memory remains useful later.
- If the explanation is stated in the source, use `explanation_source: "source"`.
- You may use established, non-controversial general knowledge to explain what a mentioned technology or concept is; mark it `explanation_source: "general_knowledge"`. Do not claim that general background came from the source, and do not infer how the entity was configured or used beyond what was stated.
- Capture unanswered questions, missing decisions, unclear ownership, and information needed to proceed as `knowledge_gaps`.

## Recommendations

- Provide practical recommendations when the source supports a useful next step, risk reduction, follow-up, or learning path.
- Every recommendation is advice from you, not a source fact. Set `ai_generated` to `true`, make the rationale clear, and do not present it as something a named person requested.
- Recommendations must not silently create deadlines, obligations, or claims.

## Output quality

- Keep titles concise, summaries self-contained, topics reusable, and topic context specific to this memory.
- Preserve the source language unless a translation is explicitly requested.
- Deduplicate repeated statements within the same bundle.
- Use empty arrays when a category has no supported items.
- Set `schema_version` to `1.0`. Identify your provider and model when known.
- Before responding, validate the object against the supplied schema and correct every missing, extra, or mistyped field.

Source material begins after this line:

---
