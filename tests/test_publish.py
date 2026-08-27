"""Tests for publish / materialize."""
from __future__ import annotations

import json
import subprocess

from wsforge import gitutil


def _push_all(root, env):
    if (root / ".git").exists():
        subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=root,
                       env=env, check=False)
    for repo in (root / "repos").iterdir():
        if (repo / ".git").exists():
            branch = gitutil.current_branch(repo)
            subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"],
                           cwd=repo, env=env, check=True)


def test_publish_refuses_unrepresented(base, ws):
    ws("fork", "child", cwd=base)
    proc = ws("publish", cwd=base / "children" / "child", check=False)
    assert proc.returncode != 0 and "not represented by a remote" in proc.stderr


def test_publish_bundle_allows_local(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    ws("publish", "--bundle", cwd=child)
    descriptor = json.loads((child / ".workspace" / "portable.json").read_text())
    assert descriptor["nodes"][0]["name"] == "child"
    assert descriptor["nodes"][0]["repositories"].keys()


def test_publish_descriptor_has_no_absolute_paths(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    ws("publish", "--bundle", cwd=child)
    text = (child / ".workspace" / "portable.json").read_text()
    data = json.loads(text)
    for node in data["nodes"]:
        assert node["relative_path"] in (".", "children/child") or "/" in node["relative_path"]
        assert not node["relative_path"].startswith("/")


def test_publish_does_not_push_implicitly(base, ws, origins, env):
    ws("fork", "child", cwd=base)
    ws("publish", "--bundle", cwd=base / "children" / "child")
    # nothing pushed: the canonical origin has no ws/* branch
    refs = subprocess.run(["git", "ls-remote", origins["lib"]], env=env,
                          capture_output=True, text=True).stdout
    assert "ws/" not in refs


def test_materialize_reconstructs(base, ws, env, tmp_path):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    _push_all(child, env)
    ws("publish", cwd=child)  # now represented on remotes
    descriptor = child / ".workspace" / "portable.json"

    into = tmp_path / "rebuilt"
    ws("materialize", str(descriptor), "--into", str(into), cwd=tmp_path)
    assert (into / "child" / "repos" / "lib" / ".git").exists()


def test_materialize_reports_missing_commit(base, ws, tmp_path):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    ws("publish", "--bundle", cwd=child)  # commits NOT actually on the remote
    descriptor = child / ".workspace" / "portable.json"
    into = tmp_path / "rebuilt"
    proc = ws("materialize", str(descriptor), "--into", str(into), cwd=tmp_path, check=False)
    assert proc.returncode != 0 and "unavailable" in proc.stderr
