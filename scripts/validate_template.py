#!/usr/bin/env python3

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    ".github/CODEOWNERS",
    "blueprints/github/ci-cd.python.yaml",
    "blueprints/github/ci-cd.node.yaml",
    "blueprints/github/ci-cd.python-node.yaml",
    "blueprints/github/security.yaml",
    "blueprints/vps/compose.single.yaml",
    "blueprints/vps/compose.python-node.yaml",
    "blueprints/vps/deploy-application",
    "blueprints/vps/ssh-deploy-dispatch",
    "docs/architecture.md",
    "docs/onboarding.md",
)

USES_PATTERN = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_REFERENCE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
PLACEHOLDER_REFERENCE = re.compile(r"^[^@\s]+@__PLATFORM_SHA__$")


def require_files() -> None:
    missing = [relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file()]
    if missing:
        raise ValueError("missing required template files: " + ", ".join(missing))


def validate_action_references() -> None:
    files = tuple((ROOT / ".github" / "workflows").glob("*.yaml")) + tuple(
        (ROOT / "blueprints" / "github").glob("*.yaml")
    )

    for path in files:
        contents = path.read_text(encoding="utf-8")
        for reference in USES_PATTERN.findall(contents):
            if reference.startswith("./"):
                continue
            if path.parent == ROOT / "blueprints" / "github":
                valid = bool(
                    FULL_SHA_REFERENCE.fullmatch(reference)
                    or PLACEHOLDER_REFERENCE.fullmatch(reference)
                )
            else:
                valid = bool(FULL_SHA_REFERENCE.fullmatch(reference))
            if not valid:
                raise ValueError(f"mutable or invalid action reference in {path}: {reference}")


def validate_workflow_safety() -> None:
    forbidden = (
        "pull_request_target:",
        "runs-on: self-hosted",
        "/var/run/docker.sock",
    )
    for path in (ROOT / "blueprints" / "github").glob("*.yaml"):
        contents = path.read_text(encoding="utf-8")
        for value in forbidden:
            if value in contents:
                raise ValueError(f"forbidden workflow pattern in {path}: {value}")


def validate_compose_safety() -> None:
    for path in (ROOT / "blueprints" / "vps").glob("compose.*.yaml"):
        contents = path.read_text(encoding="utf-8")
        if re.search(r"^\s*build:\s*$", contents, re.MULTILINE):
            raise ValueError(f"VPS Compose blueprint contains build: {path}")
        if re.search(r"^\s*ports:\s*$", contents, re.MULTILINE):
            raise ValueError(f"VPS Compose blueprint publishes host ports: {path}")
        if "external: true" not in contents or "name: proxy" not in contents:
            raise ValueError(f"VPS Compose blueprint lacks external proxy network: {path}")


def validate_required_placeholders() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "blueprints" / "github").glob("*.yaml")
    )
    for placeholder in ("__PLATFORM_SHA__", "__READINESS_PATH__"):
        if placeholder not in workflow_text:
            raise ValueError(f"missing workflow placeholder: {placeholder}")

    vps_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "blueprints" / "vps").iterdir()
        if path.is_file()
    )
    for placeholder in (
        "__APP_SLUG__",
        "__DEPLOY_COMMAND__",
        "__PUBLIC_HOSTNAME__",
    ):
        if placeholder not in vps_text:
            raise ValueError(f"missing VPS placeholder: {placeholder}")


def main() -> None:
    checks = (
        require_files,
        validate_action_references,
        validate_workflow_safety,
        validate_compose_safety,
        validate_required_placeholders,
    )
    for check in checks:
        check()
    print("template validation: pass")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(f"template validation failed: {error}") from error
