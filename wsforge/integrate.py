"""``ws integrate CHILD`` — explicit upward integration (spec §14).

A child never mutates its parent automatically. Integration validates both nodes, refuses
dirty or ambiguous state, and applies the child's changes into the parent with ordinary Git
merge primitives, leaving any conflicts visible. It never removes the child.
"""
from __future__ import annotations

from pathlib import Path

from . import gitutil, hooks, locks
from .errors import WsError
from .node import Node


def _merge_into(parent_repo: Path, source_repo: Path, ref: str, label: str) -> str:
    gitutil.fetch_from_path(parent_repo, source_repo, ref)
    fetched = gitutil.git(["rev-parse", "FETCH_HEAD"], parent_repo)
    if gitutil.git_ok(["merge-base", "--is-ancestor", fetched, "HEAD"], parent_repo):
        return "no changes"
    result = gitutil.run(["git", "merge", "--no-edit", "FETCH_HEAD"], parent_repo,
                         check=False)
    if result.returncode:
        raise WsError(f"{label}: merge left conflicts; resolve them in the parent",
                      phase="apply")
    return "merged"


def integrate(cwd: Path, child_ref: str, repo: str | None = None,
              no_hooks: bool = False, break_lock: bool = False) -> dict:
    parent = Node.discover(cwd)
    child = parent.find_child(child_ref)
    parent.validate_structure()
    child.validate_structure()

    env = {"WS_OPERATION": "integrate", "WS_PARENT_ROOT": str(parent.root),
           "WS_CHILD_ROOT": str(child.root), "WS_PARENT_ID": parent.id,
           "WS_CHILD_ID": child.id}

    with locks.lock_all([parent, child], f"integrate:{child.name}", break_lock):
        if parent.has_outer_repo() and not gitutil.is_clean(parent.root):
            raise WsError("parent outer repository is dirty", phase="preconditions")
        if child.has_outer_repo() and not gitutil.is_clean(child.root):
            raise WsError("child outer repository is dirty", phase="preconditions")

        hooks.run(parent.root, "pre-integrate", env, enabled=not no_hooks)

        summary: dict[str, str] = {}
        child_repos = child.repositories()
        selected = [repo] if repo else list(child_repos)
        if repo and repo not in child_repos:
            raise WsError(f"child has no repository {repo!r}")

        if repo is None and parent.has_outer_repo() and child.has_outer_repo():
            saved = parent.meta()
            summary["(workspace)"] = _merge_into(
                parent.root, child.root, "HEAD", "workspace-owned files")
            # a merged outer commit carries the child's node.json; keep the parent's
            # own identity (spec: created_from is immutable, node id is stable).
            if parent.reassert_identity(saved["id"], saved["name"],
                                        saved.get("created_from")):
                gitutil.commit_all(parent.root, "ws: preserve node identity")

        parent_repos = parent.repositories()
        for name in selected:
            if name not in parent_repos:
                summary[name] = "not in parent (skipped)"
                continue
            parent_repo = parent.root / parent_repos[name]["path"]
            child_repo = child.root / child_repos[name]["path"]
            if not (parent_repo / ".git").exists() or not (child_repo / ".git").exists():
                summary[name] = "not materialized (skipped)"
                continue
            if not gitutil.is_clean(parent_repo):
                raise WsError(f"parent repository {name!r} is dirty", phase="preconditions")
            if not gitutil.is_clean(child_repo):
                raise WsError(f"child repository {name!r} is dirty", phase="preconditions")
            child_branch = gitutil.current_branch(child_repo)
            summary[name] = _merge_into(parent_repo, child_repo, child_branch, name)

        hooks.run(parent.root, "post-integrate", env, enabled=not no_hooks)
    return summary
