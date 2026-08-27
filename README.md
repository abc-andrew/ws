# ws — recursive workspace forking

`ws` is a small, dependency-free CLI for creating, inheriting, updating, integrating,
publishing, and removing **recursively nested development workspaces**. It implements
[`workspace-forking-spec.md`](../workspace-forking-spec.md).

The core abstraction:

> A workspace is a filesystem node created by forking another workspace node.

A base template, project template, working instance, sample, and subtask are all the same
kind of node — they differ only by policy and use. `ws` is local-first and needs no remote,
and it does not depend on an editor, terminal multiplexer, or agent harness.

## Node layout

```text
workspace/
├── .workspace/
│   ├── node.json        # portable identity + immutable lineage (no absolute paths)
│   ├── local.json        # machine-local owner, inheritance source, advancing baseline
│   ├── hooks/            # inherited lifecycle hooks
│   └── runtime/          # locks and transient state (git-ignored)
├── artifacts/           # workspace-owned files (e.g. goal.md)
├── repos/               # repository leaves — independent Git checkouts (git-ignored)
├── children/            # nested child workspace nodes (git-ignored)
├── workspace.yaml       # repository manifest (version 1)
└── .gitignore
```

Each node's root may be its own outer Git repository tracking the workspace-owned files.
Repository contents and child workspaces are always ignored by that outer repository.

## Installing

```bash
git clone <this-repo> ~/code/ws
ln -s ~/code/ws/bin/ws ~/.local/bin/ws
ws --help
```

`bin/ws` is a thin launcher that resolves its own symlink and runs the `wsforge` package
beside it, so the install is independent of any workspace instance. Requires Python 3.10+
and Git.

## Quick start

```bash
mkdir workspace-base && cd workspace-base
ws init --protected                 # create a root node

# declare repositories in workspace.yaml, then materialize local checkouts
ws sync

ws fork toolkit                     # fork a project template
cd children/toolkit
ws fork ws-tooling                  # fork a working instance
cd children/ws-tooling
```

`workspace.yaml`:

```yaml
version: 1

repositories:
  toolkit:
    path: repos/toolkit
    origin: git@host:owner/toolkit.git
    base: main
  ws:
    path: repos/ws
    origin: git@host:owner/ws.git
    base: main
```

## How forking works

`ws fork NAME` is transactional. It verifies the parent is clean and structurally valid,
materializes the child in a temporary sibling under `children/`, and only atomically renames
it into place after every step and hook succeeds. Any failure removes the temporary child
and leaves the parent untouched.

- The outer workspace repository is locally cloned from the parent; its canonical `origin`
  is retained (or set with `--origin`).
- Each repository leaf is cloned from the parent's **local checkout** (committed state; no
  unsafe Git alternates, no linked worktrees), its canonical `origin` is restored from
  `workspace.yaml`, and a fresh branch `ws/<id>-<node>` is created from the parent's HEAD.
- The child gets a new stable node id, immutable `created_from` provenance, and an
  advancing baseline for future parent updates.

Inheritance is **snapshot-based**: later parent changes never appear in a child
automatically.

## Inheritance and integration

```bash
ws merge-parent      # merge the parent's current state into this child
ws rebase-parent     # rebase this child's own commits onto the parent's current state
ws integrate CHILD   # apply a child's changes upward into this parent
ws integrate CHILD --repo toolkit   # integrate a single repository
```

Workspace-owned files reconcile through the outer Git repository (a real three-way merge);
repository leaves reconcile per repo by fetching directly from the local parent/child
checkout. Conflicts are left visible for manual resolution, and a child never mutates its
parent automatically. The advancing baseline only moves after a fully successful update.

## Lifecycle

```bash
ws remove CHILD [--recursive] [--force]
ws detach CHILD --to PATH [--copy] [--clear-source]
ws reparent CHILD --to NEW_PARENT
```

`remove` refuses to discard a subtree with dirty state, commits not represented on any
remote, publication metadata, active locks, or descendants (without `--recursive`);
`--force` enumerates what it discards. `detach` moves a subtree to an independent location,
clears its owner, preserves provenance, and verifies every Git object store still validates.

## Inspection

```bash
ws root            # active workspace root and id
ws parent          # current owner and inheritance source
ws context         # agent-oriented summary (repos, children, dirty, pending updates, goal)
ws tree            # recursive structure, crossing ignored boundaries
ws status [--tree] # nearest workspace, or the whole subtree
ws doctor          # validate metadata, ids, containment, manifests, git health, ignores…
```

Most commands accept `--json` for machine-readable output.

## Publication

```bash
ws publish [--tree] [--push] [--bundle]
ws materialize REFERENCE [--into PATH]
```

Local forking, updating, and integration never require publication. `publish` verifies a
node (or `--tree` subtree) is committed and remotely represented, then writes a portable
descriptor (`.workspace/portable.json`) with no absolute paths. It never pushes unless
`--push` is given, and prints the exact remotes and refs first. `materialize` reconstructs a
portable subtree, verifying every referenced commit rather than substituting a default
branch.

## Hooks

Inherited executables under `.workspace/hooks/` run around operations: `pre-fork`,
`post-fork`, `pre/post-merge-parent`, `pre/post-rebase-parent`, `pre/post-integrate`,
`pre-remove`, `pre/post-detach`, `pre/post-publish`. They receive `WS_OPERATION`,
`WS_PARENT_ROOT`, `WS_CHILD_ROOT`, `WS_PARENT_ID`, `WS_CHILD_ID`, and `WS_FORK_BASELINE`.
Hooks are trusted local code; `--no-hooks` skips optional hooks but never core identity, Git
safety, baseline, or lifecycle invariants.

## Security

The workspace tree provides contextual scope, **not** security isolation. A process can
still reach `..`, absolute paths, and other files. Combine `ws` with an external sandbox for
security-sensitive use. Hooks are executable code; secrets and machine-specific credentials
are never inherited, committed, or published by default.

## Development

```bash
python3 -m py_compile bin/ws wsforge/*.py
python3 -m pytest
```

`wsforge/` is the CLI implementation; keep it dependency-free (Python stdlib + `git`).
`ws sync` is the one command beyond the spec's §24 set: it materializes declared repository
leaves from their `origin`, which a root needs because fork and parent-update clone from a
*local* parent checkout.
