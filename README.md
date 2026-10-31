<img src="doc/logo.svg" alt="" width="128" align="right">

# git-filesync

[![Tests](https://github.com/stsichler/git-filesync/actions/workflows/test.yml/badge.svg)](https://github.com/stsichler/git-filesync/actions/workflows/test.yml)
[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](LICENSE)
![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-blue.svg)
![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)

**Keep individual files in sync between Git repositories.** One repository is
**upstream**, where a file is developed; other repositories (**downstream**)
carry a copy of it and pull updates manually, one file at a time – with a
commit message listing every upstream commit that changed the file since the
last sync.

> **Vibe-coded:** git-filesync is entirely vibe-coded – all of its code, tests
> and documentation were written by [Claude](https://claude.ai) (Anthropic),
> directed by its author. The regression tests run on Linux, macOS and
> Windows on every push.

```console
$ git filesync status
Upstream changes to sync:
  (use "git filesync diff --upstream <file>..." to see what pull would bring)
  (use "git filesync pull <file>..." to sync)
	pending:    src/foo.c  (2 commits)

$ git filesync pull src/foo.c
src/foo.c: synced
src/foo.c: staged. Commit with:
    git commit
(it offers the proposed commit message; a copy stays in .git/FILESYNC_MSG)
```

## Motivation

Helper modules, build scripts or configuration files often live in several
repositories. Copied by hand, soon nobody knows which copy is current, and
the history of the changes is lost. git-filesync links **single files**,
tells you when a copy is behind, and syncs it with a meaningful commit
message.

Each linked file is a real copy committed in your repository, so the
repository stays **self-contained**: a plain clone is complete, and neither
git-filesync nor access to the upstream repository is needed to build.

For files another project publishes as **release assets** – a tool binary,
a firmware image, a generated header – there is the sibling tool
[git-assetsync](https://github.com/stsichler/git-assetsync).

### Compared to Git submodules

| | Git submodules | git-filesync |
|---|---|---|
| Unit | a whole repository, in its own directory | single files, each at any path |
| Your repository contains | a pointer to a commit elsewhere | a real copy of the file |
| Local changes | made in the other repository | exact copy by default; per file allowed (`adaptable`) and kept on every sync by a 3-way merge |
| Cloning and building | needs `--recurse-submodules` and access to every submodule | a plain clone is complete, even if upstream is gone |
| Updating | moves the pointer; your log shows a commit id | `pull` per file; the commit contains the change and lists the upstream commits |
| For everyone else | `git submodule update` after clones, pulls and branch switches | nothing – only whoever syncs needs git-filesync |

Submodules remain the better choice to use a whole repository unchanged and
work on it directly; git-filesync fits when a few files are shared, may
differ slightly per repository, and your repository should stay
self-contained.

### Compared to vendoring tools

`git subtree` and tools like
[git-vendor](https://github.com/thejoshwolfe/git-vendor) copy a whole
directory into your repository; git-vendor manages it exclusively and
discards local changes on update. git-filesync links single files at any
path, next to your own, keeps committed adaptations by merging, and lists
the upstream commits in every sync. A whole directory works too: `add`
links all its files at once.

## Features

- Single files, one by one or all files of an upstream directory; all links
  in one file, `.git-filesync`, in git-config format like `.gitmodules`
- Follows an upstream branch, or per file a tag (with a hint at newer tags)
  or the newest tag matching a pattern (`v1.*`)
- Proposed commit message listing the upstream commits since the last sync
- Exact copies by default; `adaptable` files keep local adaptations through
  a 3-way merge
- Follows files renamed upstream, reports deleted ones
- Commands named like Git commands behave like them; no command commits;
  dry runs
- A local checkout of upstream instead of fetching – works offline, and is
  only read
- Discarded uncommitted content is kept, with a hint how to get it back
- Works with Git LFS on either side and with differing line-ending conventions
- Colored output, exit codes for CI, hooks with reminders and a check that
  synced upstream commits are pushed
- One Python script, standard library only

## Installation

Requirements: Python ≥ 3.7, Git ≥ 2.28, and `git-lfs` if you sync files
stored in Git LFS. Linux, macOS and Windows (Git for Windows).

Download `git-filesync.py` from the
[latest release](https://github.com/stsichler/git-filesync/releases/latest)
and register a global Git alias:

```sh
# Linux / macOS
mkdir -p ~/tools
curl -fsSLo ~/tools/git-filesync.py https://github.com/stsichler/git-filesync/releases/latest/download/git-filesync.py
git config --global alias.filesync '!python3 ~/tools/git-filesync.py'

# Windows (download in the browser or with curl.exe; use forward slashes;
# `py` or `python`, whatever is on PATH)
git config --global alias.filesync "!py C:/tools/git-filesync.py"
```

Alternatively (Linux/macOS) put an executable copy named `git-filesync` on
your `PATH`. Check with `git filesync --version`; to update, download the
script again (the [releases](https://github.com/stsichler/git-filesync/releases)
list the changes). You can also point the alias at a clone of this
repository (`main`, or a tag like `v0.21.1`), or [ship git-filesync with
your repository](MANUAL.md#shipping-git-filesync-with-your-repository).

## Quick start

```sh
cd my-repo

# 1. Link a file (once): staged like git add, then committed - git commit
#    offers the proposed message. Without -b the upstream default branch is
#    used, without -p the same path as here. The directory (src) must exist.
git filesync add https://github.com/owner/lib.git src/foo.c -p lib/foo.c
git commit

# 2. See what needs syncing
git filesync status

# 3. Sync one file: it is staged, git commit offers the proposed message
git filesync pull src/foo.c
git commit
```

Proposed commit message:

```
[filesync] Sync src/foo.c from owner/lib@a1b2c3d (2026-10-28)

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)

Upstream changes since 3f2a9c1 (2026-09-12):
- Fix off-by-one in buffer handling (9e8d7c6, 2026-10-27)
- Add support for chunked transfer (a1b2c3d, 2026-10-28)
```

## Commands

Basic commands – what you need day to day:

| Command | Purpose |
|---|---|
| `status [PATH…]` | state of the linked files, like `git status` |
| `pull PATH…`, `pull --all` | sync files from upstream, keeping local adaptations |
| `diff [PATH…]`, `difftool [PATH…]` | local changes against the synced upstream version |
| `restore PATH…` | files back to the synced upstream version, like `git restore` |
| `add URL\|SOURCE FILE\|DIR` | link a file (or all files of an upstream directory) to upstream |
| `rm PATH…`, `unlink PATH…`, `mv OLD… NEW` | remove links with their files (like `git rm`) or without, move them |

Advanced commands:

| Command | Purpose |
|---|---|
| `set PATH… OPTIONS` | change source, tag, upstream path or adaptable of linked files |
| `edit` | edit `.git-filesync` in the editor; checked and staged afterwards |
| `source [ACTION …]` | list sources; rename, change URL or branch |
| `source map [URL\|SOURCE [DIR]]` | use a local checkout of the upstream repository instead of fetching |
| `cache [ACTION]` | the cache of upstream clones: show, list, prune, clear, print its directory |
| `hooks [install\|uninstall]` | hooks for `push` and `merge`: reminders, check that synced upstream commits are pushed |

`git filesync <command> -h` lists a command's options; the
**[manual](MANUAL.md)** describes everything in detail.

## Development

The whole tool is the single file `git-filesync.py`. Tests:

```sh
test/regress.sh                        # Linux/macOS (bash); needs git, python3, git-lfs for the LFS part
PYTHON=python test/regress.sh          # Windows, in Git Bash
```

The tests build throwaway upstream and downstream repositories and check
every command, also with Git LFS, line-ending conversions, mapped checkouts
and offline – and that nothing outside the repository is ever written. They
run on every push via GitHub Actions.

Issues and pull requests are welcome. Please add a test to `test/regress.sh`
for any change in behavior.

## License

[MIT No Attribution (MIT-0)](LICENSE) – free to use, also in commercial and
closed-source projects; no attribution required.
