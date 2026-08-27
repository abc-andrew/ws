"""Node-local operation locks (spec §20).

Locks live under ``.workspace/runtime/`` (git-ignored) and record enough process
information to diagnose stale operations. Multi-node operations must acquire locks in
deterministic ancestor-to-descendant order to avoid deadlock; :func:`lock_all` sorts by
path depth to guarantee that.
"""
from __future__ import annotations

import contextlib
import os
import socket
import time
from pathlib import Path

from . import util
from .errors import WsError
from .node import Node

LOCK_NAME = "lock.json"


def _lock_path(node: Node) -> Path:
    return node.runtime_dir / LOCK_NAME


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire(node: Node, operation: str, break_lock: bool = False) -> Path:
    path = _lock_path(node)
    if path.exists():
        info = util.read_json(path)
        alive = info.get("host") == socket.gethostname() and _process_alive(info.get("pid", -1))
        if alive:
            raise WsError(
                f"{node.root.name}: locked by pid {info.get('pid')} for "
                f"{info.get('operation')!r} since {info.get('started')}")
        if not break_lock:
            raise WsError(
                f"{node.root.name}: stale lock from pid {info.get('pid')} "
                f"({info.get('operation')!r}); rerun with --break-lock to override")
    util.write_json(path, {
        "operation": operation,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return path


def release(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


@contextlib.contextmanager
def hold(node: Node, operation: str, break_lock: bool = False):
    path = acquire(node, operation, break_lock)
    try:
        yield
    finally:
        release(path)


@contextlib.contextmanager
def lock_all(nodes: list[Node], operation: str, break_lock: bool = False):
    """Lock several nodes ancestor-to-descendant (shallowest path first)."""
    unique: dict[Path, Node] = {n.root: n for n in nodes}
    ordered = sorted(unique.values(), key=lambda n: len(n.root.parts))
    held: list[Path] = []
    try:
        for node in ordered:
            held.append(acquire(node, operation, break_lock))
        yield
    finally:
        for path in reversed(held):
            release(path)
