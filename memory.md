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
- `app/schemas.py` is the canonical ingestion contract. It defines two bundle formats: `KnowledgeBundle` (schema 1.0, the editorial memory records) and `GraphBundle` (schema 2.0, a node-link knowledge graph of `nodes[]` + directional `edges[]` with referential integrity). `/import` dispatches on `schema_version`. The graph view (force-directed, client-side, self-hosted `force-graph`) is the primary surface; it unifies author-imported v2 graphs with a namespaced projection of v1 memory records, so both data shapes appear in one graph. It supports exploration: search (highlight + zoom-to-match), clickable legend category filters, an AI-inferred-link toggle, click-to-select with neighbor highlighting, node-neighborhood isolation, a reset, and progressive disclosure (highest-degree nodes first with a "show all" control) past a node cap for large graphs. Nodes glow (neon) and scale by degree so hubs stand out; hovering highlights a node's links; camera transitions are instant under `prefers-reduced-motion`. Grounding carries into v2 as node/edge `provenance` (`source` vs `ai_inferred`) plus `evidence`/`source`.
- `app/prompt.py` holds a prompt library: source-preparation prompts (email review, meeting-transcript review, interactive daily report) that output a **written report**, and the **graph schema generator** that appends the v2 JSON schema and outputs graph JSON. The `/prompt` page is a gated library — bodies are not inlined; they load on demand from `/prompts/{id}.txt` behind a reveal button. Prompt instruction text lives in `app/content/*.md`. (No in-app AI dependency — these are static templates.)
- UI is bilingual **English / Brazilian Portuguese** via `app/i18n.py` (gettext-style: English source strings are the keys, English is the fallback). Language is a per-request `lang` cookie set by `/set-language`; templates call the injected `t()` helper, and `graph.js`/`prompts.js` carry small client-side string maps. This translates the **interface only — never user memory content**.
- `app/db.py` owns schema initialization, atomic imports, search, topic dossiers, and task views.
- `app/backup.py` owns consistent weekly backups and retention.
- `app/main.py` owns routes, authentication, upload limits, origin checks, and security headers. State-changing requests are authorized by the `Sec-Fetch-Site` fetch-metadata header (primary), with an `Origin`/`Host` comparison as fallback for clients that omit it, plus a per-form double-submit CSRF token. Do not re-introduce a bare `Origin == Host` check: the app sends `Referrer-Policy: no-referrer`, which makes browsers send `Origin: null` on same-origin form POSTs, and a bare check then 403s every upload.
- `deploy/` holds the reviewed runtime assets (Compose, Caddy route, restricted deploy script, sudoers rule, dispatcher snippet). `deploy/bootstrap-second-brain` is an idempotent, root-run script that automates onboarding phases 3-5: it validates staged assets, refuses a group/other-readable `app.env`, requires an immutable `deployment.env` tag, backs up the shared dispatcher and Caddyfile before patching, and rolls Caddy back on failure. Secret-bearing staged assets (`app.env`, `deployment.env`) are never committed. `deploy/Caddyfile` is the single source of truth for the public hostname; the CI `DEPLOY_URL` deployment variable and the DNS record must match it, or the post-deploy smoke check fails. The app reaches the shared Caddy ingress over an external `proxy` Docker network; the bootstrap creates that network if absent and starts only the shared Caddy container (never other applications).

## Design language

The interface is a **Cyberpunk 2077 / Edgerunners / Akira**-inspired "Neo-Tokyo night": near-black background with a faint neon grid, CRT scanlines, and cyan/magenta/yellow corner glows. Primary accent is neon cyan (`--blue` is remapped to cyan), with Cyberpunk signature yellow (`--yellow`), Akira red (`--red`), and Edgerunners magenta (`--magenta`) as secondary accents; `--green` is neon jade. Display type is **Orbitron** (self-hosted at `app/static/fonts/orbitron.woff2`, variable, loaded via `@font-face` — no CDN, CSP `font-src 'self'`), uppercase, with neon text-glow; body text stays in the sans stack for readability. Panels are dark glass with notched (`clip-path`) corners and neon hairline borders/glows; buttons and the graph HUD use the same angular neon language. The stylesheet is token-driven, so the theme lives mostly in the `:root` tokens plus a cyberpunk enhancement layer at the end of `app/static/app.css`; graph node/edge colors live in `app/static/graph.js`. Preserve visible neon focus rings, responsive collapse, and reduced-motion support (the scanline sweep and title glitch are disabled under `prefers-reduced-motion`).

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
