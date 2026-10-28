# Instructions for coding agents

Read [`memory.md`](memory.md) before changing product behavior. It contains the durable public-safe product model, architecture, design language, and invariants.

## Repository role

This is the application repository for Second Brain, a private structured-memory service. It contains the FastAPI application, tests, one container image, small callers for the shared platform workflows, and reviewed runtime/deployment assets.

Do not add personal notes, imported JSON, real email, recordings, credentials, infrastructure secrets, or generated databases to Git.

## Local validation

Use Python 3.13 when available:

```bash
python -m pip install --requirement requirements-dev.txt
python -m pytest -q tests
actionlint .github/workflows/*.yaml
git diff --check
bash -n deploy/deploy-second-brain
```

Validate the Docker image and Compose model when those areas change. Use the synthetic `examples/example-memory.json`; never test with private user data.

Run Gitleaks with the centrally reviewed configuration when available. Do not add repository-local suppressions.

## Application invariants

- `app/schemas.py` is the canonical JSON ingestion contract.
- Keep source facts, explicit actions, entity enrichment, knowledge gaps, and AI recommendations separate.
- Do not weaken evidence requirements, strict unknown-field rejection, timezone validation, or atomic imports.
- Production must fail startup when authentication is absent. `/ready` must remain content-free.
- Do not log uploads, memory content, search terms, authentication data, or secrets.
- Do not introduce an AI API or model credential into the application without an explicit product decision.
- Preserve accessible semantics, visible focus, responsive behavior, and reduced-motion support.

## CI/CD trust rules

The repository consumes `kanedasec/platform-workflows` as the central trust root.

1. Pin every external action and reusable workflow to a full 40-character commit SHA.
2. Never use `pull_request_target`, self-hosted runners, or checkout credentials persisted into the worktree.
3. Keep pull requests unable to publish, deploy, or receive deployment secrets.
4. Keep the SGP Manager security path fail closed. Outages, malformed responses, stale decisions, or authentication failures block promotion; they never authorize a fallback deploy.
5. Give `packages: write` only to the container publishing job.
6. Publish and deploy only `sha-<full-commit>` images, never mutable tags.
7. Do not expose Docker or arbitrary shell inputs through reusable workflows.

## Runtime and deployment rules

- The VPS pulls immutable images; it never builds application source.
- Caddy is the only public ingress. Do not add Compose `ports:` or `build:` entries.
- The application runs as UID/GID `10001` with a read-only root filesystem, dropped capabilities, and only its data volume writable.
- The deployment user must not receive Docker group membership, root SSH, password SSH, or unrestricted sudo.
- The forced SSH dispatcher and sudoers rule must allow only the exact application deployment command.
- Keep the root-owned deployment script's tag validation, OCI revision verification, health wait, deployment lock, and rollback behavior.
- Do not commit app credentials, Tailscale credentials, SSH material, known-hosts values, or application data.

## Delivery discipline

Work on a feature branch, preserve unrelated user changes, and commit only after relevant local validation succeeds. Do not claim deployment is complete until a protected post-merge run publishes the immutable image, the restricted deployment succeeds, and both the root authentication response and readiness endpoint pass public smoke checks.
