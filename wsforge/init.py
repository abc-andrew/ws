"""``ws init`` — create a root workspace node (spec §5.4, §25.1)."""
from __future__ import annotations

from pathlib import Path

from . import gitutil, manifest, scaffold, util
from .errors import WsError
from .node import Node


def init(cwd: Path, name: str | None = None, protected: bool = False,
         origin: str | None = None, branch: str = "main", no_git: bool = False) -> Node:
    root = cwd.resolve()
    if (root / ".workspace" / "node.json").exists():
        raise WsError(f"{root} is already a workspace node")
    display = name or root.name

    scaffold.ensure_layout(root)

    manifest_path = root / manifest.MANIFEST_NAME
    if not manifest_path.exists():
        manifest_path.write_text(manifest.emit({}))
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(scaffold.GITIGNORE)

    node = Node(root)
    node.write_meta({
        "schema": util.SCHEMA,
        "id": util.uuid7(),
        "name": display,
        "created_from": None,
        "policy": {"protected": protected, "fork_source": True,
                   "base_branch": branch},
    })
    node.write_local({
        "schema": util.SCHEMA,
        "owner": None,
        "inheritance_source": None,
        "baseline": None,
    })
    scaffold.reset_goal(root, display)

    if not no_git and not node.has_outer_repo():
        gitutil.run(["git", "init", "-b", branch, str(root)])
        gitutil.commit_all(root, f"ws: initialize workspace {display}")
        if origin:
            gitutil.git(["remote", "add", "origin", origin], root)
    return node
