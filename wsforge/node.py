"""The workspace node model: discovery, metadata, and lineage (spec §7, §9)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitutil, manifest, util
from .errors import WsError

WS_DIR = ".workspace"
NODE_JSON = "node.json"
LOCAL_JSON = "local.json"
HOOKS_DIR = "hooks"
RUNTIME_DIR = "runtime"


def find_root(start: Path) -> Path | None:
    """Nearest ancestor of ``start`` (inclusive) containing ``.workspace/node.json``."""
    start = start.resolve()
    for directory in (start, *start.parents):
        if (directory / WS_DIR / NODE_JSON).is_file():
            return directory
    return None


def require_root(start: Path) -> Path:
    root = find_root(start)
    if root is None:
        raise WsError("not inside a workspace (no .workspace/node.json found)")
    return root


@dataclass
class Node:
    root: Path

    # --- construction -----------------------------------------------------
    @classmethod
    def at(cls, path: Path) -> "Node":
        if not (path / WS_DIR / NODE_JSON).is_file():
            raise WsError(f"not a workspace node: {path}")
        return cls(path.resolve())

    @classmethod
    def discover(cls, start: Path) -> "Node":
        return cls(require_root(start))

    # --- paths ------------------------------------------------------------
    @property
    def ws_dir(self) -> Path:
        return self.root / WS_DIR

    @property
    def node_json(self) -> Path:
        return self.ws_dir / NODE_JSON

    @property
    def local_json(self) -> Path:
        return self.ws_dir / LOCAL_JSON

    @property
    def hooks_dir(self) -> Path:
        return self.ws_dir / HOOKS_DIR

    @property
    def runtime_dir(self) -> Path:
        return self.ws_dir / RUNTIME_DIR

    @property
    def repos_dir(self) -> Path:
        return self.root / "repos"

    @property
    def children_dir(self) -> Path:
        return self.root / "children"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def manifest_path(self) -> Path:
        return self.root / manifest.MANIFEST_NAME

    # --- metadata ---------------------------------------------------------
    def meta(self) -> dict:
        return util.read_json(self.node_json)

    def write_meta(self, data: dict) -> None:
        util.write_json(self.node_json, data)

    def local(self) -> dict:
        if not self.local_json.is_file():
            return {"schema": util.SCHEMA, "owner": None,
                    "inheritance_source": None, "baseline": None}
        return util.read_json(self.local_json)

    def write_local(self, data: dict) -> None:
        util.write_json(self.local_json, data)

    @property
    def id(self) -> str:
        return self.meta()["id"]

    @property
    def name(self) -> str:
        return self.meta()["name"]

    def policy(self) -> dict:
        return self.meta().get("policy", {})

    def reassert_identity(self, node_id: str, name: str, created_from) -> bool:
        """Restore per-node identity fields, returning True if anything changed.

        A node's ``id``, ``name``, and ``created_from`` are unique to it. Merging the
        outer repository in the child->parent direction (integrate) would otherwise carry
        the *other* node's identity in via ``node.json``; this reasserts our own.
        """
        meta = self.meta()
        if (meta.get("id") == node_id and meta.get("name") == name
                and meta.get("created_from") == created_from):
            return False
        meta["id"] = node_id
        meta["name"] = name
        meta["created_from"] = created_from
        self.write_meta(meta)
        return True

    def repositories(self) -> dict[str, dict[str, str]]:
        return manifest.parse(self.manifest_path)

    # --- structure --------------------------------------------------------
    def has_outer_repo(self) -> bool:
        return gitutil.is_git_repo(self.root)

    def repo_paths(self) -> dict[str, Path]:
        return {name: self.root / spec["path"]
                for name, spec in self.repositories().items()}

    def children(self) -> list["Node"]:
        result: list[Node] = []
        if not self.children_dir.is_dir():
            return result
        for entry in sorted(self.children_dir.iterdir()):
            if entry.is_symlink():
                continue  # symlinked child roots are invalid (§7); doctor flags them
            if entry.is_dir() and (entry / WS_DIR / NODE_JSON).is_file():
                result.append(Node.at(entry))
        return result

    def find_child(self, ref: str) -> "Node":
        """Resolve an immediate child by name, id, or path (spec §14)."""
        for child in self.children():
            if child.root.name == ref or child.id == ref:
                return child
        candidate = (self.children_dir / ref).resolve()
        for child in self.children():
            if child.root == candidate:
                return child
        raise WsError(f"no such child: {ref}")

    # --- lineage ----------------------------------------------------------
    def owner_path(self) -> Path | None:
        return self._linked_path("owner")

    def inheritance_source_path(self) -> Path | None:
        return self._linked_path("inheritance_source")

    def _linked_path(self, key: str) -> Path | None:
        link = self.local().get(key)
        if not link:
            return None
        target = (self.root / link["relative_path"]).resolve()
        if not (target / WS_DIR / NODE_JSON).is_file():
            raise WsError(f"{key} is unavailable at {target}")
        found = Node.at(target)
        if found.id != link["node_id"]:
            raise WsError(
                f"{key} id mismatch: expected {link['node_id']}, found {found.id}")
        return target

    def baseline(self) -> dict | None:
        return self.local().get("baseline")

    def set_baseline(self, workspace_commit: str | None,
                     repositories: dict[str, str]) -> None:
        data = self.local()
        data["baseline"] = {"workspace_commit": workspace_commit,
                            "repositories": repositories}
        self.write_local(data)

    # --- validation -------------------------------------------------------
    def validate_structure(self) -> None:
        meta = self.meta()
        for key in ("schema", "id", "name"):
            if key not in meta:
                raise WsError(f"{self.node_json}: missing {key}")
        manifest.parse(self.manifest_path)
        if not self.children_dir.exists():
            raise WsError(f"missing children/ directory in {self.root}")
