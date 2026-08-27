"""Shared pytest fixtures: real bare origin repos and a ``ws`` subprocess runner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_WS = REPO_ROOT / "bin" / "ws"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   env={**_base_env(), **GIT_ENV},
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _base_env():
    import os
    return dict(os.environ)


@pytest.fixture
def env():
    return {**_base_env(), **GIT_ENV}


def make_origin(root: Path, name: str, files: dict[str, str] | None = None) -> str:
    """Create a bare origin repo with an initial commit on ``main``; return its URL."""
    bare = root / "origins" / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    seed = root / "seeds" / name
    seed.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], seed)
    (seed / "README.md").write_text(f"{name} v1\n")
    for rel, content in (files or {}).items():
        (seed / rel).write_text(content)
    _git(["add", "-A"], seed)
    _git(["commit", "-q", "-m", f"init {name}"], seed)
    _git(["remote", "add", "origin", str(bare)], seed)
    _git(["push", "-q", "origin", "main"], seed)
    return str(bare)


@pytest.fixture
def origins(tmp_path):
    return {
        "toolkit": make_origin(tmp_path, "toolkit"),
        "lib": make_origin(tmp_path, "lib"),
    }


@pytest.fixture
def ws(env):
    """Return a runner: ``ws(*args, cwd=path, check=True) -> CompletedProcess``."""
    def run(*args, cwd: Path, check: bool = True):
        proc = subprocess.run(
            [sys.executable, str(BIN_WS), *args], cwd=str(cwd),
            env=env, capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise AssertionError(
                f"ws {' '.join(args)} failed ({proc.returncode}):\n{proc.stderr}")
        return proc
    return run


@pytest.fixture
def workspace_origin(tmp_path):
    """A bare origin for the outer workspace repository (unseeded)."""
    bare = tmp_path / "origins" / "workspace.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    return str(bare)


@pytest.fixture
def base(tmp_path, origins, workspace_origin, ws):
    """A root node 'base' with toolkit+lib declared and materialized."""
    root = tmp_path / "base"
    root.mkdir()
    ws("init", "base", "--origin", workspace_origin, cwd=root)
    manifest = "version: 1\n\nrepositories:\n"
    for name, url in origins.items():
        manifest += f"  {name}:\n    path: repos/{name}\n    origin: {url}\n    base: main\n"
    (root / "workspace.yaml").write_text(manifest)
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "add repos"], root)
    ws("sync", cwd=root)
    return root


def commit_in(repo: Path, filename: str, content: str, message: str):
    (repo / filename).write_text(content)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)


def add_hook(root: Path, name: str, body: str, executable: bool = True):
    """Write, (optionally) chmod, and commit a hook so the outer repo stays clean."""
    h = root / ".workspace" / "hooks" / name
    h.write_text(body)
    h.chmod(0o755 if executable else 0o644)
    _git(["add", "-A", "-f"], root)
    _git(["commit", "-q", "-m", f"add hook {name}"], root)
    return h
