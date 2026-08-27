"""Tests for ``ws integrate`` (upward integration)."""
from __future__ import annotations

from conftest import commit_in
from wsforge import gitutil
from wsforge.node import Node


def test_integrate_repo_commit(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(child / "repos" / "lib", "feature.txt", "feature", "child feature")

    ws("integrate", "child", cwd=base)
    assert (base / "repos" / "lib" / "feature.txt").exists()


def test_integrate_preserves_parent_identity(base, ws):
    parent_id = Node.at(base).id
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(child / "repos" / "lib", "feature.txt", "feature", "child feature")

    ws("integrate", "child", cwd=base)
    assert Node.at(base).id == parent_id
    assert Node.at(base).meta()["created_from"] is None


def test_integrate_repo_selection(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(child / "repos" / "lib", "lib.txt", "x", "lib change")
    commit_in(child / "repos" / "toolkit", "tk.txt", "y", "toolkit change")

    ws("integrate", "child", "--repo", "toolkit", cwd=base)
    assert (base / "repos" / "toolkit" / "tk.txt").exists()
    assert not (base / "repos" / "lib" / "lib.txt").exists()


def test_integrate_refuses_dirty_parent(base, ws):
    ws("fork", "child", cwd=base)
    (base / "repos" / "lib" / "dirty.txt").write_text("x")
    proc = ws("integrate", "child", cwd=base, check=False)
    assert proc.returncode != 0 and "dirty" in proc.stderr


def test_integrate_does_not_remove_child(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(child / "repos" / "lib", "feature.txt", "feature", "child feature")
    ws("integrate", "child", cwd=base)
    assert child.exists()
