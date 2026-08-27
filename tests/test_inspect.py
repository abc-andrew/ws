"""Tests for inspection commands."""
from __future__ import annotations

import json


def test_root_json(base, ws):
    data = json.loads(ws("root", "--json", cwd=base).stdout)
    assert data["name"] == "base" and data["root"].endswith("/base")


def test_parent_of_child(base, ws):
    ws("fork", "child", cwd=base)
    data = json.loads(ws("parent", "--json", cwd=base / "children" / "child").stdout)
    assert data["owner"]["available"] is True
    assert data["inheritance_source"]["node_id"] == json.loads(
        ws("root", "--json", cwd=base).stdout)["id"]


def test_context_reports_pending_updates(base, ws):
    from conftest import commit_in
    ws("fork", "child", cwd=base)
    commit_in(base / "repos" / "lib", "x.txt", "y", "advance")
    data = json.loads(ws("context", "--json", cwd=base / "children" / "child").stdout)
    assert "lib" in data["pending_parent_updates"]
    assert data["children"] == []


def test_tree_crosses_boundaries(base, ws):
    ws("fork", "child", cwd=base)
    out = ws("tree", cwd=base).stdout
    assert "base" in out and "child" in out and "toolkit" in out


def test_status_tree_recurses(base, ws):
    ws("fork", "child", cwd=base)
    out = ws("status", "--tree", cwd=base).stdout
    assert out.count("WORKSPACE") >= 2


def test_doctor_healthy(base, ws):
    data = json.loads(ws("doctor", "--json", cwd=base).stdout)
    assert data["ok"] is True


def test_doctor_flags_symlinked_child(base, ws, tmp_path):
    # a symlinked child root is rejected (§21.4)
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / ".workspace").mkdir()
    (real / ".workspace" / "node.json").write_text(json.dumps(
        {"schema": 1, "id": "x", "name": "bad", "created_from": None, "policy": {}}))
    (real / "children").mkdir()
    (real / "workspace.yaml").write_text("version: 1\n\nrepositories: {}\n")
    link = base / "children" / "linked"
    link.symlink_to(real)
    data = json.loads(ws("doctor", "--json", cwd=base, check=False).stdout)
    symlink_check = next(c for c in data["checks"] if "symlinked" in c["name"])
    assert symlink_check["ok"] is False
