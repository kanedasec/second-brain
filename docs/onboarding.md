# Application onboarding recipe

Replace `NEW_APP` with the repository/application slug. The slug must use only
lowercase letters, digits, and hyphens and must match the SGP Manager
application name.

## 1. Create from the template

```bash
gh repo create kanedasec/NEW_APP \
  --private \
  --template kanedasec/application-template \
  --clone

cd NEW_APP
git switch -c feature/bootstrap-cicd
```

Read `AGENTS.md`, select a stack profile, and copy it:

```bash
cp blueprints/github/ci-cd.python.yaml .github/workflows/ci.yaml
cp blueprints/github/security.yaml .github/workflows/security.yaml
rm .github/workflows/template-validation.yaml
```

For the first PR, remove the `deploy` job from `ci.yaml`. Keep
`containers.needs: standard-ci`.

Replace every placeholder and verify none remain:

```bash
rg -n '__[A-Z0-9_]+__' .github/workflows
```

Use a reviewed `platform-workflows` full commit SHA, never `main`.

## 2. Create the SGP Manager application

Create an SGP application whose slug exactly equals `NEW_APP`. Configure the
expected gate policies for:

```text
sast
secrets
sca
```

The application caller derives this slug from the GitHub repository name.

## 3. Configure the security environment

In GitHub, create an environment named `security-policy` and add the shared:

```text
SGP_MANAGER_API_KEY
```

Do not store it as a plaintext repository variable.

## 4. Merge the publishing bootstrap

Commit, push, and open a PR:

```bash
git add .
git commit -m "ci: bootstrap standardized pipeline"
git push -u origin feature/bootstrap-cicd
gh pr create --base main
```

After the PR passes and merges, confirm GHCR contains every expected
`sha-<merge-commit>` image. Decide deliberately whether the packages are public
or private. A private package requires a root-controlled read-only registry
credential on the VPS; a public package requires none.

## 5. Prepare VPS directories

Connect only through Tailscale:

```bash
ssh kanedasec@100.114.123.6
```

Create infrastructure and persistent-state directories:

```bash
sudo install -d -o root -g root -m 0755 /opt/infra/NEW_APP
sudo install -d -o root -g root -m 0750 /opt/data/NEW_APP
```

Instantiate the appropriate Compose blueprint as:

```text
/opt/infra/NEW_APP/compose.yaml
```

Create an application environment file even when initially empty:

```bash
sudoedit /opt/infra/NEW_APP/app.env
sudo chown root:root /opt/infra/NEW_APP/app.env
sudo chmod 0600 /opt/infra/NEW_APP/app.env
```

Create deployment state with the first GHCR SHA tag:

```bash
sudoedit /opt/infra/NEW_APP/deployment.env
sudo chown root:root /opt/infra/NEW_APP/deployment.env
sudo chmod 0644 /opt/infra/NEW_APP/deployment.env
```

The file contains only:

```dotenv
IMAGE_TAG=sha-<full-40-character-commit>
```

Validate Compose:

```bash
cd /opt/infra/NEW_APP
sudo docker compose \
  --env-file ./app.env \
  --env-file ./deployment.env \
  -f compose.yaml \
  config --quiet
```

## 6. Install the deployment script

Instantiate `blueprints/vps/deploy-application` on the VPS as:

```text
/usr/local/sbin/deploy-NEW_APP
```

Replace the service and image arrays with quoted Bash values. For one image:

```bash
PULL_SERVICES=(app)
HEALTH_SERVICES=(app)
IMAGE_REPOSITORIES=(ghcr.io/kanedasec/NEW_APP-app)
```

For backend and frontend:

```bash
PULL_SERVICES=(backend frontend)
HEALTH_SERVICES=(backend frontend)
IMAGE_REPOSITORIES=(
    ghcr.io/kanedasec/NEW_APP-backend
    ghcr.io/kanedasec/NEW_APP-frontend
)
```

Secure and validate:

```bash
sudo chown root:root /usr/local/sbin/deploy-NEW_APP
sudo chmod 0755 /usr/local/sbin/deploy-NEW_APP
sudo bash -n /usr/local/sbin/deploy-NEW_APP
```

## 7. Extend sudo and forced SSH

Create an explicit sudoers entry using `visudo`:

```bash
sudo visudo -f /etc/sudoers.d/deploy-NEW_APP
```

Insert:

```sudoers
deployer ALL=(root) NOPASSWD: /usr/local/sbin/deploy-NEW_APP
```

Then:

```bash
sudo chmod 0440 /etc/sudoers.d/deploy-NEW_APP
sudo visudo --check
```

Extend the existing forced-command dispatcher with an exact command-to-script
case. Do not create dynamic root paths from `SSH_ORIGINAL_COMMAND`.

Verify unrelated sudo remains denied:

```bash
sudo -u deployer sudo -n /usr/bin/id
```

## 8. Add DNS and Caddy

Create:

```text
NEW_APP.kanedasec.com.br A 152.53.48.159
```

Instantiate the Caddy blueprint with the application's proxy-network alias and
container port. Validate, then reload:

```bash
sudo docker exec caddy \
  caddy validate \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile

sudo docker exec caddy \
  caddy reload \
  --config /etc/caddy/Caddyfile \
  --adapter caddyfile
```

Do not publish an application host port for Caddy to reach it.

## 9. Perform the first manual deployment

```bash
sudo /usr/local/sbin/deploy-NEW_APP \
  sha-<full-40-character-commit>
```

Verify:

```bash
sudo docker compose \
  --env-file /opt/infra/NEW_APP/app.env \
  --env-file /opt/infra/NEW_APP/deployment.env \
  -f /opt/infra/NEW_APP/compose.yaml \
  ps

curl --fail --silent --show-error \
  https://NEW_APP.kanedasec.com.br/

curl --fail --silent --show-error \
  https://NEW_APP.kanedasec.com.br/ready
```

## 10. Configure the development environment

Create `development` in GitHub and restrict it to `main`.

Add environment secrets interactively:

```bash
gh secret set TS_OAUTH_CLIENT_ID --env development
gh secret set TS_OAUTH_SECRET --env development
gh secret set DEPLOY_SSH_PRIVATE_KEY \
  --env development \
  < /path/to/the/shared/deployment/private/key
```

Add environment variables:

```bash
gh variable set DEPLOY_HOST --env development --body "100.114.123.6"
gh variable set DEPLOY_USER --env development --body "deployer"
gh variable set DEPLOY_COMMAND --env development --body "deploy-NEW_APP"
gh variable set DEPLOY_URL \
  --env development \
  --body "https://NEW_APP.kanedasec.com.br"
gh variable set DEPLOY_KNOWN_HOSTS \
  --env development \
  --body "<trusted known_hosts line>"
```

Never place credential values directly in shell arguments or documentation.

## 11. Enable CD

Restore the reviewed `deploy` job in `.github/workflows/ci.yaml`, open a PR,
and require all CI/security checks. After merge, verify this exact order:

```text
Standard CI → Application containers → Development deployment
```

Confirm the deployment job creates an ephemeral Tailscale node, the forced SSH
command succeeds, the VPS runs the merge commit's SHA tag, and both HTTPS smoke
tests pass.

## 12. Configure repository rules

Repository-template settings are not inherited. Configure `main` with:

- pull requests required;
- branch up-to-date required;
- conversation resolution required;
- force pushes and deletion blocked;
- required Standard CI jobs for the selected stack;
- required Semgrep, Gitleaks, Trivy, and SGP Manager policy checks;
- CODEOWNER approval when an independent reviewer exists.
