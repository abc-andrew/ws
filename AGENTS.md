# ws development

`ws` implements the recursive workspace forking model in `workspace-forking-spec.md`.

- `bin/ws` is a thin launcher: it resolves its own symlink and runs the `wsforge` package
  beside it. Keep it minimal.
- `wsforge/` is the implementation. Keep it dependency-free (Python 3.10+ stdlib and the
  `git` CLI only — no YAML library; the tiny `workspace.yaml` is hand-parsed in
  `manifest.py`).
- Prefer small, single-purpose modules: one operation per file (`fork.py`, `inherit.py`,
  `integrate.py`, `lifecycle.py`, `publish.py`, `inspect.py`), with shared primitives in
  `gitutil.py`, `node.py`, `manifest.py`, `locks.py`, `hooks.py`, `scaffold.py`, `util.py`.

## Invariants to preserve

- Every fork is transactional: materialize in a temp dir under `children/`, validate, then
  atomically rename. On failure, remove the temp dir and leave the parent unchanged.
- Per-node identity (`id`, `name`, `created_from`) must survive outer-repo merges. Use
  `Node.reassert_identity` after any child↔parent outer merge (see `integrate.py`).
- Repository leaves clone from the *local* parent/child checkout, never via Git alternates
  or linked worktrees. After a local clone, reset the canonical origin with
  `gitutil.set_canonical_origin` (it drops stale remote-tracking refs so
  remote-representation checks stay honest).
- Generated branch names are `ws/<id-tail>-<node-name>`; the id tail comes from the random
  end of the UUIDv7 (`util.id_prefix`), not its timestamp prefix, to stay unique.
- The advancing baseline in `local.json` only moves after a fully successful parent update.
- Portable metadata (`node.json`, descriptors) must never contain absolute paths.

## Tests

`python3 -m pytest`. Tests drive the CLI as a subprocess against real temporary Git repos
(`tests/conftest.py` builds bare origins and a `base` node fixture). Keep the outer repo
clean in fixtures/tests before forking — the clean-fork precondition fires first otherwise.
