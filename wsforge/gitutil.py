"""Thin wrappers around the ``git`` CLI and common repository queries."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import WsError


def run(args: list[str], cwd: Path | None = None, check: bool = True,
        capture: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(cwd) if cwd else None, text=True, check=check, env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def git(args: list[str], cwd: Path, check: bool = True) -> str:
    p = run(["git", *args], cwd, check=check)
    if check and p.returncode:
        raise WsError(f"git {' '.join(args)} failed: {(p.stderr or '').strip()}")
    return (p.stdout or "").strip()


def git_ok(args: list[str], cwd: Path) -> bool:
    return run(["git", *args], cwd, check=False).returncode == 0


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists() and git_ok(["rev-parse", "--git-dir"], path)


def is_clean(repo: Path) -> bool:
    """True when the working tree has no staged, unstaged, or untracked changes."""
    return git(["status", "--porcelain"], repo).strip() == ""


def head_sha(repo: Path) -> str:
    return git(["rev-parse", "HEAD"], repo)


def current_branch(repo: Path) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"], repo, check=False)


def object_exists(repo: Path, sha: str) -> bool:
    return git_ok(["cat-file", "-e", f"{sha}^{{commit}}"], repo)


def _identity_args(repo: Path) -> list[str]:
    """Provide a fallback commit identity only when none is configured."""
    if git(["config", "user.email"], repo, check=False):
        return []
    return ["-c", "user.name=ws", "-c", "user.email=ws@localhost"]


def commit_all(repo: Path, message: str) -> None:
    git(["add", "-A"], repo)
    if run(["git", "diff", "--cached", "--quiet"], repo, check=False).returncode:
        git([*_identity_args(repo), "commit", "--no-verify", "-m", message], repo)


def has_remote_containing(repo: Path, sha: str) -> bool:
    """True when ``sha`` is contained by a remote-tracking branch (§18/§15.2)."""
    return bool(git(["branch", "-r", "--contains", sha], repo, check=False).strip())


def local_clone(source: Path, dest: Path) -> None:
    """Clone a local repository copying objects (hardlinks), never alternates.

    A plain ``git clone <path>`` hardlinks pack/loose objects into the destination,
    which stay valid even if the source is later removed. It must NOT use
    ``--shared``/``--reference`` (unsafe alternates) or linked worktrees (§12.4).
    """
    run(["git", "clone", "--local", str(source), str(dest)], capture=True, check=True)


def set_canonical_origin(repo: Path, url: str | None) -> None:
    """Point ``origin`` at the canonical URL, dropping stale remote-tracking refs.

    A local clone copies the source's ``refs/remotes/origin/*``. Those refer to the
    *parent's* branches, not the canonical remote, and would make representation checks
    (``has_remote_containing``) lie. Removing and re-adding the remote clears them so the
    node's knowledge of its canonical remote starts empty until it fetches or pushes.
    """
    git(["remote", "remove", "origin"], repo, check=False)
    if url:
        git(["remote", "add", "origin", url], repo)


def fetch_from_path(repo: Path, source: Path, refspec: str | None = None) -> None:
    """Fetch objects directly from another local checkout (§13.3)."""
    args = ["fetch", "--no-tags", str(source)]
    if refspec:
        args.append(refspec)
    git(args, repo)
