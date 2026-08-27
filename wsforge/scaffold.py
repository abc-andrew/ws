"""Shared node scaffolding used by ``init`` and ``fork``."""
from __future__ import annotations

from pathlib import Path

# Outer repository ignores (spec §11): repository contents, local children, and
# machine-local metadata are never tracked by the node's outer Git repository.
GITIGNORE = """\
/repos/*
!/repos/.gitkeep

/children/*
!/children/.gitkeep

/.workspace/local.json
/.workspace/runtime/
/.workspace/portable.json
"""

GOAL_TEMPLATE = """\
# Goal: {name}

_Describe the goal of this workspace._
"""


def ensure_layout(root: Path) -> None:
    """Create the standard node directory skeleton with keep files."""
    for sub in ("repos", "children", "artifacts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
        keep = root / sub / ".gitkeep"
        if not keep.exists():
            keep.write_text("")
    (root / ".workspace" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / ".workspace" / "runtime").mkdir(parents=True, exist_ok=True)


def reset_goal(root: Path, name: str) -> None:
    """Artifact-reset policy (spec §12.6): (re)create artifacts/goal.md for the scope."""
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / "goal.md").write_text(GOAL_TEMPLATE.format(name=name))
