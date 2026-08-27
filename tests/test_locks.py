"""Tests for operation locks."""
from __future__ import annotations

import json
import os

from wsforge import locks
from wsforge.errors import WsError
from wsforge.node import Node


def test_lock_blocks_live_process(base):
    node = Node.at(base)
    path = locks.acquire(node, "fork:x")
    try:
        # a lock owned by this (alive) process must block a second acquire
        try:
            locks.acquire(node, "fork:y")
            assert False, "expected lock contention"
        except WsError as exc:
            assert "locked" in str(exc)
    finally:
        locks.release(path)


def test_stale_lock_requires_break(base):
    node = Node.at(base)
    node.runtime_dir.mkdir(parents=True, exist_ok=True)
    (node.runtime_dir / locks.LOCK_NAME).write_text(json.dumps({
        "operation": "fork:old", "pid": 999999, "host": os.uname().nodename,
        "started": "2000-01-01T00:00:00"}))
    try:
        locks.acquire(node, "fork:new")
        assert False, "expected stale-lock refusal"
    except WsError as exc:
        assert "stale lock" in str(exc)
    # with break_lock it proceeds
    path = locks.acquire(node, "fork:new", break_lock=True)
    locks.release(path)


def test_lock_released_after_fork(base, ws):
    ws("fork", "child", cwd=base)
    assert not (base / ".workspace" / "runtime" / locks.LOCK_NAME).exists()
