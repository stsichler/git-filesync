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

```console
$ git filesync status
Upstream changes to sync:
  (use "git filesync diff --upstream <file>..." to see what pull would bring)
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
meaningful commit message.

Because each linked file is a real copy committed in your repository, the
repository stays **self-contained**: after a plain clone or checkout every
file is there – unlike with Git submodules, nothing has to be fetched from
other repositories, and neither git-filesync nor access to the upstream repository is
needed to build.

For files another project publishes as **release assets** – a tool binary,
a firmware image, a generated header – there is its sibling
[git-assetsync](https://github.com/stsichler/git-assetsync), built the same
way.

### Compared to Git submodules

| | Git submodules | git-filesync |
|---|---|---|
| Unit | a whole repository, in its own directory | single files, each at any path in your repository |
| What your repository contains | a pointer to a commit in the other repository | a real copy of the file, committed like any other file |
| Local changes | made and committed in the other repository | allowed in your repository as committed adaptations, kept on every sync by a 3-way merge – or forbidden per file (`strict`) |
| Cloning and building | needs `--recurse-submodules` and access to every submodule repository | a plain clone is complete and works on its own, even if an upstream repository is no longer reachable |
| Updating | moves the pointer; your log shows only the new commit id | `pull` per file; the commit contains the actual change, its proposed message lists the upstream commits it brings |
| For everyone else | `git submodule update` after clones, pulls and branch switches | nothing – only whoever syncs needs git-filesync |

Submodules remain the better choice when you want a whole repository
unchanged and work on it directly; git-filesync fits when a few files are
shared, may differ slightly per repository, and your repository should stay
self-contained.

### Compared to vendoring tools

`git subtree` and tools like
[git-vendor](https://github.com/thejoshwolfe/git-vendor) also copy content
into your repository, but always a whole directory (git-vendor: filtered).
git-vendor manages that directory exclusively – files of your own in it are
removed – and discards local changes on update (keeping them as a patch is
experimental there). git-filesync links single files at any path – next to
your own files, under another name if you like – keeps your committed
adaptations by merging, and lists the upstream commits in every sync commit.
To take a whole directory, `add` links all its files (with `--include` /
`--exclude` patterns) in one go; each of them is an ordinary link
afterwards.

## Features

- Links single files between repositories – one by one or all files of a
  upstream directory at once; all links of a repository live in one file,
  `.git-filesync`, at its root (git-config format, like `.gitmodules`)
- Self-contained repositories: linked files are committed copies, so a clone is
  complete without fetching anything from other repositories
- Follows an upstream branch, or is pinned to a tag per file (e.g. a release) –
  with a hint at newer tags – or follows the newest tag matching a pattern
  (`v1.*`); `pull --tag` tries another tag once
- Proposed commit message lists all upstream commits touching the file since
  the last sync
- Local adaptations on top of the upstream version are kept via 3-way merge,
  shown with `diff` / `difftool` – or forbidden per file (`strict`)
- Files renamed upstream are followed, deleted ones reported
- Commands named like Git commands behave like them (`status`, `pull`,
  `diff`, `difftool`, `restore`, `rm`, `mv`); dry runs for `pull`, `add`,
  `rm`, `unlink`, `mv`
- Optional local checkout of the upstream repository instead of fetching – works
  offline; the checkout is only read, never written to
- Uncommitted content that `restore`, `add --overwrite` or `rm -f` discard is
  kept as a blob, with a hint how to get it back
- Git LFS upstream, downstream, both or neither
- Correct with differing line-ending conventions (`core.autocrlf`, `text=auto`)
- Colored output, CI-friendly exit codes, hooks: reminders, and a warning
  when a push refers to upstream commits that aren't pushed yet
- One self-contained Python script, standard library only

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
your `PATH`. Either way the tool is invoked as `git filesync …`; check with
`git filesync --version`. To update, download the script again; the
[releases](https://github.com/stsichler/git-filesync/releases) list the
changes of each version.

You can also clone the repository and point the alias at the script in
it: `main` is the current development state, a tag like `v0.16.0` a
release. Or let git-filesync keep a copy of itself in your project, so
everyone has the same version – see
[Shipping git-filesync with your repository](MANUAL.md#shipping-git-filesync-with-your-repository).

## Quick start

```sh
cd my-repo

# 1. Link a file (once): staged like git add, then committed - git commit
#    offers the proposed message. Without -b the upstream default branch is
#    used, without -p the same path as here.
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
[filesync] Sync src/foo.c from owner/lib@a1b2c3d

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)

Upstream changes since 3f2a9c1:
- Fix off-by-one in buffer handling (9e8d7c6)
- Add support for chunked transfer (a1b2c3d)
```

A `pull` stages all files it syncs, with their entries in `.git-filesync`,
like `git merge --squash`, and proposes one commit message for them; no
git-filesync command commits.

## Commands

Basic commands – what you need day to day:

| Command | Purpose |
|---|---|
| `status [PATH…]` | state of the linked files, like `git status` |
| `pull PATH…`, `pull --all` | sync files from upstream, keeping local adaptations |
| `diff [PATH…]`, `difftool [PATH…]` | local changes against the synced upstream version |
| `restore PATH…` | files back to the synced upstream version, like `git restore` |
| `add URL\|SOURCE FILE\|DIR` | link a file (or all files of an upstream directory) to upstream |
| `rm PATH…`, `unlink PATH…`, `mv OLD NEW` | remove links with their files (like `git rm`) or without, move them |

Advanced commands:

| Command | Purpose |
|---|---|
| `set PATH… OPTIONS` | change source, upstream path or strict of linked files |
| `edit` | edit `.git-filesync` in the editor; checked and staged afterwards |
| `source [ACTION …]` | list and add sources; rename, change URL or branch |
| `source map [URL\|SOURCE [DIR]]` | use a local checkout of the upstream repository instead of fetching |
| `cache [ACTION]` | the cache of upstream clones: show, list, prune, clear |
| `hooks [install\|uninstall]` | hooks for `push` and `merge`: reminders, check that synced upstream commits are pushed |

`git filesync <command> -h` describes a command and lists its options. The
**[manual](MANUAL.md)** describes all commands and options in detail,
along with the `.git-filesync` file, local modifications, strict files,
local checkouts, Git LFS, line endings and CI.

## Development

The whole tool is the single file `git-filesync.py`. Tests:

```sh
test/regress.sh            # Linux/macOS (bash); needs git, python3, git-lfs for the LFS part
```

The script builds throwaway upstream/downstream repositories in a temp directory
and checks linking, status, pull, merge, conflicts, diff / difftool, strict
files, `.git-filesync` handling (sources, unlink, mv, commit consistency),
unsafe registry entries, wildcard characters in file names, local checkout
mappings, offline operation, eol handling (autocrlf /
text=auto / plain), Git LFS in all combinations, colors, hooks, tags,
sources, files renamed or deleted upstream, dry runs and directories – and
after every command that nothing outside the repository was written to (the
upstream repositories are read-only for git-filesync). It runs on every push
via GitHub Actions.

Issues and pull requests are welcome. Please add a test to `test/regress.sh`
for any change in behavior.

## License

[MIT No Attribution (MIT-0)](LICENSE) – free to use, also in commercial and
closed-source projects; no attribution required.

## Acknowledgements

This project – design, code, tests and documentation – was developed together
with [Claude](https://claude.ai) by Anthropic.
