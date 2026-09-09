# CI/CD integration instructions for agents

## Purpose

This repository is a secure application-onboarding template for the
`kanedasec` self-hosted DevSecOps lab. An agent working in a repository created
from this template must integrate the application without weakening the trust
boundaries described below.

Read this document completely before creating or modifying workflows,
Dockerfiles, Compose files, VPS scripts, GitHub settings, or credentials.

## Required architecture

The required application path is:

```text
Developer workstation
        ↓ feature branch
GitHub pull request
        ├── Standard CI
        └── Differential security → SGP Manager policy gate
        ↓ protected merge
main
        ↓ Standard CI succeeds
GitHub-hosted runner builds containers
        ↓
GHCR sha-<full-commit> images
        ↓ protected development environment
Ephemeral Tailscale node: tag:github-deploy
        ↓ Tailnet grant: VPS TCP/22 only
OpenSSH as deployer
        ↓ forced command
Restricted sudo to one root-owned deployment script
        ↓
docker compose pull + up -d --no-build
        ↓
Caddy proxy network
        ↓
Public HTTPS application
```

GitHub-hosted runners perform build and validation. The VPS only pulls and
runs artifacts. Never build application source on the VPS.

## Non-negotiable security rules

1. Do not expose public TCP/22 or suggest adding a Netcup firewall rule for it.
2. Do not enable root SSH or password SSH.
3. Do not add the deployment user to `docker` or grant unrestricted sudo.
4. Do not install a persistent general-purpose self-hosted GitHub runner.
5. Do not publish application host ports. Caddy must be the only public ingress.
6. Do not use `build:` in the VPS Compose definition.
7. Do not put credentials in Git, Dockerfiles, Compose files, artifacts, or logs.
8. Do not deploy from pull requests or unprotected branches.
9. Do not reference reusable workflows or actions by `main`, version-only tags,
   or other mutable references. Use full commit SHAs.
10. Do not deploy `latest` or the mutable `dev` convenience tag.
11. Do not let application repositories control scanner suppressions. Scanner
    exceptions belong to the reviewed central platform policy.
12. Do not give a GitHub runner direct Docker socket access on the VPS.
13. Do not alter unrelated VPS applications, persistent data, Caddy routes, or
    Tailnet permissions while onboarding one application.

## Repository roles

The application repository contains:

- source code and tests;
- one Dockerfile per deployable component;
- `.github/workflows/ci.yaml`, a small caller and ordered pipeline;
- `.github/workflows/security.yaml`, a small security caller;
- no deployment credentials.

`kanedasec/platform-workflows` contains:

- language CI profiles;
- differential Semgrep, Gitleaks, and Trivy scanners;
- SGP Manager policy integration;
- GHCR build and publish logic;
- the ephemeral Tailscale and restricted SSH deployment action.

The VPS contains, per application:

- `/opt/infra/<application>/compose.yaml`;
- `/opt/infra/<application>/app.env` with mode `0600` when needed;
- `/opt/infra/<application>/deployment.env` containing only `IMAGE_TAG`;
- `/opt/data/<application>/` persistent state;
- `/usr/local/sbin/deploy-<application>`, root-owned and mode `0755`;
- an explicit sudoers allowlist entry for that script.

## Understand the workflow ordering

Pull requests run Standard CI and the separate security workflow. Container
publishing and deployment are skipped.

On `main`, the CI/CD workflow is a single dependency graph:

```text
standard-ci → containers → deploy
```

The `needs:` relationships enforce this order. Do not split publishing and
deployment into an independent push workflow; independent workflows are
scheduled concurrently unless an explicit cross-workflow mechanism is added.

## Select the CI profile

Choose exactly one blueprint:

- `ci-cd.python.yaml`: Python application, one container image.
- `ci-cd.node.yaml`: Node.js application, one container image.
- `ci-cd.python-node.yaml`: Python backend and Node frontend, two images.

For a materially different stack, add a structured reusable profile to
`platform-workflows` through its protected review process. Do not insert
arbitrary application-supplied shell commands into a generic privileged
workflow.

## Required placeholders

Before activating a blueprint, replace every `__PLACEHOLDER__`. At minimum:

```text
__PLATFORM_SHA__       reviewed 40-character platform-workflows revision
__APP_SLUG__           GitHub repository name and SGP application slug
__PUBLIC_HOSTNAME__    application DNS name
__DEPLOY_COMMAND__     deploy-<application>
__CONTAINER_PORT__     application container listen port
__READINESS_PATH__     public health/readiness path, normally /ready
```

Search for unresolved placeholders before committing:

```bash
rg -n '__[A-Z0-9_]+__' .
```

Do not activate CI/CD while unresolved placeholders remain.

## Safe onboarding sequence

### Phase 1: application validation and publishing

1. Confirm the repository name equals the intended SGP Manager application
   slug.
2. Ensure application tests pass locally.
3. Create secure Dockerfiles and health endpoints.
4. Copy and configure the appropriate CI/CD blueprint, but temporarily omit
   the `deploy` job.
5. Copy `blueprints/github/security.yaml`.
6. Delete the template-only `.github/workflows/template-validation.yaml`.
7. Create `security-policy` and configure `SGP_MANAGER_API_KEY`.
8. Configure branch rules and required PR checks.
9. Merge through a pull request and confirm GHCR receives every expected
   `sha-<full-commit>` image.

### Phase 2: manual VPS bootstrap

1. Configure DNS for `<application>.kanedasec.com.br` to `152.53.48.159`.
2. Create `/opt/infra/<application>` and `/opt/data/<application>`.
3. Instantiate a Compose blueprint. It must use GHCR images and the external
   `proxy` network without `ports:` or `build:`.
4. Instantiate and install the root-owned deployment script.
5. Add one explicit sudoers entry for the script.
6. Extend the forced SSH dispatcher with an exact allowlist mapping.
7. Add the Caddy route and reload Caddy only after validation.
8. Manually pull and run the first published SHA tag.
9. Verify container health and public HTTPS `/` plus the readiness endpoint.

### Phase 3: automated deployment

1. Create the `development` GitHub Environment.
2. Restrict it to the `main` branch.
3. Add the shared Tailscale and SSH secrets and application-specific variables.
4. Restore the `deploy` job in `.github/workflows/ci.yaml`.
5. Open a PR and pass CI, scanners, and the SGP policy gate.
6. Merge and observe `standard-ci → containers → deploy`.
7. Confirm `deployment.env`, Compose image references, container health, and
   public HTTPS all identify the merge commit.

Detailed commands are in `docs/onboarding.md`.

## GitHub Environments

Create `security-policy` with this environment secret:

```text
SGP_MANAGER_API_KEY
```

Create `development`, restricted to `main`, with these environment secrets:

```text
TS_OAUTH_CLIENT_ID
TS_OAUTH_SECRET
DEPLOY_SSH_PRIVATE_KEY
```

And these environment variables:

```text
DEPLOY_HOST=100.114.123.6
DEPLOY_USER=deployer
DEPLOY_COMMAND=deploy-<application>
DEPLOY_URL=https://<application>.kanedasec.com.br
DEPLOY_KNOWN_HOSTS=<pinned VPS ED25519 known_hosts entry>
```

Never retrieve a host key using unauthenticated `ssh-keyscan` during the
deployment job. Obtain and pin it through the already trusted administrator
connection.

## Shared deployment credential consequence

This lab deliberately uses one Tailscale OAuth client and one SSH deployment
key across the pipeline. This reduces operational overhead but creates shared
blast radius: any repository that receives the shared deployment secrets can
attempt any command permitted by the server-side dispatcher.

The dispatcher and sudoers configuration must therefore remain exact
allowlists. Do not construct a root script path dynamically from caller input.
Per-application credentials or workload identity should be introduced later if
cryptographic isolation between applications becomes necessary.

## Branch protection

For `main`, require:

- pull requests;
- branch up-to-date before merge;
- conversation resolution;
- no force pushes;
- no deletion;
- Standard CI workflow validation;
- every enabled language test/build job;
- differential Semgrep, Gitleaks, and Trivy;
- SGP Manager policy gate.

Protect `.github/`, deployment blueprints, and agent instructions with
CODEOWNERS when an independent reviewer exists. A template repository does not
copy rulesets to repositories created from it; configure them explicitly.

## Verification before handoff

An agent must report evidence for:

```text
local tests
workflow syntax validation
no unresolved placeholders
no detected secrets
full-SHA action pins
GHCR image names and sha tag
VPS Compose config --quiet
no published application host ports
healthy containers
successful HTTPS root and readiness checks
Tailnet CI access limited to VPS TCP/22
deployer absent from docker and sudo groups
sudo denied for unrelated root commands
```

Do not claim onboarding is complete until the first automated post-merge
deployment and smoke test succeed.
