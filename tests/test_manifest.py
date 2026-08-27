"""Unit tests for manifest parsing/validation and id/name helpers."""
from __future__ import annotations

import pytest

from wsforge import manifest, util
from wsforge.errors import WsError


def write(tmp_path, text):
    p = tmp_path / "workspace.yaml"
    p.write_text(text)
    return p


def test_parse_valid(tmp_path):
    p = write(tmp_path, """
version: 1

repositories:
  toolkit:
    path: repos/toolkit
    origin: git@host:o/toolkit.git
    base: main
""")
    repos = manifest.parse(p)
    assert repos["toolkit"] == {
        "path": "repos/toolkit", "origin": "git@host:o/toolkit.git", "base": "main"}


def test_empty_repositories(tmp_path):
    assert manifest.parse(write(tmp_path, "version: 1\n\nrepositories: {}\n")) == {}


def test_bad_version(tmp_path):
    with pytest.raises(WsError, match="version must be 1"):
        manifest.parse(write(tmp_path, "version: 2\n\nrepositories: {}\n"))


def test_missing_field(tmp_path):
    with pytest.raises(WsError, match="missing origin"):
        manifest.parse(write(tmp_path, """
version: 1

repositories:
  a:
    path: repos/a
    base: main
"""))


def test_path_escape_rejected(tmp_path):
    with pytest.raises(WsError, match="under repos/"):
        manifest.parse(write(tmp_path, """
version: 1

repositories:
  a:
    path: repos/../a
    origin: x
    base: main
"""))


def test_path_outside_repos_rejected(tmp_path):
    with pytest.raises(WsError, match="under repos/"):
        manifest.parse(write(tmp_path, """
version: 1

repositories:
  a:
    path: elsewhere/a
    origin: x
    base: main
"""))


def test_emit_roundtrip(tmp_path):
    repos = {"a": {"path": "repos/a", "origin": "u", "base": "main"}}
    p = write(tmp_path, manifest.emit(repos))
    assert manifest.parse(p) == repos


def test_uuid7_format_and_ordering():
    ids = [util.uuid7() for _ in range(50)]
    assert len(set(ids)) == 50
    for i in ids:
        assert len(i) == 36 and i[14] == "7"  # version nibble
    # id_prefix uses the random tail (not the timestamp head) for branch uniqueness
    assert util.id_prefix(ids[0]) == ids[0].replace("-", "")[-8:]
    assert len(util.id_prefix(ids[0])) == 8


@pytest.mark.parametrize("name,ok", [
    ("feature", True), ("a-b_c.1", True), (".", False), ("..", False),
    ("a/b", False), (".hidden", False), ("", False)])
def test_valid_name(name, ok):
    assert util.valid_name(name) is ok
