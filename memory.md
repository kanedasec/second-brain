# Second Brain project memory

This file gives coding agents durable, public-safe context. Keep it free of credentials, personal knowledge, machine-specific paths, infrastructure addresses, and private environment values.

## Product intent

Second Brain is a private memory atlas. A user gives notes, email, briefings, diary text, or transcripts to an external AI using the prompt served by the app. The primary AI handoff returns unified schema-3.0 JSON. The user uploads that one file and browses the same grounded knowledge through chronology, topics, context search, task status, facts, gaps, recommendations, and the relationship graph.

The product must make epistemic boundaries obvious:

- facts and actions require source evidence;
- actions are explicit commitments, never inferred AI suggestions;
- entity explanations say whether they came from the source or general knowledge;
- recommendations are always labeled as AI-generated advice;
- missing data remains missing rather than being guessed.

## Technical shape

- Python 3.13, FastAPI, Pydantic, Jinja, and SQLite.
- Server-rendered HTML with a small dependency-free JavaScript layer.
- `app/schemas.py` is the canonical ingestion contract. It defines three bundle formats: legacy `KnowledgeBundle` (schema 1.0, editorial memory records), legacy `GraphBundle` (schema 2.0, graph-only nodes and edges), and the primary `AtlasBundle` (schema 3.0, memories plus nodes and edges in one object). `/import` dispatches on `schema_version`. Schema-3 imports write both representations in one SQLite transaction, so every application surface updates or the entire file rolls back. Every schema-3 memory must have a matching `mem:<memory-id>` graph node with category `memory`; the graph merge preserves the memory projection's `record_id`, keeping authored memory nodes linked to their full record. Before a schema-3 write, reconciliation previews exact-ID updates and unique normalized-label/category matches. The user must explicitly confirm the matching plan; ambiguous matches are blocked. Confirmed non-memory matches reuse the existing ID, legacy memory matches are folded into `mem:<memory-id>` with their stored edges rewired, and editorial projections reuse a single authored same-label/category identity. Do not infer editorial facts, actions, or gaps from legacy graph-only data.
- The graph view (force-directed, client-side, self-hosted `force-graph`) unifies author-imported graphs with a namespaced projection of editorial memory records. It supports exploration: search (highlight + zoom-to-match), clickable legend category filters, an AI-inferred-link toggle, click-to-select with neighbor highlighting, node-neighborhood isolation, a reset, and progressive disclosure (highest-degree nodes first with a "show all" control) past a node cap for large graphs. Nodes glow (neon) and scale by degree so hubs stand out; hovering highlights a node's links; camera transitions are instant under `prefers-reduced-motion`. Grounding carries into graph data as node/edge `provenance` (`source` vs `ai_inferred`) plus `evidence`/`source`.
- `app/prompt.py` holds a three-group prompt library: source-preparation prompts (email review, meeting-transcript review, interactive daily report) that output a **written report**; the primary **unified atlas generator** that appends the schema-3 JSON Schema and outputs one JSON file for every view; and a **presentation builder** that turns an exported graph into a single-page HTML / PPTX / PDF presentation. Legacy schema-1 and schema-2 prompt/schema endpoints remain available for compatibility but the UI advertises schema 3.0. The `/prompt` page is a gated library — bodies are not inlined; they load on demand from `/prompts/{id}.txt` behind a reveal button. Prompt instruction text lives in `app/content/*.md`. (No in-app AI dependency — these are static templates.)
- `GET /export/graph.json` exports the graph as a schema-2.0 `GraphBundle` that round-trips back through import (validated before download). With no params it exports the whole graph ("Export all" toolbar button); with `?nodes=id1,id2&depth=N` it exports only those seed nodes plus everything within `N` relationship hops (edges undirected for reach), default depth 3. In the viewer, nodes are added to an export set via the detail panel's "Add to export" button or modifier-click (Shift/Ctrl/Cmd+click), and a selection bar downloads the subgraph at a chosen level depth.
- UI is bilingual **English / Brazilian Portuguese** via `app/i18n.py` (gettext-style: English source strings are the keys, English is the fallback). Language is a per-request `lang` cookie set by `/set-language`; templates call the injected `t()` helper, and `graph.js`/`prompts.js` carry small client-side string maps. This translates the **interface only — never user memory content**.
- `app/db.py` owns schema initialization, atomic imports, search, topic dossiers, and task views.
- `app/backup.py` owns consistent weekly backups and retention.
- `app/main.py` owns routes, authentication, upload limits, origin checks, and security headers. State-changing requests are authorized by the `Sec-Fetch-Site` fetch-metadata header (primary), with an `Origin`/`Host` comparison as fallback for clients that omit it, plus a per-form double-submit CSRF token. Do not re-introduce a bare `Origin == Host` check: the app sends `Referrer-Policy: no-referrer`, which makes browsers send `Origin: null` on same-origin form POSTs, and a bare check then 403s every upload.
- `deploy/` holds the reviewed runtime assets (Compose, Caddy route, restricted deploy script, sudoers rule, dispatcher snippet). `deploy/bootstrap-second-brain` is an idempotent, root-run script that automates onboarding phases 3-5: it validates staged assets, refuses a group/other-readable `app.env`, requires an immutable `deployment.env` tag, backs up the shared dispatcher and Caddyfile before patching, and rolls Caddy back on failure. Secret-bearing staged assets (`app.env`, `deployment.env`) are never committed. `deploy/Caddyfile` is the single source of truth for the public hostname; the CI `DEPLOY_URL` deployment variable and the DNS record must match it, or the post-deploy smoke check fails. The app reaches the shared Caddy ingress over an external `proxy` Docker network; the bootstrap creates that network if absent and starts only the shared Caddy container (never other applications).

## Design language

The interface is a **Cyberpunk 2077 / Edgerunners / Akira**-inspired "Neo-Tokyo night": near-black background with a faint neon grid, CRT scanlines, and cyan/magenta/yellow corner glows. Primary accent is neon cyan (`--blue` is remapped to cyan), with Cyberpunk signature yellow (`--yellow`), Akira red (`--red`), and Edgerunners magenta (`--magenta`) as secondary accents; `--green` is neon jade. Display type is **Orbitron** (self-hosted at `app/static/fonts/orbitron.woff2`, variable, loaded via `@font-face` — no CDN, CSP `font-src 'self'`), uppercase, with neon text-glow; body text stays in the sans stack for readability. Panels are dark glass with notched (`clip-path`) corners and neon hairline borders/glows; buttons and the graph HUD use the same angular neon language. The stylesheet is token-driven, so the theme lives mostly in the `:root` tokens plus a cyberpunk enhancement layer at the end of `app/static/app.css`; graph node/edge colors live in `app/static/graph.js`. Preserve visible neon focus rings, responsive collapse, and reduced-motion support (the scanline sweep and title glitch are disabled under `prefers-reduced-motion`).

## Invariants

1. Keep schema versions `1.0` and `2.0` backward compatible; schema `3.0` is the primary complete-atlas format.
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

Use `examples/example-atlas.json` for primary synthetic manual testing and `examples/example-memory.json` for legacy schema-1 checks. They must remain fictional and contain no personal data.

## Good next increments

- schema migrations and export/restore tooling;
- editable action status with an audit trail;
- encrypted-at-rest storage strategy;
- related-memory suggestions based on local, deterministic signals;
- optional passkey or identity-aware proxy authentication;
- end-to-end browser accessibility tests.
