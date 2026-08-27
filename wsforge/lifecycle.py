"""``ws remove`` / ``ws detach`` / ``ws reparent`` — node lifecycle (spec §15)."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import gitutil, hooks, locks, util
from .errors import WsError
from .node import Node


def inspect_subtree(node: Node) -> list[str]:
    """Return human-readable reasons the subtree rooted at ``node`` is unsafe to discard."""
    issues: list[str] = []

    def visit(n: Node) -> None:
        rel = n.root.name
        if n.has_outer_repo() and not gitutil.is_clean(n.root):
            issues.append(f"{rel}: uncommitted workspace-owned changes")
        for name, path in n.repo_paths().items():
            if not (path / ".git").exists():
                continue
            if not gitutil.is_clean(path):
                issues.append(f"{rel}/{name}: uncommitted repository changes")
            head = gitutil.head_sha(path)
            if not gitutil.has_remote_containing(path, head):
                issues.append(f"{rel}/{name}: commit {head[:12]} not on any remote")
        if (n.ws_dir / "portable.json").exists():
            issues.append(f"{rel}: has publication metadata")
        if (n.runtime_dir / locks.LOCK_NAME).exists():
            issues.append(f"{rel}: has an active operation lock")
        for tmp in n.children_dir.glob(".wsfork-*"):
            issues.append(f"{rel}: incomplete fork transaction {tmp.name}")
        for grandchild in n.children():
            visit(grandchild)

    visit(node)
    return issues


def remove(cwd: Path, child_ref: str, recursive: bool = False, force: bool = False,
           no_hooks: bool = False, break_lock: bool = False) -> list[str]:
    parent = Node.discover(cwd)
    child = parent.find_child(child_ref)

    if child.children() and not recursive:
        raise WsError(f"{child.name} has descendants; pass --recursive to remove them")

    issues = inspect_subtree(child)
    if issues and not force:
        listed = "\n  - ".join(issues)
        raise WsError(f"refusing to remove {child.name}; unsafe state:\n  - {listed}\n"
                      "resolve these or pass --force to discard them")

    with locks.hold(parent, f"remove:{child.name}", break_lock):
        env = {"WS_OPERATION": "remove", "WS_PARENT_ROOT": str(parent.root),
               "WS_CHILD_ROOT": str(child.root), "WS_PARENT_ID": parent.id,
               "WS_CHILD_ID": child.id}
        hooks.run(child.root, "pre-remove", env, enabled=not no_hooks)
        shutil.rmtree(child.root)
    return issues


def detach(cwd: Path, child_ref: str, to: Path, copy: bool = False,
           clear_source: bool = False, no_hooks: bool = False,
           break_lock: bool = False) -> Node:
    parent = Node.discover(cwd)
    child = parent.find_child(child_ref)
    child.validate_structure()

    dest = to.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise WsError(f"destination {dest} exists and is not empty")

    issues = inspect_subtree(child)
    if issues:
        listed = "\n  - ".join(issues)
        raise WsError(f"refusing to detach {child.name}; validate subtree first:\n  - {listed}")

    with locks.hold(parent, f"detach:{child.name}", break_lock):
        env = {"WS_OPERATION": "detach", "WS_PARENT_ROOT": str(parent.root),
               "WS_CHILD_ROOT": str(child.root), "WS_PARENT_ID": parent.id,
               "WS_CHILD_ID": child.id}
        hooks.run(child.root, "pre-detach", env, enabled=not no_hooks)

        dest.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(child.root, dest, symlinks=True)
        else:
            shutil.move(str(child.root), str(dest))

        detached = Node(dest)
        local = detached.local()
        local["owner"] = None  # a detached node has no current owner (§5.4)
        if clear_source:
            local["inheritance_source"] = None
        elif local.get("inheritance_source"):
            # keep provenance: re-point the source at the still-existing former parent
            local["inheritance_source"]["relative_path"] = util.rel_path(parent.root, dest)
        detached.write_local(local)

        # verify every Git object store remains valid without the former parent (§15.3.6)
        stores = [detached.root] if detached.has_outer_repo() else []
        stores += [p for p in detached.repo_paths().values() if (p / ".git").exists()]
        for store in stores:
            if gitutil.run(["git", "fsck", "--no-dangling"], store, check=False).returncode:
                raise WsError(f"object store invalid after detach: {store}", phase="verify")

        env["WS_CHILD_ROOT"] = str(dest)
        hooks.run(dest, "post-detach", env, enabled=not no_hooks)
    return detached


def reparent(cwd: Path, child_ref: str, to: Path, confirm_source_change: bool = False,
             break_lock: bool = False) -> Node:
    old_parent = Node.discover(cwd)
    child = old_parent.find_child(child_ref)
    new_parent = Node.at(to)
    child.validate_structure()
    new_parent.validate_structure()

    dest = new_parent.children_dir / child.name
    if dest.exists():
        raise WsError(f"{new_parent.name} already has a child named {child.name!r}")

    source = child.local().get("inheritance_source")
    if source and source.get("node_id") != new_parent.id and not confirm_source_change:
        raise WsError("inheritance source differs from the new owner; "
                      "pass --confirm-source-change to proceed")

    with locks.lock_all([old_parent, new_parent], f"reparent:{child.name}", break_lock):
        new_parent.children_dir.mkdir(exist_ok=True)
        shutil.move(str(child.root), str(dest))
        moved = Node(dest)
        local = moved.local()
        local["owner"] = {"node_id": new_parent.id,
                          "relative_path": util.rel_path(new_parent.root, dest)}
        moved.write_local(local)
    return moved
