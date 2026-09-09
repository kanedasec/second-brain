# CI/CD architecture

## Pull-request path

Every feature change enters through a pull request:

```text
feature/*
   ├── Standard CI
   │     ├── actionlint workflow validation
   │     ├── language tests
   │     └── frontend build/tests when applicable
   └── Differential security
         ├── Semgrep SAST
         ├── Gitleaks secrets
         ├── Trivy SCA
         └── SGP Manager policy decision
```

Security scans do not receive the SGP API key. They upload redacted reports as
short-lived workflow artifacts. A separate caller-side job binds to the
`security-policy` GitHub Environment, downloads those reports, and asks SGP
Manager whether each gate passes.

Branch rules require the resulting checks before merge.

## Main-branch path

The application CI/CD workflow uses job dependencies:

```text
standard-ci
     ↓ needs
containers
     ↓ needs
deploy
```

`standard-ci` repeats after merge to validate the exact main-branch commit.
`containers` receives `packages: write`, builds on a GitHub-hosted runner, and
publishes GHCR images named:

```text
ghcr.io/kanedasec/<repository>-<component>:sha-<full-commit>
```

The workflow also publishes `dev` as a convenience tag, but deployment must use
the SHA tag.

The deployment job binds to the `development` environment only after container
publishing succeeds. It joins Tailscale as an ephemeral
`tag:github-deploy` node, connects to the VPS's Tailscale IPv4 address, pins the
VPS OpenSSH host key, and invokes one forced command.

The VPS deployment user does not belong to `docker` or `sudo`. Sudoers permits
only the root-owned application deployment script. That script validates the
tag, serializes deployments, pulls images, verifies OCI revision labels,
updates `deployment.env` atomically, starts Compose without building, checks
health, and attempts rollback on failure.

After SSH returns successfully, the GitHub-hosted runner requests the public
HTTPS root and readiness endpoint. This verifies the complete path through DNS,
the Netcup firewall, Caddy TLS, the Docker proxy network, and the application.

## Trust boundaries

### Pull request to protected main

Pull-request code is untrusted. It receives no deployment secrets and cannot
publish or deploy. Branch rules and required checks control promotion to main.

### Main to GHCR

The publish job uses the ephemeral workflow `GITHUB_TOKEN`. Only that job gets
`packages: write`. Image tags and OCI revision labels link artifacts to source.

### GitHub to Tailnet

The Tailscale OAuth client may create only tagged ephemeral nodes. Tailnet
policy grants the tag only TCP/22 to the VPS, not access to workstations,
phones, dashboards, Caddy, or unrelated private services.

### Runner to VPS

The pinned known-hosts entry authenticates the VPS. The deployment SSH key
authenticates the runner. The authorized-key forced command removes shell,
forwarding, PTY, and arbitrary command access.

### Deployer to root and Docker

Docker daemon access is root-equivalent. The deployer never receives it.
Restricted sudo exposes only an input-validating, root-owned deployment script.

### Caddy to application

Caddy is the only service publishing host TCP/80 and TCP/443. Application
containers join the external `proxy` network and normally expose no host ports.
