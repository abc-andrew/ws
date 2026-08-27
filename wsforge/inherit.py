"""``ws merge-parent`` / ``ws rebase-parent`` — explicit downward updates (spec §13).

Inheritance is snapshot-based: a child only sees later parent changes when it explicitly
runs one of these. Workspace-owned files reconcile through the outer Git repository (a real
three-way merge); repository leaves reconcile per repo by fetching the parent's current
state directly from its local checkout. The advancing baseline moves only on full success.
"""
from __future__ import annotations

from pathlib import Path

from . import gitutil, hooks, locks, util
from .errors import WsError
from .node import Node


def _require_clean(node: Node) -> None:
    if node.has_outer_repo() and not gitutil.is_clean(node.root):
        raise WsError("workspace outer repository is dirty; commit or discard first",
                      phase="preconditions")
    for name, path in node.repo_paths().items():
        if (path / ".git").exists() and not gitutil.is_clean(path):
            raise WsError(f"repository {name!r} is dirty", phase="preconditions")


def _integrate_ref(repo: Path, mode: str, onto: str, base: str | None) -> None:
    """Merge or rebase the working branch of ``repo`` onto ``onto``."""
    if mode == "merge":
        result = gitutil.run(["git", "merge", "--no-edit", onto], repo, check=False)
    else:  # rebase child-only commits (base..HEAD) onto the parent's new state
        args = ["git", "rebase", "--onto", onto, base or onto]
        result = gitutil.run(args, repo, check=False)
    if result.returncode:
        raise WsError(
            f"{mode} left conflicts in {repo.name}; resolve them, baseline not advanced",
            phase="reconcile")


def _update(cwd: Path, mode: str, no_hooks: bool, break_lock: bool) -> dict:
    node = Node.discover(cwd)
    source_path = node.inheritance_source_path()
    if source_path is None:
        raise WsError("no inheritance source recorded; nothing to update from",
                      phase="parent-discovery")
    source = Node.at(source_path)
    baseline = node.baseline() or {"workspace_commit": None, "repositories": {}}

    hook_prefix = "merge-parent" if mode == "merge" else "rebase-parent"
    env = {"WS_OPERATION": hook_prefix, "WS_CHILD_ROOT": str(node.root),
           "WS_PARENT_ROOT": str(source.root), "WS_CHILD_ID": node.id,
           "WS_PARENT_ID": source.id}

    with locks.lock_all([source, node], hook_prefix, break_lock):
        _require_clean(node)
        hooks.run(node.root, f"pre-{hook_prefix}", env, enabled=not no_hooks)

        # 1. Workspace-owned files via the outer repository (spec §13.2, §13.4).
        new_workspace_commit = baseline.get("workspace_commit")
        if node.has_outer_repo() and source.has_outer_repo():
            saved = node.meta()
            gitutil.fetch_from_path(node.root, source.root, "HEAD")
            _integrate_ref(node.root, mode, "FETCH_HEAD",
                           baseline.get("workspace_commit"))
            # defensively keep our own identity across the outer merge/rebase
            if node.reassert_identity(saved["id"], saved["name"],
                                      saved.get("created_from")):
                gitutil.commit_all(node.root, "ws: preserve node identity")
            new_workspace_commit = gitutil.head_sha(source.root)

        # 2. Repository leaves (spec §13.3), after the manifest merge.
        summary: dict[str, str] = {}
        new_repo_baseline: dict[str, str] = dict(baseline.get("repositories", {}))
        child_repos = node.repositories()
        source_repos = source.repositories()
        for name, spec in child_repos.items():
            child_repo = node.root / spec["path"]
            source_repo = source.root / spec["path"]
            if name not in source_repos:
                summary[name] = "child-only (kept)"
                continue
            if not (source_repo / ".git").exists():
                summary[name] = "source not materialized (skipped)"
                continue
            parent_head = gitutil.head_sha(source_repo)
            if not (child_repo / ".git").exists():
                # parent-added repository: materialize from the local parent (§13.4).
                gitutil.local_clone(source_repo, child_repo)
                gitutil.set_canonical_origin(child_repo, spec["origin"])
                branch = f"ws/{util.id_prefix(node.id)}-{node.name}"
                gitutil.git(["checkout", "-b", branch, parent_head], child_repo)
                summary[name] = "materialized from parent"
            else:
                gitutil.fetch_from_path(child_repo, source_repo, parent_head)
                _integrate_ref(child_repo, mode, "FETCH_HEAD",
                               baseline.get("repositories", {}).get(name))
                summary[name] = mode + "d"
            new_repo_baseline[name] = parent_head

        for name in baseline.get("repositories", {}):
            if name in source_repos and name not in child_repos:
                summary[name] = "removed by parent (left in place; remove manually)"

        node.set_baseline(new_workspace_commit, new_repo_baseline)
        hooks.run(node.root, f"post-{hook_prefix}", env, enabled=not no_hooks)
    return summary


def merge_parent(cwd: Path, no_hooks: bool = False, break_lock: bool = False) -> dict:
    return _update(cwd, "merge", no_hooks, break_lock)


def rebase_parent(cwd: Path, no_hooks: bool = False, break_lock: bool = False) -> dict:
    return _update(cwd, "rebase", no_hooks, break_lock)
