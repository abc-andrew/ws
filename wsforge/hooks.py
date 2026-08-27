"""Inherited lifecycle hooks (spec §16).

Hooks are workspace-owned executables under ``.workspace/hooks/``. They run local code
and are trusted as code from the source workspace. ``--no-hooks`` skips these optional
hooks but never core identity, Git safety, baseline, or lifecycle invariants — those live
in the operations themselves, not here.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import gitutil
from .errors import WsError

# Recognised hook names (spec §16); unknown files under hooks/ are ignored.
KNOWN_HOOKS = {
    "pre-fork", "post-fork",
    "pre-merge-parent", "post-merge-parent",
    "pre-rebase-parent", "post-rebase-parent",
    "pre-integrate", "post-integrate",
    "pre-remove", "pre-detach", "post-detach",
    "pre-publish", "post-publish",
}


def hook_path(root: Path, name: str) -> Path:
    return root / ".workspace" / "hooks" / name


def exists(root: Path, name: str) -> bool:
    path = hook_path(root, name)
    return path.is_file()


def run(root: Path, name: str, env: dict[str, str], enabled: bool = True) -> None:
    """Run a hook from ``root`` if present and enabled.

    A non-zero exit stops the operation (raising :class:`WsError`). A present but
    non-executable hook is reported rather than silently skipped.
    """
    if not enabled:
        return
    path = hook_path(root, name)
    if not path.is_file():
        return
    if not os.access(path, os.X_OK):
        raise WsError(f"hook {name} is not executable: {path}", phase=f"hook:{name}")
    full_env = {**os.environ, **{k: v for k, v in env.items() if v is not None}}
    result = gitutil.run([str(path)], cwd=root, check=False, capture=False, env=full_env)
    if result.returncode:
        raise WsError(f"hook {name} failed with exit {result.returncode}",
                      phase=f"hook:{name}")
