"""Tests for merge-parent / rebase-parent (downward updates)."""
from __future__ import annotations

from conftest import commit_in
from wsforge import gitutil
from wsforge.node import Node


def test_merge_parent_brings_repo_commit(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(base / "repos" / "lib", "README.md", "lib v1\nlib v2\n", "parent change")
    parent_head = gitutil.head_sha(base / "repos" / "lib")

    ws("merge-parent", cwd=child)
    assert "lib v2" in (child / "repos" / "lib" / "README.md").read_text()
    # baseline advanced to the parent's new HEAD
    assert Node.at(child).baseline()["repositories"]["lib"] == parent_head


def test_merge_parent_preserves_child_identity(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    child_id = Node.at(child).id
    commit_in(base / "repos" / "lib", "README.md", "changed\n", "parent change")
    ws("merge-parent", cwd=child)
    assert Node.at(child).id == child_id
    assert Node.at(child).meta()["created_from"]["node_id"] == Node.at(base).id


def test_rebase_parent_replays_child_commits(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    commit_in(child / "repos" / "lib", "child.txt", "child work", "child commit")
    commit_in(base / "repos" / "lib", "parent.txt", "parent work", "parent commit")

    ws("rebase-parent", cwd=child)
    lib = child / "repos" / "lib"
    # both parent and child changes are present, child replayed on top
    assert (lib / "parent.txt").exists() and (lib / "child.txt").exists()


def test_merge_parent_conflict_leaves_baseline(base, ws):
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    old_baseline = Node.at(child).baseline()["repositories"]["lib"]
    # conflicting edits to the same line in parent and child
    commit_in(child / "repos" / "lib", "README.md", "child edit\n", "child")
    commit_in(base / "repos" / "lib", "README.md", "parent edit\n", "parent")

    proc = ws("merge-parent", cwd=child, check=False)
    assert proc.returncode != 0 and "conflict" in proc.stderr
    # baseline must NOT advance on failure
    assert Node.at(child).baseline()["repositories"]["lib"] == old_baseline


def test_merge_parent_materializes_added_repo(base, ws, tmp_path):
    from conftest import make_origin
    ws("fork", "child", cwd=base)
    child = base / "children" / "child"
    # parent adds a new repository to the manifest and materializes it
    url = make_origin(tmp_path, "extra")
    manifest = (base / "workspace.yaml").read_text()
    manifest += f"  extra:\n    path: repos/extra\n    origin: {url}\n    base: main\n"
    (base / "workspace.yaml").write_text(manifest)
    commit_in(base, "workspace.yaml", manifest, "add extra")  # commit manifest
    ws("sync", cwd=base)

    ws("merge-parent", cwd=child)
    assert (child / "repos" / "extra" / ".git").exists()
