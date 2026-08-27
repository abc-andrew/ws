"""Tests for lifecycle hooks."""
from __future__ import annotations

from conftest import add_hook


def test_pre_and_post_fork_run_with_env(base, ws):
    add_hook(base, "pre-fork",
             '#!/bin/sh\necho "pre $WS_PARENT_ID" >> "$WS_PARENT_ROOT/pre.log"\n')
    add_hook(base, "post-fork",
             '#!/bin/sh\necho "post $WS_CHILD_ID" > "$WS_CHILD_ROOT/post.log"\n')

    ws("fork", "child", cwd=base)
    assert (base / "pre.log").read_text().startswith("pre ")
    assert (base / "children" / "child" / "post.log").read_text().startswith("post ")


def test_failing_hook_aborts_fork(base, ws):
    add_hook(base, "pre-fork", "#!/bin/sh\nexit 7\n")
    proc = ws("fork", "child", cwd=base, check=False)
    assert proc.returncode != 0 and "pre-fork" in proc.stderr
    assert not (base / "children" / "child").exists()


def test_no_hooks_skips_optional(base, ws):
    add_hook(base, "pre-fork", "#!/bin/sh\nexit 7\n")
    ws("fork", "child", "--no-hooks", cwd=base)
    assert (base / "children" / "child").exists()


def test_non_executable_hook_reported(base, ws):
    add_hook(base, "pre-fork", "#!/bin/sh\ntrue\n", executable=False)
    proc = ws("fork", "child", cwd=base, check=False)
    assert proc.returncode != 0 and "not executable" in proc.stderr
