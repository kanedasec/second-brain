# Second Brain architecture

## Data flow

```text
Private source text
  -> external AI + versioned ingestion prompt
  -> unified schema-v3 JSON atlas
  -> authenticated upload
  -> Pydantic validation
  -> one SQLite transaction
  -> memory atlas / topic dossiers / task radar / relationship graph
```

The application does not call an AI service. This keeps model choice flexible and prevents API credentials or source text from being sent by the service itself.

## Grounding model

The schema separates five kinds of information:

| Kind | Rule | Presentation |
| --- | --- | --- |
| Facts | Must include source evidence and confidence | “What you know” |
| Actions | Only explicit commitments or requests | Task radar |
| Entity explanations | Only for mentioned entities; provenance is source or general knowledge | “Mentioned, explained” |
| Knowledge gaps | Missing or unresolved information | “What you still need” |
| Recommendations | Must carry `ai_generated: true` | Visibly labeled AI advice |

The importer forbids unknown fields, requires timezone-aware timestamps, requires evidence for facts/actions/entities, and writes the editorial and graph representations atomically. Exact file checksums and stable memory IDs prevent accidental duplicates. Before a schema-3 write, graph reconciliation classifies inserts, exact-ID updates, and same-label/category identity merges. Updates and merges require an explicit matching-plan confirmation; multiple semantic candidates block the import rather than guessing. Schema 1.0 memory-only and schema 2.0 graph-only bundles remain supported; the importer never guesses editorial facts or tasks from graph-only data.

## Application components

- FastAPI handles HTTP, validation, authentication, and security headers.
- Jinja templates and small progressive-enhancement JavaScript provide the interface without a frontend build step.
- SQLite stores normalized memories, topics, facts, entities, actions, gaps, and recommendations alongside first-class graph nodes and edges.
- A separate process using the same immutable image schedules consistent SQLite backups.

Search covers titles, summaries, context, people, facts, evidence, topics, and entity explanations. Topic pages assemble facts and gaps from all connected memories. Task status is computed at read time from explicit deadlines.

## Runtime security

Private routes use HTTP Basic authentication over Caddy-managed HTTPS. Production configuration fails startup when credentials are absent. Unsafe cross-origin browser requests are rejected, uploads are size-limited and schema-validated, and responses set a restrictive content security policy.

The container runs as an unprivileged user with a read-only root filesystem, dropped capabilities, process limits, and only the persistent data volume writable. It publishes no host port and is reachable only through the external proxy network.

## Backup lifecycle

The backup service calculates the next Friday at 23:55 in the configured timezone. It uses SQLite's online backup API, runs `PRAGMA integrity_check`, writes a SHA-256 companion file, and retains a rolling 93-day window. Application and backup processes share the persistent data volume.

## Delivery path

```text
pull request
  -> standard CI
  -> every registered full-repository scanner
  -> SGP Manager bypass resolution
     OR strict all-severity blocking with no bypasses when unavailable
  -> protected main
  -> immutable GHCR sha-<commit> image
  -> protected deployment environment
  -> restricted deployment command
  -> public root expects 401; /ready expects 200
```

Every platform reference is pinned to a full commit SHA. The deployment script accepts only immutable SHA tags, verifies the OCI revision label, performs health checks, and rolls back deployment state on failure.
