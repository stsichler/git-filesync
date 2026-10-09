# git-filesync manual

Detailed description of the concepts, commands and options of git-filesync.
For motivation and installation see the [README](README.md).

## Contents

- [Concepts](#concepts)
  - [Master, slave and links](#master-slave-and-links)
  - [The `.git-filesync` file](#the-git-filesync-file)
  - [Local modifications on top of the master version](#local-modifications-on-top-of-the-master-version)
  - [Strict files](#strict-files)
- [Commands](#commands)
  - [Common options](#common-options)
  - [`status`](#status) · [`pull`](#pull) · [`diff`](#diff) · [`difftool`](#difftool)
  - [`add`](#add) · [`unlink`](#unlink) · [`mv`](#mv) · [`map`](#map)
  - [`install-hooks`, `uninstall-hooks`](#install-hooks-uninstall-hooks)
- [Further topics](#further-topics)
  - [Git LFS](#git-lfs) · [Line endings](#line-endings) · [Offline operation](#offline-operation)
  - [Colors](#colors) · [CI](#ci) · [Exit codes](#exit-codes) · [Binary files](#binary-files)

## Concepts

### Master, slave and links

The **master** is the repository where a file is developed. A **slave** is a
repository that carries a copy of it. The slave records a **link** for each
such file: which master repository and branch, which path there, and which
master version the copy is based on. Updates are never applied
automatically – `pull` syncs one file at a time, with a commit message that
lists every master commit that changed the file since the last sync.

All commands run inside the slave repository.

### The `.git-filesync` file

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
  or not – don't matter.
- Everything else may be edited by hand, e.g. when a file was renamed in the
  master: `git config -f .git-filesync file.src/foo.c.path lib/new_name.c`.
- When the last link is removed, the file is deleted.
- File paths must lie inside the working tree. Entries pointing outside it
  (`..`, absolute paths) or into a `.git` directory are reported as errors
  and never written – a cloned repository's `.git-filesync` can't make
  `pull` touch other files.

### Local modifications on top of the master version

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
**uncommitted changes** – `status` shows both separately. `pull` keeps
adaptations by merging them with the new master version, and – like
`git pull` – refuses files with uncommitted changes (see [`pull`](#pull)).
`diff` and `difftool` show both kinds (see [`diff`](#diff)).

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

## Commands

| Command | Purpose |
|---|---|
| [`status [PATH…]`](#status) | state of the linked files, like `git status` |
| [`pull PATH…`, `pull --all`](#pull) | sync files from the master |
| [`diff [PATH…] [-- OPTS]`](#diff) | local changes against the synced master version |
| [`difftool [PATH…] [-- OPTS]`](#difftool) | the same in your difftool |
| [`add FILE URL\|SOURCE`](#add) | link a file to a file in a master repository |
| [`unlink PATH…`](#unlink) | remove links, keep the files |
| [`mv OLD NEW`](#mv) | move a linked file and its link |
| [`map [URL [DIR]]`](#map) | use a local checkout of the master |
| [`install-hooks`, `uninstall-hooks`](#install-hooks-uninstall-hooks) | reminder hooks |

Commands named like a Git command behave like it (`status`, `pull`, `diff`,
`difftool`, `mv`): same kind of output, same exit codes, same caution with
uncommitted changes. `git filesync` without a command runs `status`.

Paths are relative to the current directory. Where `PATH…` is accepted, a
directory stands for all linked files below it. Options follow the command
(`git filesync status --no-fetch`); `git filesync <command> -h` lists them.

### Common options

| Option | Commands | Effect |
|---|---|---|
| `--no-fetch` | `status`, `pull`, `diff`, `difftool`, `add` | don't fetch, use the cached state (offline) |
| `--remote` | same | ignore local checkout mappings (see [`map`](#map)) |
| `--color[=always\|never\|auto]`, `--no-color` | all | override `color.filesync` / `color.ui` (see [Colors](#colors)) |

### `status`

`status [PATH…]` – state of all (or the given) linked files.

| Option | Effect |
|---|---|
| `-s`, `--short` | short format, three columns |
| `-v`, `--verbose` | also list every linked file with its source |
| `--exit-code` | exit with 1 if something is to sync or a strict file is modified |
| `--hook` | terse output on stderr, used by the [reminder hooks](#install-hooks-uninstall-hooks) |

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
off by `advice.statusHints = false`. Warnings (e.g. about a mapped checkout)
follow in a `Warnings:` section.

**Short format** (`-s`), like `git status -s`, one line per file that has
something to report, with three columns:

| Column | Meaning |
|---|---|
| 1 – upstream | `P` pending, `O` master branch older than last sync, `D` history diverged or previous sync point unknown, `N` not in the working tree yet, `E` error |
| 2 – committed | `A` adapted |
| 3 – working tree | `M` modified, `D` deleted, `?` not committed yet |

```
P   src/a.c
PA  src/b.c
 AM src/c.c
 A  include/x.h  (strict!)
```

Like `git status`, the exit code is 0 (2 on errors); `--exit-code` makes it
1 when something is to sync or a strict file is modified (for scripts and
[CI](#ci)).

### `pull`

`pull PATH…`, `pull --all` – sync to the master's current version of the
file: the version on the source's branch (with a [local checkout](#map):
that checkout's branch). Recorded is the master commit that last changed the
file. The editor opens with the proposed commit message:

```
Sync src/foo.c from owner/lib@a1b2c3d

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)

Upstream changes since 3f2a9c1:
- Fix off-by-one in buffer handling (9e8d7c6)
- Add support for chunked transfer (a1b2c3d)
```

Each sync commit contains the file and its updated entry in `.git-filesync`.

| Option | Effect |
|---|---|
| `--all` | all linked files with something to sync |
| `--commit REV` | sync to this master revision instead – branch, tag or commit id, also backwards; exactly one file |
| `--overwrite` | discard local adaptations and take the master version as is (also when the file is up to date) |
| `--autostash` | set uncommitted changes aside, sync, re-apply them |
| `--no-edit` | commit with the proposed message without opening the editor |
| `--no-commit` | only update and stage the file and its entry; prints the `git commit` command |

**Adaptations** are merged with the new master version (3-way merge, base =
the last synced version). On conflicts the file gets the usual conflict
markers; resolve them, then run the `git add` / `git commit -e -F …` command
printed by the tool – the prepared message is kept in `.git/FILESYNC_MSG_*`.
`--overwrite` skips the merge and discards the adaptations.

**Uncommitted changes:** like `git pull`, `pull` refuses a file with
uncommitted changes (`your local changes … would be overwritten by pull`):
commit or stash them first. `--autostash` sets them aside, syncs (the sync
commit contains only the synced version) and re-applies them to the working
file. This works for modified files, not for deleted or not yet committed
ones. If the sync itself ends in conflicts, the stashed version is not
re-applied but kept in `.git/FILESYNC_STASH_*`.

**Revisions:** `--commit` accepts branch names (`develop` means the master's
current `develop`), tags and commit ids. Recorded is the commit that last
changed the file up to that revision. Going back to an older version works
the same way; the commit message then lists what is reverted.

**Other entries in `.git-filesync`:** because all links share one file, a
sync commit must not pick up uncommitted entries of *other* files (that
commit would record their new state without their content). `pull`
therefore refuses to commit while `.git-filesync` has uncommitted changes
for other files – commit those first (e.g. after `add`), or use
`--no-commit` to stage everything and commit it together.

With `--all`, a file that can't be synced (conflict, strict violation, …) is
reported and the other files are still synced.

### `diff`

`diff [PATH…] [-- OPTS]` – local changes against the synced master version.

| Option | Effect |
|---|---|
| `--committed` | only the committed adaptations (synced → `HEAD`) |
| `--upstream` | what `pull` would bring (synced → current master) |
| `--master-paths` | name files by their master path, for `git apply` in the master |

```sh
git filesync diff                    # all local changes: synced master version -> working file
git filesync diff --committed        # adaptations only: synced master version -> HEAD
git filesync diff --upstream         # what `pull` would bring: synced -> current master
git filesync diff -- --stat          # anything after `--` goes to `git diff`
```

Without file arguments all linked files are covered. `diff` runs a single
`git diff` in the slave repository, so pager, colors and diff options work as
usual. With `--exit-code` or `--quiet` after `--`, exit code 1 means
differences, like `git diff`.

**Upstreaming local changes:** `--master-paths` names the files by their
path in the master, giving a patch that can be applied there:

```sh
git filesync diff --master-paths src/foo.c > foo.patch
cd ~/src/lib && git apply -3 ../slave-repo/foo.patch
```

`-3` uses the base version recorded in the patch, so it also works when the
master has moved on in the meantime.

### `difftool`

`difftool [PATH…] [-- OPTS]` – the same as [`diff`](#diff), file by file in
your difftool (`diff.tool`); `OPTS` go to `git difftool` (e.g. `-t meld`).

| Option | Effect |
|---|---|
| `--committed`, `--upstream` | as for `diff` |
| `-y`, `--no-prompt` | don't ask before each file |
| `--prompt` | ask even for explicitly given files |

Without `--upstream` / `--committed`, the right side is the real working
file, so edits made in the tool are kept.

Like `git difftool`, `difftool` without file arguments asks before each file
(`Viewing (1/3): 'src/foo.c'` / `Launch 'meld' [Y/n/q]?`; Enter = yes,
`q` = stop). `-y` / `--no-prompt` or `difftool.prompt = false` skip the
questions, `--prompt` asks even for explicitly given files.

### `add`

`add FILE URL|SOURCE` – link FILE to a file in a master repository, given by
its URL or by the name of a `[source]` already in `.git-filesync`.

| Option | Effect |
|---|---|
| `-b`, `--branch BRANCH` | master branch; default: the master's default branch, or the branch of the given `[source]` |
| `-p`, `--path PATH` | path in the master; default: the same as FILE |
| `--commit REV` | master revision FILE corresponds to, instead of looking it up |
| `--strict` | the file must stay an exact copy (see [Strict files](#strict-files)) |
| `--force` | relink a file that is already linked |

- If FILE exists, the master version it matches is looked up and recorded
  as its base. If none matches, the branch head is taken (with a warning) and
  the differences count as adaptations; `--commit` chooses a better base.
- If FILE doesn't exist, it is fetched from the master.
- `.git-filesync` and a fetched file are staged – commit when ready.

```sh
git filesync add src/foo.c https://github.com/owner/lib.git -p lib/foo.c
git filesync add include/bar.h lib --strict     # reuse [source "lib"]
```

### `unlink`

`unlink PATH…` – remove the links; the files themselves are kept.
`.git-filesync` is staged.

### `mv`

`mv OLD NEW` – move a linked file (`git mv`) and its link together; NEW may
be an existing directory. Both are staged.

### `map`

`map [URL [DIR]]` – use the local checkout DIR instead of fetching the master
URL. Without DIR, the mappings are listed (only those for URL, if given).

| Option | Effect |
|---|---|
| `--global` | in your global Git config, for all repositories (default: this repository's config) |
| `--unset` | remove the mapping for URL |

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

### `install-hooks`, `uninstall-hooks`

`install-hooks` adds a `pre-push` hook (fetches and warns) and a
`post-merge` hook (cached state only). They report pending syncs, errors and
strict violations, and never block. If a hook already exists, the lines to
add are printed instead. With `core.hooksPath` set, the hooks go there (with
a warning, as other repositories may share that directory).

`uninstall-hooks` deletes hook files that only contain the git-filesync
lines; from other hooks it removes just those lines.

## Further topics

### Git LFS

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

### Line endings

Master and slave may normalize differently (e.g. CRLF committed in the
master, `core.autocrlf` or `text=auto` in the slave). The master's content is
always compared and merged in the form the slave would store it, and written
as a checkout of the slave would produce it – no false "local
modifications", no eol-only conflicts.

### Offline operation

With a [mapped local checkout](#map), all commands work without network
access (`add` takes the default branch from the checkout's `origin/HEAD`,
or – with a warning if the checkout has a remote – from the branch checked
out there). Without a mapping, the cache is used after a failed fetch; file
versions never read before may be missing there (blobless clone): `status`
then warns and counts the file as modified, `pull --overwrite` brings it back
to a known state. `--no-fetch` skips the network explicitly.

### Colors

Output is colored like `git status`: pending upstream changes yellow,
adaptations cyan (information, not a problem), uncommitted changes red,
strict violations and errors bold red.

Colors follow `color.filesync`, falling back to `color.ui` (default: on for
terminals); `--color[=always|never|auto]` and `--no-color` override that,
and `NO_COLOR` turns colors off. Hook output on stderr is colored the same
way. `diff` is colored by `git diff` itself.

### CI

A scheduled job in the slave repo fails when a sync is pending
(`status --exit-code`), so e.g. GitHub notifies you:

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
      - run: curl -fsSLo /tmp/git-filesync.py https://raw.githubusercontent.com/stsichler/git-filesync/main/git-filesync.py
      - run: python3 /tmp/git-filesync.py status --exit-code
```

(For private master repositories the job needs a token with read access.)

### Exit codes

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | unfinished: `pull` with conflicts or without commit; `status --exit-code` with something to sync or a strict violation; `diff -- --exit-code` with differences |
| `2` | error |

### Binary files

Binary files can be synced, but not merged with local modifications.
