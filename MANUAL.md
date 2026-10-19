# git-filesync manual

Detailed description of the concepts, commands and options of git-filesync.
For motivation and installation see the [README](README.md).

## Contents

- [Concepts](#concepts)
  - [Upstream, downstream and links](#upstream-downstream-and-links)
  - [The `.git-filesync` file](#the-git-filesync-file)
  - [Local modifications on top of the upstream version](#local-modifications-on-top-of-the-upstream-version)
  - [Strict files](#strict-files)
- [Commands](#commands)
  - [Common options](#common-options)
  - [`status`](#status) · [`pull`](#pull) · [`diff`](#diff) · [`difftool`](#difftool)
  - [`add`](#add) · [`set`](#set) · [`edit`](#edit) · [`unlink`](#unlink) · [`mv`](#mv) · [`source`](#source) · [`map`](#map) · [`cache`](#cache)
  - [`install-hooks`, `uninstall-hooks`](#install-hooks-uninstall-hooks)
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
automatically – `pull` syncs one file at a time, with a commit message that
lists every upstream commit that changed the file since the last sync.

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
	strict = true          # optional, see below
	commit = …
	blob = …
[source "owner/lib-2"]
	url = https://github.com/owner/lib.git
	tag = v1.2.0           # pinned to a tag instead of following a branch
	branch = main          # optional: where newer tags are looked for
```

- A `[source]` names an upstream repository and either a branch it follows or
  a tag it is [pinned](#pinning-to-a-tag) to – the latter optionally with
  the branch on which [newer tags](#newer-tags) are looked for. `add` with
  a URL reuses an existing source only if URL *and* branch/tag match (with
  `--tag` but no `-b`: a source pinned to that tag, whatever its branch),
  and creates one otherwise; `add` with the name of a source uses exactly
  that source. A new source is
  named `owner/repo` after its URL; if that name is already taken by another
  URL, branch or tag, a number is appended (`owner/repo-2`, …). Rename it
  with [`source rename`](#source); `status`, `add` and the commit messages
  of `pull` show it.
- `[file]` sections are keyed by the path in the downstream repository.
- `commit` and `blob` are maintained by the tool: `blob` is the synced
  version of the upstream file, `commit` the upstream commit that last changed
  it (not the branch tip at sync time). One file version thus always gives
  the same entry, and commits that don't touch the file – unpushed, rebased
  or not – don't matter.
- Everything else may be edited by hand – with [`edit`](#edit), or e.g.
  `git config -f .git-filesync file.src/foo.c.path lib/new_name.c` (a file
  renamed upstream is [followed by `pull`](#files-renamed-or-deleted-upstream)
  anyway). [`source`](#source) changes URL, branch and tag of a source.
- When the last link is removed, the file is deleted.
- File paths must lie inside the working tree. Entries pointing outside it
  (`..`, absolute paths) or into a `.git` directory are reported as errors
  and never written – a cloned repository's `.git-filesync` can't make
  `pull` touch other files.

### Local modifications on top of the upstream version

The file downstream doesn't have to be identical to the upstream version: it
may carry local adaptations. Its entry in `.git-filesync` records the
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

### Strict files

Some files should stay exact copies. Mark them with `add --strict`, or
later with [`set --strict`](#set):

```sh
git filesync set src/foo.c --strict
```

In `.git-filesync` this is `strict = true` in the `[file]` (as everywhere in
git config, a bare `strict` without a value means true).

For a strict file, adaptations as well as uncommitted changes are reported
as a violation: `status` marks them `NOT ALLOWED: strict` (`-s`: `(strict!)`,
`--exit-code`: 1), the hooks report it, and `pull` refuses to merge (other
files of `pull --all` are still synced). Inspect with `diff`, then discard
adaptations with `pull --overwrite`, uncommitted changes with `git restore`,
or lift the restriction (`git filesync set --no-strict FILE`).

## Commands

| Command | Purpose |
|---|---|
| [`status [PATH…]`](#status) | state of the linked files, like `git status` |
| [`pull PATH…`, `pull --all`](#pull) | sync files from upstream |
| [`diff [PATH…] [-- OPTS]`](#diff) | local changes against the synced upstream version |
| [`difftool [PATH…] [-- OPTS]`](#difftool) | the same in your difftool |
| [`add FILE\|DIR URL\|SOURCE`](#add) | link a file – or all files of a directory – to the upstream repository |
| [`set PATH… OPTIONS`](#set) | change the link of linked files: source, upstream path, strict |
| [`edit`](#edit) | edit `.git-filesync` in the editor |
| [`unlink PATH…`](#unlink) | remove links, keep the files |
| [`mv OLD NEW`](#mv) | move a linked file and its link |
| [`source [ACTION …]`](#source) | list sources, rename them, change URL, branch or tag |
| [`map [URL\|SOURCE [DIR]]`](#map) | use a local checkout of upstream |
| [`cache [ACTION]`](#cache) | the cache of upstream clones: show, list, prune, clear |
| [`install-hooks`, `uninstall-hooks`](#install-hooks-uninstall-hooks) | hooks: reminders, push check |

Commands named like a Git command behave like it (`status`, `pull`, `diff`,
`difftool`, `add`, `mv`; `source` like `git remote`): same kind of output,
same exit codes, same caution with uncommitted changes. Like in Git, only
`pull` commits; `add`, `set`, `mv`, `unlink` and `source` stage their changes, and
`add` prepares a proposed commit message that a plain `git commit` offers
(see [Proposed commit messages](#proposed-commit-messages)). `git filesync`
without a command runs `status`.

Paths are relative to the current directory. Where `PATH…` is accepted, a
directory stands for all linked files below it. Options follow the command
(`git filesync status --no-fetch`); `git filesync <command> -h` lists them.

### Common options

| Option | Commands | Effect |
|---|---|---|
| `--no-fetch` | `status`, `pull`, `diff`, `difftool`, `add`, `set`, `source -v` | don't fetch, use the cached state (offline) |
| `--remote` | same | ignore local checkout mappings (see [`map`](#map)) |
| `--color[=always\|never\|auto]`, `--no-color` | all | override `color.filesync` / `color.ui` (see [Colors](#colors)) |

### `status`

`status [PATH…]` – state of all (or the given) linked files.

| Option | Effect |
|---|---|
| `-s`, `--short` | short format, three columns |
| `-v`, `--verbose` | also list every linked file with its source; for a [pinned](#pinning-to-a-tag) one also the [newer tags](#newer-tags) of upstream |
| `--exit-code` | exit with 1 if something is to sync or a strict file is modified |

`status` looks at each linked file in three independent respects:

| Respect | Compares | States |
|---|---|---|
| upstream | synced upstream version ↔ current upstream | up to date, `pending`, `older`, `changed`, `renamed`, `deleted`, `new` |
| committed | synced upstream version ↔ committed file (`HEAD`) | `unmodified`, `adapted` |
| working tree | committed file ↔ working file | clean, `modified`, `deleted`, `new file` |

and reports them in sections like `git status`:

```
Upstream changes to sync:
  (use "git filesync diff --upstream <file>..." to see what pull would bring)
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
| 1 – upstream | `P` pending, `O` upstream branch older than last sync, `D` history diverged or previous sync point unknown, `R` renamed upstream, `X` deleted upstream, `N` not in the working tree yet, `E` error |
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

`pull PATH…`, `pull --all` – sync to the current upstream version of the
file: the version on the source's branch (with a [local checkout](#map):
that checkout's branch), or at its [tag](#pinning-to-a-tag). Recorded is the upstream commit that last changed the
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
| `--commit REV` | sync to this upstream revision instead – branch, tag or commit id, also backwards; exactly one file. The link keeps its branch or tag |
| `-b`, `--branch BRANCH` | switch the files to following BRANCH and sync them (see [Switching branch or tag](#switching-branch-or-tag)); with `--tag`: the branch to look for newer tags on |
| `--tag TAG` | switch the files to (pin them to) TAG and sync them; the source's branch stays the one to look for newer tags on |
| `--overwrite` | discard local adaptations and take the upstream version as is (also when the file is up to date) |
| `--autostash` | set uncommitted changes aside, sync, re-apply them |
| `--no-edit` | commit with the proposed message without opening the editor |
| `--no-commit` | only update and stage the file and its entry; a plain `git commit` then offers the proposed message (see [Proposed commit messages](#proposed-commit-messages)) |
| `--dry-run` | change nothing, only report per file what would happen: the version it would sync to, whether adaptations merge cleanly or how many conflicts there would be, a rename upstream, and every refusal |

**Adaptations** are merged with the new upstream version (3-way merge, base =
the last synced version). On conflicts the file gets the usual conflict
markers; resolve them, then `git add` the file and run `git commit`, which
offers the proposed message (see [Proposed commit
messages](#proposed-commit-messages)). `--overwrite` skips the merge and
discards the adaptations.

**Uncommitted changes:** like `git pull`, `pull` refuses a file with
uncommitted changes (`your local changes … would be overwritten by pull`):
commit or stash them first. `--autostash` sets them aside, syncs (the sync
commit contains only the synced version) and re-applies them to the working
file. This works for modified files, not for deleted or not yet committed
ones. If the sync itself ends in conflicts, the stashed version is not
re-applied but kept in `.git/FILESYNC_STASH_*`.

**Revisions:** `--commit` accepts branch names (`develop` means the current
upstream `develop`), tags and commit ids. Recorded is the commit that last
changed the file up to that revision. Going back to an older version works
the same way; the commit message then lists what is reverted.

**Other entries in `.git-filesync`:** because all links share one file, a
sync commit must not pick up uncommitted entries of *other* files (that
commit would record their new state without their content). `pull`
therefore refuses to commit while `.git-filesync` has uncommitted changes
for other files – commit those first (e.g. after [`add`](#add)), or use
`--no-commit` to stage everything and commit it together.

With `--all`, a file that can't be synced (conflict, strict violation, file
deleted upstream, …) is reported and the other files are still synced.

For files of a source [pinned to a tag](#pinning-to-a-tag), `pull` ends with
a hint if upstream has [newer tags](#newer-tags):

```
hint: owner/lib is pinned to tag v1.2.0; the newest tag on branch main is v1.4.0 (use 'git filesync pull --tag v1.4.0 <file>...' to switch)
```

A file **renamed upstream** is followed: `pull` takes the new path into
the entry and notes the rename in the commit message. A file **deleted
upstream** is refused, see [Files renamed or deleted
upstream](#files-renamed-or-deleted-upstream).

#### Switching branch or tag

`pull -b BRANCH` and `pull --tag TAG` switch the given files to another
branch or tag of their upstream and sync them in the same step – adaptations
are merged with the 3-way merge as usual, the base being the version synced
so far. The commit message says `Switched from tag v1.2.0 to tag v1.3.0.`

- `--tag TAG` keeps the source's branch as the one to look for [newer
  tags](#newer-tags) on; `--tag TAG -b BRANCH` sets both; `-b BRANCH`
  alone makes the files follow BRANCH (the tag is removed).
- If the given files (or `--all`) are **all files of a source**, the source
  itself is changed, as with [`source set-tag`](#source) /
  `set-branch`.
- If they are only **some of its files**, the source is split: the given
  files move to the source with the same URL and the new branch and tag – an
  existing one, or a new one (`owner/lib-2`) – and the others stay where
  they are. A source left without files is removed.
- Files that don't change between the two versions get no sync commit of
  their own; a switch that no sync commit takes along is committed on its
  own (`Switch owner/lib from tag v1.2.0 to tag v1.3.0`).
- A branch or tag that doesn't exist upstream is refused, nothing
  changes. `--dry-run` shows the switch (`would: …`) along with the syncs.

```sh
git filesync pull --tag v1.3.0 --all             # all files, all sources: to v1.3.0
git filesync pull --tag v1.3.0 src/foo.c         # only this file (its source may be split)
git filesync pull -b main src/                   # these files follow main again
```

`pull --commit` is different: it syncs one file to any revision, but the
link keeps following its branch or tag (`status` then shows it as ahead or
behind).

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
same options of [`pull`](#pull) (`--commit` for one file only, files
renamed upstream are followed), so replacing `pull` with
`diff --upstream` in a command line previews its changes. They only work
with `--upstream`; `.git-filesync` stays untouched. `pull --dry-run` tells
whether the adaptations would merge cleanly; on conflicts it points to
both diffs.

**Upstreaming local changes:** `--for-upstream` names the files by their
upstream path, giving a patch that can be applied there (with
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
| `--prompt` | ask even for explicitly given files |

Without `--upstream` / `--committed`, the right side is the real working
file, so edits made in the tool are kept.

Like `git difftool`, `difftool` without file arguments asks before each file
(`Viewing (1/3): 'src/foo.c'` / `Launch 'meld' [Y/n/q]?`; Enter = yes,
`q` = stop). `-y` / `--no-prompt` or `difftool.prompt = false` skip the
questions, `--prompt` asks even for explicitly given files.

### `add`

`add FILE URL|SOURCE` – link FILE to a file in an upstream repository, given by
its URL or by the name of a `[source]` already in `.git-filesync`:

- **URL**: the file joins an existing source only if the URL and the
  branch or tag (`-b`, `--tag`, default: the upstream default branch) both
  match – with `--tag` but no `-b`, a source pinned to that tag is taken
  whatever branch it looks for newer tags on; otherwise a new source is
  created.
- **Name of a source**: the file joins exactly this source, whether it
  follows a branch or is pinned to a tag. `-b` / `--tag` are not needed; if
  given, they must match the source (otherwise `add` refuses – give the URL
  to link to another branch or tag).

`add DIR URL|SOURCE` – the same for every file below an upstream
directory (see [below](#linking-a-directory)).

| Option | Effect |
|---|---|
| `-b`, `--branch BRANCH` | upstream branch; default: the upstream default branch, or the branch/tag of the given `[source]`. With `--tag`: the branch to look for [newer tags](#newer-tags) on (a warning if the tag isn't on it) |
| `--tag TAG` | [pin](#pinning-to-a-tag) to an upstream tag instead of following a branch |
| `-p`, `--path PATH` | upstream path; default: the same as FILE or DIR (`/`: the upstream root) |
| `--include PATTERN` | directory: only files matching PATTERN; repeatable |
| `--exclude PATTERN` | directory: skip files matching PATTERN; repeatable, beats `--include` |
| `--commit REV` | upstream revision FILE corresponds to, instead of looking it up |
| `--strict` | the file must stay an exact copy (see [Strict files](#strict-files)) |
| `--force` | relink a file that is already linked |
| `-n`, `--dry-run` | change nothing, only show what would be linked and on which upstream version it would be based |

- If FILE exists, the upstream version it matches is looked up and recorded
  as its base. If none matches, the branch head is taken (with a warning) and
  the differences count as adaptations; `--commit` chooses a better base.
- If FILE doesn't exist, it is fetched from upstream.
- Like `git add`, `add` stages FILE (as it is in the working tree) and its
  entry in `.git-filesync`, but doesn't commit. A plain `git commit` then
  opens the editor with the proposed commit message (`git commit --no-edit`
  takes it as it is; see [Proposed commit
  messages](#proposed-commit-messages)):

  ```
  Add src/foo.c from owner/lib@a1b2c3d

  Upstream: https://github.com/owner/lib.git (main:lib/foo.c)
  ```

  For an existing FILE the subject is `Link FILE to …` (`Relink …` with
  `--force`); the message notes local modifications and `--strict`. Several
  `add`s (and `pull --no-commit`) in a row go into one commit, with all
  their messages.

```sh
git filesync add src/foo.c https://github.com/owner/lib.git -p lib/foo.c
git commit                                            # with the proposed message
git filesync add include/bar.h owner/lib --strict     # reuse [source "owner/lib"]
git filesync add src/ owner/lib -p lib/util.h         # into an existing directory: src/util.h
git filesync add cfg/x.yml https://github.com/owner/lib.git --tag v1.2.0
```

#### Linking a directory

If DIR is an existing directory, or the upstream path is a directory, or
`--include` / `--exclude` are given, `add` links every file below upstream
directory: `-p api` with DIR `proto` links `api/v1/x.proto` as
`proto/v1/x.proto`. (An upstream *file* given for an existing directory goes
into it, like `cp`.) Each file gets its own ordinary `[file]` entry – after
`add` there is no difference to files linked one by one – and all of them
are staged together, with one proposed message:

```
Add 2 files from owner/backend@a1b2c3d

Upstream: https://github.com/owner/backend.git (main:api/)

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
git filesync add proto https://github.com/owner/backend.git -p api \
    --include '*.proto' --exclude '*_test.proto' --exclude test/
```

### `set`

`set PATH… OPTIONS` – change the link of linked files: their source, their
upstream path, whether they are strict. It does for files what
[`source`](#source) does for sources: only `.git-filesync` is changed (and
staged); `status` then shows what changes, and `pull` syncs.

| Option | Effect |
|---|---|
| `--source URL\|SOURCE` | link to another upstream repository – a fork, a moved repository – or to another `[source]`. URL, name and `-b` / `--tag` are taken as for [`add`](#add). If the files are all files of their source and there is no source with that URL and branch or tag yet, the source itself is changed; otherwise they move to that source (created if necessary), and a source left without files is removed |
| `-b`, `--branch BRANCH` | with `--source`: as for `add`; without: the files follow BRANCH, like `pull -b`, but without syncing |
| `--tag TAG` | with `--source`: as for `add`; without: [pin](#pinning-to-a-tag) the files to TAG, like `pull --tag`, but without syncing |
| `-p`, `--path PATH` | another upstream path (exactly one file) |
| `--strict`, `--no-strict` | mark the files as [strict](#strict-files), or allow adaptations again |
| `-n`, `--dry-run` | only show what would change |

The synced version the files are based on (`commit` / `blob`) is kept where
it still applies, so adaptations stay adaptations:

- **another branch or tag** of the same upstream: kept as it is;
- **another upstream** (`--source` with another URL): kept if that one has
  it – the recorded commit, or else the newest commit on its branch with the
  same version of the file (e.g. a copy with a history of its own).
  Otherwise there is a warning, and the previous sync point counts as
  unknown;
- **another path** (`-p`): looked up as for `add` – the upstream version the
  file matches; if none matches, the branch head, with a warning, and the
  differences count as adaptations. (A file renamed upstream doesn't
  need this: [`pull`](#pull) follows renames.)

```sh
git filesync set src/foo.c --strict
git filesync set src/ --source https://github.com/me/lib-fork.git    # all files below src/
git filesync set src/foo.c -p lib/foo_v2.c
git filesync set cfg/ --tag v1.3.0      # like pull --tag, without syncing
```

### `edit`

`edit` – open `.git-filesync` in your editor, like `git config --edit`
(`GIT_EDITOR`, `core.editor`, `VISUAL`, `EDITOR`). Afterwards the file is
checked and staged, like after [`set`](#set):

- If it can no longer be read, `edit` fails and stages nothing; run it
  again to fix the file.
- Gaps that `status` would report – a file whose `[source]` doesn't exist,
  a source without `url` or without branch and tag, a file without `path`,
  `commit` or `blob`, a source no file uses – are shown as warnings.
- Without changes, nothing happens.

For the usual changes, the commands that know what they mean are safer:
[`set`](#set) (source, path, strict of files), [`source`](#source) (URL,
branch, tag, name of a source), [`unlink`](#unlink), [`mv`](#mv). `edit`
keeps whatever you write: a changed `commit` or `blob` changes what counts
as an adaptation.

### `unlink`

`unlink PATH…` – remove the links; the files themselves are kept.
`.git-filesync` is staged. `-n` / `--dry-run` only lists what would be
unlinked.

### `mv`

`mv OLD NEW` – move a linked file (`git mv`) and its link together; NEW may
be an existing directory. Both are staged. `-n` / `--dry-run` only shows
what would be moved.

### `source`

`source [ACTION …]` – list and change the `[source]` sections, like
`git remote`. Only `.git-filesync` is changed (and staged); commit it on its
own, or it goes into the next sync commit.

| Command | Effect |
|---|---|
| `source` | list the source names (`-v`: with URL, branch or tag – for a tag also the [newer tags](#newer-tags) of upstream – and number of linked files) |
| `source rename OLD NEW` | rename a source, including every `source =` line |
| `source set-url NAME URL` | change the URL, e.g. after upstream moved (its commits must be there) |
| `source set-branch NAME BRANCH` | follow BRANCH; for a source pinned to a tag only the branch to look for newer tags on (the tag stays) |
| `source set-branch NAME --unset` | for a pinned source: look for newer tags on all branches |
| `source set-tag NAME TAG` | [pin](#pinning-to-a-tag) to TAG; a branch stays, as the one to look for newer tags on |
| `source set-tag NAME --unset` | remove the tag: follow the source's branch again (it needs one) |

```
$ git filesync source -v
owner/lib	https://github.com/owner/lib.git (main, 3 files)
owner/lib-2	https://github.com/owner/lib.git (tag v1.2.0 on main, newest v1.4.0, 1 file)
owner/lib-3	https://github.com/owner/lib.git (tag v1.2.0, newest v1.2.1 on maint; v1.4.0 on main, 1 file)
```

`source -v` accepts `--no-fetch` and `--remote` like `status`.

A change that would make two sources identical (same URL and same branch or
tag) is refused; move the files with `pull -b` / `pull --tag` instead,
which also syncs them (see [Switching branch or
tag](#switching-branch-or-tag)). After changing URL, branch or tag, `status`
shows what is to sync for the source's files.

### `map`

`map [URL|SOURCE [DIR]]` – use the local checkout DIR instead of fetching the
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
git filesync map https://github.com/owner/lib.git ~/src/lib
git filesync map owner/lib ~/src/lib      # the same, by the name of the [source]
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
git filesync map                     # list mappings (scope, overridden ones marked)
git filesync map URL --unset         # remove this repo's mapping
git filesync map --global URL --unset
```

When mapped, `status` and `pull` use the source's branch **as it is in that
checkout** (for a [pinned source](#pinning-to-a-tag): the tag there) – its local branch, including commits not yet pushed – no matter
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

`--remote` bypasses the mapping.

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
git filesync cache [list | prune [--older-than DAYS] [--max-size SIZE] [-n] | clear [-n] | dir]
```

The cache of upstream clones (one blobless clone per URL, see
[`map`](#map)), shared by all repositories of your user. Works outside a
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
| `prune` | remove clones not used for `filesync.cacheMaxAge` days, then the least recently used beyond `filesync.cacheMaxSize`; `--older-than DAYS` and `--max-size SIZE` (e.g. `500M`, `2G`) set other limits for this run; `-n` only shows what would be removed |
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

### `install-hooks`, `uninstall-hooks`

`install-hooks` adds a `pre-push` hook (fetches) and a `post-merge` hook
(cached state only). Both report pending syncs, errors and strict
violations on stderr. If a hook already exists, the lines to add are
printed instead; hooks installed by an older version are updated. With
`core.hooksPath` set, the hooks go there (with a warning, as other
repositories may share that directory).

**Push check:** the `pre-push` hook also looks at the commits being pushed:
a linked file synced to an upstream commit that isn't on the upstream
server – typically pulled from an unpushed commit of a [mapped
checkout](#map) – is reported:

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

The hooks run `git filesync hook pre-push` / `hook post-merge`, which are
not meant to be run by hand (without the arguments git passes, `hook
pre-push` checks `HEAD`).

`uninstall-hooks` deletes hook files that only contain the git-filesync
lines; from other hooks it removes just those lines.

## Further topics

### Pinning to a tag

Instead of following a branch, a source can be pinned to a tag, e.g. a
release of upstream:

```sh
git filesync add cfg/x.yml https://github.com/owner/lib.git --tag v1.2.0
```

`.git-filesync` then has `tag = v1.2.0` in the `[source]`. `status`
compares against the version at the tag – commits on the upstream branches
don't matter – and `pull` syncs to it. A `branch` in a pinned source (`add
--tag v1.2.0 -b main`, or kept when a source following `main` is pinned)
only says where to look for [newer tags](#newer-tags).

Tags are taken as immutable, like Git does: once the tag is in the cache,
`status` (and the hooks) fetch nothing for it, so they need no network for
pinned sources. A tag moved on the server is only noticed when the cache is
fetched for another reason. With a [mapped checkout](#map), the tag in that
checkout is used, whatever is checked out there.

Since a pinned file only changes when the tag does, `pull` usually has
nothing to do – except to bring a file back to the tag's version (e.g. after
`pull --commit`) or after the tag was changed. To learn about newer
releases, `pull`, `status -v` and `source -v` fetch the upstream tags (unless
`--no-fetch`) and name the [newer tags](#newer-tags).

To move on to a newer release, switch and sync in one step:

```sh
git filesync pull --tag v1.3.0 --all        # or only some files, see pull
```

or change the source and sync later: `git filesync source set-tag owner/lib
v1.3.0`, then `git filesync pull --all`. `pull -b BRANCH` / `source set-tag
NAME --unset` go back to following a branch. `pull --commit` still syncs a
single file to any revision.

#### Newer tags

Tag names are taken as opaque – `v1.10` and `v1.9`, `release-7` or
`tool-20261016` are just names – and tags carry no reliable date
(lightweight tags have none of their own, and a tag may be set on an old
commit later). So "newer" is defined by the commit graph alone: on a branch,
the newest tag after the pinned one is on the first tagged commit after it
along the branch's first-parent line, i.e. the commits the branch itself
went through. Tags on side branches merged into it don't count.

- With a `branch` in the source, only that branch is looked at, so there is
  at most one newest tag (several names if several tags are on that commit:
  `v1.4.0 = release-7`):

  ```
  hint: owner/lib is pinned to tag v1.2.0; the newest tag on branch main is v1.4.0 (use 'git filesync pull --tag v1.4.0 <file>...' to switch)
  ```

  If the pinned tag isn't on that branch, `status` warns.
- Without, every branch containing the pinned tag is looked at, so there
  may be several – e.g. a maintenance release and the next major one:

  ```
  hint: owner/lib is pinned to tag v1.2.0; newer tags: v1.2.1 on maint; v1.4.0 on main (use 'git filesync pull --tag TAG <file>...' to switch, 'git filesync source set-branch owner/lib BRANCH' to look on one branch only)
  ```

Pre-releases count like any other tag. Branches are those of upstream
(`origin/…` in the cache); with a [mapped checkout](#map) its local branches
and tags, unpushed ones included.

### Proposed commit messages

Whenever changes are staged with a proposed commit message but not committed
– by `add`, by `pull --no-commit`, after merge conflicts, or when the commit
was aborted – the message is put into `.git/SQUASH_MSG`. Git offers that
file as the message of the next plain `git commit` (as after `git merge
--squash`); `git commit --no-edit` takes it as it is. IDEs such as VS Code
fill their commit message box with it. Git removes it after the next commit,
whatever its message, and on `git reset`.

- Several commands in a row (e.g. `add` for some files and `pull
  --no-commit` for others, then one commit for all of them) collect their
  messages there.
- A copy stays in `.git/FILESYNC_SQUASH_MSG` until the next proposal (the
  path is printed along with the hint to commit). It brings the message
  back if `SQUASH_MSG` is gone – after a commit that was aborted with an
  empty message and then made with another one, after `git reset`, or
  after `git commit -m`:
  `git commit -e -F .git/FILESYNC_SQUASH_MSG`.
- A `SQUASH_MSG` that git-filesync didn't write (e.g. from `git merge
  --squash`) is left alone. The tool then keeps the message in
  `.git/FILESYNC_MSG_*` and prints a `git commit -e -F …` command that uses
  it.

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
  `git filesync unlink src/foo.c && git rm src/foo.c`. `pull --commit REV`
  still syncs to a revision that has the file.

Renames are detected the way `git diff -M` does (similar content); in the
blobless cache this needs the file contents of that one commit, which are
fetched. If the previous sync point is unknown, the missing path is
reported as an error; fix the path by hand then (see [The `.git-filesync`
file](#the-git-filesync-file)).

### Git LFS

Whether a synced file is stored in Git LFS upstream, downstream, in both or
in neither doesn't matter:

- Upstream side: LFS pointers are resolved to the real content (`git lfs
  smudge` in the mapped checkout or the cache; the content comes from the
  local LFS store or the upstream LFS server). Comparisons against an upstream
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

### Offline operation

With a [mapped local checkout](#map), all commands work without network
access (`add` takes the default branch from the checkout's `origin/HEAD`,
or – with a warning if the checkout has a remote – from the branch checked
out there). Sources [pinned to a tag](#pinning-to-a-tag) work offline as
soon as the tag is in the cache; `pull`, `status -v` and `source -v`, which
look for newer tags, then warn that fetching failed and go on. Without a
mapping, the cache is used after a failed fetch; file versions never read
before may be missing there (blobless clone): `status` then warns and
counts the file as modified, `pull --overwrite` brings it back to a known
state. `--no-fetch` skips the network explicitly.

### Colors

Output is colored like `git status`: pending upstream changes yellow,
adaptations cyan (information, not a problem), uncommitted changes red,
strict violations and errors bold red.

Colors follow `color.filesync`, falling back to `color.ui` (default: on for
terminals); `--color[=always|never|auto]` and `--no-color` override that,
and `NO_COLOR` turns colors off. Hook output on stderr is colored the same
way. `diff` is colored by `git diff` itself.

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
`https://github.com/stsichler/git-filesync/releases/download/v0.9.0/git-filesync.py`
instead. (For private upstream repositories the job needs a token with read
access.)

### Exit codes

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | unfinished: `pull` with conflicts or without commit; `status --exit-code` with something to sync (including files deleted upstream) or a strict violation; `diff -- --exit-code` with differences |
| `2` | error |

`--dry-run` / `-n` exit with 0, or 2 on errors – also for refusals they
report (`pull --dry-run` on a strict violation, …); expected merge conflicts
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
  file matches: `git filesync add 'f[1].txt' …` turns into `f1.txt` when
  that file exists.
- **Arguments starting with `/`** become Windows paths: `--include /x.md`
  turns into `C:/Program Files/Git/x.md`. For the upstream root, `-p .`
  works as well as `-p /`.

For such arguments, run the script directly instead of through the alias,
e.g. `py C:/tools/git-filesync.py add docs owner/lib --include /x.md` in
cmd or PowerShell; in Git Bash, put `MSYS_NO_PATHCONV=1` in front of it.
Don't set `MSYS_NO_PATHCONV` (or `MSYS=noglob`) for git itself: it breaks
how git passes the arguments to the alias.

### Shipping git-filesync with your repository

git-filesync can keep a copy of itself in your repository, so everyone has
the same version without installing it:

```sh
git filesync add tools/git-filesync.py https://github.com/stsichler/git-filesync.git \
    -p git-filesync.py --tag v0.9.0 --strict
git config alias.filesync '!python3 tools/git-filesync.py'     # each clone, once (Windows: !py …)
```

The alias goes into the repository's own config (`.git/config`), so it has
to be set in each clone; it takes precedence over a global alias. Git runs
shell aliases in the top-level directory, so the relative path works from
any subdirectory. To update, pin the new release and sync:
`git filesync pull --tag vX.Y.Z tools/git-filesync.py` (`pull` and
`status -v` name the newest release).
