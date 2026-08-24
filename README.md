# ws

`ws` is a small, dependency-free CLI for Git-based, multi-repository development workspaces. It connects a shared workspace base, project-specific templates, task worktrees, independent child repositories, [wtm](https://github.com/jarredkenny/worktree-manager), and [jmux](https://github.com/jarredkenny/jmux).

The central idea is to separate **where work happens** from **what repositories are being changed**:

```text
shared workspace base
        ↓ ordinary Git ancestry and merges
project workspace template (main)
        ↓ wtm branch + worktree
workspace instance
        ↓ ws bootstrap reads repos.yaml
independent repositories under repos/*
```

No Git submodules are used. The outer workspace repository tracks workspace structure and notes; application and tool changes are committed in their own repositories.

## The four levels

### 0. Shared base template

A base repository contains infrastructure that every project workspace should inherit:

```text
workspace-base/
├── AGENTS.md
├── .claude/rules/          # shared rules, numbered 00–49
├── .workspace/templates/
│   └── goal.md
├── .wtm/post_create
├── artifacts/.gitkeep
├── repos/.gitkeep
├── .gitignore
└── README.md
```

The base knows nothing about a particular application. It owns conventions, shared agent guidance, the thin wtm hook, and workspace scaffolding.

This installation uses [`abc-andrew/workspace-base`](https://github.com/abc-andrew/workspace-base) as the base template.

`ws` itself is maintained in this standalone repository rather than vendored into the base. The base hook simply invokes the installed command:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec ws bootstrap
```

### 1. Project workspace template

Each logical project has a separate metarepo derived from the base. Its `main` branch is the golden template for all workspaces in that project.

The project repository shares Git ancestry with the base and keeps two remotes:

```text
origin -> the project workspace repository
base   -> the shared workspace-base repository
```

It adds project-owned files such as:

```text
repos.yaml
PROJECT.md
.claude/rules/50-project-architecture.md
.claude/rules/55-project-development.md
```

This installation uses [`abc-andrew/toolkit-workspace`](https://github.com/abc-andrew/toolkit-workspace) as the project template. Its `main` branch inherits the shared base and currently defines two child repositories:

```yaml
version: 1

repos:
  toolkit:
    path: repos/toolkit
    remote: git@abc-andrew.github.com:abc-andrew/toolkit.git
    base: main

  ws:
    path: repos/ws
    remote: git@abc-andrew.github.com:abc-andrew/ws.git
    base: main
```

The base remains reusable because these repository choices exist only in the Toolkit project template.

### 2. Workspace instance

A workspace instance is a branch and Git worktree of the project metarepo. It represents one task, investigation, or stream of work:

```text
toolkit-workspace/
├── .git/              # wtm bare/control repository
├── main/              # golden Toolkit template
├── ws-tooling/        # workspace instance
├── auth-redesign/     # another instance
└── api-research/      # another instance
```

On creation, `ws bootstrap` initializes only:

```text
artifacts/
└── goal.md
```

`goal.md` starts untracked so creating a workspace does not make an unsolicited commit. Commit it to the outer workspace branch when the goal is worth sharing.

Workspace instances do not contain lock files and do not pin coordinated child SHAs. Recreating an instance clones the current base branches from `repos.yaml`. Exact cross-repository reconstruction can be added later if it becomes necessary.

### 3. Independent child repositories

Each entry in `repos.yaml` is cloned under `repos/` as a normal, independent Git repository:

```text
ws-tooling/
├── artifacts/goal.md             # outer metarepo
├── repos.yaml                    # outer metarepo
└── repos/
    ├── toolkit/                  # abc-andrew/toolkit Git repository
    └── ws/                       # abc-andrew/ws Git repository
```

The outer `.gitignore` ignores `repos/*`, so the project metarepo never records child contents. There are no submodules or hidden Git links.

Git ownership is explicit:

- Workspace goals and notes are committed in the outer workspace branch.
- Toolkit changes are committed and pushed from `repos/toolkit`.
- `ws` changes are committed and pushed from `repos/ws`.
- `ws status` must be used because outer `git status` cannot show child changes.

## Installing ws

`ws` requires Python 3 and Git. Install it from a stable clone before creating workspaces, because the wtm hook calls it during worktree creation:

```bash
git clone git@github.com:abc-andrew/ws.git ~/code/ws
ln -s ~/code/ws/bin/ws ~/.local/bin/ws
ws --help
```

The stable installation is independent of any workspace instance. A workspace may contain `repos/ws` for developing the tool, but deleting that workspace must not remove the installed command.

## Creating a project template from the shared base

Create a new private project workspace repository on GitHub, then derive its local history from the base:

```bash
git clone git@github.com:abc-andrew/workspace-base.git my-project-workspace-seed
cd my-project-workspace-seed

git remote rename origin base
git remote add origin git@github.com:OWNER/my-project-workspace.git

# Add repos.yaml, PROJECT.md, and project rules numbered 50–89.
git add .
git commit -m "Configure project workspace"
git push -u origin main
```

Convert the clean checkout to wtm's control-repository layout:

```bash
cd ..
mv my-project-workspace-seed ~/workspaces/my-project-workspace
cd ~/workspaces/my-project-workspace
wtm init
```

The result is:

```text
~/workspaces/my-project-workspace/
├── .git/       # bare/control Git data
└── main/       # golden project template
```

Run `ws bootstrap` once in `main` if the golden worktree should have local child clones. Child contents remain ignored and are not pushed with the metarepo.

## Adding repositories to a project

Edit `repos.yaml` on the project template's `main` branch:

```yaml
version: 1

repos:
  frontend:
    path: repos/frontend
    remote: git@github.com:OWNER/frontend.git
    base: main

  backend:
    path: repos/backend
    remote: git@github.com:OWNER/backend.git
    base: main
```

Then validate and publish the template change:

```bash
cd ~/workspaces/my-project-workspace/main
ws bootstrap
ws doctor
git add repos.yaml PROJECT.md
git commit -m "Add backend to workspace"
git push origin main
```

New workspace instances inherit the updated manifest. Existing instances can merge `main` and run `ws bootstrap` to add missing children.

## Creating and using a workspace

From the wtm control directory:

```bash
cd ~/workspaces/toolkit-workspace
wtm create feature-name --from main --no-shell
cd feature-name
```

wtm creates the outer branch/worktree and runs the checked-in `.wtm/post_create`. That hook invokes:

```bash
ws bootstrap
```

Bootstrap then:

1. reads `repos.yaml`;
2. refreshes local bare mirror caches for efficient clones;
3. clones each missing child repository;
4. checks out its configured base branch;
5. creates a local `workspace/<instance-name>` child branch for task workspaces; and
6. creates `artifacts/goal.md` without overwriting an existing goal.

Inspect the complete workspace with:

```bash
ws status
```

Example shape:

```text
WORKSPACE  ws-tooling

META       ws-tooling  ac86a74b0af9
?? artifacts/goal.md

TOOLKIT    workspace/ws-tooling  a0a8bdde5cd7
  clean

WS         workspace/ws-tooling  18ba3189c5b4
  clean
```

## Repository workflow

Work in each repository according to ownership:

```bash
# Application change
cd repos/toolkit
git add ...
git commit -m "Implement feature"
git push -u origin workspace/feature-name

# Workspace CLI change
cd ../ws
git add ...
git commit -m "Improve workspace status"
git push -u origin workspace/feature-name

# Workspace goal or notes
cd ../..
git add artifacts/goal.md
git commit -m "Document workspace goal"
```

Open and merge pull requests in each child repository independently. The outer workspace branch does not replace those repository workflows.

Before archiving, `ws archive` checks every child repository for:

- uncommitted work; and
- a HEAD commit not represented by any fetched remote branch.

It never pushes child repositories automatically. Once child work is safe, it commits outer artifacts and pushes the workspace branch:

```bash
ws archive
```

## Sharing the base template

Publish `workspace-base/main` and grant projects read access. Project metarepos consume updates through ordinary Git:

```bash
cd ~/workspaces/toolkit-workspace/main
ws update-base
git push origin main
```

`ws update-base` performs the equivalent of:

```bash
git fetch base main
git merge base/main
```

Keep base-owned files stable and make project customization additive to minimize merge conflicts. Shared Claude rules use numbers 00–49; project rules use 50–89.

Multiple project templates can share the same base history:

```text
workspace-base/main
├── toolkit-workspace/main
├── commerce-workspace/main
└── platform-workspace/main
```

Each project chooses its own `repos.yaml` without teaching the base about application repositories.

## Sharing project templates

The project metarepo's `main` branch is the shared golden template. Team members clone/adopt that repository with wtm, then create their own workspace branches from `main`.

Changes that should affect every future instance belong on project `main`, for example:

- repository membership in `repos.yaml`;
- project architecture documentation;
- project-level agent rules; and
- shared workspace conventions specific to that project.

Task goals and temporary investigation notes should stay on workspace-instance branches rather than modifying the golden template.

## Sharing workspace instances for reference

A workspace instance can be shared by committing its outer artifacts and pushing its outer branch:

```bash
git add artifacts/goal.md
git commit -m "Document ws tooling workspace"
git push -u origin ws-tooling
```

Another person can materialize the outer branch from the wtm control directory:

```bash
wtm checkout ws-tooling
```

wtm checks out the branch and runs `.wtm/post_create`; `ws bootstrap` then populates child repositories from the current bases in `repos.yaml`.

This shares the workspace's goal, notes, metarepo history, and repository composition. It does **not** pin child commits. For reference, include child pull-request URLs or branch names in workspace notes when they matter.

## How wtm fits

[wtm](https://github.com/jarredkenny/worktree-manager) manages one project metarepo as a bare/control repository with sibling worktrees:

```text
wtm project/control directory
├── .git/
├── main/
├── task-a/
└── task-b/
```

Useful commands:

```bash
wtm create task-a --from main --no-shell  # new branch and worktree
wtm list                                  # list project worktrees
wtm checkout existing-branch              # materialize a pushed workspace branch
wtm delete task-a --force                  # remove a local worktree
```

The checked-in `.wtm/post_create` is the integration point. Its version comes from the branch used to create or check out the worktree, and it delegates setup to the installed `ws` command.

## How jmux fits

[jmux](https://github.com/jarredkenny/jmux) treats the wtm control directory as a project and its worktrees as sessions/workspaces.

For Toolkit, the conceptual view is:

```text
Toolkit Workspace
├── main
├── ws-tooling
├── auth-redesign
└── api-research
```

Configure a jmux project with the wtm control directory and enable wtm integration:

```json
{
  "projects": [
    {
      "id": "toolkit",
      "title": "Toolkit Workspace",
      "dir": "/Users/andrewnicholson/workspaces/toolkit-workspace",
      "settings": {
        "defaultBaseBranch": "main",
        "wtmIntegration": true,
        "autoLaunchAgent": true,
        "agentCommand": "pi"
      }
    }
  ]
}
```

In jmux, `Ctrl-a n` → select the project → create a worktree runs the same underlying operation as:

```bash
wtm create NAME --from main --no-shell
```

The wtm hook runs `ws bootstrap`, after which jmux opens the resulting worktree and can launch the configured agent. jmux manages terminal sessions and visibility; wtm manages outer Git worktrees; `ws` populates and inspects the independent child repositories.

## Commands

```text
ws bootstrap    clone missing repositories from repos.yaml and create artifacts/goal.md
ws status       aggregate outer and child branch, SHA, dirty, and ahead/behind state
ws archive      verify child safety, commit outer artifacts, and push the workspace branch
ws update-base  fetch and merge base/main into the project metarepo
ws doctor       validate tools, remotes, manifest, ignores, child Git, GitHub, wtm, and jmux
```

## Development

`bin/ws` is the canonical CLI source. Keep it dependency-free and conservative around Git state.

```bash
python3 -m py_compile bin/ws
```

Toolkit Workspace includes this repository at `repos/ws`, so the tool can be developed alongside Toolkit without conflating their Git histories.
