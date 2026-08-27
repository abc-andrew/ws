"""``ws publish`` / ``ws materialize`` — portability (spec §18).

Local forking, updating, and integration never require publication. Publication makes a
node (or subtree) portable: it verifies committed and remotely-represented state, emits a
portable descriptor with no absolute paths, and only pushes when explicitly asked.
Reconstruction verifies every referenced commit rather than substituting a default branch.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import gitutil, hooks, util
from .errors import WsError
from .node import Node

DESCRIPTOR_NAME = "portable.json"


def _has_absolute_paths(value) -> bool:
    if isinstance(value, str):
        return value.startswith("/") or value.startswith("~") or ":\\" in value
    if isinstance(value, dict):
        return any(_has_absolute_paths(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_absolute_paths(v) for v in value)
    return False


def _subtree(root: Node) -> list[Node]:
    nodes = [root]
    for child in root.children():
        nodes.extend(_subtree(child))
    return nodes


def _check_node(node: Node, subtree_root: Node, allow_bundle: bool) -> tuple[dict, list[str]]:
    issues: list[str] = []
    if node.has_outer_repo() and not gitutil.is_clean(node.root):
        issues.append(f"{node.name}: workspace-owned state is uncommitted")
    if _has_absolute_paths(node.meta().get("created_from")):
        issues.append(f"{node.name}: portable metadata contains absolute paths")

    workspace = {"origin": None, "commit": None}
    if node.has_outer_repo():
        workspace["origin"] = gitutil.git(["remote", "get-url", "origin"],
                                          node.root, check=False) or None
        workspace["commit"] = gitutil.head_sha(node.root)
        if not allow_bundle and not gitutil.has_remote_containing(node.root, workspace["commit"]):
            issues.append(f"{node.name}: workspace commit not represented by a remote")

    repositories: dict[str, dict] = {}
    for name, spec in node.repositories().items():
        path = node.root / spec["path"]
        if not (path / ".git").exists():
            issues.append(f"{node.name}/{name}: not materialized")
            continue
        if not gitutil.is_clean(path):
            issues.append(f"{node.name}/{name}: repository state is uncommitted")
        head = gitutil.head_sha(path)
        if not allow_bundle and not gitutil.has_remote_containing(path, head):
            issues.append(f"{node.name}/{name}: commit {head[:12]} not represented by a remote")
        repositories[name] = {"origin": spec["origin"], "commit": head}

    entry = {
        "id": node.id,
        "name": node.name,
        "owner_node_id": (node.meta().get("created_from") or {}).get("node_id"),
        "workspace": workspace,
        "repositories": repositories,
        "relative_path": util.rel_path(node.root, subtree_root.root),
    }
    return entry, issues


def publish(cwd: Path, tree: bool = False, push: bool = False,
            bundle: bool = False, no_hooks: bool = False) -> dict:
    root = Node.discover(cwd)
    nodes = _subtree(root) if tree else [root]

    hooks.run(root.root, "pre-publish",
              {"WS_OPERATION": "publish", "WS_CHILD_ROOT": str(root.root),
               "WS_CHILD_ID": root.id}, enabled=not no_hooks)

    entries: list[dict] = []
    all_issues: list[str] = []
    for node in nodes:
        entry, issues = _check_node(node, root, bundle)
        entries.append(entry)
        all_issues.extend(issues)

    if all_issues:
        listed = "\n  - ".join(all_issues)
        raise WsError(f"not portable:\n  - {listed}")

    descriptor = {"schema": util.SCHEMA, "root_id": root.id, "nodes": entries}

    if push:
        _push(nodes, descriptor)

    (root.ws_dir / DESCRIPTOR_NAME).write_text(json.dumps(descriptor, indent=2) + "\n")
    hooks.run(root.root, "post-publish",
              {"WS_OPERATION": "publish", "WS_CHILD_ROOT": str(root.root),
               "WS_CHILD_ID": root.id}, enabled=not no_hooks)
    return descriptor


def _push(nodes: list[Node], descriptor: dict) -> None:
    print("The following remotes and refs will be pushed:")
    plan: list[tuple[Path, str, str]] = []
    for node in nodes:
        if node.has_outer_repo() and gitutil.git(["remote", "get-url", "origin"], node.root, check=False):
            branch = gitutil.current_branch(node.root)
            plan.append((node.root, "origin", branch))
        for name, spec in node.repositories().items():
            path = node.root / spec["path"]
            if (path / ".git").exists():
                plan.append((path, "origin", gitutil.current_branch(path)))
    for repo, remote, ref in plan:
        print(f"  {repo}: {remote} {ref} -> {gitutil.git(['remote', 'get-url', remote], repo, check=False)}")
    for repo, remote, ref in plan:
        gitutil.run(["git", "push", remote, ref], repo, capture=False)


def materialize(cwd: Path, reference: str, into: Path | None = None) -> Path:
    ref_path = Path(reference)
    if ref_path.is_dir():
        ref_path = ref_path / ".workspace" / DESCRIPTOR_NAME
    descriptor = json.loads(ref_path.read_text())
    target_root = (into or cwd).resolve()

    entries = sorted(descriptor["nodes"], key=lambda e: e["relative_path"].count("/"))
    root_name = next(e["name"] for e in entries if e["relative_path"] == ".")
    root_dest = target_root / root_name
    for entry in entries:
        rel = entry["relative_path"]
        dest = root_dest if rel == "." else root_dest / rel
        dest.mkdir(parents=True, exist_ok=True)

        ws = entry.get("workspace") or {}
        if ws.get("origin") and ws.get("commit"):
            _clone_at(ws["origin"], ws["commit"], dest, entry["name"])
        for name, repo in entry.get("repositories", {}).items():
            _clone_at(repo["origin"], repo["commit"], dest / "repos" / name,
                      f"{entry['name']}/{name}")
    return root_dest


def _clone_at(origin: str, commit: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = gitutil.run(["git", "clone", origin, str(dest)], check=False)
    if result.returncode:
        raise WsError(f"{label}: cannot clone {origin} (unavailable)")
    if not gitutil.object_exists(dest, commit):
        gitutil.run(["git", "fetch", "origin", commit], dest, check=False)
    if not gitutil.object_exists(dest, commit):
        raise WsError(f"{label}: commit {commit[:12]} unavailable at {origin}")
    gitutil.git(["checkout", commit], dest)
