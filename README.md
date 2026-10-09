# git-filesync

[![Tests](https://github.com/stsichler/git-filesync/actions/workflows/test.yml/badge.svg)](https://github.com/stsichler/git-filesync/actions/workflows/test.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](LICENSE)
![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-blue.svg)
![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)

**Keep individual files in sync between Git repositories.** One repository is
the **master** where a file is developed; other repositories (**slaves**)
carry a copy of it and pull updates manually, one file at a time – with a
commit message listing every master commit that changed the file since the
last sync.

```console
$ git filesync status
Upstream changes to sync:
  (use "git filesync pull <file>..." to sync)
	pending:    src/foo.c  (2 commits)

$ git filesync pull src/foo.c
[main 4f1c2a9] Sync src/foo.c from owner/lib@a1b2c3d
 2 files changed, 3 insertions(+), 3 deletions(-)
```

## Why?

Helper modules, build scripts or configuration files often live in several
repositories at once. Copying them by hand works – until nobody knows which
copy is current and the history of the changes is lost. git-filesync links
**single files**, tells you when a copy is behind, and syncs it with a
meaningful commit.

### Compared to Git submodules

| | Git submodules | git-filesync |
|---|---|---|
| Unit | a whole repository, in its own directory | single files, each at any path in your repository |
| What your repository contains | a pointer to a commit in the other repository | a real copy of the file, committed like any other file |
| Local changes | made and committed in the other repository | allowed in your repository as committed adaptations, kept on every sync by a 3-way merge – or forbidden per file (`strict`) |
| Cloning and building | needs `--recurse-submodules` and access to every submodule repository | a plain clone is complete and works on its own, even if a master repository is no longer reachable |
| Updating | moves the pointer; your log shows only the new commit id | `pull` per file; the commit contains the actual change and lists the master commits it brings |
| For everyone else | `git submodule update` after clones, pulls and branch switches | nothing – only whoever syncs needs git-filesync |

Submodules remain the better choice when you want a whole repository
unchanged and work on it directly; git-filesync fits when a few files are
shared, may differ slightly per repository, and your repository should stay
self-contained. (`git subtree` also copies content, but always a whole
directory, and it has no per-file view of what is behind or adapted.)

## Features

- Links single files between repositories; all links of a slave live in one
  file, `.git-filesync`, at its root (git-config format, like `.gitmodules`)
- Proposed commit message lists all master commits touching the file since
  the last sync
- Local adaptations on top of the master version are kept via 3-way merge,
  shown with `diff` / `difftool` – or forbidden per file (`strict`)
- Commands named like Git commands behave like them (`status`, `pull`,
  `diff`, `difftool`, `mv`)
- Optional local checkout of the master instead of fetching – works offline
- Git LFS in the master, the slave, both or neither
- Correct with differing line-ending conventions (`core.autocrlf`, `text=auto`)
- Colored output, reminder hooks, CI-friendly exit codes
- One self-contained Python script, standard library only

## Installation

Requirements: Python ≥ 3.7, Git ≥ 2.26, and `git-lfs` if you sync files
stored in Git LFS. Linux, macOS and Windows (Git for Windows).

Clone the repository and register a global Git alias:

```sh
git clone https://github.com/stsichler/git-filesync.git ~/tools/git-filesync

# Linux / macOS
git config --global alias.filesync '!python3 ~/tools/git-filesync/git-filesync.py'

# Windows (use forward slashes; `py` or `python`, whatever is on PATH)
git config --global alias.filesync "!py C:/tools/git-filesync/git-filesync.py"
```

Alternatively (Linux/macOS) put an executable copy named `git-filesync` on
your `PATH`. Either way the tool is invoked as `git filesync …`; check with
`git filesync --version`.

## Quick start

```sh
cd slave-repo

# 1. Link a file (once). Without -b the master's default branch is used,
#    without -p the same path as in the slave repo.
git filesync add src/foo.c https://github.com/owner/lib.git -p lib/foo.c
git commit -m "Link src/foo.c to owner/lib"

# 2. See what needs syncing
git filesync status

# 3. Sync one file – the editor opens with the proposed commit message
git filesync pull src/foo.c
```

Proposed commit message:

```
Sync src/foo.c from owner/lib@a1b2c3d

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)

Upstream changes since 3f2a9c1:
- Fix off-by-one in buffer handling (9e8d7c6)
- Add support for chunked transfer (a1b2c3d)
```

Each sync commit contains the file and its updated entry in `.git-filesync`.

## Commands

| Command | Purpose |
|---|---|
| `status [PATH…]` | state of the linked files, like `git status` |
| `pull PATH…`, `pull --all` | sync files from the master, keeping local adaptations |
| `diff [PATH…]`, `difftool [PATH…]` | local changes against the synced master version |
| `add FILE URL\|SOURCE` | link a file to a file in a master repository |
| `unlink PATH…`, `mv OLD NEW` | remove or move links |
| `map [URL [DIR]]` | use a local checkout of the master instead of fetching |
| `install-hooks`, `uninstall-hooks` | reminder hooks for `push` and `merge` |

`git filesync <command> -h` lists the options of a command. The
**[manual](MANUAL.md)** describes all commands and options in detail,
along with the `.git-filesync` file, local modifications, strict files,
local checkouts, Git LFS, line endings and CI.

## Development

The whole tool is the single file `git-filesync.py`. Tests:

```sh
test/regress.sh            # Linux/macOS (bash); needs git, python3, git-lfs for the LFS part
```

The script builds throwaway master/slave repositories in a temp directory
and checks linking, status, pull, merge, conflicts, diff / difftool, strict
files, `.git-filesync` handling (sources, unlink, mv, commit consistency),
unsafe registry entries, wildcard characters in file names, local checkout
mappings, offline operation, eol handling (autocrlf /
text=auto / plain), Git LFS in all combinations, colors and hooks. It runs on
every push via GitHub Actions.

Issues and pull requests are welcome. Please add a test to `test/regress.sh`
for any change in behavior.

## License

[MIT No Attribution (MIT-0)](LICENSE) – free to use, also in commercial and
closed-source projects; no attribution required.

## Acknowledgements

This project – design, code, tests and documentation – was developed together
with [Claude](https://claude.ai) by Anthropic.
