"""Command-line entry point and argument dispatch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fork as fork_mod
from . import init as init_mod
from . import inherit, inspect, integrate, lifecycle, publish, sync
from .errors import WsError


def _emit(data, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(text)


def _cmd_init(args, cwd: Path) -> None:
    node = init_mod.init(cwd, name=args.name, protected=args.protected,
                         origin=args.origin, branch=args.branch)
    _emit({"root": str(node.root), "id": node.id}, args.json,
          f"initialized workspace {node.name} at {node.root}")


def _cmd_fork(args, cwd: Path) -> None:
    node = fork_mod.fork(cwd, args.name,
                         from_path=Path(args.from_path) if args.from_path else None,
                         origin=args.origin, protected=args.protected,
                         no_hooks=args.no_hooks, keep_temp=args.keep_temp,
                         break_lock=args.break_lock)
    _emit({"root": str(node.root), "id": node.id, "name": node.name}, args.json,
          f"forked {node.name} at {node.root}")


def _cmd_sync(args, cwd: Path) -> None:
    created = sync.sync(cwd)
    _emit({"materialized": created}, args.json,
          "materialized: " + (", ".join(created) if created else "(nothing to do)"))


def _cmd_root(args, cwd: Path) -> None:
    data = inspect.root_info(cwd)
    _emit(data, args.json, f"{data['root']}  {data['id']}")


def _cmd_parent(args, cwd: Path) -> None:
    data = inspect.parent_info(cwd)
    lines = []
    for key in ("owner", "inheritance_source"):
        info = data[key]
        if info:
            lines.append(f"{key}: {info.get('path') or info['node_id']} "
                         f"({'available' if info.get('available') else 'unavailable'})")
        else:
            lines.append(f"{key}: (none)")
    _emit(data, args.json, "\n".join(lines))


def _cmd_context(args, cwd: Path) -> None:
    data = inspect.context(cwd)
    lines = [
        f"root:   {data['root']}",
        f"id:     {data['id']}  ({data['name']})",
        f"owner:  {(data['owner'] or {}).get('path') or '(none)'}",
        f"source: {(data['inheritance_source'] or {}).get('path') or '(none)'}",
        f"dirty:  {data['outer_dirty']}",
        "repositories: " + (", ".join(
            r["name"] + ("" if r.get("materialized") else "(missing)")
            for r in data["repositories"]) or "(none)"),
        "children: " + (", ".join(data["children"]) or "(none)"),
        "pending parent updates: " + (", ".join(data["pending_parent_updates"]) or "(none)"),
    ]
    _emit(data, args.json, "\n".join(lines))


def _cmd_tree(args, cwd: Path) -> None:
    data = inspect.tree_data(cwd)
    _emit(data, args.json, "\n".join(inspect.render_tree(data)))


def _cmd_status(args, cwd: Path) -> None:
    data = inspect.status_data(cwd, recursive=args.tree)
    _emit(data, args.json, "\n".join(inspect.render_status(data)))


def _cmd_doctor(args, cwd: Path) -> None:
    data = inspect.doctor(cwd)
    lines = [("OK   " if c["ok"] else "FAIL ") + c["name"] +
             (f"  ({c['detail']})" if c["detail"] and not c["ok"] else "")
             for c in data["checks"]]
    lines.append("doctor: healthy" if data["ok"] else "doctor: problems found")
    _emit(data, args.json, "\n".join(lines))
    if not data["ok"]:
        raise SystemExit(1)


def _cmd_merge_parent(args, cwd: Path) -> None:
    summary = inherit.merge_parent(cwd, no_hooks=args.no_hooks, break_lock=args.break_lock)
    _emit(summary, args.json,
          "\n".join(f"{k}: {v}" for k, v in summary.items()) or "up to date")


def _cmd_rebase_parent(args, cwd: Path) -> None:
    summary = inherit.rebase_parent(cwd, no_hooks=args.no_hooks, break_lock=args.break_lock)
    _emit(summary, args.json,
          "\n".join(f"{k}: {v}" for k, v in summary.items()) or "up to date")


def _cmd_integrate(args, cwd: Path) -> None:
    summary = integrate.integrate(cwd, args.child, repo=args.repo,
                                  no_hooks=args.no_hooks, break_lock=args.break_lock)
    _emit(summary, args.json, "\n".join(f"{k}: {v}" for k, v in summary.items()))


def _cmd_remove(args, cwd: Path) -> None:
    issues = lifecycle.remove(cwd, args.child, recursive=args.recursive,
                              force=args.force, no_hooks=args.no_hooks,
                              break_lock=args.break_lock)
    note = "removed" + (f" (discarded: {len(issues)} item(s))" if issues else "")
    _emit({"removed": args.child, "discarded": issues}, args.json, note)


def _cmd_detach(args, cwd: Path) -> None:
    node = lifecycle.detach(cwd, args.child, Path(args.to), copy=args.copy,
                            clear_source=args.clear_source, no_hooks=args.no_hooks,
                            break_lock=args.break_lock)
    _emit({"detached": str(node.root), "id": node.id}, args.json,
          f"detached to {node.root}")


def _cmd_reparent(args, cwd: Path) -> None:
    node = lifecycle.reparent(cwd, args.child, Path(args.to),
                              confirm_source_change=args.confirm_source_change,
                              break_lock=args.break_lock)
    _emit({"root": str(node.root), "id": node.id}, args.json,
          f"reparented to {node.root}")


def _cmd_publish(args, cwd: Path) -> None:
    descriptor = publish.publish(cwd, tree=args.tree, push=args.push,
                                 bundle=args.bundle, no_hooks=args.no_hooks)
    _emit(descriptor, args.json,
          f"published {len(descriptor['nodes'])} node(s); descriptor written")


def _cmd_materialize(args, cwd: Path) -> None:
    dest = publish.materialize(cwd, args.reference,
                               into=Path(args.into) if args.into else None)
    _emit({"root": str(dest)}, args.json, f"materialized at {dest}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ws", description="recursive workspace forking")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_json(p):
        p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("init", help="create a root workspace node")
    p.add_argument("name", nargs="?")
    p.add_argument("--protected", action="store_true")
    p.add_argument("--origin")
    p.add_argument("--branch", default="main")
    add_json(p); p.set_defaults(func=_cmd_init)

    p = sub.add_parser("fork", help="fork the nearest (or --from) workspace")
    p.add_argument("name")
    p.add_argument("--from", dest="from_path")
    p.add_argument("--origin")
    p.add_argument("--protected", action="store_true")
    p.add_argument("--no-hooks", action="store_true")
    p.add_argument("--keep-temp", action="store_true", help="retain temp dir on failure")
    p.add_argument("--break-lock", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_fork)

    p = sub.add_parser("sync", help="materialize declared repositories from origin")
    add_json(p); p.set_defaults(func=_cmd_sync)

    for name, func in (("root", _cmd_root), ("parent", _cmd_parent),
                       ("context", _cmd_context), ("tree", _cmd_tree)):
        p = sub.add_parser(name)
        add_json(p); p.set_defaults(func=func)

    p = sub.add_parser("status", help="status of the nearest workspace")
    p.add_argument("--tree", action="store_true", help="recurse into descendants")
    add_json(p); p.set_defaults(func=_cmd_status)

    p = sub.add_parser("doctor", help="validate the workspace")
    add_json(p); p.set_defaults(func=_cmd_doctor)

    for name, func in (("merge-parent", _cmd_merge_parent),
                       ("rebase-parent", _cmd_rebase_parent)):
        p = sub.add_parser(name)
        p.add_argument("--no-hooks", action="store_true")
        p.add_argument("--break-lock", action="store_true")
        add_json(p); p.set_defaults(func=func)

    p = sub.add_parser("integrate", help="integrate a child's changes upward")
    p.add_argument("child")
    p.add_argument("--repo")
    p.add_argument("--no-hooks", action="store_true")
    p.add_argument("--break-lock", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_integrate)

    p = sub.add_parser("remove", help="remove a child subtree")
    p.add_argument("child")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-hooks", action="store_true")
    p.add_argument("--break-lock", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_remove)

    p = sub.add_parser("detach", help="detach a child to an independent location")
    p.add_argument("child")
    p.add_argument("--to", required=True)
    p.add_argument("--copy", action="store_true")
    p.add_argument("--clear-source", action="store_true")
    p.add_argument("--no-hooks", action="store_true")
    p.add_argument("--break-lock", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_detach)

    p = sub.add_parser("reparent", help="move a child under a new parent")
    p.add_argument("child")
    p.add_argument("--to", required=True)
    p.add_argument("--confirm-source-change", action="store_true")
    p.add_argument("--break-lock", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_reparent)

    p = sub.add_parser("publish", help="verify portability and emit a descriptor")
    p.add_argument("--tree", action="store_true")
    p.add_argument("--push", action="store_true")
    p.add_argument("--bundle", action="store_true",
                   help="accept commits not on a remote (portable bundle intent)")
    p.add_argument("--no-hooks", action="store_true")
    add_json(p); p.set_defaults(func=_cmd_publish)

    p = sub.add_parser("materialize", help="reconstruct a portable subtree")
    p.add_argument("reference")
    p.add_argument("--into")
    add_json(p); p.set_defaults(func=_cmd_materialize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args, Path.cwd())
    except WsError as exc:
        print(f"ws: {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
