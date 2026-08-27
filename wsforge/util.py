"""Small dependency-free helpers: identifiers, JSON IO, path safety."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from .errors import WsError

SCHEMA = 1

# A workspace or repository name: no path separators, no leading dot, no traversal.
_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


def uuid7() -> str:
    """Return a UUIDv7-style, time-ordered identifier.

    Layout follows RFC 9562 v7: 48-bit big-endian Unix millisecond timestamp,
    version nibble 7, variant bits 10, the remainder random. Time ordering makes
    ids sortable and their 8-char prefix a useful branch component.
    """
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0x2 << 62
    value |= rand_b
    hexs = f"{value:032x}"
    return f"{hexs[0:8]}-{hexs[8:12]}-{hexs[12:16]}-{hexs[16:20]}-{hexs[20:32]}"


def id_prefix(node_id: str) -> str:
    """A short, stable, per-node hex tag for branch names.

    Uses the random tail of the id rather than its leading bytes: a UUIDv7's first
    hex chars are the timestamp, identical for ids minted within the same window, so a
    leading prefix would collide across sibling/nested forks. The random tail keeps
    generated branch names unique within a repository (spec §12.5).
    """
    return node_id.replace("-", "")[-8:]


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(name)) and name not in (".", "..")


def require_name(name: str, kind: str = "name") -> str:
    if not valid_name(name):
        raise WsError(f"invalid {kind}: {name!r}")
    return name


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise WsError(f"missing {path}")
    except json.JSONDecodeError as exc:
        raise WsError(f"invalid JSON in {path}: {exc}")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def rel_path(target: Path, start: Path) -> str:
    """POSIX relative path from ``start`` to ``target`` (portable, no absolutes)."""
    return Path(os.path.relpath(target, start)).as_posix()


def is_within(child: Path, parent: Path) -> bool:
    """True when ``child`` resolves to a location at or beneath ``parent``.

    Both are resolved so symlinks that escape the parent are rejected.
    """
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
