# git-filesync manual

Detailed description of the concepts, commands and options of git-filesync.
For motivation and installation see the [README](README.md).

## Contents

- [Concepts](#concepts)
  - [Upstream, downstream and links](#upstream-downstream-and-links)
  - [The `.git-filesync` file](#the-git-filesync-file)
  - [Exact copies and adaptable files](#exact-copies-and-adaptable-files)
  - [Local modifications on top of the upstream version](#local-modifications-on-top-of-the-upstream-version)
- [Commands](#commands)
  - [Common options](#common-options)
  - [`status`](#status) · [`pull`](#pull) · [`diff`](#diff) · [`difftool`](#difftool) · [`restore`](#restore)
  - [`add`](#add) · [`rm`](#rm) · [`unlink`](#unlink) · [`mv`](#mv)
- [Advanced commands](#advanced-commands)
  - [`set`](#set) · [`edit`](#edit) · [`source`](#source) · [`source map`](#source-map) · [`cache`](#cache)
  - [`hooks`](#hooks)
- [Further topics](#further-topics)
  - [Pinning to a tag](#pinning-to-a-tag) · [Proposed commit messages](#proposed-commit-messages) · [Files renamed or deleted upstream](#files-renamed-or-deleted-upstream)
  - [Git LFS](#git-lfs) · [Line endings](#line-endings) · [Offline operation](#offline-operation)
  - [Colors](#colors) · [CI](#ci) · [Exit codes](#exit-codes) · [Binary files](#binary-files) · [Windows](#windows)
  - [Shipping git-filesync with your repository](#shipping-git-filesync-with-your-repository)

## Concepts

### Upstream, downstream and links

The **upstream repository** (short: upstream) is where a file is developed.
A **downstream repository** carries a copy of it and records a **link** for
each such file: which upstream repository and branch (or tag), which path
there, and which upstream version the copy is based on. Updates are never applied
automatically – `pull` syncs the files you choose and proposes a commit
message that lists every upstream commit that changed each file since the
last sync.

All commands run inside the downstream repository.

### The `.git-filesync` file

Lives at the root of the downstream repository and is committed like any other
file. Git-config format:

```ini
[source "owner/lib"]
	url = https://github.com/owner/lib.git
	branch = main
[file "src/foo.c"]
	source = owner/lib
	path = lib/foo.c       # path upstream
	commit = 3f2a9c1e…     # upstream commit the synced version comes from
	blob = 8d01b7aa…       # the upstream file at that commit
[file "include/bar.h"]
	source = owner/lib
	path = include/bar.h
	adaptable = true       # optional, see below
	commit = …
	blob = …
[file "cfg/x.yml"]
	source = owner/lib
	path = cfg/x.yml
	tag = v1.2.0           # optional: pinned to a tag instead of following the branch
	commit = …
	blob = …
```

- A `[source]` names an upstream repository and the branch its files follow,
  like a remote with its branch. `add` with a URL reuses an existing source
  only if URL *and* branch match, and creates one otherwise; `add` with the
  name of a source uses exactly that source. A new source is named
  `owner/repo` after its URL; if that name is already taken by another URL
  or branch, a number is appended (`owner/repo-2`, …). Rename it with
  [`source rename`](#source); `status`, `add` and the commit messages of
  `pull` show it.
- `[file]` sections are keyed by the path in the downstream repository. A
  `tag` in one [pins](#pinning-to-a-tag) that file to an upstream tag (or
  the newest tag matching a pattern); the source's branch is then where
  [newer tags](#newer-tags) are looked for. Up to 0.13 the tag was a key of
  the `[source]`; such an entry is now an error, to be fixed by hand.
- `commit` and `blob` are maintained by the tool: `blob` is the synced
  version of the upstream file, `commit` the upstream commit that last changed
  it (not the branch tip at sync time). One file version thus always gives
  the same entry, and commits that don't touch the file – unpushed, rebased
  or not – don't matter. If the recorded commit isn't found upstream any
  more (history rewritten there), `status` shows the file as `changed
  (previous sync point unknown)`, and `pull` records the current commit –
  also if the file itself is the same.
- An entry **without** `commit` and `blob` is a **new link**, not synced
  yet: `status` shows it as `new`, and `pull` syncs it the first time,
  exactly as [`add`](#add) would – a missing file is fetched, an existing
  one must be the upstream version (else `pull` refuses, as `add` does:
  `--overwrite` takes the upstream version; with `adaptable = true` the
  file is kept, its differences count as adaptations). That way many files
  can be linked at once: write their entries with [`edit`](#edit) – only
  `source` and `path` (and `tag`, `adaptable` as needed), e.g. by copy and
  paste – then `pull --all`. The first sync is `add`: the file is staged
  as it is in the working tree, uncommitted changes included
  (`--overwrite`: replaced, the content kept as a blob). Until then, such a
  link has nothing to [`restore`](#restore) or `diff` against (`diff
  --upstream` shows the whole file); `pull -n` tells whether its first sync
  would be refused.
- Everything else may be edited by hand – with [`edit`](#edit), or e.g.
  `git config -f .git-filesync file.src/foo.c.path lib/new_name.c` (a file
  renamed upstream is [followed by `pull`](#files-renamed-or-deleted-upstream)
  anyway). [`source`](#source) changes URL and branch of a source,
  [`set`](#set) the source and tag of files.
- When the last link is removed, the file is deleted.
- File paths must lie inside the working tree. Entries pointing outside it
  (`..`, absolute paths) or into a `.git` directory are reported as errors
  and never written – a cloned repository's `.git-filesync` can't make
  `pull` touch other files. The same goes for a path that something is in
  the way of: a directory (or anything else but a file) where the file
  belongs, a parent directory that is a file, or one that is a symbolic
  link. Writing the file, git would delete what is there (a directory with
  all in it), or write elsewhere; so no command writes, deletes or reads
  there, and `status` reports an error – move it away, or remove the link
  with `unlink`.

### Exact copies and adaptable files

By default a linked file must stay an **exact copy** of its upstream
version. Any change of it, committed or not, is reported as a violation:
`status` marks it `NOT ALLOWED: not adaptable` (`-s`: `(not adaptable!)`,
`--exit-code`: 1), the hooks report it, and `pull` refuses to sync it
(other files of `pull --all` are still synced; if there is nothing to
sync, `pull --all` leaves it alone and says it needs attention). Inspect with `diff`, then go
back to the synced upstream version with [`restore -SW`](#restore) (or,
for committed changes, sync and discard in one step with `pull
--overwrite`), discard only uncommitted changes with `git restore` – or
allow changes by marking the file adaptable.

An **adaptable** file may carry local adaptations, which `pull` keeps (see
below). Mark a file with `add --adaptable`, or later with [`set
--adaptable`](#set) (`--no-adaptable` takes it back):

```sh
git filesync set src/foo.c --adaptable
```

In `.git-filesync` this is `adaptable = true` in the `[file]` (as everywhere
in git config, a bare `adaptable` without a value means true).

### Local modifications on top of the upstream version

An [adaptable](#exact-copies-and-adaptable-files) file downstream doesn't
have to be identical to the upstream version: it may carry local
adaptations. Its entry in `.git-filesync` records the
**base** of the file – "this file is based on upstream commit X" – not its
content. Since file and entry are always committed together, every downstream
commit precisely defines the local layer: file content minus upstream
version named in the entry.

```
  upstream version (entry: commit X)  +  local modifications  =  file downstream
```

Committed local changes are **adaptations**; changes not committed yet are
**uncommitted changes** – `status` shows both separately. `pull` keeps
adaptations by merging them with the new upstream version, and – like
`git pull` – refuses files with uncommitted changes (see [`pull`](#pull)).
`diff` and `difftool` show both kinds (see [`diff`](#diff)).

A linked file must exist once it is synced, adaptable or not: one that
is **missing** in the working tree – deleted, the deletion committed or not – is never
allowed, as its link is still there. (A directory there is no missing
file, but an [error](#the-git-filesync-file): `restore` would delete it.) Bring it back with
[`restore`](#restore), or remove the link with [`unlink`](#unlink) (or the
link and the file with [`rm`](#rm)).

## Commands

Basic commands – what you need day to day:

| Command | Purpose |
|---|---|
| [`status [PATH…]`](#status) | state of the linked files, like `git status` |
| [`pull PATH…`, `pull --all`](#pull) | sync files from upstream |
| [`diff [PATH…] [-- OPTS]`](#diff) | local changes against the synced upstream version |
| [`difftool [PATH…] [-- OPTS]`](#difftool) | the same in your difftool |
| [`restore PATH…`](#restore) | files back to the synced upstream version, like `git restore` |
| [`add URL\|SOURCE FILE\|DIR`](#add) | link a file – or all files of a directory – to the upstream repository |
| [`rm PATH…`](#rm) | remove linked files and their links, like `git rm` |
| [`unlink PATH…`](#unlink) | remove links, keep the files |
| [`mv OLD NEW`](#mv) | move a linked file and its link |

[Advanced commands](#advanced-commands) – to change links and sources, and for setup:

| Command | Purpose |
|---|---|
| [`set PATH… OPTIONS`](#set) | change the link of linked files: source, tag, upstream path, adaptable |
| [`edit`](#edit) | edit `.git-filesync` in the editor |
| [`source [ACTION …]`](#source) | list sources, rename them, change URL or branch |
| [`source map [URL\|SOURCE [DIR]]`](#source-map) | use a local checkout of upstream |
| [`cache [ACTION]`](#cache) | the cache of upstream clones: show, list, prune, clear, print its directory |
| [`hooks [ACTION]`](#hooks) | the hooks: show, install, remove; reminders, push check |

Commands named like a Git command behave like it (`status`, `pull`, `diff`,
`difftool`, `restore`, `add`, `rm`, `mv`; `source` like `git remote`): same
kind of output, same exit codes, same caution with uncommitted changes.

**No command commits** – you do. Like `git add`, `git rm`, `git mv` and
`git restore`, the commands only change the working tree or stage: `pull`,
`add`, `rm`, `mv`, `set`, `unlink`, `edit` and `source` stage, `restore`
(without `-S`) leaves the index alone. `pull` stages like `git merge
--squash`. So you can look at everything before it goes into the history,
undo it (`git restore -SW`), or combine several commands – and changes of
your own – into one commit. `pull` and `add` prepare a proposed commit
message that a plain `git commit` offers (see [Proposed commit
messages](#proposed-commit-messages)); for `pull` it lists the upstream
commits since the last sync of each file, so `git log FILE` shows every
sync of FILE.

The reading commands – `status`, `diff`, `difftool`, `source` (listing) and
the hooks – change nothing in the repository: even the Git objects they
need to compare files in this repository's form, or to build the trees for
`diff`, go into a temporary object directory that is removed afterwards.

`git filesync` without a command runs `status`.

Paths are relative to the current directory – the ones you give, and the
ones in the output and in suggested commands. Where `PATH…` is accepted, a
directory stands for all linked files below it. Options follow the command
(`git filesync status --no-fetch`); `git filesync <command> -h` describes
the command and lists them.

### Common options

| Option | Commands | Effect |
|---|---|---|
| `--no-fetch` | `status`, `pull`, `diff`/`difftool`, `restore`, `add`, `set`, `source set-url`/`set-branch` | don't fetch, use the cached state (offline); an upstream repository not in the [cache](#cache) yet is cloned anyway. `restore` and `diff` of local changes fetch even without it only if the cache lacks the branch – the synced versions don't change |
| `--remote` | as `--no-fetch` | ignore [mappings](#source-map) this once: work against the upstream URL (its clone in the cache), the mapping stays. With `--no-fetch`: the cached state |
| `--color[=always\|never\|auto]`, `--no-color` | all | override `color.filesync` / `color.ui` (see [Colors](#colors)) |

### `status`

`status [PATH…]` – state of all (or the given) linked files.

| Option | Effect |
|---|---|
| `-s`, `--short` | short format, three columns |
| `-v`, `--verbose` | also list every linked file with its source; for a [pinned](#pinning-to-a-tag) one also the [newer tags](#newer-tags) on the source's branch |
| `--exit-code` | exit with 1 if something is to sync, a linked file is missing, or a file that isn't adaptable is modified |

`status` looks at each linked file in three independent respects:

| Respect | Compares | States |
|---|---|---|
| upstream | synced upstream version ↔ current upstream | up to date, `pending`, `older`, `changed`, `renamed`, `deleted`, `new` (a [new link](#the-git-filesync-file), not synced yet) |
| committed | synced upstream version ↔ committed file (`HEAD`) | `unmodified`, `adapted` |
| working tree | committed file ↔ working file | clean, `modified`, `new file`; not there: `missing` |

and reports them in sections like `git status`:

```
Upstream changes to sync:
  (use "git filesync diff --upstream <file>..." to see what pull would bring)
  (use "git filesync pull <file>..." to sync)
	pending:    src/foo.c  (2 commits)

Locally adapted files:
  (use "git filesync diff --committed <file>..." to see the adaptations)
  (use "git filesync restore -SW <file>..." to discard them, or "git filesync set --adaptable <file>..." to allow them)
	adapted:    include/x.h  (NOT ALLOWED: not adaptable)
	adapted:    src/foo.c

Missing files:
  (use "git filesync restore <file>..." to bring them back (the synced version))
  (use "git filesync unlink <file>..." to remove the links)
	missing:    src/old.c  (NOT ALLOWED: still linked)

Uncommitted changes:
  (use "git filesync diff <file>..." to see all local changes)
  (use "git restore <file>..." to discard uncommitted changes)
	modified:   src/bar.c
```

`renamed` and `deleted` are explained under [Files renamed or deleted in
upstream](#files-renamed-or-deleted-upstream). Without anything to
report: `nothing to sync, all 5 linked files unmodified`. Paths are shown relative to the current directory. `-v` adds a
`Linked files:` section with every file and its source; the hints are turned
off by `advice.statusHints = false`. Warnings (e.g. about a mapped checkout)
follow in a `Warnings:` section.

**Short format** (`-s`), like `git status -s`, one line per file that has
something to report, with three columns:

| Column | Meaning |
|---|---|
| 1 – upstream | `P` pending, `O` upstream branch older than last sync, `D` history diverged or previous sync point unknown, `R` renamed upstream, `X` deleted upstream, `N` new link (not synced yet), `E` error |
| 2 – committed | `M` adapted (committed modifications, like git's index column) |
| 3 – working tree | `M` modified, `D` missing (deleted; marked `(missing!)`), `?` not committed yet |

```
P   src/a.c
PM  src/b.c
 MM src/c.c
 M  include/x.h  (not adaptable!)
  D src/old.c  (missing!)
```

Like `git status`, the exit code is 0 (2 on errors); `--exit-code` makes it
1 when something is to sync, a linked file is missing, or a file that isn't
adaptable is modified (for scripts and [CI](#ci)).

### `pull`

`pull PATH…`, `pull --all` – sync to the current upstream version of the
file: the version on the source's branch (with a [local checkout](#source-map):
that checkout's branch), or at its [tag](#pinning-to-a-tag). Recorded is the upstream commit that last changed the
file.

What `pull` syncs to follows simple rules: `--commit REV` – exactly that
commit; a tag – exactly that tag; a [tag pattern](#tag-patterns) – the
newest matching tag on the source's branch; otherwise the head of the
branch. A branch, tag or commit that is given but can't be found upstream
is an error (there is nothing to sync to); settings that merely don't fit
together, like a tag that isn't on the source's branch, give a warning.

The synced files and their updated entries in `.git-filesync` are staged,
like after `git merge --squash`; nothing is committed. A plain `git commit`
then opens the editor with the proposed commit message (`git commit
--no-edit` takes it as it is):

```
[filesync] Sync src/foo.c from owner/lib@a1b2c3d

Upstream: https://github.com/owner/lib.git (main:lib/foo.c, 2026-10-28)

Upstream changes since 3f2a9c1 (2026-09-12):
- Fix off-by-one in buffer handling (9e8d7c6, 2026-10-27)
- Add support for chunked transfer (a1b2c3d, 2026-10-28)
```

A `pull` proposes **one commit** for all files it syncs. For several files
the subject says how many (`[filesync] Sync 3 files from owner/lib`, or `…
from 2 sources`), and each file gets a section of the message like the one
above. A file that can't be synced (a refusal, an error) is reported and
left out; the others are still synced and staged.

In scripts and CI: `git filesync pull --all && git commit --no-edit`.

| Option | Effect |
|---|---|
| `--all` | all linked files with something to sync (with `--commit`, `-b` or `--tag`: all linked files); not together with paths. Files it leaves alone that need attention – missing, or modified but not adaptable – are named instead of `everything up to date`: `2 linked files: not synced, but need attention (see 'git filesync status')` |
| `--commit REV` | sync to this upstream revision, once (as `-b`) – branch, tag or commit id, also backwards. The link keeps its branch or tag |
| `-b`, `--branch BRANCH` | sync to the head of BRANCH, once: the files keep following their own branch or tag (see [Another branch or tag, once](#another-branch-or-tag-once)) |
| `--tag TAG` | sync to TAG, once (as `-b`) |
| `--overwrite` | discard local adaptations and take the upstream version as is (also when the file is up to date); uncommitted changes are still refused – except at the first sync of a [new link](#the-git-filesync-file), which works like `add --overwrite`: the file is replaced, its content kept as a blob |
| `-n`, `--dry-run` | change nothing, only report per file what would happen: the version it would sync to, whether adaptations merge cleanly or how many conflicts there would be, a rename upstream, and every refusal |
| `-v`, `--verbose` | before each file, a line on where it comes from (as in `status -v`) and the version synced so far: `src/foo.c: from owner/lib:lib/foo.c (main), synced at 3f2a9c1` |

**Adaptations** are merged with the new upstream version (3-way merge, base =
the last synced version). On conflicts the file gets the usual conflict
markers and is left unstaged, like after `git merge`; `pull` exits with 1.
Resolve the conflicts, then `git add` the files and run `git commit`, which
offers the proposed message for all of them (see [Proposed commit
messages](#proposed-commit-messages)). `--overwrite` skips
the merge and discards the adaptations.

**Uncommitted changes:** like `git pull`, `pull` refuses a file with
uncommitted changes (`your local changes … would be overwritten by pull`):
commit or stash them first (`git stash`, then `git stash pop` after the
sync), or discard them with `git restore`.

**Missing files:** `pull` refuses a [missing](#local-modifications-on-top-of-the-upstream-version)
file – bring it back with `restore` first (or remove the link with
`unlink`); `pull --all` leaves it alone, and says it needs attention. A [new link](#the-git-filesync-file)
(no `commit` and `blob` yet) is no missing file: `pull` fetches it.

**Revisions:** `--commit` accepts branch names (`develop` means the current
upstream `develop`), tags and commit ids. Recorded is the commit that last
changed the file up to that revision. Going back to an older version works
the same way; the commit message then lists what is reverted.

For files [pinned to a tag](#pinning-to-a-tag), `pull` ends with a hint if
upstream has [newer tags](#newer-tags) on the source's branch:

```
hint: 3 files pinned to tag v1.2.0; the newest tag on branch main is v1.4.0 (use 'git filesync set --tag v1.4.0 <file>...' and pull to switch)
```

A file **renamed upstream** is followed: `pull` takes the new path into
the entry and notes the rename in the commit message. A file **deleted
upstream** is refused, see [Files renamed or deleted
upstream](#files-renamed-or-deleted-upstream).

#### Another branch or tag, once

`pull -b BRANCH` and `pull --tag TAG` sync the given files (or `--all`)
once to the head of another branch or to a tag of their upstream – e.g. to
try a release before switching to it. Adaptations are merged as usual. Like
`git pull <remote> <branch>`, this doesn't change what the files follow:
their entries keep their branch or tag, only the synced version is updated.
`pull` ends with a hint:

```
hint: the links still follow their own branch or tag, so a plain pull goes back; to stay on tag v1.3.0, use 'git filesync set --tag v1.3.0 <file>...'
```

`status` then shows the files as `older` (their own tag is older than the
synced version) or `pending`, and a plain `pull` syncs them back. To switch
for good, change what the files follow with [`set -b` / `--tag`](#set),
then `pull`.

With `--all`, every file is synced, also those up to date with their own
branch or tag. A branch or tag that doesn't exist upstream is refused; `-b`
and `--tag` can't be combined. `pull --commit REV` does the same for any
revision – a commit id belongs to one upstream repository, so files of
other ones get an error (and the others are synced).

```sh
git filesync pull --tag v1.3.0 --all       # all files to v1.3.0, once
git filesync set src/ --tag v1.3.0         # switch for good ...
git filesync pull src/                     # ... and sync
```

### `diff`

`diff [PATH…] [-- OPTS]` – local changes against the synced upstream version.

| Option | Effect |
|---|---|
| `--committed` | only the committed adaptations (synced → `HEAD`) |
| `--upstream` | what `pull` would bring (synced → current upstream) |
| `--commit REV`, `-b BRANCH`, `--tag TAG` | with `--upstream`: what `pull` with the same option would bring (synced → that revision, branch or tag); nothing is switched |
| `--for-upstream` | a patch for the upstream repository: upstream paths, standard `a/` `b/` prefixes, for `git apply`; not with `--upstream` |

```sh
git filesync diff                    # all local changes: synced upstream version -> working file
git filesync diff --committed        # adaptations only: synced upstream version -> HEAD
git filesync diff --upstream         # what `pull` would bring: synced -> current upstream
git filesync diff --upstream --tag v1.3.0 src/foo.c   # what `pull --tag v1.3.0` would bring
git filesync diff -- --stat          # anything after `--` goes to `git diff`
```

Without file arguments all linked files are covered. `diff` runs a single
`git diff` in the downstream repository, so pager, colors and diff options
work as usual. With `--exit-code` or `--quiet` after `--`, exit code 1 means
differences, like `git diff`.

`--commit`, `-b` and `--tag` select the upstream version exactly like the
same options of [`pull`](#pull) (files renamed upstream are followed),
so replacing `pull` with
`diff --upstream` in a command line previews its changes. They only work
with `--upstream`; `.git-filesync` stays untouched. `pull --dry-run` tells
whether the adaptations would merge cleanly; on conflicts it points to
both diffs.

**Upstreaming local changes:** `--for-upstream` names the files by their
current upstream path (the new one, if a file was renamed there), giving a
patch that can be applied there (with
`--committed`: only the committed adaptations):

```sh
git filesync diff --for-upstream src/foo.c > foo.patch
cd ~/src/lib && git apply -3 ../my-repo/foo.patch
```

The patch is relative to the synced version, not to the current upstream
state, and records that version's blob id. `-3` uses it as the base of a
3-way merge, so the patch applies on any upstream branch or commit – check
out the one you want first; conflicts are resolved there with the usual Git
tools.

### `difftool`

`difftool [PATH…] [-- OPTS]` – the same as [`diff`](#diff), file by file in
your difftool (`diff.tool`); `OPTS` go to `git difftool` (e.g. `-t meld`).

| Option | Effect |
|---|---|
| `--committed`, `--upstream`, `--commit`, `-b`, `--tag` | as for `diff` |
| `-y`, `--no-prompt` | don't ask before each file |
| `--prompt` | ask even with `difftool.prompt = false` |

Without `--upstream` / `--committed`, the right side is the real working
file, so edits made in the tool are kept.

Like `git difftool`, `difftool` asks before each file
(`Viewing (1/3): 'src/foo.c'` / `Launch 'meld' [Y/n/q]?`; Enter = yes,
`q` = stop). `-y` / `--no-prompt` or `difftool.prompt = false` skip the
questions, `--prompt` asks anyway; of `-y` and `--prompt`, the last one
given counts.

### `restore`

`restore PATH…` – like `git restore`, but from the synced upstream version
(the base recorded in `.git-filesync`) instead of the index: the files get
that version back, e.g. to discard the changes of a file that isn't
adaptable, or to bring back a missing file. A [new
link](#the-git-filesync-file), not synced yet, has nothing to restore.
`.git-filesync` stays as it is, nothing is committed – commit the result
like any change. Unlike `pull --overwrite`, `restore` doesn't bring in a
newer upstream version.

| Option | Effect |
|---|---|
| `-S`, `--staged` | restore the index (what is staged) instead of the working tree |
| `-W`, `--worktree` | restore the working tree – the default; with `-S`: both |

`restore -SW` is the way to discard committed adaptations: the file is
back at the synced version and staged, ready to commit. Files that are at
the synced version already are reported with `nothing to restore`.

`git restore FILE` (without `filesync`) discards uncommitted changes as
usual, back to the committed state, adaptations included.

<a id="discarded-content"></a>Like `git restore`, `restore` overwrites
uncommitted changes in the working tree. Their content isn't lost, though:
before a file with content in neither HEAD nor the index (if that stays)
is overwritten, it is kept as a blob, exactly as it was, and reported:

```text
discarded: src/lib.c (git show 3f2a9c1d07be to get it back)
```

`git show 3f2a9c1d07be > src/lib.c` brings it back – until Git removes
unreferenced objects (`git gc`, after two weeks by default). The same
applies to `add --overwrite` and `rm -f`.

### `add`

`add URL|SOURCE FILE` – link FILE to a file in an upstream repository, given by
its URL or by the name of a `[source]` already in `.git-filesync` (first
upstream, then here – as in `source map` and `git submodule add`):

- **URL**: the file joins an existing source only if the URL and the
  branch (`-b`, default: the upstream default branch) both match;
  otherwise a new source is created.
- **Name of a source**: the file joins exactly this source. `-b` is not
  needed; if given, it must be the source's branch (otherwise `add` refuses
  – give the URL to link to another branch).

With `--tag`, the file is [pinned](#pinning-to-a-tag) to that tag (the tag
goes into its `[file]` entry); the source and its branch are found as
above.

`add URL|SOURCE DIR` – the same for every file below an upstream
directory (see [below](#linking-a-directory)).

| Option | Effect |
|---|---|
| `-b`, `--branch BRANCH` | the source's upstream branch; default: the upstream default branch, or the branch of the given `[source]`. For a pinned file the branch to look for [newer tags](#newer-tags) on (a warning if the tag isn't on it) |
| `--tag TAG` | [pin](#pinning-to-a-tag) the file to an upstream tag instead of following the branch; a [pattern](#tag-patterns): the newest matching tag on the branch |
| `-p`, `--path PATH` | upstream path; default: the same as FILE or DIR (`/`: the upstream root). Backslashes count as `/`, e.g. in a path copied from a checkout on Windows |
| `--include PATTERN` | directory: only files matching PATTERN; repeatable |
| `--exclude PATTERN` | directory: skip files matching PATTERN; repeatable, beats `--include` |
| `--commit REV` | upstream revision to base FILE on, instead of the head of the branch (or the tag) |
| `--overwrite` | replace an existing FILE (for DIR: existing files) with the upstream version; uncommitted content is kept as a blob ([discarded content](#discarded-content)) |
| `--adaptable` | local adaptations allowed; also: keep an existing FILE that differs from the base (see [Exact copies and adaptable files](#exact-copies-and-adaptable-files)) |
| `--force` | relink a file that is already linked – like `unlink` and `add`: the entry is made anew, with `--tag` and `--adaptable` as given now |
| `-n`, `--dry-run` | change nothing, only show what would be linked and on which upstream version it would be based |

- The base is always the upstream version `pull` would sync to: the head of
  the branch (or the tag), or the revision given with `--commit`.
- If FILE exists, it must be the base, as a linked file must stay an exact
  copy. If it differs, `add` refuses and names the ways on:
  - `--adaptable` keeps it as it is: the differences count as
    [adaptations](#local-modifications-on-top-of-the-upstream-version),
    which `pull` keeps. If FILE is an older copy of the upstream file, that
    means the upstream changes since then would be kept reverted;
  - `--overwrite` takes the upstream version instead;
  - `--commit` names the upstream version FILE is a copy of (then `pull`
    brings the changes since).
- If FILE doesn't exist, it is fetched from upstream. Its directory must
  exist, as for `cp`: `add` doesn't create a mistyped one (`error:
  directory 'src/new' does not exist`); a FILE ending in `/` for an upstream
  file must be an existing directory, which the file goes into. `restore` does create missing
  directories, bringing back a missing file – the entry is there already,
  as for `git checkout`.
- Like `git add`, `add` stages FILE (as it is in the working tree) and its
  entry in `.git-filesync`, but doesn't commit – also a file matched by
  `.gitignore`: linking a file means tracking it. A plain `git commit` then
  opens the editor with the proposed commit message (`git commit --no-edit`
  takes it as it is; see [Proposed commit
  messages](#proposed-commit-messages)):

  ```
  [filesync] Add src/foo.c from owner/lib@a1b2c3d

  Upstream: https://github.com/owner/lib.git (main:lib/foo.c, 2026-10-28)
  ```

  For an existing FILE the subject is `Link FILE to …` (`Relink …` with
  `--force`); the message notes local modifications and `--adaptable`. Several
  `add`s (and `pull`s) in a row go into one commit, with all their
  messages.

```sh
git filesync add https://github.com/owner/lib.git src/foo.c -p lib/foo.c
git commit                                            # with the proposed message
git filesync add owner/lib include/bar.h --adaptable  # reuse [source "owner/lib"]
git filesync add owner/lib src/ -p lib/util.h         # into an existing directory: src/util.h
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag v1.2.0
```

#### Linking a directory

If DIR is an existing directory, or the upstream path is a directory, or
`--include` / `--exclude` are given, `add` links every file below upstream
directory: `-p api` with DIR `proto` links `api/v1/x.proto` as
`proto/v1/x.proto`. (An upstream *file* given for an existing directory goes
into it, like `cp`.) As for `cp -r`, DIR itself may be new, but the
directory it goes into must exist; subdirectories below DIR are created as
upstream has them. Each file gets its own ordinary `[file]` entry – after
`add` there is no difference to files linked one by one – and all of them
are staged together, with one proposed message:

```
[filesync] Add 2 files from owner/backend@a1b2c3d

Upstream: https://github.com/owner/backend.git (main:api/, 2026-10-28)

- proto/a.proto
- proto/v1/b.proto
```

Files already linked are skipped (`--force` relinks them), so running the
same `add` again later links just the files that are new upstream.
Existing files are linked as they are, like a single FILE.

Patterns work like `.gitignore` lines, relative to the upstream directory:

| Pattern | Matches |
|---|---|
| `*.proto` | without `/`: a name at any depth |
| `/top.txt`, `v1/*.proto` | with a leading or inner `/`: relative to the upstream directory |
| `test/` | trailing `/`: a directory (with everything below it) |
| `**/gen/*.h` | `**/` any number of directories; `*` and `?` don't match `/`; `[abc]`, `[!abc]` |

```sh
git filesync add https://github.com/owner/backend.git proto -p api \
    --include '*.proto' --exclude '*_test.proto' --exclude test/
```

### `rm`

`rm PATH…` – like `git rm`: remove the files and their links; both are
staged. A file with uncommitted changes (or one never committed) is not
removed – nothing is, then – unless `-f` / `--force` is given (its
uncommitted content is then kept as a blob, see [discarded
content](#discarded-content)); a committed adaptation is no reason to refuse. A file that is gone already just loses
its link. `-n` / `--dry-run` only lists what would be removed. To keep the
files, use [`unlink`](#unlink).

### `unlink`

`unlink PATH…` – remove the links; the files themselves are kept.
`.git-filesync` is staged. `-n` / `--dry-run` only lists what would be
unlinked.

### `mv`

`mv OLD NEW` – move a linked file (`git mv`) and its link together; NEW may
be an existing directory. As for `git mv`, the directory NEW goes into must
exist, and a NEW ending in `/` must be an existing directory. Both are staged. `-n` / `--dry-run` only shows
what would be moved.

## Advanced commands

### `set`

`set PATH… OPTIONS` – change the link of linked files: their source, their
tag, their upstream path, whether they are adaptable. It does for files what
[`source`](#source) does for sources: only `.git-filesync` is changed (and
staged); `status` then shows what changes, and `pull` syncs.

| Option | Effect |
|---|---|
| `--source URL\|SOURCE` | take the files from another upstream repository – a fork, a moved repository – or from the `[source]` SOURCE |
| `-b`, `--branch BRANCH` | follow BRANCH (with `--source URL`: a branch of that upstream; default: its default branch) |
| `--tag TAG` | [pin](#pinning-to-a-tag) the files to TAG (or a [pattern](#tag-patterns)) from now on; the source's branch is where [newer tags](#newer-tags) are looked for. A tag that doesn't exist upstream is refused |
| `--no-tag` | follow the source's branch again |
| `-p`, `--path PATH` | another upstream path (exactly one file; `\` counts as `/`, as for `add`) |
| `--adaptable`, `--no-adaptable` | allow [local adaptations](#exact-copies-and-adaptable-files), or not any more (the default) |
| `-n`, `--dry-run` | only show what would change |

As for [`add`](#add), URL and branch select the `[source]` the files use:
the one with that URL and branch, created if there is none – or, when all
files of a source move, that source itself changes (keeping its name, like
[`source set-url` / `set-branch`](#source)). A source left without files is
removed. `--source SOURCE` with another `-b` than its branch is refused.

Several options can go together, e.g. to pin files to a tag on another
branch:

```sh
git filesync set cfg/ -b maint --tag 'v1.2.*'    # the newest v1.2.* on maint
```

`--tag` is checked on the branch the files follow then: a tag not on it
gives a warning naming the branches it is on, a pattern without a match
there an error naming the branches with matching tags.

The synced version the files are based on (`commit` / `blob`) is kept where
it still applies, so adaptations stay adaptations:

- **another tag, or a source on another branch** of the same upstream:
  kept as it is;
- **another upstream** (`--source` with another URL): kept if that one has
  it – the recorded commit, or else the newest commit on its branch with the
  same version of the file (e.g. a copy with a history of its own).
  Otherwise there is a warning, and the previous sync point counts as
  unknown;
- **another path** (`-p`): as for `add` – the version of that path at the
  head of the branch (or the tag). The file itself stays as it is, so
  differences count as adaptations; for a file that isn't adaptable they
  are a change not allowed, which `status` reports and `pull --overwrite`
  resolves by taking the new version. (A file renamed upstream doesn't need
  this: [`pull`](#pull) follows renames.)

```sh
git filesync set src/foo.c --adaptable
git filesync set src/ --source https://github.com/me/lib-fork.git    # all files below src/
git filesync set src/foo.c -p lib/foo_v2.c
git filesync set cfg/ --tag v1.3.0      # pin to v1.3.0 from now on; then pull
git filesync set cfg/ --no-tag          # follow the branch again
```

### `edit`

`edit` – open `.git-filesync` in your editor, like `git config --edit`
(`GIT_EDITOR`, `core.editor`, `VISUAL`, `EDITOR`). Afterwards the file is
checked and staged, like after [`set`](#set):

- If it can no longer be read, `edit` fails and stages nothing; run it
  again to fix the file.
- Gaps that `status` would report – a file whose `[source]` doesn't exist,
  a source without `url` or without branch (or with a tag, as before 0.14), a file without `path`
  or with only one of `commit` and `blob` (neither: a [new
  link](#the-git-filesync-file)), a source no file uses – are shown as warnings.
- Without changes, nothing happens.

For the usual changes, the commands that know what they mean are safer:
[`set`](#set) (source, tag, path, adaptable of files), [`source`](#source) (URL,
branch, name of a source), [`rm`](#rm), [`unlink`](#unlink), [`mv`](#mv). `edit`
keeps whatever you write: a changed `commit` or `blob` changes what counts
as an adaptation.

Comments and your own layout in `.git-filesync` are kept: the commands
change only the lines they have to. A changed value keeps the indentation,
spacing and comment of its line, a renamed entry the comment of its header.
A removed entry takes its header, its keys and the lines between them
along; comments and blank lines after its last key stay – e.g. one that
introduces the next entry.

### `source`

`source [ACTION …]` – list and change the `[source]` sections, like
`git remote`. Sources are created by [`add`](#add) and [`set`](#set) as
needed, and removed when no file uses them any more. Only `.git-filesync`
is changed (and staged); commit it on its own, or it goes into the next
sync commit.

| Command | Effect |
|---|---|
| `source` | list the source names (`-v`: with URL, branch and number of linked files) |
| `source rename OLD NEW` | rename a source, including every `source =` line |
| `source set-url NAME URL` | change the URL, e.g. after upstream moved; the synced versions are looked up there as for [`set --source`](#set) |
| `source set-branch NAME BRANCH` | follow BRANCH – all files of the source; for [pinned](#pinning-to-a-tag) ones the branch to look for newer tags on |

```
$ git filesync source -v
owner/lib	https://github.com/owner/lib.git (main, 3 files)
owner/lib-dev	https://github.com/owner/lib.git (dev, 1 file)
```

`set-url` and `set-branch` refuse a branch that doesn't exist upstream, as
[`set -b`](#set) does (`--no-fetch`: checked in the cache). Tags are a
matter of the files: [`set --tag`](#set), and `status -v` shows them.

A change that would make two sources identical (same URL and branch) is
refused; move the files with [`set -b` / `--source`](#set) instead. After changing
URL or branch, `status` shows what is to sync for the source's files.

### `source map`

`source map [URL|SOURCE [DIR]]` – use the local checkout DIR instead of fetching the
upstream URL. Instead of the URL, the name of a `[source]` in
`.git-filesync` can be given: its URL is meant – the mapping always belongs
to the URL, so it applies to every source with that URL. Without DIR, the
mappings are listed (only those for the URL, if given).

| Option | Effect |
|---|---|
| `--global` | in your global Git config, for all repositories (default: this repository's config) |
| `--unset` | remove the mapping for the URL |

```sh
cd my-repo
git filesync source map https://github.com/owner/lib.git ~/src/lib
git filesync source map owner/lib ~/src/lib      # the same, by the name of the [source]
```

Something that looks like a URL (`scheme://…`, or `host:path` like
`git@github.com:owner/lib.git`) is always taken as one. An argument that
is neither a URL, nor a source, nor an existing path is refused when
setting a mapping – most likely a mistyped name.

This writes `filesync.<url>.localpath` into the **downstream repository's
own config** (`.git/config`). Different downstream repositories can thus
point to different checkouts of the same upstream – e.g. one at the newest
state, another at an older one until its own code has been adapted.

With `--global` the mapping goes into your global Git config and applies to
all repositories without a mapping of their own; a repository's own mapping
always takes precedence.

```sh
git filesync source map                     # list mappings (scope, overridden ones marked)
git filesync source map URL --unset         # remove this repo's mapping
git filesync source map --global URL --unset
```

When mapped, `status` and `pull` use the source's branch **as it is in that
checkout** (for a [pinned file](#pinning-to-a-tag): the tag there) – its local branch, including commits not yet pushed – no matter
which branch is currently checked out there. Nothing is fetched; all of this
works offline.

- local branch ahead of the last sync → `N upstream commit(s) pending`
- local branch older than the last sync (e.g. reset) → `upstream branch is N
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

The checkout is only read: git-filesync writes nothing into it – Git
doesn't refresh its index, Git LFS stores nothing in its `.git/lfs` (an
LFS object missing there is fetched with the cache clone of the URL). So a
read-only checkout, e.g. on a network share, works too. Only if the
checkout is itself a partial clone (`--filter`), Git fetches objects
missing there into it as usual.

To work against the server once, e.g. to compare with what is pushed, add
`--remote` to the command (`git filesync status --remote`); to do so for
good, remove the mapping (`source map URL --unset`).

Without a mapping, `status` and `pull` work against the upstream repository on
the server. It is cached as a blobless partial clone in `~/.cache/git-filesync`
(Windows: `%LOCALAPPDATA%\git-filesync`, override with `FILESYNC_CACHE`) and
fetched (branches and tags) on each run – except when all that is needed is
a tag already in the cache. Credentials are whatever your Git uses for that
URL. File contents are fetched only when needed, which requires Git's wire
protocol v2: git-filesync asks for it, whatever `protocol.version` says (Git
2.27 and 2.28 default to v0); GitHub, GitLab and other current servers
support it. The cache only holds what can be fetched again: deleting it is
safe, the next run clones anew. See [`cache`](#cache) for its size and how
it is cleaned up.

### `cache`

```
git filesync cache [list | prune [--max-age DAYS] [--max-size SIZE] [-n] | clear [-n] | dir]
```

The cache of upstream clones (one blobless clone per URL, see
[`source map`](#source-map)), shared by all repositories of your user. Works outside a
repository, too.

```
$ git filesync cache
/home/me/.cache/git-filesync: 12 clones, 85.3 MiB
cleaned up automatically: clones unused for 90 days (filesync.cacheMaxAge, filesync.cacheMaxSize)
$ git filesync cache list
  31.2 MiB  2026-10-19  https://github.com/owner/lib.git
   4.1 MiB  2026-09-02  https://gitlab.com/group/tools.git
…
```

| Action | Effect |
|---|---|
| (none) | where the cache is, how big, and its limits |
| `list` | the clones, most recently used first: size, last used, URL |
| `prune` | remove clones not used for `filesync.cacheMaxAge` days, then the least recently used beyond `filesync.cacheMaxSize`; `--max-age DAYS` and `--max-size SIZE` (e.g. `500M`, `2G`) set other limits for this run – `0` means no limit, as in the settings below (to remove everything: `clear`); `-n` only shows what would be removed |
| `clear` | remove all clones (`-n`: only show them) |
| `dir` | print the cache's directory, e.g. to keep it between CI runs |

**Automatically**, after a fetch and at most once a day, the cache is
cleaned up by the configured limits:

| Setting | Default | Effect |
|---|---|---|
| `filesync.cacheMaxAge` | `90` | remove clones unused for that many days; `0` or `off`: never |
| `filesync.cacheMaxSize` | (none) | then remove the least recently used clones until the cache is at most this big, e.g. `2G`; `0` or `off`: no limit |

A clone used in the last minutes is never removed, so a command running in
parallel doesn't lose its clone. A removed clone is simply cloned again
when it is needed; only the offline fallback ("using cached state") needs
it to be there.

### `hooks`

`hooks install` adds a `pre-push` hook (fetches) and a `post-merge` hook
(cached state only). Both report pending syncs, errors, missing files and
changes not allowed (files that aren't adaptable) on stderr. If a hook of another tool already exists, the lines
to add are printed instead; `hooks install --force` adds them itself, right
after the `#!` line – before anything else, as needed for `git lfs
pre-push` (see below) and for hooks that end with `exec` or `exit`. Hooks
installed by an older version are updated in place. With
`core.hooksPath` set, the hooks go there (with a warning, as other
repositories may share that directory).

`hooks` without an action shows the state of each hook – `installed`,
`outdated` (installed by an older version: run `hooks install` again), `not
installed`, or a hook of another tool without our lines – and the
directory, if `core.hooksPath` sets it:

```
$ git filesync hooks
pre-push: installed
post-merge: not installed (install with 'git filesync hooks install')
```

**Sharing `pre-push` with Git LFS (or git-assetsync):** git passes the refs
being pushed to the hook on stdin, once – whichever command reads them
first gets them. The git-filesync block reads them and hands them on to
the commands after it; it can't get them back from a command before it.
So put it **before** `git lfs pre-push` (as `hooks install` says when the
hook exists, and `hooks install --force` does). Otherwise Git LFS works, but the push check sees nothing to
check. git-assetsync's block works the same way; the two can come in
either order, both before `git lfs pre-push`:

```sh
#!/bin/sh
# git-filesync: …
git_filesync_refs=$([ $# -eq 0 ] || cat)
printf '%s\n' "$git_filesync_refs" | git filesync hook pre-push "$@" || [ $? -ne 3 ] || exit 1
[ -z "$git_filesync_refs" ] || exec <<git_filesync_refs_end
$git_filesync_refs
git_filesync_refs_end
command -v git-lfs >/dev/null 2>&1 || { …; exit 2; }
git lfs pre-push "$@"
```

Before 0.9.1 the block was a single line that kept the refs to itself: put
first, it left Git LFS without them – the push went through, but no LFS
objects were uploaded. Run `git filesync hooks install` again: it replaces
the old line by the block, in the same place – in a shared hook, check that
the block comes before `git lfs pre-push`.

**Push check:** the `pre-push` hook also looks at the commits being pushed:
a linked file synced to an upstream commit that isn't on the upstream
server – typically pulled from an unpushed commit of a [mapped
checkout](#source-map) – is reported:

```
filesync: src/foo.c: synced from upstream commit 1a2b3c4d5e6f, which is not on the server (https://github.com/owner/lib.git) - push it there first
```

Others couldn't find that version as the base for their next `pull`. The
check asks the server itself (via the cache clone, whatever is mapped): the
commit must be on one of its branches or tags. Entries the remote already
has – in the commits the push replaces, or on its remote-tracking branches
(`origin/*`) – were checked when they were pushed and are skipped, so a
push usually doesn't contact the upstream server at all. Like Git with submodules, it
only warns by default; `filesync.pushCheck` sets what happens:

| `filesync.pushCheck` | Effect |
|---|---|
| `warn` (default) | report, push anyway |
| `error` | report and refuse the push (`git push --no-verify` skips it) |
| `off` | no check |

```sh
git config filesync.pushCheck error            # this repository
git config --global filesync.pushCheck error   # all repositories
```

A server that can't be reached is reported, but never refuses the push.
Apart from `error`, the hooks never block – not even if git-filesync itself
fails or is missing.

The hooks run `git filesync hook pre-push` / `hook post-merge` (not in the
command list), which are not meant to be run by hand (without the arguments
git passes, `hook pre-push` checks `HEAD`).

`hooks uninstall` deletes hook files that only contain the git-filesync
lines; from other hooks it removes just those lines.

Until 0.11, the commands were `install-hooks` and `uninstall-hooks`; hooks
installed by them keep working.

## Further topics

### Pinning to a tag

Instead of following its source's branch, a file can be pinned to a tag,
e.g. a release of upstream:

```sh
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag v1.2.0
git filesync set cfg/ --tag v1.2.0          # files already linked
```

`.git-filesync` then has `tag = v1.2.0` in the file's `[file]` entry; its
source stays as it is, files following the branch and pinned ones can share
it. `status` compares against the version at the tag – commits on the
upstream branches don't matter – and `pull` syncs to it. The source's
branch is where [newer tags](#newer-tags) are looked for. A branch that
doesn't exist upstream is an error; a tag that isn't on it, a warning.

Tags are taken as immutable, like Git does: once the tag is in the cache,
`status` (and the hooks) fetch nothing for it, so they need no network for
pinned files. A tag moved on the server is only noticed when the cache is
fetched for another reason. With a [mapped checkout](#source-map), the tag
in that checkout is used, whatever is checked out there.

Since a pinned file only changes when the tag does, `pull` usually has
nothing to do – except to bring a file back to the tag's version (e.g. after
`pull --commit`) or after the tag was changed. To learn about newer
releases, `pull` and `status -v` fetch the upstream tags (unless
`--no-fetch`) and name the [newer tags](#newer-tags).

To move on to a newer release, change the tag of the files, then sync:

```sh
git filesync set cfg/ --tag v1.3.0
git filesync pull cfg/
```

`set FILE… --no-tag` goes back to following the branch. `pull --tag v1.3.0`
[tries a tag once](#another-branch-or-tag-once) without switching;
`pull --commit` syncs once to any revision.

#### Tag patterns

A tag with `*`, `?` or `[…]` is a pattern (as in shell globs, matched
against the whole tag name): the file follows the **newest matching tag on
its source's branch**, so `pull` moves on to a new release by itself:

```sh
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag 'v1.*'
```

- "Newest" is meant as for [newer tags](#newer-tags): by the commit graph,
  not by name or date – the first commit along the branch's first-parent
  line, from its head back, that has a matching tag.
- `status` fetches the upstream tags (unless `--no-fetch`) and shows a new
  matching tag as `pending`, like a new commit on a branch. `status -v`
  shows which tags the pattern matches now (`tag v1.* = v1.4 on main`;
  several tags on that commit: `v1.4 = rel-4`). The commit message of
  `pull` names the tag.
- Tags that don't match are ignored – there is no hint at them.
- No matching tag on the branch is an error (`set --tag` refuses such a
  pattern).
- `pull --tag PATTERN` [syncs once](#another-branch-or-tag-once) to the
  newest matching tag on the source's branch.

#### Newer tags

Tag names are taken as opaque – `v1.10` and `v1.9`, `release-7` or
`tool-20261016` are just names – and tags carry no reliable date
(lightweight tags have none of their own, and a tag may be set on an old
commit later). So "newer" is defined by the commit graph alone, on the
source's branch: the newest tag is on the first tagged commit from the
branch head back along its first-parent line (one that contains the pinned
tag), i.e. among the commits the branch itself went through. Tags on side branches merged into it don't
count. So there is at most one newest tag (several names if several tags are
on that commit: `v1.4.0 = release-7`):

```
hint: 3 files pinned to tag v1.2.0; the newest tag on branch main is v1.4.0 (use 'git filesync set --tag v1.4.0 <file>...' and pull to switch)
```

If the pinned tag isn't on that branch, `status` warns. To follow a
maintenance line (`maint` with `v1.2.1`), switch the files to that branch:
`set FILE… -b maint --tag v1.2.1`.

Pre-releases count like any other tag. Branches are those of upstream
(`origin/…` in the cache); with a [mapped checkout](#source-map) its local branches
and tags, unpushed ones included.

### Proposed commit messages

`add` and `pull` stage their changes and put a proposed commit message into
`.git/SQUASH_MSG`. Git offers that
file as the message of the next plain `git commit` (as after `git merge
--squash`); `git commit --no-edit` takes it as it is. IDEs such as VS Code
fill their commit message box with it. Git removes it after the next commit,
whatever its message, and on `git reset`.

Every proposed message starts with `[filesync] `, so commits made with
git-filesync are easy to find later (`git log --grep='^\[filesync\]'`).

In the text, every upstream commit comes with its date (the committer
date): `Upstream changes since 3f2a9c1 (2026-09-12):`, `- Fix … (9e8d7c6,
2026-10-27)`, and the synced version's in the `Upstream:` line. The subject
has the commit id only.

- Several commands in a row (e.g. `add` for some files and `pull` for
  others, then one commit for all of them) collect their messages there.
- A `SQUASH_MSG` of git's own (e.g. from `git merge --squash`) gets the
  proposal added as well: the next commit contains both.
- A copy of `SQUASH_MSG` stays in `.git/FILESYNC_MSG` (the path is printed
  along with the hint to commit); each proposal rewrites it, so it never
  grows beyond what the next commit is offered. It brings the message back
  if `SQUASH_MSG` is gone – after `git reset`, or after a commit made with
  another message (`git commit -m`):
  `git commit -e -F .git/FILESYNC_MSG`.

### Files renamed or deleted upstream

When the linked path no longer exists upstream, `status` looks at the
commit that removed it:

- **renamed** (also with changes, also several times): shown as
  `renamed:    src/foo.c  (lib/foo.c -> lib/bar.c, 2 commits)`, short
  format `R`. `pull` follows the rename – it takes the new path into the
  entry, merges adaptations as usual and notes the rename in the commit
  message (`Renamed upstream: lib/foo.c -> lib/bar.c`); the listed commits
  cover both paths.
- **deleted**: shown as `deleted:    src/foo.c  (upstream, by 1a2b3c4)`,
  short format `X`, counted as something to do by `--exit-code` and the
  hooks. `pull` refuses and says what to do: keep the file as your own
  with `git filesync unlink src/foo.c`, or delete it too with
  `git filesync rm src/foo.c`. `pull --commit REV`
  still syncs to a revision that has the file.

Renames are detected the way `git diff -M` does (similar content); in the
blobless cache this needs the file contents of that one commit, which are
fetched. If the previous sync point is unknown, the missing path is
reported as an error; fix the path by hand then (see [The `.git-filesync`
file](#the-git-filesync-file)).

### Git LFS

Whether a synced file is stored in Git LFS upstream, downstream, in both or
in neither doesn't matter:

- Upstream side: LFS pointers are resolved to the real content: from the
  LFS store of a mapped checkout (only read), otherwise with `git lfs
  smudge` in the cache clone, from the upstream LFS server. Comparisons against an upstream
  file in LFS use the pointer's SHA-256, so no download is needed to tell
  whether the downstream copy is unmodified.
- Downstream side: the file is written as real content and stored the way
  the downstream repository's `.gitattributes` say – as an LFS object if it
  is tracked there, as a regular blob otherwise.
- `diff`, `difftool` and merges always work on the real content.

If LFS content can't be retrieved (git-lfs missing, LFS server unreachable,
`GIT_LFS_SKIP_SMUDGE`), the command fails with a clear message instead of
writing a pointer file.

### Line endings

Upstream and downstream may normalize differently (e.g. CRLF committed
upstream, `core.autocrlf` or `text=auto` downstream). The upstream content
is always compared and merged in the form the downstream repository would
store it, and written as a checkout there would produce it – no false
"local modifications", no eol-only conflicts.

`.git-filesync` is written with the line ends of a checkout, by the git
attributes and `core.autocrlf` (e.g. CRLF with `.git-filesync eol=crlf`
in `.gitattributes`); a file with other line ends gets them as a whole.

### Offline operation

With a [mapped local checkout](#source-map), all commands work without network
access (`add` takes the default branch from the checkout's `origin/HEAD`,
or – with a warning if the checkout has a remote – from the branch checked
out there). Files [pinned to a tag](#pinning-to-a-tag) work offline as
soon as the tag is in the cache; `pull` and `status -v`, which
look for newer tags, then warn that fetching failed and go on. Without a
mapping, the cache is used after a failed fetch; file versions never read
before may be missing there (blobless clone): `status` then warns and
counts the file as modified, `pull --overwrite` brings it back to a known
state. `--no-fetch` skips the network explicitly.

### Colors

Output is colored like `git status`: pending upstream changes yellow,
adaptations cyan (information, not a problem), uncommitted changes red,
changes not allowed (files that aren't adaptable) and errors bold red.

Colors follow `color.filesync`, falling back to `color.ui` (default: on for
terminals); `--color[=always|never|auto]` and `--no-color` override that,
and `NO_COLOR` turns colors off. Hook output on stderr is colored the same
way. `diff` is colored by `git diff` itself. The help (`-h`) follows the
same rules, with Python 3.14 or later (earlier versions have no colors for
it); being Python's own, it is colored only on a terminal.

### CI

A scheduled job in the downstream repo fails when a sync is pending
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
      - run: curl -fsSLo /tmp/git-filesync.py https://github.com/stsichler/git-filesync/releases/latest/download/git-filesync.py
      - run: python3 /tmp/git-filesync.py status --exit-code
```

This uses the latest release. To pin a version, download
`https://github.com/stsichler/git-filesync/releases/download/v0.20.3/git-filesync.py`
instead. (For private upstream repositories the job needs a token with read
access.)

### Exit codes

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | unfinished: `pull` with conflicts; `status --exit-code` with something to sync (including files deleted upstream), a missing file, or a change not allowed (a file that isn't adaptable); `diff -- --exit-code` with differences |
| `2` | error |
| `141` | the output went into a pipe that was closed early (`… \| head`, a pager quit), like Git (128 + SIGPIPE); reading commands stop there, the others finish their work first |

`--dry-run` / `-n` exit with 0, or 2 on errors – also for refusals they
report (`pull --dry-run` on a file that isn't adaptable, …); expected merge conflicts
are reported but don't change the exit code.

### Binary files

Binary files can be synced, but not merged with local modifications.

### Windows

git-filesync runs with Git for Windows and a Python from python.org (or
the Microsoft Store); set the alias with `py` or `python`, see the
[README](README.md). Output has LF line ends, like git's.

Git for Windows runs the alias through its own (MSYS) shell, also when you
call `git filesync` from cmd or PowerShell. That shell changes two kinds of
arguments before git-filesync sees them:

- **Wildcard characters** in file names (`*`, `?`, `[…]`) are expanded if a
  file matches: `git filesync add … 'f[1].txt'` turns into `f1.txt` when
  that file exists.
- **Arguments starting with `/`** become Windows paths: `--include /x.md`
  turns into `C:/Program Files/Git/x.md`. For the upstream root, `-p .`
  works as well as `-p /`.

For such arguments, run the script directly instead of through the alias,
e.g. `py C:/tools/git-filesync.py add owner/lib docs --include /x.md` in
cmd or PowerShell; in Git Bash, put `MSYS_NO_PATHCONV=1` in front of it.
Don't set `MSYS_NO_PATHCONV` (or `MSYS=noglob`) for git itself: it breaks
how git passes the arguments to the alias.

### Shipping git-filesync with your repository

git-filesync can keep a copy of itself in your repository, so everyone has
the same version without installing it:

```sh
git filesync add https://github.com/stsichler/git-filesync.git tools/git-filesync.py \
    -p git-filesync.py --tag v0.20.3
git config alias.filesync '!python3 tools/git-filesync.py'     # each clone, once (Windows: !py …)
```

The alias goes into the repository's own config (`.git/config`), so it has
to be set in each clone; it takes precedence over a global alias. Git runs
shell aliases in the top-level directory, so the relative path works from
any subdirectory. To update, pin the new release and sync:
`git filesync set --tag vX.Y.Z tools/git-filesync.py`, then `git filesync
pull tools/git-filesync.py` (`pull` and `status -v` name the newest
release).
