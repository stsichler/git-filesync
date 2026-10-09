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

## Contents

- [Why?](#why)
- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The `.git-filesync` file](#the-git-filesync-file)
- [Status](#status)
- [Local modifications on top of the master version](#local-modifications-on-top-of-the-master-version)
- [Local checkout of the master](#local-checkout-of-the-master-optional)
- [Git LFS](#git-lfs) · [Colors](#colors) · [Reminders](#reminders) · [Notes](#notes)
- [Development](#development) · [License](#license) · [Acknowledgements](#acknowledgements)

## Why?

Helper modules, build scripts or configuration files often live in several
repositories at once. Copying them by hand works – until nobody knows which
copy is current and the history of the changes is lost. Submodules and
subtrees only handle whole repositories or directories. git-filesync links
**single files**, tells you when a copy is behind, and syncs it with a
meaningful commit.

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

# 1. Link a file (once). Without -b the remote's default branch is used,
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

### Commands

Commands named like a Git command behave like it (`status`, `pull`, `diff`,
`difftool`, `mv`): same kind of output, same exit codes, same caution with
uncommitted changes.

| Command | Purpose |
|---|---|
| `status [-s] [-v] [--exit-code] [PATH…]` | State of all (or the given) linked files, in sections like `git status` (see below). `--hook` for terse hook output. |
| `pull FILE…` / `pull --all` | Sync to the master branch head. Refuses files with uncommitted changes like `git pull`; `--autostash` sets them aside and re-applies them. `--commit REV` syncs to a specific revision (also backwards). `--overwrite` discards local adaptations. `--no-edit`, `--no-commit`. |
| `diff [--upstream\|--committed] [--master-paths] [FILE…] [-- OPTS]` | Local changes against the synced master version; `--committed`: only the committed adaptations; `--upstream`: what `pull` would bring. |
| `difftool [--upstream\|--committed] [-y] [--prompt] [FILE…] [-- OPTS]` | The same in your configured difftool; asks before each file when no files are given. |
| `add FILE URL\|SOURCE [-b BRANCH] [-p PATH] [--commit REV] [--strict]` | Link a file. Takes a master URL or the name of a `[source]` already in `.git-filesync`. If FILE exists, the matching master version is detected automatically. |
| `unlink FILE…` | Remove links; the files themselves are kept. |
| `mv OLD NEW` | Move a linked file (`git mv`) and its link together. |
| `map [URL [DIR]] [--unset] [--global]` | Use a local checkout of the master repository; per repo by default (see below). |
| `install-hooks` / `uninstall-hooks` | Install / remove `pre-push` and `post-merge` reminder hooks. |

Common options: `--no-fetch` (use cached state, offline), `--remote` (ignore
local checkout mappings), `--color[=always|never|auto]` / `--no-color`.

## The `.git-filesync` file

Lives at the root of the slave repository and is committed like any other
file. Git-config format:

```ini
[source "lib"]
	url = https://github.com/owner/lib.git
	branch = main
[file "src/foo.c"]
	source = lib
	path = lib/foo.c       # path in the master
	commit = 3f2a9c1e…     # master commit the synced version comes from
	blob = 8d01b7aa…       # master's file at that commit
[file "include/bar.h"]
	source = lib
	path = include/bar.h
	strict = true          # optional, see below
	commit = …
	blob = …
```

- A `[source]` names a master repository and branch once; `add` reuses an
  existing source for the same URL and branch and creates one otherwise.
- `[file]` sections are keyed by the path in the slave repository.
- `commit` and `blob` are maintained by the tool: `blob` is the synced
  version of the master's file, `commit` the master commit that last changed
  it (not the branch tip at sync time). One file version thus always gives
  the same entry, and commits that don't touch the file – unpushed, rebased
  or not – don't matter. Everything else may be edited by hand, e.g. when a file was renamed in the master:
  `git config -f .git-filesync file.src/foo.c.path lib/new_name.c`.
- When the last link is removed, the file is deleted.
- File paths must lie inside the working tree. Entries pointing outside it
  (`..`, absolute paths) or into a `.git` directory are reported as errors
  and never written – a cloned repository's `.git-filesync` can't make
  `pull` touch other files.

Because all links share one file, a sync commit must not pick up uncommitted
entries of *other* files (that commit would record their new state without
their content). `pull` therefore refuses to commit while `.git-filesync` has
uncommitted changes for other files – commit those first (e.g. after `add`),
or use `--no-commit` to stage everything and commit it together.

## Status

`status` looks at each linked file in three independent respects:

| Respect | Compares | States |
|---|---|---|
| upstream | synced master version ↔ current master | up to date, `pending`, `older`, `changed`, `new` |
| committed | synced master version ↔ committed file (`HEAD`) | `unmodified`, `adapted` |
| working tree | committed file ↔ working file | clean, `modified`, `deleted`, `new file` |

and reports them in sections like `git status`:

```
Upstream changes to sync:
  (use "git filesync pull <file>..." to sync)
	pending:    src/foo.c  (2 commits)

Locally adapted files:
  (use "git filesync diff --committed <file>..." to see the adaptations)
  (use "git filesync pull --overwrite <file>..." to discard them)
	adapted:    include/x.h  (NOT ALLOWED: strict)
	adapted:    src/foo.c

Uncommitted changes:
  (use "git filesync diff <file>..." to see all local changes)
  (use "git restore <file>..." to discard uncommitted changes)
	modified:   src/bar.c
```

Without anything to report: `nothing to sync, all 5 linked files
unmodified`. Paths are shown relative to the current directory. `-v` adds a
`Linked files:` section with every file and its source; the hints are turned
off by `advice.statusHints = false`.

**Short format** (`-s`), like `git status -s`, one line per file that has
something to report, with three columns:

| Column | Meaning |
|---|---|
| 1 – upstream | `P` pending, `O` master branch older than last sync, `D` history diverged, `N` not in the working tree yet, `E` error |
| 2 – committed | `A` adapted |
| 3 – working tree | `M` modified, `D` deleted, `?` not committed yet |

```
P   src/a.c
PA  src/b.c
 AM src/c.c
 A  include/x.h  (strict!)
```

Like `git status`, the exit code is 0; `--exit-code` makes it 1 when
something is to sync or a strict file is modified (for scripts and CI).

## Local modifications on top of the master version

The file in the slave doesn't have to be identical to the master version: it
may carry local adaptations. Its entry in `.git-filesync` records the
**base** of the file – "this file is based on master commit X" – not its
content. Since file and entry are always committed together, every slave
commit precisely defines the local layer: file content minus the master
version named in the entry.

```
  master version (entry: commit X)  +  local modifications  =  file in the slave
```

Committed local changes are **adaptations**; changes not committed yet are
**uncommitted changes** – `status` shows both separately.

- `pull` merges adaptations with the new master version (3-way merge, base =
  the last synced version). On conflicts the file gets the usual conflict
  markers; resolve them, then run the `git add` / `git commit -e -F …` command
  printed by the tool – the prepared message is kept in `.git/FILESYNC_MSG_*`.
- Like `git pull`, `pull` refuses a file with **uncommitted changes**
  (`your local changes … would be overwritten by pull`): commit or stash
  them first. `pull --autostash` sets them aside, syncs (the sync commit
  contains only the synced version) and re-applies them to the working file.
- `pull --overwrite` discards the adaptations and takes the master version as
  is.

### Seeing the differences

```sh
git filesync diff                    # all local changes: synced master version -> working file
git filesync diff --committed        # adaptations only: synced master version -> HEAD
git filesync diff --upstream         # what `pull` would bring: synced -> current master
git filesync diff -- --stat          # anything after `--` goes to `git diff`
git filesync difftool src/foo.c      # same in your difftool (diff.tool)
```

Without file arguments all linked files are covered. `diff` runs a single
`git diff` in the slave repository, so pager, colors and diff options work as
usual. `difftool` opens the real working file on the right side, so edits
made in the tool are kept.

Like `git difftool`, `difftool` without file arguments asks before each file
(`Viewing (1/3): 'src/foo.c'` / `Launch 'meld' [Y/n/q]?`; Enter = yes,
`q` = stop). `-y` / `--no-prompt` or `difftool.prompt = false` skip the
questions, `--prompt` asks even for explicitly given files.

**Upstreaming local changes:** `diff --master-paths` names the files by their
path in the master, giving a patch that can be applied there:

```sh
git filesync diff --master-paths src/foo.c > foo.patch
cd ~/src/lib && git apply -3 ../slave-repo/foo.patch
```

`-3` uses the base version recorded in the patch, so it also works when the
master has moved on in the meantime.

### Strict files

Some files should stay exact copies. Mark them with `add --strict` or

```sh
git config -f .git-filesync file.src/foo.c.strict true
```

(As everywhere in git config, a bare `strict` without a value means true.)

For a strict file, adaptations as well as uncommitted changes are reported
as a violation: `status` marks them `NOT ALLOWED: strict` (`-s`: `(strict!)`,
`--exit-code`: 1), the hooks report it, and `pull` refuses to merge (other
files of `pull --all` are still synced). Inspect with `diff`, then discard
adaptations with `pull --overwrite`, uncommitted changes with `git restore`,
or lift the restriction (`strict = false`).

## Local checkout of the master (optional)

```sh
cd slave-repo
git filesync map https://github.com/owner/lib.git ~/src/lib
```

This writes `filesync.<url>.localpath` into the **slave repository's own
config** (`.git/config`). Different slaves can thus point to different
checkouts of the same master – e.g. one at the newest state, another at an
older one until its own code has been adapted.

With `--global` the mapping goes into your global Git config and applies to
all repositories without a mapping of their own; a repository's own mapping
always takes precedence.

```sh
git filesync map                     # list mappings (scope, overridden ones marked)
git filesync map URL --unset         # remove this repo's mapping
git filesync map --global URL --unset
```

When mapped, `status` and `pull` use the source's branch **as it is in that
checkout** – its local branch, including commits not yet pushed – no matter
which branch is currently checked out there. Nothing is fetched; all of this
works offline.

- local branch ahead of the last sync → `N upstream commit(s) pending`
- local branch older than the last sync (e.g. reset) → `master branch is N
  commit(s) older than last sync`; `pull` goes back to it and the commit
  message lists what is reverted
- a different branch checked out in the checkout, with a different version
  of the file → warning (that version is *not* synced)
- uncommitted changes to the file in the checkout → warning (only committed
  states are synced)
- the file's version comes from an unpushed commit → warning, because
  other machines can't resolve that commit (unpushed commits that don't
  touch the file don't matter)
- no local branch of that name in the checkout → `origin/<branch>` as last
  fetched there is used, with a note

`--remote` bypasses the mapping.

Without a mapping, `status` and `pull` work against the master repository on
the server. It is cached as a blobless partial clone in `~/.cache/git-filesync`
(Windows: `%LOCALAPPDATA%\git-filesync`, override with `FILESYNC_CACHE`) and
fetched on each run. Credentials are whatever your Git uses for that URL.

## Git LFS

Whether a synced file is stored in Git LFS in the master, in the slave, in
both or in neither doesn't matter:

- Master side: LFS pointers are resolved to the real content (`git lfs
  smudge` in the mapped checkout or the cache; the content comes from the
  local LFS store or the master's LFS server). Comparisons against a master
  file in LFS use the pointer's SHA-256, so no download is needed to tell
  whether the slave's copy is unmodified.
- Slave side: the file is written as real content and stored the way the
  slave's `.gitattributes` say – as an LFS object if it is tracked there,
  as a regular blob otherwise.
- `diff`, `difftool` and merges always work on the real content.

If LFS content can't be retrieved (git-lfs missing, LFS server unreachable,
`GIT_LFS_SKIP_SMUDGE`), the command fails with a clear message instead of
writing a pointer file.

## Colors

Output is colored like `git status`: pending upstream changes yellow,
adaptations cyan (information, not a problem), uncommitted changes red,
strict violations and errors bold red.

Colors follow `color.filesync`, falling back to `color.ui` (default: on for
terminals); `--color[=always|never|auto]` and `--no-color` override that,
and `NO_COLOR` turns colors off. Hook output on stderr is colored the same
way. `diff` is colored by `git diff` itself.

## Reminders

**Hooks:** `git filesync install-hooks` adds a `pre-push` hook (fetches and
warns) and a `post-merge` hook (cached state only). They report pending
syncs, errors and strict violations, and never block. If a hook already
exists, the lines to add are printed instead. `git filesync uninstall-hooks`
deletes hook files that only contain the git-filesync lines; from other hooks
it removes just those lines.

**CI (GitHub Actions):** a scheduled job in the slave repo fails when a sync is
pending (`status --exit-code`), so GitHub notifies you:

```yaml
name: filesync
on:
  schedule: [{ cron: "23 6 * * 1" }]
  workflow_dispatch:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl -fsSLo /tmp/git-filesync.py https://raw.githubusercontent.com/OWNER/git-filesync/main/git-filesync.py
      - run: python3 /tmp/git-filesync.py status --exit-code
```

(For private master repositories the job needs a token with read access.)

## Notes

- Line endings: master and slave may normalize differently (e.g. CRLF
  committed in the master, `core.autocrlf` or `text=auto` in the slave). The
  master's content is always compared and merged in the form the slave would
  store it, and written as a checkout of the slave would produce it – no
  false "local modifications", no eol-only conflicts.
- `--commit` accepts branch names (`develop` means the master's current
  `develop`), tags and commit ids. Recorded is the commit that last changed
  the file up to that revision.
- Offline: with a mapped local checkout, all commands work without network
  access (`add` takes the default branch from the checkout's `origin/HEAD`,
  or – with a warning if the checkout has a remote – from the branch checked
  out there). Without a mapping, the cache is used after a failed fetch; file
  versions never read before may be missing there (blobless clone): `status`
  then warns and counts the file as modified, `pull --overwrite` brings it
  back to a known state. `--no-fetch` skips the network explicitly.
- Exit codes: `0` ok, `1` unfinished (`pull` with conflicts or without
  commit; `status --exit-code` with something to sync or a strict violation;
  `diff -- --exit-code` with differences), `2` error.
- Binary files can be synced, but not merged with local modifications.

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
