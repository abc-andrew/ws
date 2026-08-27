"""Parse, validate, and emit the small ``workspace.yaml`` manifest (spec §10).

The schema is intentionally tiny so it can be handled without a YAML dependency::

    version: 1
    repositories:
      toolkit:
        path: repos/toolkit
        origin: git@host:owner/toolkit.git
        base: main
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import WsError

MANIFEST_NAME = "workspace.yaml"
_REPO_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1]
    return value


def parse(path: Path) -> dict[str, dict[str, str]]:
    """Return ``{name: {path, origin, base}}`` or raise :class:`WsError`."""
    if not path.is_file():
        raise WsError(f"missing manifest: {path}")
    repos: dict[str, dict[str, str]] = {}
    in_repos = False
    current: str | None = None
    version: str | None = None
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if indent == 0 and text.startswith("version:"):
            version = _scalar(text.split(":", 1)[1])
        elif indent == 0 and text in ("repositories:", "repositories: {}"):
            in_repos = True  # "{}" is an explicit empty mapping
        elif in_repos and indent == 2 and text.endswith(":"):
            current = text[:-1].strip()
            if not _REPO_NAME_RE.fullmatch(current):
                raise WsError(f"{path}:{number}: invalid repository name")
            if current in repos:
                raise WsError(f"{path}:{number}: duplicate repository {current!r}")
            repos[current] = {}
        elif in_repos and indent == 4 and current and ":" in text:
            key, value = text.split(":", 1)
            repos[current][key.strip()] = _scalar(value)
        else:
            raise WsError(f"{path}:{number}: unsupported manifest syntax")
    if version != "1":
        raise WsError(f"{path}: version must be 1")
    _validate(path, repos)
    return repos


def _validate(path: Path, repos: dict[str, dict[str, str]]) -> None:
    for name, spec in repos.items():
        missing = {"path", "origin", "base"} - spec.keys()
        if missing:
            raise WsError(f"{path}: {name} missing {', '.join(sorted(missing))}")
        rel = Path(spec["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[:1] != ("repos",):
            raise WsError(f"{path}: {name} path must be a relative path under repos/")


def emit(repos: dict[str, dict[str, str]]) -> str:
    """Render a manifest dict back to canonical ``workspace.yaml`` text."""
    if not repos:
        return "version: 1\n\nrepositories: {}\n"
    lines = ["version: 1", "", "repositories:"]
    for name in repos:
        spec = repos[name]
        lines.append(f"  {name}:")
        for key in ("path", "origin", "base"):
            lines.append(f"    {key}: {spec[key]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
