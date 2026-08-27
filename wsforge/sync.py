"""``ws sync`` — materialise declared repository leaves from their origins.

Implementation extension to the §24 command set. The spec has fork and parent-update
clone repository leaves *from the local parent checkout* (§12.4, §13.3), so a root — which
has no parent — needs a way to create its own checkouts from the configured ``origin`` at
the manifest ``base`` branch (§10.6). ``sync`` is that operation and is idempotent.
"""
from __future__ import annotations

from pathlib import Path

from . import gitutil
from .errors import WsError
from .node import Node


def sync(cwd: Path) -> list[str]:
    node = Node.discover(cwd)
    created: list[str] = []
    repos = node.repositories()
    for name, spec in repos.items():
        path = node.root / spec["path"]
        if (path / ".git").exists():
            continue
        if path.exists() and any(path.iterdir()):
            raise WsError(f"{name}: {path} exists and is not empty")
        path.parent.mkdir(parents=True, exist_ok=True)
        result = gitutil.run(
            ["git", "clone", "--origin", "origin", "--branch", spec["base"],
             spec["origin"], str(path)], check=False)
        if result.returncode:
            raise WsError(f"{name}: clone failed: {(result.stderr or '').strip()}")
        created.append(name)
    return created
