# Deployment onboarding

Follow this in phases. Do not enable automated deployment until the application image has passed CI/security and a manual immutable deployment has succeeded.

## 1. Repository controls

Create a protected `security-policy` environment containing the `SGP_MANAGER_API_KEY` secret. When SGP Manager is offline or cannot return a trusted policy, `.github/workflows/security.yaml` runs every registered scanner and enforces every severity with no bypasses. Clean reports continue; findings, scanner failures, and invalid evidence block promotion.

Protect `main` with required pull requests, current branches, resolved conversations, and these checks:

- workflow validation and backend tests;
- every registered Semgrep, Gitleaks, and Trivy job;
- `Security policy (SGP Manager)`.

The first publishing PR may temporarily omit the `deploy` job if the runtime has not yet been bootstrapped.

## 2. GitHub environments

Create a protected `development` environment limited to `main`. Configure the Tailscale OAuth, restricted SSH key, pinned known-hosts value, Tailscale deployment host, deployment user, exact command `deploy-second-brain`, and public origin as described in the platform workflow contract.

Never place those values in the repository, an artifact, or a command shown in logs.

## 3. Persistent runtime

Phases 3 through 5 are automated by the reviewable, idempotent, root-run [`deploy/bootstrap-second-brain`](../deploy/bootstrap-second-brain) script. Stage the assets it expects in one directory (`compose.yaml`, `app.env`, `deployment.env`, `deploy-second-brain`, `sudoers`, `Caddyfile`), then run it as root with that directory as its only argument. It validates every asset, requires an immutable `deployment.env` tag, refuses a group- or other-readable `app.env`, backs up the shared dispatcher and Caddyfile before patching them, and restores Caddy on any validation or reload failure. The manual steps below describe what it installs; perform them by hand only if you are not using the script.

Create the application infrastructure directory and a persistent data directory owned by UID/GID `10001`, the container's unprivileged runtime identity. Install:

- [`deploy/compose.yaml`](../deploy/compose.yaml) as the application's Compose file;
- an `app.env` readable only by root;
- `deployment.env` containing only an initial immutable `IMAGE_TAG=sha-<40 hex>` value;
- [`deploy/deploy-second-brain`](../deploy/deploy-second-brain) as a root-owned executable;
- the exact sudoers rule from [`deploy/sudoers`](../deploy/sudoers).

The application environment must set a unique username, a strong password of at least 16 characters, and the intended timezone. Do not add a `ports:` or `build:` key to the runtime Compose file.

Validate before starting anything:

```bash
docker compose --env-file ./app.env --env-file ./deployment.env -f compose.yaml config --quiet
bash -n /usr/local/sbin/deploy-second-brain
visudo --check
```

## 4. Restricted deployment path

Add `deploy-second-brain` as an exact branch in the existing forced SSH dispatcher; the snippet is provided in [`deploy/ssh-dispatch-snippet`](../deploy/ssh-dispatch-snippet). Keep the dispatcher allowlist explicit and deny unrelated commands.

Confirm the deployment user is not a member of the Docker or sudo groups and that unrelated sudo commands fail.

## 5. Caddy and first deployment

Add [`deploy/Caddyfile`](../deploy/Caddyfile) to the existing Caddy configuration, validate it, and reload only after the application container is reachable on the proxy network.

Deploy an image whose tag matches a published repository commit. Verify:

- both `app` and `backup` services are running;
- `app` is healthy and has no host port;
- unauthenticated `/` returns `401`;
- authenticated `/` returns `200`;
- `/ready` returns `200` without credentials;
- the backup process logs its next Friday schedule;
- a manually invoked test backup passes integrity validation before relying on the weekly schedule.

## 6. Enable automated deployment

Restore the deployment job if it was omitted, then merge through the protected path. Observe this exact sequence:

```text
Standard CI -> Application container -> Development deployment
```

Confirm the running image and OCI revision match the merge commit. Do not describe the rollout as complete until the first post-merge deployment and both public smoke checks succeed.
