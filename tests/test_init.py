"""Tests for ``ws init`` and ``ws sync``."""
from __future__ import annotations

import json
import subprocess


def test_init_scaffold(tmp_path, ws):
    root = tmp_path / "base"
    root.mkdir()
    ws("init", "base", "--protected", cwd=root)
    assert (root / ".workspace" / "node.json").is_file()
    assert (root / "workspace.yaml").is_file()
    for d in ("repos", "children", "artifacts"):
        assert (root / d / ".gitkeep").is_file()
    meta = json.loads((root / ".workspace" / "node.json").read_text())
    assert meta["created_from"] is None
    assert meta["policy"]["protected"] is True
    assert (root / ".git").is_dir()


def test_init_gitignore_boundaries(tmp_path, ws, env):
    root = tmp_path / "base"
    root.mkdir()
    ws("init", cwd=root)
    for probe in ("repos/x", "children/x", ".workspace/local.json"):
        r = subprocess.run(["git", "check-ignore", "-q", probe], cwd=root, env=env)
        assert r.returncode == 0, f"{probe} should be ignored"


def test_init_refuses_existing(tmp_path, ws):
    root = tmp_path / "base"
    root.mkdir()
    ws("init", cwd=root)
    proc = ws("init", cwd=root, check=False)
    assert proc.returncode != 0
    assert "already a workspace" in proc.stderr


def test_sync_materializes(base):
    assert (base / "repos" / "toolkit" / ".git").exists()
    assert (base / "repos" / "lib" / ".git").exists()


def test_sync_idempotent(base, ws):
    proc = ws("sync", cwd=base)
    assert "nothing to do" in proc.stdout
