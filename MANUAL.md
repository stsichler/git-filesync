# git-filesync manual

The concepts, commands and options of git-filesync in detail. For
motivation and installation see the [README](README.md).

## Contents

- [Concepts](#concepts)
  - [Upstream, downstream and links](#upstream-downstream-and-links)
  - [The `.git-filesync` file](#the-git-filesync-file)
  - [Exact copies and adaptable files](#exact-copies-and-adaptable-files)
  - [Local modifications on top of the upstream version](#local-modifications-on-top-of-the-upstream-version)
  - [Linked directories](#linked-directories)
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

The **upstream repository** is where a file is developed. A **downstream
repository** carries a copy of it and records a **link**: which upstream
repository and branch (or tag), which path there, and which upstream
version the copy is based on. Nothing is updated automatically – `pull`
syncs the files you choose and proposes a commit message listing every
upstream commit that changed them since the last sync.

All commands run inside the downstream repository.

### The `.git-filesync` file

The links live in `.git-filesync` at the root of the downstream repository,
committed like any other file, in git-config format:

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
[dir "third_party/lib"]
	source = owner/lib
	path = lib             # upstream directory ('/': the root)
	exclude = test/ '*_test.c'   # optional, like include: patterns, quoted as in a shell
	commit = …             # upstream commit that last changed the directory
	tree = …               # the upstream directory at that commit
```

- A `[source]` is an upstream repository with the branch its files follow,
  like a remote with its branch. `add` and `set` create sources as needed
  and name them after the URL (`owner/repo`, with a number appended if the
  name is taken: `owner/repo-2`); a source without files is removed. To
  rename one, use [`source rename`](#source).
- A `[file]` is keyed by the path in the downstream repository. A `tag` in
  it [pins](#pinning-to-a-tag) the file to an upstream tag (or the newest
  tag matching a pattern).
- A `[dir]` is a [linked directory](#linked-directories); it takes `tag`
  and `adaptable` like a `[file]`, its base is `commit` and `tree`.
- `include` / `exclude` are words separated by blanks, quoted as in a
  shell with `'…'` where needed – git config itself removes `"…"`.
- `commit` and `blob` are maintained by the tool: `blob` is the synced
  version of the upstream file, `commit` the upstream commit that last
  changed it (not the branch tip at sync time). So commits that don't touch
  the file don't matter, pushed or not.
- `pull --all` takes only **plain updates**: the recorded commit is in the
  history of the branch head or tag to sync to. A branch that went back
  (`older`), a diverged history (another branch, a rebased commit) or a
  commit the source doesn't have (it is behind, or history was rewritten)
  isn't guessed at: `pull --all` leaves such files out, `pull FILE` syncs
  them (see [`pull`](#pull)).
- An entry **without** `commit` and `blob` (`tree`) is a **new link**: `status`
  shows it as `new`, and `pull` does its first sync exactly as
  [`add`](#add) would. This links many files at once: write their entries
  with [`edit`](#edit) – just `source` and `path` (and `tag`, `adaptable`
  as needed) – then run `pull --all`. Until its first sync, a new link has
  nothing to [`restore`](#restore) or `diff` against (`diff --upstream`
  shows the whole file); `pull -n` tells whether the first sync would be
  refused.
- Everything else may be edited by hand, but [`set`](#set),
  [`source`](#source), [`rm`](#rm), [`unlink`](#unlink) and [`mv`](#mv) know
  what a change means. When the last link is removed, the file is deleted.
  A command that stages the file warns if it had changes not staged before
  the command ran: they are staged too.

Paths must lie inside the working tree: entries pointing outside it (`..`,
absolute paths) or into a `.git` directory are errors and never written, so
a cloned repository's `.git-filesync` can't make `pull` touch other files.
The same holds when something is **in the way** of a linked file – a
directory (or anything but a file) where it belongs, a parent that is a
file or a symbolic link: git would delete what is there, or write
elsewhere. No command writes, deletes or reads there (only `restore -S`,
which sets just the index, works); `status` reports an error. Move it away,
or remove the link with `unlink`.

### Exact copies and adaptable files

By default a linked file must stay an **exact copy** of its upstream
version. Any change, committed, staged or not, is a violation: `status` marks it
`NOT ALLOWED: not adaptable` (`-s`: `(not adaptable!)`, `--exit-code`: 1),
the hooks report it, and `pull` refuses the file. Look at the change with
`diff`, then:

- go back to the synced version with [`restore -SW`](#restore) – or sync
  and discard in one step with `pull --overwrite`;
- discard uncommitted changes with `git restore -SW`;
- or allow changes: mark the file **adaptable**.

```sh
git filesync set src/foo.c --adaptable     # or add --adaptable; --no-adaptable takes it back
```

In `.git-filesync` this is `adaptable = true` (a bare `adaptable` means
true, as everywhere in git config).

### Local modifications on top of the upstream version

An [adaptable](#exact-copies-and-adaptable-files) file may differ from its
upstream version. Its entry records the **base** – "this file is based on
upstream commit X" – not the content. Since file and entry are committed
together, every commit defines the local layer exactly:

```
  upstream version (entry: commit X)  +  local modifications  =  file downstream
```

Committed local changes are **adaptations**, the others **uncommitted
changes**; `status` shows them separately. `pull` keeps adaptations by
merging them with the new upstream version and, like `git pull`, refuses
files with uncommitted changes. `diff` and `difftool` show both.

A synced file must exist, adaptable or not: a **missing** one – deleted,
committed or not – is never allowed while it is linked. Bring it back with
[`restore`](#restore), or remove the link with [`unlink`](#unlink) (link and
file: [`rm`](#rm)).

### Linked directories

A `[dir]` entry links a whole directory: `add URL DIR` (see [Linking a
directory](#linking-a-directory)). Its files are those of the upstream
directory at the base that its `include` / `exclude` patterns select.
`pull` keeps them in sync – also adding the files new upstream and deleting
those deleted there. Everything else in the directory belongs to this
repository: no command looks at it or touches it.

Each file of the entry follows the rules of a linked file: an exact copy
unless the entry is adaptable, merged on `pull`, never missing. `status`
shows the entry in one line, with the number of files concerned:
`missing:    lib/  (2 of 40 files, NOT ALLOWED: still linked)`.

`pull` refuses the whole entry where it would lose local content, and
names the files:

- a file **missing** here but still upstream (gone upstream too: fine);
- a file **adapted here and deleted upstream** (or no longer selected by
  the patterns) – `--overwrite` deletes it, `--force` keeps it as a file of
  this repository;
- a file **new upstream** where a different one of this repository is –
  `--overwrite` replaces it, `--force` keeps it as an adaptation (an
  adaptable entry only).

Other patterns ([`set --include` / `--exclude`](#set)) change only
`.git-filesync`; the next `pull` applies them like a change upstream:
files they now select are fetched, those they no longer select deleted.
Until then `status` shows the entry as pending (`patterns changed; files: 2
new`), and its files are still those of the old patterns, which the entry
keeps in `synced-include` / `synced-exclude` (only while they select other
files; `pull` removes them).

Entries don't overlap: no `[file]` or other `[dir]` inside a `[dir]`.
Commands that change an entry – `pull`, `set`, `rm`, `unlink`, `mv` – take
the whole directory; `status`, `diff`, `difftool` and `restore` also take
files in it (a file of this repository there isn't linked: an error).

## Commands

Basic commands – what you need day to day:

| Command | Purpose |
|---|---|
| [`status [PATH…]`](#status) | state of the linked files, like `git status` |
| [`pull PATH…`, `pull --all`](#pull) | sync files from upstream |
| [`diff [PATH…] [-- OPTS]`](#diff) | local changes against the synced upstream version |
| [`difftool [PATH…] [-- OPTS]`](#difftool) | the same in your difftool |
| [`restore PATH…`](#restore) | files back to the synced upstream version, like `git restore` |
| [`add URL\|SOURCE FILE\|DIR`](#add) | link a file – or a directory – to the upstream repository |
| [`rm PATH…`](#rm) | remove linked files and their links, like `git rm` |
| [`unlink PATH…`](#unlink) | remove links, keep the files |
| [`mv OLD… NEW`](#mv) | move linked files and their links |

[Advanced commands](#advanced-commands) – to change links and sources, and for setup:

| Command | Purpose |
|---|---|
| [`set PATH… [OPTIONS]`](#set) | change (or show) the link of linked files: source, tag, upstream path, adaptable, patterns |
| [`edit`](#edit) | edit `.git-filesync` in the editor |
| [`source [ACTION …]`](#source) | list sources, rename them, change URL or branch |
| [`source map [URL\|SOURCE [DIR]]`](#source-map) | use a local checkout of upstream |
| [`cache [ACTION]`](#cache) | the cache of upstream clones: show, list, prune, clear, print its directory |
| [`hooks [ACTION]`](#hooks) | the hooks: show, install, remove; reminders, push check |

Commands named like a Git command behave like it (`status`, `pull`,
`diff`, `difftool`, `restore`, `add`, `rm`, `mv`; `source` like `git
remote`): the same kind of output and exit codes, the same caution with
uncommitted changes.

**No command commits.** They change the working tree or stage, like `git
add` – `pull` like `git merge --squash` – and you commit. So you can check
everything first, undo it (`git restore -SW`), or combine several commands
and your own changes in one commit. `pull` and `add` prepare a [proposed
commit message](#proposed-commit-messages) that a plain `git commit`
offers. The reading commands (`status`, `diff`, `difftool`, listing
sources, the hooks) change nothing in the repository.

**`-n` / `--dry-run`** is there for every command that stages something
or deletes files – except `restore` (like `git restore`), `edit` and
`hooks`. It leaves out only the writing: it reads, checks and accesses
upstream as without it, refuses the same, and shows what would change.

Without a command, `status` runs. `PATH` is a file or a directory (all
linked files below it), relative to the current directory, as are the
paths in the output. Options follow the command; `git filesync <command>
-h` lists them.

Two options mean the same everywhere (also in git-assetsync):
**`--overwrite`** replaces local content – an existing file, local
adaptations – with the upstream version; **`--force`** does something
refused by default without losing local content (relink a file, add lines
to the hooks of other tools; `rm -f` removes uncommitted changes, but keeps
them as below).

<a id="discarded-content"></a>**Discarded content can be got back.**
Before `restore`, `rm -f` or `--overwrite` replace or delete content that
isn't committed, they keep it as a Git object and say so:

```text
discarded: src/lib.c (git show 3f2a9c1d07be to get it back)
```

`git show 3f2a9c1d07be > src/lib.c` writes it back exactly. Where the
index goes too (`rm -f`, `--overwrite`, `restore -S`), a staged version is
kept as well (`discarded: src/lib.c, as staged …`). `git gc` removes such
objects after a while (normally two weeks).

### Common options

| Option | Commands | Effect |
|---|---|---|
| `--no-fetch` | `status`, `pull`, `diff`/`difftool`, `restore`, `add`, `set`, `source set` | don't fetch, use the cached state (offline); an upstream not in the [cache](#cache) yet is cloned anyway. `restore`, `diff` of local changes and `set` without `--source`, `-b`, `--tag`, `-p` fetch only if the cache lacks the branch, even without it |
| `--remote` | as `--no-fetch` | ignore [mappings](#source-map) this once and use the upstream URL; the mapping stays. With `--no-fetch`: the cached state |
| `--color[=always\|never\|auto]`, `--no-color` | all | override `color.filesync` / `color.ui` (see [Colors](#colors)) |

### `status`

`status [PATH…]` – state of all (or the given) linked files.

| Option | Effect |
|---|---|
| `-s`, `--short` | short format, three columns |
| `-v`, `--verbose` | also list every linked file with its source; for a [pinned](#pinning-to-a-tag) one the [newer tags](#newer-tags) too |
| `--exit-code` | exit with 1 if something is to sync, a linked file is missing, or a file that isn't adaptable is modified |

Each file is looked at in three independent respects:

| Respect | Compares | States |
|---|---|---|
| upstream | synced upstream version ↔ current upstream | up to date, `pending`, `older`, `changed`, `renamed`, `deleted`, `new` |
| committed | synced upstream version ↔ committed file (`HEAD`) | `unmodified`, `adapted` |
| working tree | committed file ↔ staged and working file (uncommitted changes) | clean, `modified`, `new file`, `missing` |

The output has sections like `git status`:

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
  (use "git restore -SW <file>..." to discard uncommitted changes)
	modified:   src/bar.c
```

A [linked directory](#linked-directories) has one line, the files
concerned counted in the note: `pending:    lib/  (2 commits; files: 1 new,
1 deleted)`, `adapted:    lib/  (3 of 40 files)`.

With nothing to report: `nothing to sync, all 5 linked files unmodified`.
`-v` adds a `Linked files:` section, warnings (e.g. about a mapped
checkout) follow in a `Warnings:` section, and `advice.statusHints = false`
turns the hints off. For `renamed` and `deleted` see [Files renamed or
deleted upstream](#files-renamed-or-deleted-upstream).

The **short format** (`-s`), like `git status -s`, has one line per file
with something to report:

| Column | Meaning |
|---|---|
| 1 – upstream | `P` pending, `O` upstream older than last sync, `D` history diverged (or previous sync point unknown), `R` renamed upstream, `X` deleted upstream, `N` new link, `E` error |
| 2 – committed | `M` adapted |
| 3 – working tree | `M` modified, `D` missing (marked `(missing!)`), `?` not committed yet |

```
P   src/a.c
PM  src/b.c
 MM src/c.c
 M  include/x.h  (not adaptable!)
  D src/old.c  (missing!)
```

Like `git status`, the exit code is 0 (2 on errors); see `--exit-code` for
scripts and [CI](#ci).

### `pull`

`pull PATH…`, `pull --all` – sync files to their current upstream version.
What that is follows simple rules: a [tag](#pinning-to-a-tag) – exactly
that tag; a [tag pattern](#tag-patterns) – the newest matching tag on the
source's branch; otherwise the head of the branch (with a [mapped
checkout](#source-map): of the branch there). Something given that doesn't
exist upstream is an error; settings that merely don't fit together, like
a tag that isn't on the branch, give a warning.

The synced files and their entries are staged, like after `git merge
--squash`; nothing is committed. `pull` proposes **one commit** for all of
them – for several files with a section each and a subject like
`[filesync] Sync 3 files from owner/lib` – and a plain `git commit` offers
it:

```
[filesync] Sync src/foo.c from owner/lib@a1b2c3d (2026-10-28)

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)

Upstream changes since 3f2a9c1 (2026-09-12):
- Fix off-by-one in buffer handling (9e8d7c6, 2026-10-27)
- Add support for chunked transfer (a1b2c3d, 2026-10-28)
```

What `pull` does with a file depends on its state (code of `status -s`):

| State | `pull PATH…` | `pull --all` |
|---|---|---|
| up to date | nothing | nothing |
| pending (`P`), new link (`N`), renamed upstream (`R`) | syncs | syncs |
| older than last sync (`O`) | goes back | left out |
| history diverged (`D`), also with the same version or the previous sync point unknown | syncs | left out |
| deleted upstream (`X`) | error: `unlink` or `rm` it | error |
| missing | error: `restore` or `unlink` it | error; nothing to sync: left out |
| modified, but not adaptable | error: `--overwrite`, `restore -SW` or `set --adaptable` | error; nothing to sync: left out |
| uncommitted changes (adaptable) | something to sync: error – commit, stash or discard them, as for `git pull`, or `--overwrite` | the same |

`pull --all` takes only plain updates along the history of the branch or
tag, and names each file it leaves out with the reason (`warning: a.c:
older than last sync - left out`). With `--commit`,
`-b` or `--tag`, `--all` takes every file as if named. Files left out
don't change the exit code; an error makes it 2, conflicts 1, and the
other files are still synced. In scripts and CI: `git filesync pull --all
&& git commit --no-edit`.

| Option | Effect |
|---|---|
| `--all` | all linked files, see the table above; not together with paths |
| `--commit REV` | sync to this revision once – a branch, tag or commit id, also backwards (the message then lists what is reverted); the file keeps its branch or tag |
| `-b`, `--branch BRANCH` | sync to the head of BRANCH once (see [Another branch or tag, once](#another-branch-or-tag-once)) |
| `--tag TAG` | sync to TAG once |
| `--overwrite` | take the upstream version as it is, discarding adaptations and uncommitted changes ([kept](#discarded-content)), also if the file is up to date |
| `-W`, `--worktree` | write to the working tree only: nothing staged, `.git-filesync` unchanged – see [Trying a newer version](#trying-a-newer-version) |
| `--force` | [linked directory](#linked-directories): keep a file of this repository that `pull` would delete (adapted, deleted upstream) or replace (new upstream) |
| `-n`, `--dry-run` | change nothing; report per file what would happen: the version, whether adaptations merge cleanly (or how many conflicts), a rename upstream, every refusal |
| `-v`, `--verbose` | before each file, where it comes from and the version synced so far: `src/foo.c: from owner/lib:lib/foo.c (main), synced at 3f2a9c1` |

- **Adaptations** are merged with the new upstream version (3-way merge,
  base: the last synced version). On conflicts the file gets the usual
  conflict markers and stays unstaged, and `pull` exits with 1: resolve
  them, `git add` the files, then `git commit`.
- **Renamed upstream:** `pull` follows the file, see [Files renamed or
  deleted upstream](#files-renamed-or-deleted-upstream).
- **Linked directories:** `pull` syncs all their files or none, see
  [Linked directories](#linked-directories).
- **Pinned files:** `pull` ends with a hint if there are [newer
  tags](#newer-tags) on the source's branch.
- **Pulling again before the commit** works, e.g. to another version: what
  a pull staged counts as synced, not as a local change, and the proposed
  message gets a section for each pull. Merged adaptations are local
  changes, though: commit them first.

#### Trying a newer version

`pull -W` writes what `pull` would sync into the working tree only –
nothing staged, `.git-filesync` unchanged –, e.g. to see whether your
project still builds with it. It refuses what `pull` refuses and takes the
same options.

```sh
git filesync pull -W src/foo.c             # try it
git restore src/foo.c                      # go back
git filesync pull --overwrite src/foo.c    # or take it
```

Meanwhile `status` shows the file as pending, with uncommitted changes –
for a file that isn't adaptable as not allowed, which it is until taken.
Files new upstream in a [linked directory](#linked-directories) stay after
`git restore`. For an adaptable file, `pull --overwrite` drops your
adaptations; to keep them, `git restore` and `pull`.

#### Another branch or tag, once

`pull -b BRANCH` and `pull --tag TAG` sync the given files (or `--all`)
once to the head of another branch or to a tag – e.g. to try a release
before switching to it. Like `git pull <remote> <branch>`, this doesn't
change what the files follow; `pull` ends with a hint:

```
hint: the links still follow their own branch or tag, so 'git filesync pull <file>...' goes back; to stay on tag v1.3.0, use 'git filesync set --tag v1.3.0 <file>...'
```

`status` then shows the files as `older`, `diverged` or `pending`, and
`pull FILE` syncs them back. To switch for good, use [`set -b` / `--tag`](#set), then
`pull`. With `--all`, every file is synced, also those up to date. A
commit id (`--commit`) belongs to one upstream repository, so files of
other ones get an error.

```sh
git filesync pull --tag v1.3.0 --all       # all files to v1.3.0, once
git filesync set src/ --tag v1.3.0         # switch for good ...
git filesync pull src/                     # ... and sync
```

### `diff`

`diff [PATH…] [-- OPTS]` – local changes against the synced upstream
version, in one `git diff` (pager, colors and options as usual; anything
after `--` goes to `git diff`).

| Option | Effect |
|---|---|
| `--committed` | only the committed adaptations (synced → `HEAD`) |
| `--upstream` | what `pull` would bring (synced → current upstream) |
| `--commit REV`, `-b BRANCH`, `--tag TAG` | with `--upstream`: what `pull` with that option would bring |
| `--for-upstream` | a patch for the upstream repository (upstream paths, for `git apply`); not with `--upstream` |

```sh
git filesync diff                    # all local changes: synced upstream version -> working file
git filesync diff --committed        # adaptations only: synced upstream version -> HEAD
git filesync diff --upstream         # what pull would bring
git filesync diff --upstream --tag v1.3.0 src/foo.c   # what pull --tag v1.3.0 would bring
git filesync diff -- --stat
```

With `-- --exit-code` or `-- --quiet`, exit code 1 means differences, like
`git diff`. A change only staged, with the working file as in `HEAD`, shows
`git diff --cached`. Whether adaptations would merge cleanly tells `pull --dry-run`.
For a [linked directory](#linked-directories), `diff` shows its files only
(`--upstream`: also those new and deleted upstream).

**Upstreaming local changes:** `--for-upstream` gives a patch with the
current upstream paths (with `--committed`: only the adaptations):

```sh
git filesync diff --for-upstream src/foo.c > foo.patch
cd ~/src/lib && git apply -3 ../my-repo/foo.patch
```

The patch is relative to the synced version and records its blob id, so
`git apply -3` merges it into any upstream branch – check out the one you
want first.

### `difftool`

`difftool [PATH…] [-- OPTS]` – the same as [`diff`](#diff), file by file in
your difftool (`diff.tool`); `OPTS` go to `git difftool` (e.g. `-t meld`).

| Option | Effect |
|---|---|
| `--committed`, `--upstream`, `--commit`, `-b`, `--tag` | as for `diff` |
| `-y`, `--no-prompt` | don't ask before each file |
| `--prompt` | ask even with `difftool.prompt = false` |

Like `git difftool`, it asks before each file (`Launch 'meld' [Y/n/q]?`);
of `-y` and `--prompt`, the last one given counts. Without `--upstream` /
`--committed`, the right side is the working file itself, so edits made in
the tool are kept.

### `restore`

`restore PATH…` – like `git restore`, but the source is the synced upstream
version (the base recorded in `.git-filesync`): e.g. to discard the changes
of a file that isn't adaptable, or to bring back a missing file. Unlike
`pull --overwrite`, it brings in no newer upstream version; `.git-filesync`
stays as it is. A new link has nothing to restore. For a [linked
directory](#linked-directories), `restore` takes its files (all, or those
given); the repository's own files stay.

| Option | Effect |
|---|---|
| `-S`, `--staged` | restore the index instead of the working tree |
| `-W`, `--worktree` | restore the working tree – the default; with `-S`: both |

`restore -SW` discards committed adaptations: the synced version is back
and staged, ready to commit. (`git restore FILE` discards only uncommitted
changes, as usual.) Uncommitted content it overwrites is
[kept](#discarded-content).

### `add`

`add URL|SOURCE FILE` – link FILE to a file in an upstream repository, given
by its URL or by the name of a `[source]` (upstream first, then here – as
in `git submodule add`):

- **URL**: the file joins the source with that URL and branch (`-b`,
  default: the upstream default branch), which is created if needed.
- **Source name**: the file joins that source; a `-b` must be its branch.

`add URL|SOURCE DIR` links an upstream directory (see [Linking a
directory](#linking-a-directory)).

| Option | Effect |
|---|---|
| `-b`, `--branch BRANCH` | the upstream branch; for a pinned file where [newer tags](#newer-tags) are looked for |
| `--tag TAG` | [pin](#pinning-to-a-tag) the file to a tag, or a [pattern](#tag-patterns) |
| `-p`, `--path PATH` | upstream path; default: the same as FILE or DIR (`/`: the upstream root; `\` counts as `/`) |
| `--include PATTERN` | directory: only files matching PATTERN; repeatable |
| `--exclude PATTERN` | directory: skip files matching PATTERN; repeatable, beats `--include` |
| `--per-file` | directory: an entry for each file instead of one for the directory |
| `--commit REV` | base FILE on this upstream revision instead of the head of the branch (or the tag) |
| `--overwrite` | replace an existing file that differs with the upstream version ([discarded content](#discarded-content) is kept) |
| `--adaptable` | allow local adaptations; an existing FILE that differs is kept as it is |
| `--force` | relink a file already linked: its entry is made anew, with the options given now |
| `-n`, `--dry-run` | only show what would be linked, and on which version |

The base is the version `pull` would sync to (or `--commit`). If FILE
doesn't exist, it is fetched; its directory must exist, as for `cp` (a
FILE ending in `/` must be an existing directory, which the file goes
into). If FILE exists, it must be that version; otherwise `add` refuses
and names the ways on:

- `--adaptable` keeps it: the differences become
  [adaptations](#local-modifications-on-top-of-the-upstream-version) (for
  an older copy this means the upstream changes since then stay reverted);
- `--overwrite` takes the upstream version;
- `--commit` names the upstream version FILE is a copy of, and `pull` then
  brings the changes since.

Like `git add`, `add` stages FILE – as it is in the working tree, also if
`.gitignore` matches it – and its entry, with a proposed commit message:

```
[filesync] Add src/foo.c from owner/lib@a1b2c3d (2026-10-28)

Upstream: https://github.com/owner/lib.git (main:lib/foo.c)
```

For an existing FILE the subject is `Link FILE to …` (`Relink …` with
`--force`).

```sh
git filesync add https://github.com/owner/lib.git src/foo.c -p lib/foo.c
git filesync add owner/lib include/bar.h --adaptable  # by the name of the [source]
git filesync add owner/lib src/ -p lib/util.h         # into an existing directory: src/util.h
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag v1.2.0
```

#### Linking a directory

If DIR is an existing directory, the upstream path a directory, or
`--include` / `--exclude` are given, `add` links DIR to the upstream
directory: one `[dir]` entry, a [linked directory](#linked-directories).
`-p api` with DIR `proto` gets `api/v1/x.proto` as `proto/v1/x.proto`. As
for `cp -r`, DIR may be new, but its parent must exist. Existing files are
compared with upstream as for FILE. All is staged with one proposed
message:

```
[filesync] Add proto/ from owner/backend@a1b2c3d (2026-10-28)

Upstream: https://github.com/owner/backend.git (main:api/)

- proto/a.proto
- proto/v1/b.proto
```

With `--per-file`, each file gets a `[file]` entry of its own instead;
`pull` then adds and deletes no files. Files already linked are skipped
(`--force` relinks them), so the same `add` later links just the files new
upstream.

Patterns work like `.gitignore` lines, relative to the upstream directory:

| Pattern | Matches |
|---|---|
| `*.proto` | without `/`: a name at any depth |
| `/top.txt`, `v1/*.proto` | with a leading or inner `/`: relative to the upstream directory |
| `test/` | trailing `/`: a directory with everything below it |
| `**/gen/*.h` | `**/` any number of directories; `*` and `?` don't match `/`; `[abc]`, `[!abc]` |

```sh
git filesync add https://github.com/owner/backend.git proto -p api \
    --include '*.proto' --exclude '*_test.proto' --exclude test/
```

### `rm`

`rm PATH…` – like `git rm`: remove the files and their links, staged. If
one has uncommitted changes (or was never committed), nothing is removed –
unless `-f` / `--force` is given ([discarded content](#discarded-content) is
kept). A file already gone just loses its link. `-n` / `--dry-run` only
lists what would be removed; to keep the files, use [`unlink`](#unlink).
Of a [linked directory](#linked-directories), `rm` removes the entry's
files; those of this repository stay.

### `unlink`

`unlink PATH…` – remove the links, keep the files; `.git-filesync` is
staged. `-n` / `--dry-run` only lists them.

### `mv`

`mv OLD NEW` – move a linked file and its link, both staged, like `git mv`:
NEW may be an existing directory; the directory NEW goes into must exist,
and a NEW ending in `/` must be an existing directory. `mv OLD… DIR` moves
several files into the existing directory DIR – all or none. A [linked
directory](#linked-directories) moves as a whole, with the files of this
repository in it. `-n` / `--dry-run` only shows what would be moved.

## Advanced commands

### `set`

`set PATH… OPTIONS` – change the link of linked files: source, tag,
upstream path, adaptable, patterns. Only `.git-filesync` changes (staged);
`status` then shows what is to sync, and `pull` syncs.

`set PATH…` without options shows the links as the `set` command that sets
them, one line per entry – every aspect, also those not set (`--no-tag`),
so it serves as a template for other entries. Entered again, it changes
nothing. `set --list` shows all entries. The quoting is that of a POSIX
shell (also Git Bash, mostly PowerShell; not cmd.exe).

```
$ git filesync set third_party/lib
git filesync set third_party/lib/ --source https://github.com/owner/lib.git -b main --no-tag -p lib --no-adaptable --no-include --exclude test/ --exclude '*_test.c'
```

| Option | Effect |
|---|---|
| `--source URL\|SOURCE` | take the files from another upstream – a fork, a moved repository – or from the `[source]` SOURCE |
| `-b`, `--branch BRANCH` | follow BRANCH (with `--source URL`: of that upstream; default: its default branch) |
| `--tag TAG` | [pin](#pinning-to-a-tag) the files to TAG or a [pattern](#tag-patterns); a tag that doesn't exist is refused |
| `--no-tag` | follow the source's branch again |
| `-p`, `--path PATH` | another upstream path (one file or directory); the same path changes nothing |
| `--adaptable`, `--no-adaptable` | allow [local adaptations](#exact-copies-and-adaptable-files), or not any more (the default) |
| `--include PATTERN`, `--exclude PATTERN` | [linked directory](#linked-directories): new patterns (repeatable; they replace the old ones); the files follow at the next `pull` |
| `--no-include`, `--no-exclude` | linked directory: remove the patterns |
| `--list` | show all entries (see above) |
| `-n`, `--dry-run` | only show what would change |

URL and branch select the source, as for [`add`](#add): the one with that
URL and branch, created if needed – or, if all files of a source move, that
source itself changes (as with [`source set`](#source)).
A source left without files is removed. A `--tag` not on the branch gives a
warning, a pattern without a match there an error; both name the branches
that have it.

The base (`commit` / `blob`) is kept where it still applies, so adaptations
stay adaptations:

- **another tag or branch** of the same upstream: kept; if the new one
  doesn't contain it, the file counts as `older` or `diverged` (also with
  the same version) until `pull FILE` moves it there – `pull --all` leaves it out;
- **another upstream**: kept if it has that version (the recorded commit,
  or else the newest commit on its branch with the same file); otherwise a
  warning: the previous sync point counts as unknown, and `pull FILE`
  syncs the file;
- **another path**: as for `add`, the version at the head of the branch (or
  the tag). The file stays as it is, so differences count as adaptations –
  or, if it isn't adaptable, as a change not allowed, which `pull
  --overwrite` resolves. (Renames upstream need no `set`: `pull` follows
  them.) A linked directory with another path becomes a new link: `pull`
  compares its files, as `add` does.

New patterns take effect at the next `pull`, like a change upstream (see
[Linked directories](#linked-directories)). `set` says what that will do,
with `-n` too:

```text
third_party/lib/: exclude test/ -> (none) (at the next pull: 12 new, 0 deleted)
```

```sh
git filesync set src/foo.c --adaptable
git filesync set src/ --source https://github.com/me/lib-fork.git    # all files below src/
git filesync set src/foo.c -p lib/foo_v2.c
git filesync set cfg/ -b maint --tag 'v1.2.*'    # the newest v1.2.* on maint
git filesync set cfg/ --no-tag                   # follow the branch again
```

### `edit`

`edit` – open `.git-filesync` in your editor, like `git config --edit`
(`GIT_EDITOR`, `core.editor`, `VISUAL`, `EDITOR`); afterwards it is checked
and staged. A file that can't be read any more is not staged – run `edit`
again to fix it. Gaps that `status` would report (a missing `[source]`,
`url`, `branch` or `path`, only one of `commit` and `blob` (`tree`),
overlapping entries, an unused source) are shown as warnings. `edit` keeps whatever you write: a changed
`commit` or `blob` changes what counts as an adaptation.

Your comments and layout are kept: commands change only the lines they
have to. A changed value keeps the indentation and comment of its line, a
renamed entry the comment of its header; a removed entry takes its lines up
to its last key, so comments after it stay.

### `source`

`source [ACTION …]` – list and change the `[source]` sections, like
`git remote`. Only `.git-filesync` changes (staged).

| Command | Effect |
|---|---|
| `source` | list the source names (`-v`: with URL, branch and number of entries) |
| `source rename OLD NEW` | rename a source and every reference to it |
| `source set NAME --url URL` | change the URL, e.g. after upstream moved; the synced versions are looked up there as for [`set --source`](#set) |
| `source set NAME -b BRANCH` | follow BRANCH, for all files of the source; for [pinned](#pinning-to-a-tag) ones where newer tags are looked for |
| `source set NAME` | show the source as the command that sets it, like [`set`](#set) (`--list`: all sources) |

`rename` and `source set` take `-n` / `--dry-run`.

```
$ git filesync source -v
owner/lib	https://github.com/owner/lib.git (main, 3 files)
owner/lib-dev	https://github.com/owner/lib.git (dev, 1 file)
```

`source set` refuses a branch that doesn't exist upstream, and
a change that would make two sources identical – move the files with
[`set`](#set) instead.

### `source map`

`source map [URL|SOURCE [DIR]]` – use the local checkout DIR instead of
fetching from URL (or from the URL of the `[source]` SOURCE). The mapping
belongs to the URL, so it applies to every source with it. Without DIR, the
mappings are listed.

| Option | Effect |
|---|---|
| `--global` | in your global Git config, for all repositories (default: this repository's `.git/config`) |
| `--unset` | remove the mapping |

```sh
git filesync source map https://github.com/owner/lib.git ~/src/lib
git filesync source map owner/lib ~/src/lib      # the same, by the name of the [source]
git filesync source map                          # list (scope, overridden ones marked)
git filesync source map owner/lib --unset
```

Something that looks like a URL (`scheme://…`, `host:path`) is always taken
as one; an argument that is neither a URL, nor a source, nor an existing
path is refused. A repository's own mapping beats a global one, so
repositories can point to different checkouts of the same upstream.
DIR is kept as given, only made absolute: a junction, symlink or drive
letter on the way stays. A relative DIR counts from the real current
directory; reached through a junction, give DIR absolute.

A mapped source uses **its branch as it is in the checkout** (pinned files:
the tag there) – the local branch, unpushed commits included, whatever is
checked out there. Nothing is fetched; it works offline.

- local branch ahead of the last sync → `pending`; behind it (e.g. reset) →
  `older`, and `pull` goes back, listing what is reverted;
- warnings: another branch checked out there with a different version of
  the file (that one is *not* synced); uncommitted changes to the file
  there (only committed states are synced); the file's version comes from
  an unpushed commit (others can't resolve it);
- no local branch of that name → `origin/<branch>` as last fetched there,
  with a note.

The checkout is only read – also from a read-only network share; LFS
objects missing there come via the cache clone. To work against the server
once, add [`--remote`](#common-options) (`git filesync status --remote`).

Without a mapping, a source is fetched into a blobless partial clone in
`~/.cache/git-filesync` (Windows: `%LOCALAPPDATA%\git-filesync`, or
`FILESYNC_CACHE`) on each run – except when all that is needed is a tag
already there. Credentials are those your Git uses for the URL. File
contents are fetched only when needed, with Git's wire protocol v2 (current
servers all support it). Deleting the cache is safe; see [`cache`](#cache).

### `cache`

```
git filesync cache [list | prune [--max-age DAYS] [--max-size SIZE] [-n] | clear [-n] | dir]
```

The cache of upstream clones, one per URL, shared by all your repositories;
works outside a repository too.

```
$ git filesync cache
/home/me/.cache/git-filesync: 12 clones, 85.3 MiB
cleaned up automatically: clones unused for 90 days (filesync.cacheMaxAge, filesync.cacheMaxSize)
$ git filesync cache list
  31.2 MiB  2026-10-19  https://github.com/owner/lib.git
   4.1 MiB  2026-09-02  https://gitlab.com/group/tools.git
```

| Action | Effect |
|---|---|
| (none) | where the cache is, how big, and its limits |
| `list` | the clones, most recently used first: size, last used, URL |
| `prune` | remove clones by the configured limits; `--max-age DAYS` and `--max-size SIZE` (e.g. `500M`, `2G`) set others for this run, `0` meaning no limit; `-n` only shows them |
| `clear` | remove all clones (`-n`: only show them) |
| `dir` | print the cache's directory, e.g. to keep it between CI runs |

After a fetch, at most once a day, the cache is pruned automatically:

| Setting | Default | Effect |
|---|---|---|
| `filesync.cacheMaxAge` | `90` | remove clones unused for that many days; `0` or `off`: never |
| `filesync.cacheMaxSize` | (none) | then remove the least recently used ones until the cache is at most this big, e.g. `2G`; `0` or `off`: no limit |

Clones used in the last minutes are never removed; a removed one is cloned
again when needed.

### `hooks`

`hooks install` adds a `pre-push` hook (fetches) and a `post-merge` hook
(cached state only). Both report pending syncs, errors, missing files and
changes not allowed on stderr, and never block – unless the push check is
set to `error`. If a hook of another tool exists, the lines to add are
printed; `hooks install --force` puts them right after its `#!` line. With
`core.hooksPath` set, the hooks go there (with a warning, as other
repositories may share it). `hooks uninstall` removes our lines again (and
hook files with nothing else).

`hooks` without an action shows the state of each hook: `installed`,
`outdated` (run `hooks install` again), `not installed`, or a hook of
another tool without our lines.

```
$ git filesync hooks
pre-push: installed
post-merge: not installed (install with 'git filesync hooks install')
```

**Sharing `pre-push` with Git LFS:** git passes the refs being pushed on
stdin, once. The git-filesync block reads them and hands them on to the
commands after it, so it must come **before** `git lfs pre-push` (as
`hooks install --force` puts it); after it, the push check sees nothing.
git-assetsync's block works the same way; the two may come in either order.

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

**Push check:** `pre-push` also reports a linked file synced to an upstream
commit that isn't on the upstream server – typically pulled from an
unpushed commit of a [mapped checkout](#source-map); others couldn't use it
as their base:

```
filesync: src/foo.c: synced from upstream commit 1a2b3c4d5e6f, which is not on the server (https://github.com/owner/lib.git) - push it there first
```

The commit must be on a branch or tag of the server (asked via the cache
clone). Entries the remote already has were checked when they were pushed,
so a push usually doesn't contact the upstream server at all. Like Git with
submodules, it only warns by default:

| `filesync.pushCheck` | Effect |
|---|---|
| `warn` (default) | report, push anyway |
| `error` | report and refuse the push (`git push --no-verify` skips it) |
| `off` | no check |

A server that can't be reached never refuses the push. The hooks run the
internal command `git filesync hook pre-push` / `hook post-merge`.

## Further topics

### Pinning to a tag

Instead of following its source's branch, a file can be pinned to a tag,
e.g. a release:

```sh
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag v1.2.0
git filesync set cfg/ --tag v1.2.0          # files already linked
```

The `[file]` entry then has `tag = v1.2.0`; the source stays, shared with
files following its branch, which is where [newer tags](#newer-tags) are
looked for. `status` compares against the version at the tag, and `pull`
syncs to it.

Tags are taken as immutable, as Git does: once a tag is in the cache,
`status` and the hooks fetch nothing for it (a tag moved on the server is
noticed only with the next fetch for another reason). With a [mapped
checkout](#source-map), the tag there is used. `pull` and `status -v` fetch
the tags (unless `--no-fetch`) to name newer ones.

To move on to a newer release, change the tag, then sync:

```sh
git filesync set cfg/ --tag v1.3.0
git filesync pull cfg/
```

`set --no-tag` follows the branch again; `pull --tag` [tries a tag
once](#another-branch-or-tag-once).

#### Tag patterns

A tag with `*`, `?` or `[…]` is a pattern (shell glob, whole tag name): the
file follows the **newest matching tag on the source's branch**, so `pull`
moves on to new releases by itself:

```sh
git filesync add https://github.com/owner/lib.git cfg/x.yml --tag 'v1.*'
```

- "Newest" is meant as for [newer tags](#newer-tags), by the commit graph.
- `status` fetches the tags (unless `--no-fetch`) and shows a new matching
  tag as `pending`; `status -v` shows which tag the pattern matches now
  (`tag v1.* = v1.4 on main`). The commit message names the tag.
- Tags that don't match are ignored; no match on the branch is an error.

#### Newer tags

Tag names are opaque (`v1.10` vs. `v1.9`, `tool-20261016`), and tags carry
no reliable date. So "newer" is defined by the commit graph: the newest tag
is on the first tagged commit from the branch head back along its
first-parent line – tags on merged side branches don't count:

```
hint: 3 files pinned to tag v1.2.0; the newest tag on branch main is v1.4.0 (use 'git filesync set --tag v1.4.0 <file>...' and pull to switch)
```

If the pinned tag isn't on the branch, `status` warns; to follow a
maintenance line, switch the files to it: `set FILE… -b maint --tag
v1.2.1`. Pre-releases count like any tag. With a [mapped
checkout](#source-map), its local branches and tags count, unpushed ones
included.

### Proposed commit messages

`add` and `pull` put a proposed commit message into `.git/SQUASH_MSG`,
which git offers for the next plain `git commit` (`git commit --no-edit`
takes it as it is); IDEs such as VS Code show it too. Git removes it after
the next commit and on `git reset`.

- Every message starts with `[filesync] ` (`git log --grep='^\[filesync\]'`).
- Every upstream commit id comes with its date (the committer date): `…
  from owner/lib@a1b2c3d (2026-10-28)`, `- Fix … (9e8d7c6, 2026-10-27)`.
- Several commands in a row add their messages, also to one of git's own
  (e.g. from `git merge --squash`).
- A copy stays in `.git/FILESYNC_MSG`, to get it back after `git reset` or
  `git commit -m`: `git commit -e -F .git/FILESYNC_MSG`.

### Files renamed or deleted upstream

When the linked path no longer exists upstream, `status` looks at the
commit that removed it:

- **renamed** (also with changes, also repeatedly): `renamed:    src/foo.c
  (lib/foo.c -> lib/bar.c, 2 commits)`, short format `R`. `pull` follows
  it: the new path goes into the entry, adaptations are merged, and the
  message notes the rename.
- **deleted**: `deleted:    src/foo.c  (upstream, by 1a2b3c4)`, short
  format `X`, counted by `--exit-code` and the hooks. `pull` refuses: keep
  the file as your own (`unlink`), or delete it too (`rm`); `pull --commit`
  still syncs to a revision that has it.

Renames are detected as by `git diff -M` (similar content). If the previous
sync point is unknown, the missing path is an error; fix it with `set -p`.
A [linked directory](#linked-directories) gone upstream counts as deleted
(a rename isn't followed); a file in it renamed upstream takes its
adaptations along.

### Git LFS

Whether a file is stored in Git LFS upstream, downstream, in both or in
neither doesn't matter:

- Upstream LFS pointers are resolved to the content – from a mapped
  checkout's LFS store, or with `git lfs smudge` from the LFS server.
  Comparisons use the pointer's SHA-256, without a download.
- Downstream, the file is stored as `.gitattributes` say – as an LFS
  object or a regular blob.
- `diff`, `difftool` and merges work on the real content.

If LFS content can't be retrieved (no git-lfs, server unreachable,
`GIT_LFS_SKIP_SMUDGE`), the command fails instead of writing a pointer
file.

### Line endings

Upstream and downstream may normalize differently (CRLF committed upstream,
`core.autocrlf` or `text=auto` downstream). Upstream content is compared
and merged in the form the downstream repository stores, and written as a
checkout would – no false modifications, no eol-only conflicts.
`.git-filesync` itself is written with the line ends of a checkout.

### Offline operation

With a [mapped checkout](#source-map), all commands work offline (`add`
takes the default branch from the checkout's `origin/HEAD`). Files [pinned
to a tag](#pinning-to-a-tag) work offline once the tag is in the cache. If a
fetch fails, the cache is used with a warning; a file version never read
before may be missing there, so `status` warns and counts the file as
modified (`pull --overwrite` gets it back to a known state). `--no-fetch`
skips the network explicitly.

### Colors

Output is colored like `git status`: pending upstream changes yellow,
adaptations cyan, uncommitted changes red, changes not allowed and errors
bold red. Colors follow `color.filesync`, else `color.ui` (default: on for
terminals); `--color[=WHEN]`, `--no-color` and `NO_COLOR` override that.
Hook output is colored the same way, `diff` by `git diff`. The help (`-h`)
has colors from Python 3.14 on, only on a terminal.

### CI

To learn when upstream has changed, let a scheduled CI job in the
downstream repository run `status --exit-code`: it fails when a sync is
pending, and GitHub (or your CI) notifies you of the failed run. It only
reports – syncing stays with you.

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

To pin a version, download
`https://github.com/stsichler/git-filesync/releases/download/v0.23.2/git-filesync.py`
instead. Private upstream repositories need a token with read access.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | unfinished: `pull` with conflicts; `status --exit-code` with something to sync, a missing file or a change not allowed; `diff -- --exit-code` with differences |
| `2` | error |
| `141` | the output went into a pipe closed early (`… \| head`, a pager quit), like Git; reading commands stop there, the others finish their work |

`--dry-run` exits with 0, or 2 on errors – also for the refusals it
reports; expected merge conflicts don't change it.

### Binary files

Binary files can be synced, but not merged with local modifications.

### Windows

git-filesync runs with Git for Windows and a Python from python.org or the
Microsoft Store (alias with `py` or `python`, see the [README](README.md)).
Git for Windows runs the alias through its MSYS shell, also from cmd or
PowerShell, and that shell changes two kinds of arguments:

- **Wildcards** in file names (`*`, `?`, `[…]`) are expanded if a file
  matches: `'f[1].txt'` becomes `f1.txt` when that file exists.
- **Arguments starting with `/`** become Windows paths: `--include /x.md`
  becomes `C:/Program Files/Git/x.md`. For the upstream root, `-p .` works
  as well as `-p /`.

For such arguments, run the script directly, e.g. `py
C:/tools/git-filesync.py add owner/lib docs --include /x.md` in cmd or
PowerShell, or with `MSYS_NO_PATHCONV=1` in front in Git Bash. Don't set
`MSYS_NO_PATHCONV` (or `MSYS=noglob`) for git itself: that breaks the
alias.

### Shipping git-filesync with your repository

git-filesync can keep a copy of itself in your repository, so everyone has
the same version:

```sh
git filesync add https://github.com/stsichler/git-filesync.git tools/git-filesync.py \
    -p git-filesync.py --tag v0.23.2
git config alias.filesync '!python3 tools/git-filesync.py'     # each clone, once (Windows: !py …)
```

The repository's alias beats a global one, and git runs it in the
top-level directory, so it works from any subdirectory. To update: `git
filesync set --tag vX.Y.Z tools/git-filesync.py`, then `pull` (`pull` and
`status -v` name the newest release).
