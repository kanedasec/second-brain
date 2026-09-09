# Application CI/CD template

Private template repository for applications built on the `kanedasec`
DevSecOps lab platform.

This repository is intentionally an onboarding kit rather than a runnable
sample application. It provides reviewed blueprints for:

- pull-request CI and differential security;
- commit-SHA-tagged GHCR publishing;
- GitHub Environment-controlled deployment;
- ephemeral Tailscale access to the VPS;
- forced SSH commands and restricted sudo;
- Docker Compose runtime definitions with no application host ports;
- Caddy-only public ingress and HTTPS smoke tests.

## Start a new application

Create a repository from this template:

```bash
gh repo create kanedasec/NEW_APPLICATION \
  --private \
  --template kanedasec/application-template \
  --clone
```

Then enter the repository and read `AGENTS.md` before enabling workflows:

```bash
cd NEW_APPLICATION
sed -n '1,260p' AGENTS.md
```

Choose one CI/CD blueprint:

```text
blueprints/github/ci-cd.python.yaml
blueprints/github/ci-cd.node.yaml
blueprints/github/ci-cd.python-node.yaml
```

The complete onboarding sequence is in
[`docs/onboarding.md`](docs/onboarding.md).

## What a GitHub template does not copy

Repository templates copy Git files. They do not copy:

- repository visibility decisions;
- branch rulesets or required status checks;
- GitHub Environments, secrets, or variables;
- SGP Manager application objects and policy configuration;
- Tailscale credentials or policy;
- GHCR package visibility;
- DNS records;
- VPS Compose files, deployment scripts, or Caddy configuration.

Those controls must be configured for every new application using the
onboarding checklist.

## Platform trust root

Application workflows must call `kanedasec/platform-workflows` using a full
40-character commit SHA. Never reference `main` or a mutable release tag.

The current reviewed example pin in the blueprints is:

```text
d2f64a7d70a3112c7a99687e60963be804306a31
```

Agents must verify that the selected revision still contains every referenced
workflow and action before using a newer revision.
