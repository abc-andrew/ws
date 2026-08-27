"""Tests for remove / detach / reparent."""
from __future__ import annotations

import json

from conftest import commit_in
from wsforge import gitutil
from wsforge.node import Node


def _push_all(root, env):
    import subprocess
    for repo in (root / "repos").iterdir():
        if (repo / ".git").exists():
            branch = gitutil.current_branch(repo)
            subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"],
                           cwd=repo, env=env, check=True)


def test_remove_requires_recursive_for_descendants(base, ws):
    ws("fork", "mid", cwd=base)
    ws("fork", "leaf", cwd=base / "children" / "mid")
    proc = ws("remove", "mid", cwd=base, check=False)
    assert proc.returncode != 0 and "--recursive" in proc.stderr


def test_remove_refuses_unpushed(base, ws):
    ws("fork", "child", cwd=base)
    proc = ws("remove", "child", cwd=base, check=False)
    assert proc.returncode != 0 and "not on any remote" in proc.stderr
    assert (base / "children" / "child").exists()


def test_remove_force_discards(base, ws):
    ws("fork", "child", cwd=base)
    proc = ws("remove", "child", "--force", cwd=base)
    assert not (base / "children" / "child").exists()


def test_remove_clean_when_pushed(base, ws, env):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    _push_all(child, env)
    ws("remove", "child", cwd=base)  # no force needed once represented on a remote
    assert not child.exists()


def test_detach_moves_and_clears_owner(base, ws, env, tmp_path):
    ws("fork", "child", cwd=base)
    _push_all(base / "children" / "child", env)
    dest = tmp_path / "detached"
    ws("detach", "child", "--to", str(dest), cwd=base)
    assert not (base / "children" / "child").exists()
    n = Node.at(dest)
    assert n.local()["owner"] is None
    # provenance preserved
    assert n.meta()["created_from"]["node_id"] == Node.at(base).id
    # object stores still valid
    assert gitutil.run(["git", "fsck"], dest / "repos" / "lib", check=False).returncode == 0


def test_reparent_updates_owner(base, ws, env):
    ws("fork", "a", cwd=base)
    ws("fork", "b", cwd=base)
    ws("fork", "moving", cwd=base / "children" / "a")
    a = base / "children" / "a"
    b = base / "children" / "b"
    ws("reparent", "moving", "--to", str(b), "--confirm-source-change", cwd=a)
    assert (b / "children" / "moving").exists()
    assert Node.at(b / "children" / "moving").local()["owner"]["node_id"] == Node.at(b).id
