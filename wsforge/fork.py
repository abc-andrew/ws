"""``ws fork NAME`` — the universal constructor (spec §12).

Forking is transactional from the user's perspective: the child is fully materialised in a
temporary sibling under ``children/`` and only atomically renamed into place after every
step and hook has succeeded. Any failure removes the temporary child and leaves the parent
untouched, reporting the failing phase.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import gitutil, hooks, locks, scaffold, util
from .errors import WsError
from .node import Node


def _canonical_origin(repo: Path) -> str | None:
    url = gitutil.git(["remote", "get-url", "origin"], repo, check=False)
    return url or None


def _check_preconditions(parent: Node) -> dict:
    """Verify §12.2 preconditions and return the fork baseline snapshot."""
    parent.validate_structure()
    workspace_commit = None
    if parent.has_outer_repo():
        if not gitutil.is_clean(parent.root):
            raise WsError("parent outer repository is dirty; commit or discard changes",
                          phase="preconditions")
        workspace_commit = gitutil.head_sha(parent.root)
    repo_heads: dict[str, str] = {}
    for name, path in parent.repo_paths().items():
        if not (path / ".git").exists():
            raise WsError(f"parent repository {name!r} is not materialized (run ws sync)",
                          phase="preconditions")
        if not gitutil.is_clean(path):
            raise WsError(f"parent repository {name!r} is dirty", phase="preconditions")
        repo_heads[name] = gitutil.head_sha(path)
    return {"workspace_commit": workspace_commit, "repositories": repo_heads}


def _materialize_outer(parent: Node, temp: Path, origin: str | None) -> None:
    if parent.has_outer_repo():
        gitutil.local_clone(parent.root, temp)
        canonical = origin or _canonical_origin(parent.root)
        gitutil.set_canonical_origin(temp, canonical)
    else:
        # No outer repo: copy workspace-owned files directly (spec §8.1).
        temp.mkdir(parents=True, exist_ok=True)
        for rel in ("workspace.yaml", ".gitignore"):
            src = parent.root / rel
            if src.exists():
                shutil.copy2(src, temp / rel)
        if (parent.root / "artifacts").is_dir():
            shutil.copytree(parent.root / "artifacts", temp / "artifacts",
                            dirs_exist_ok=True)
        if parent.ws_dir.is_dir():
            shutil.copytree(parent.ws_dir, temp / ".workspace",
                            ignore=shutil.ignore_patterns("local.json", "runtime"),
                            dirs_exist_ok=True)


def _materialize_repos(parent: Node, temp: Path, child_id: str, child_name: str,
                       baseline: dict) -> dict[str, str]:
    repo_provenance: dict[str, str] = {}
    # one branch per node (not per repo), matching the spec's ws/<id>-<node> examples
    branch = f"ws/{util.id_prefix(child_id)}-{child_name}"
    for name, spec in parent.repositories().items():
        parent_repo = parent.root / spec["path"]
        dest = temp / spec["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        gitutil.local_clone(parent_repo, dest)
        gitutil.set_canonical_origin(dest, spec["origin"])
        parent_head = baseline["repositories"][name]
        gitutil.git(["checkout", "-b", branch, parent_head], dest)
        repo_provenance[name] = parent_head
    return repo_provenance


def fork(cwd: Path, name: str, from_path: Path | None = None,
         origin: str | None = None, protected: bool = False,
         no_hooks: bool = False, keep_temp: bool = False,
         break_lock: bool = False) -> Node:
    util.require_name(name, "workspace name")
    parent = Node.at(from_path) if from_path else Node.discover(cwd)

    dest = parent.children_dir / name
    if dest.exists():
        raise WsError(f"child {name!r} already exists", phase="validate")

    with locks.hold(parent, f"fork:{name}", break_lock):
        baseline = _check_preconditions(parent)
        child_id = util.uuid7()

        env = {
            "WS_OPERATION": "fork",
            "WS_PARENT_ROOT": str(parent.root),
            "WS_PARENT_ID": parent.id,
            "WS_CHILD_ID": child_id,
            "WS_FORK_BASELINE": baseline["workspace_commit"] or "",
        }
        hooks.run(parent.root, "pre-fork", env, enabled=not no_hooks)

        parent.children_dir.mkdir(exist_ok=True)
        temp = parent.children_dir / f".wsfork-{util.id_prefix(child_id)}"
        if temp.exists():
            shutil.rmtree(temp)
        try:
            _materialize_outer(parent, temp, origin)
            repo_provenance = _materialize_repos(parent, temp, child_id, name, baseline)

            child = Node(temp)
            scaffold.ensure_layout(temp)
            meta = child.meta() if child.node_json.is_file() else {}
            policy = dict(meta.get("policy", {}))
            policy["protected"] = protected or policy.get("protected", False)
            policy.setdefault("fork_source", True)
            child.write_meta({
                "schema": util.SCHEMA,
                "id": child_id,
                "name": name,
                "created_from": {
                    "node_id": parent.id,
                    "workspace_commit": baseline["workspace_commit"],
                    "repositories": repo_provenance,
                },
                "policy": policy,
            })
            rel_to_parent = util.rel_path(parent.root, temp)
            link = {"node_id": parent.id, "relative_path": rel_to_parent}
            child.write_local({
                "schema": util.SCHEMA,
                "owner": link,
                "inheritance_source": link,
                "baseline": {
                    "workspace_commit": baseline["workspace_commit"],
                    "repositories": dict(repo_provenance),
                },
            })
            scaffold.reset_goal(temp, name)

            if gitutil.is_git_repo(temp):
                gitutil.commit_all(temp, f"ws: initialize node {name}")

            env["WS_CHILD_ROOT"] = str(temp)
            hooks.run(temp, "post-fork", env, enabled=not no_hooks)

            child.validate_structure()
        except BaseException as exc:
            if not keep_temp and temp.exists():
                shutil.rmtree(temp, ignore_errors=True)
            if isinstance(exc, WsError):
                raise
            raise WsError(f"fork failed: {exc}", phase="materialize")

        # local.json records a path relative to the temp dir; rewrite for final dest.
        temp.rename(dest)
        final = Node(dest)
        rel_final = util.rel_path(parent.root, dest)
        local = final.local()
        local["owner"]["relative_path"] = rel_final
        local["inheritance_source"]["relative_path"] = rel_final
        final.write_local(local)
        return final
