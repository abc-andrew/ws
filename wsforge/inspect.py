"""Read-only inspection: root, parent, context, tree, status, doctor (spec §17, §21).

Because ordinary search tools respect ``.gitignore`` (which hides ``repos/`` and
``children/``), these commands deliberately traverse the known workspace boundaries.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import gitutil, manifest, util
from .errors import WsError
from .node import Node


# --- primitive queries ----------------------------------------------------

def _repo_status(node: Node) -> list[dict]:
    rows = []
    for name, spec in node.repositories().items():
        path = node.root / spec["path"]
        if not (path / ".git").exists():
            rows.append({"name": name, "materialized": False})
            continue
        rows.append({
            "name": name,
            "materialized": True,
            "branch": gitutil.current_branch(path),
            "head": gitutil.head_sha(path)[:12],
            "clean": gitutil.is_clean(path),
        })
    return rows


def _link_info(node: Node, key: str) -> dict | None:
    link = node.local().get(key)
    if not link:
        return None
    info = {"node_id": link["node_id"], "relative_path": link["relative_path"]}
    try:
        target = node._linked_path(key)
        info["available"] = target is not None
        info["path"] = str(target) if target else None
    except WsError:
        info["available"] = False
        info["path"] = None
    return info


def _pending_updates(node: Node) -> list[str]:
    """Repositories whose local parent has advanced past the child's baseline."""
    try:
        source_path = node.inheritance_source_path()
    except WsError:
        return []
    if source_path is None:
        return []
    source = Node.at(source_path)
    baseline = (node.baseline() or {}).get("repositories", {})
    pending = []
    for name, spec in source.repositories().items():
        path = source.root / spec["path"]
        if (path / ".git").exists() and baseline.get(name) != gitutil.head_sha(path):
            pending.append(name)
    return pending


# --- commands -------------------------------------------------------------

def root_info(cwd: Path) -> dict:
    node = Node.discover(cwd)
    return {"root": str(node.root), "id": node.id, "name": node.name}


def parent_info(cwd: Path) -> dict:
    node = Node.discover(cwd)
    return {"owner": _link_info(node, "owner"),
            "inheritance_source": _link_info(node, "inheritance_source")}


def context(cwd: Path) -> dict:
    node = Node.discover(cwd)
    goal = node.artifacts_dir / "goal.md"
    return {
        "root": str(node.root),
        "id": node.id,
        "name": node.name,
        "policy": node.policy(),
        "owner": _link_info(node, "owner"),
        "inheritance_source": _link_info(node, "inheritance_source"),
        "outer_dirty": node.has_outer_repo() and not gitutil.is_clean(node.root),
        "repositories": _repo_status(node),
        "children": [c.name for c in node.children()],
        "pending_parent_updates": _pending_updates(node),
        "goal": goal.read_text() if goal.exists() else None,
    }


def tree_data(cwd: Path) -> dict:
    node = Node.discover(cwd)

    def build(n: Node) -> dict:
        return {
            "name": n.name,
            "id": n.id,
            "repositories": _repo_status(n),
            "children": [build(c) for c in n.children()],
        }

    return build(node)


def render_tree(data: dict, prefix: str = "", is_root: bool = True) -> list[str]:
    lines = [data["name"]] if is_root else []
    repos = data["repositories"]
    children = data["children"]
    entries: list[tuple[str, object]] = [("repo", r) for r in repos]
    entries += [("child", c) for c in children]
    for index, (kind, item) in enumerate(entries):
        last = index == len(entries) - 1
        branch = "└── " if last else "├── "
        extend = "    " if last else "│   "
        if kind == "repo":
            if item.get("materialized"):
                lines.append(f"{prefix}{branch}{item['name']}  {item['branch']}  "
                             f"{item['head']}  {'clean' if item['clean'] else 'dirty'}")
            else:
                lines.append(f"{prefix}{branch}{item['name']}  (not materialized)")
        else:
            lines.append(f"{prefix}{branch}{item['name']}")
            lines.extend(render_tree(item, prefix + extend, is_root=False))
    return lines


def status_data(cwd: Path, recursive: bool = False) -> dict:
    node = Node.discover(cwd)

    def build(n: Node) -> dict:
        entry = {
            "name": n.name,
            "outer": {
                "branch": gitutil.current_branch(n.root),
                "head": gitutil.head_sha(n.root)[:12],
                "clean": gitutil.is_clean(n.root),
            } if n.has_outer_repo() else None,
            "repositories": _repo_status(n),
        }
        if recursive:
            entry["children"] = [build(c) for c in n.children()]
        return entry

    return build(node)


def render_status(data: dict, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines = [f"{pad}WORKSPACE  {data['name']}"]
    if data.get("outer"):
        o = data["outer"]
        lines.append(f"{pad}  outer   {o['branch']}  {o['head']}  "
                     f"{'clean' if o['clean'] else 'dirty'}")
    for r in data["repositories"]:
        if r.get("materialized"):
            lines.append(f"{pad}  {r['name']:8} {r['branch']}  {r['head']}  "
                         f"{'clean' if r['clean'] else 'dirty'}")
        else:
            lines.append(f"{pad}  {r['name']:8} (not materialized)")
    for child in data.get("children", []):
        lines.extend(render_status(child, indent + 1))
    return lines


def doctor(cwd: Path) -> dict:
    node = Node.discover(cwd)
    checks: list[dict] = []

    def check(ok: bool, name: str, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    meta = node.meta()
    check(meta.get("schema") == util.SCHEMA and bool(meta.get("id")), "node metadata schema")

    # unique ids within the visible subtree (§21.2)
    seen: dict[str, str] = {}
    dup = False
    stack = [node]
    while stack:
        n = stack.pop()
        nid = n.id
        if nid in seen:
            dup = True
        seen[nid] = n.root.name
        stack.extend(n.children())
    check(not dup, "node id uniqueness")

    # parent containment + expected owner id (§21.3)
    owner = node.local().get("owner")
    if owner:
        try:
            ok_owner = node.owner_path() is not None
        except WsError:
            ok_owner = False
        check(ok_owner, "owner path containment and id")

    # symlinked child roots (§21.4) — inspect raw entries, since Node resolves paths
    symlinks = []
    if node.children_dir.is_dir():
        symlinks = [e.name for e in node.children_dir.iterdir() if e.is_symlink()]
    check(not symlinks, "no symlinked child roots", ", ".join(symlinks))

    # manifest schema + repo path boundaries (§21.5)
    try:
        repos = manifest.parse(node.manifest_path)
        check(True, "manifest schema and boundaries")
    except WsError as exc:
        repos = {}
        check(False, "manifest schema and boundaries", str(exc))

    # canonical origins + git health + baseline availability (§21.6, §21.7, §21.10)
    baseline = (node.baseline() or {}).get("repositories", {})
    for name, spec in repos.items():
        path = node.root / spec["path"]
        if not (path / ".git").exists():
            check(False, f"repository materialized: {name}")
            continue
        origin = gitutil.git(["remote", "get-url", "origin"], path, check=False)
        check(origin == spec["origin"], f"canonical origin: {name}", origin)
        healthy = gitutil.run(["git", "fsck", "--no-dangling"], path, check=False).returncode == 0
        check(healthy, f"git health: {name}")
        if name in baseline:
            check(gitutil.object_exists(path, baseline[name]),
                  f"baseline object available: {name}")

    # ignore boundaries (§21.8)
    if node.has_outer_repo():
        ignored = gitutil.git_ok(["check-ignore", "-q", "repos/probe"], node.root)
        check(ignored, "outer repo ignores repos/*")
        ignored_children = gitutil.git_ok(["check-ignore", "-q", "children/probe"], node.root)
        check(ignored_children, "outer repo ignores children/*")

    # hook executability (§21.9)
    for hook_file in sorted(node.hooks_dir.glob("*")):
        if hook_file.is_file():
            check(os.access(hook_file, os.X_OK), f"hook executable: {hook_file.name}")

    # stale locks / incomplete transactions (§21.11)
    locks_present = (node.runtime_dir / "lock.json").exists()
    check(not locks_present, "no active operation lock")
    incomplete = list(node.children_dir.glob(".wsfork-*"))
    check(not incomplete, "no incomplete fork transactions",
          ", ".join(p.name for p in incomplete))

    ok = all(c["ok"] for c in checks)
    return {"root": str(node.root), "ok": ok, "checks": checks}
