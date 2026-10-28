# Second Brain project memory

This file gives coding agents durable, public-safe context. Keep it free of credentials, personal knowledge, machine-specific paths, infrastructure addresses, and private environment values.

## Product intent

Second Brain is a private memory atlas. A user gives notes, email, briefings, diary text, or transcripts to an external AI using the prompt served by the app. The AI returns schema-v1 JSON. The user uploads that JSON and browses memories through chronology, topics, context search, task status, grounded facts, and knowledge gaps.

The product must make epistemic boundaries obvious:

- facts and actions require source evidence;
- actions are explicit commitments, never inferred AI suggestions;
- entity explanations say whether they came from the source or general knowledge;
- recommendations are always labeled as AI-generated advice;
- missing data remains missing rather than being guessed.

## Technical shape

- Python 3.13, FastAPI, Pydantic, Jinja, and SQLite.
- Server-rendered HTML with a small dependency-free JavaScript layer.
- `app/schemas.py` is the canonical ingestion contract.
- `app/content/ai-ingestion-prompt.md` contains the human instructions; `app/prompt.py` appends the schema generated from Pydantic.
- `app/db.py` owns schema initialization, atomic imports, search, topic dossiers, and task views.
- `app/backup.py` owns consistent weekly backups and retention.
- `app/main.py` owns routes, authentication, upload limits, origin checks, and security headers.
- `deploy/` holds the reviewed runtime assets (Compose, Caddy route, restricted deploy script, sudoers rule, dispatcher snippet). `deploy/bootstrap-second-brain` is an idempotent, root-run script that automates onboarding phases 3-5: it validates staged assets, refuses a group/other-readable `app.env`, requires an immutable `deployment.env` tag, backs up the shared dispatcher and Caddyfile before patching, and rolls Caddy back on failure. Secret-bearing staged assets (`app.env`, `deployment.env`) are never committed.

## Design language

The interface is an editorial “memory atlas”: warm paper, dark ink, one electric-blue accent, serif display type, compact metadata, visible rules, and timeline markers. Preserve the asymmetric editorial layout, strong keyboard focus, responsive collapse, and reduced-motion behavior. Avoid generic dashboard styling or decorative effects that reduce readability.

## Invariants

1. Keep schema version `1.0` backward compatible unless a deliberate migration and new version are added.
2. Reject unknown JSON fields and naive timestamps.
3. Import each file in one transaction; never leave a partial bundle.
4. Keep facts, explicit actions, knowledge gaps, entity enrichment, and AI recommendations in separate tables and UI sections.
5. Do not add an in-app AI dependency or require model API credentials without an explicit product decision.
6. Production knowledge routes require authentication; readiness remains content-free and public.
7. Do not log uploaded content, search text, credentials, or private memory data.
8. Add tests for schema, persistence, security boundaries, and retention when changing those areas.
9. SGP Manager resolves bypasses but is not a deployment availability dependency. When it is unavailable, all registered guardrails run and every finding severity blocks with no bypasses; only clean, valid scanner evidence may continue.

## Development commands

```bash
python -m pip install --requirement requirements-dev.txt
python -m pytest -q tests
```

Use `examples/example-memory.json` for synthetic manual testing. It must remain fictional and contain no personal data.

## Good next increments

- schema migrations and export/restore tooling;
- editable action status with an audit trail;
- encrypted-at-rest storage strategy;
- related-memory suggestions based on local, deterministic signals;
- optional passkey or identity-aware proxy authentication;
- end-to-end browser accessibility tests.
