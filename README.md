# Second Brain

A private, self-hosted memory atlas for structured notes, email summaries, briefings, diary entries, and recording transcripts.

Second Brain deliberately keeps the AI outside the application. You copy the built-in prompt into ChatGPT, Claude, Copilot, or another model, add your source material, and import the resulting JSON. The app validates every field before storing it.

## What it does

- browses memories by chronology, topic, date range, and full-context search;
- separates source-grounded facts from general-knowledge explanations;
- shows explicit commitments as overdue, upcoming, later, unscheduled, or concluded, with an audited completion control;
- groups grounded facts and unanswered questions into topic dossiers;
- marks all model-generated recommendations as AI advice;
- imports one unified schema-3 file into memories, topics, tasks, search, and the graph atomically;
- provides the current prompt and JSON Schema from the web interface;
- protects private routes with HTTP Basic authentication in production;
- creates an integrity-checked SQLite backup every Friday at 23:55 and removes backups older than 93 days.

## Local development

Requires Python 3.13.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Development mode allows local access without credentials. To exercise authentication, copy `.env.example` into your own untracked environment configuration and set both credential variables.

Run the tests:

```bash
python -m pytest -q tests
```

The synthetic [`examples/example-atlas.json`](examples/example-atlas.json) exercises the primary unified format. [`examples/example-memory.json`](examples/example-memory.json) remains available for schema-1 compatibility testing.

## Ingestion flow

1. Open `/prompt` and copy or download the complete prompt.
2. Paste it into an AI, followed by the source text after the divider.
3. Save the AI response as a `.json` file without Markdown fences.
4. Upload one or more files at `/import`.
5. Review the reconciliation preflight when an upload would update or merge existing graph identities, then explicitly confirm it. Ambiguous matches remain blocked until their IDs are corrected.
6. Fix any schema errors reported by the importer; invalid or unconfirmed bundles are never partially written.

The primary versioned instructions are in [`app/content/atlas-ingestion-prompt.md`](app/content/atlas-ingestion-prompt.md). The application appends the JSON Schema generated directly from the Pydantic models, so the prompt and validation contract cannot drift independently. Schema 1.0 memory-only and schema 2.0 graph-only imports remain backward compatible, but the web interface clearly labels their limited scope.

Schema-3 graph reconciliation is deterministic: exact IDs are compared before update, and a different ID is considered a likely duplicate only when its normalized label and compatible category match exactly one existing node. The preview shows inserts, updates, and identity merges before any write. Multiple candidates are never guessed.

Open tasks can be marked concluded from `/tasks`. The transition and timestamp are stored atomically and remain visible in the concluded archive. If exactly one existing task-like graph node matches the action title (preferring the same memory relationship or explicit metadata), that node receives concluded-state metadata in the same transaction. The application never creates a graph node during task completion and never guesses between multiple matches.

## Storage and privacy

The application uses SQLite in WAL mode. Production data lives on a persistent volume and is not baked into the container image. Search terms and private routes are not written to application access logs by the production container command.

Production refuses to start unless `SECOND_BRAIN_USERNAME` and a password of at least 16 characters are configured. `/ready` remains public for container and deployment health checks; all knowledge routes require authentication.

## Deployment

The repository calls `kanedasec/platform-workflows` at immutable commit `2358c3996ce347e42ee8dfd09e2cba68a74a30bf` for Python CI, container publishing, SGP policy evaluation, and Tailscale/SSH deployment. Runtime assets are in [`deploy/`](deploy/), and the full operator checklist is in [`docs/onboarding.md`](docs/onboarding.md).

If SGP Manager is unavailable, every registered scanner still runs and low, medium, high, and critical findings all block with no bypasses. Clean reports allow delivery to continue; failed scanners and missing or malformed evidence still block publishing and deployment.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the data and trust boundaries. Agent-facing project context is maintained in [`memory.md`](memory.md).
