"""Tests for node discovery and metadata."""
from __future__ import annotations

import pytest

from wsforge import node as node_mod
from wsforge.errors import WsError
from wsforge.node import Node


def test_discover_nearest_ancestor(base):
    # from deep inside a repo leaf, discovery finds the enclosing node
    deep = base / "repos" / "lib"
    assert node_mod.find_root(deep) == base


def test_discover_from_child(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    # nearest node from inside child is the child, not base
    assert node_mod.find_root(child / "repos" / "lib") == child


def test_require_root_outside(tmp_path):
    with pytest.raises(WsError, match="not inside a workspace"):
        node_mod.require_root(tmp_path)


def test_metadata_roundtrip(base):
    n = Node.at(base)
    assert n.name == "base"
    assert n.meta()["created_from"] is None
    assert n.policy()["fork_source"] is True


def test_lineage_ids(base, ws):
    ws("fork", "child", cwd=base)
    child = Node.at(base / "children" / "child")
    assert child.owner_path() == base
    assert child.inheritance_source_path() == base
    assert child.meta()["created_from"]["node_id"] == Node.at(base).id


def test_reassert_identity(base):
    n = Node.at(base)
    original = n.id
    n.reassert_identity("aaaa-bbbb", "renamed", {"node_id": "x"})
    assert n.id == "aaaa-bbbb" and n.name == "renamed"
    assert n.reassert_identity("aaaa-bbbb", "renamed", {"node_id": "x"}) is False
    assert original != n.id
