# ws

A small, dependency-free CLI for multi-repository workspace metarepos managed with Git, wtm, and jmux.

## Install

`ws` requires Python 3 and Git. Clone this repository to a stable location and link the executable onto `PATH`:

```bash
git clone git@github.com:OWNER/ws.git ~/code/ws
ln -s ~/code/ws/bin/ws ~/.local/bin/ws
```

Workspace templates use a thin `.wtm/post_create` hook that calls `ws bootstrap`, so `ws` must be installed before creating a workspace.

## Commands

```text
ws bootstrap    clone repositories from repos.yaml and create artifacts/goal.md
ws status       show the outer metarepo and every child repository
ws archive      verify child safety, commit outer artifacts, and push the workspace branch
ws update-base  merge base/main into a project metarepo
ws doctor       validate the workspace and local integrations
```

`repos.yaml` is intentionally constrained to a small version-1 schema. Child repositories remain independent and are ignored by the outer metarepo.

## Development

Run syntax validation with:

```bash
python3 -m py_compile bin/ws
```

Toolkit Workspace includes this repository at `repos/ws` for development. Changes here do not require copying code into `workspace-base`; the command is installed independently.
