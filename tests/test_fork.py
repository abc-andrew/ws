"""Tests for the transactional ``ws fork``."""
from __future__ import annotations

import json

from conftest import commit_in
from wsforge import gitutil
from wsforge.node import Node


def test_fork_happy_path(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    assert (child / ".workspace" / "node.json").is_file()
    n = Node.at(child)
    # new id, populated provenance, empty children, clean outer repo
    assert n.id != Node.at(base).id
    cf = n.meta()["created_from"]
    assert cf["node_id"] == Node.at(base).id
    assert set(cf["repositories"]) == {"toolkit", "lib"}
    assert n.children() == []
    assert gitutil.is_clean(child)
    # every repo leaf shares one ws/<id-tail>-<node> branch (spec §12.5)
    from wsforge import util
    expected = f"ws/{util.id_prefix(n.id)}-child"
    assert gitutil.current_branch(child / "repos" / "toolkit") == expected
    assert gitutil.current_branch(child / "repos" / "lib") == expected


def test_fork_repo_origin_is_canonical(base, ws, origins):
    ws("fork", "child", cwd=base)
    url = gitutil.git(["remote", "get-url", "origin"],
                      base / "children" / "child" / "repos" / "toolkit")
    assert url == origins["toolkit"]


def test_fork_rejects_dirty_repo(base, ws):
    (base / "repos" / "toolkit" / "dirty.txt").write_text("x")
    proc = ws("fork", "child", cwd=base, check=False)
    assert proc.returncode != 0
    assert "dirty" in proc.stderr
    assert not (base / "children" / "child").exists()


def test_fork_accepts_unpushed_commit(base, ws):
    # a committed-but-unpushed parent commit is a valid fork source (§26.8)
    commit_in(base / "repos" / "lib", "new.txt", "local", "unpushed")
    ws("fork", "child", cwd=base)
    head = gitutil.head_sha(base / "children" / "child" / "repos" / "lib")
    assert head == gitutil.head_sha(base / "repos" / "lib")


def test_fork_rejects_duplicate_name(base, ws):
    ws("fork", "child", cwd=base)
    proc = ws("fork", "child", cwd=base, check=False)
    assert proc.returncode != 0 and "already exists" in proc.stderr


def test_fork_atomic_on_hook_failure(base, ws):
    from conftest import add_hook
    add_hook(base, "post-fork", "#!/bin/sh\nexit 3\n")
    proc = ws("fork", "child", cwd=base, check=False)
    assert proc.returncode != 0
    assert "post-fork" in proc.stderr
    # no partial child, no leftover temp dir, parent untouched
    assert not (base / "children" / "child").exists()
    assert not list((base / "children").glob(".wsfork-*"))


def test_nested_fork(base, ws):
    ws("fork", "mid", cwd=base)
    mid = base / "children" / "mid"
    ws("fork", "leaf", cwd=mid)
    leaf = Node.at(mid / "children" / "leaf")
    assert leaf.owner_path() == mid
    assert leaf.meta()["created_from"]["node_id"] == Node.at(mid).id
