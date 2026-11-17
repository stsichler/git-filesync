#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT-0
# Copyright (c) 2026 Stefan Sichler - https://github.com/stsichler/git-filesync
# Developed together with Claude (Anthropic).
#
# Found this file in your repository? It was probably copied there - maybe
# kept up to date by git-filesync itself. Run it with --help, or see the
# manual linked at the end of the following text.
"""
git-filesync - keep individual files in sync between Git repositories.

A repository lists its synced files in .git-filesync at its root
(git-config format, like .gitmodules), each linked to a file in an
upstream repository:

    [source "owner/lib"]
        url = https://github.com/owner/lib.git
        branch = main          ; followed by its files (pinned ones: where
                               ; newer tags are looked for)
    [file "src/foo.c"]
        source = owner/lib
        path = lib/foo.c       ; path in the upstream repository
        tag = v1.2             ; optional: pinned to the tag (with * ? [...]:
                               ; the newest matching tag on the branch)
        adaptable = true       ; optional: local adaptations allowed
        commit = <upstream commit of the last sync>
        blob = <blob id of the upstream file at that commit>
    [dir "third_party/lib"]    ; a directory: the files of an upstream one
        source = owner/lib
        path = lib             ; upstream directory (/: the root)
        exclude = test/ '*_test.c'   ; optional, like include: patterns
        synced-exclude = test/ ; only after set changed exclude: the files
                               ; are those of these patterns until pull
        commit = <upstream commit that last changed it>
        tree = <the upstream directory at that commit>

A link records the upstream version the file is based on (commit/blob).
A file must stay an exact copy of it, unless it is marked adaptable: then
local adaptations on top of it are allowed and kept by a 3-way merge on
pull. An entry without commit and blob (e.g. written by hand, to link
many files at once) is a new link: pull syncs it the first time, as add
would. A [dir] entry's files are those of the upstream directory at its
base its patterns select, each one like a linked file; pull also adds and
deletes them. All other files in the directory are this repository's own,
which no command touches. Entries don't overlap.

HEAD, the index and the working tree each have their .git-filesync, and
an entry there describes the file there. A command stages only what it
changes in it (pull and add an entry whole, with its file and [source]);
other changes - made by hand, or written with -W - stay unstaged.

Commands (run inside the repository; without a command: status).
PATH may be a file or a directory (= all linked files below it; a file in
a [dir] entry: that entry - pull, set, rm, unlink take it whole); options
follow the command. No command commits: they stage (restore: with -S), like
their git namesakes, and propose a commit message that a plain `git commit`
offers (.git/SQUASH_MSG; a copy stays in .git/FILESYNC_MSG) - committing
is up to you.

Basic commands:

    status [PATH...]            state of the linked files like `git status`:
                                upstream changes to sync, committed
                                adaptations, missing files, changes to be
                                committed and not staged
        -s, --short             short format, three columns: upstream (P
                                pending, O older, D diverged or previous
                                sync point unknown, R renamed, X deleted
                                upstream, N new link; E error), the index
                                (against HEAD) and the working tree
                                (against the index): A new, U another
                                base, M modified, D missing; notes:
                                (adapted) committed, (not adaptable!)
        -v, --verbose           also list all linked files with their sources
                                (pinned ones with the newest tag: on the
                                first tagged commit from the head of the
                                source's branch back along its first-parent
                                line)
        --exit-code             exit 1 if something is to sync, a linked
                                file is missing, or a file that isn't
                                adaptable is modified

    pull PATH... | --all        sync to the upstream version of the files and
                                stage them, like `git merge --squash`; the
                                proposed message lists the upstream commits
                                since the last sync per file; adaptations
                                are merged (conflicts: resolve, then git
                                add), uncommitted changes refused (but
                                with --overwrite), a missing file too (see
                                restore); a new link is synced the first
                                time as by add; a file renamed upstream is
                                followed, one deleted there is reported; a
                                [dir] entry: all its files or none
        --all                   all files with something to sync (with
                                --commit, -b, --tag: all files); names
                                those left out that need attention
                                (missing; modified, but not adaptable;
                                not a plain update along the history:
                                older, diverged, previous sync point
                                unknown - pull FILE)
        -b, --branch BRANCH     sync to the head of BRANCH, once: the files
                                keep following their own branch or tag
                                (to switch: set -b/--tag)
        --tag TAG               sync to TAG, once (as -b)
        --commit REV            sync to this upstream revision, once (as -b;
                                also backwards)
        --overwrite             discard local adaptations instead of merging,
                                and uncommitted changes (kept, see restore)
        -W, --worktree          files and entries in the working tree only,
                                nothing staged (to try a newer version;
                                pull PATH or git add PATH .git-filesync
                                stages it, restore PATH goes back)
        --force                 [dir]: keep a file of this repository that
                                pull would delete (adapted, deleted
                                upstream) or replace (new upstream)
        -n, --dry-run           only report what would happen (incl.
                                merge conflicts); change nothing
        -v, --verbose           before each file: where it comes from (as
                                status -v) and the version synced so far

    diff [PATH...] [-- OPTS]    local changes vs. the synced upstream version
                                (one `git diff`, OPTS passed to it)
        --committed             only committed adaptations (synced -> HEAD)
        --cached, --staged      the index (against the base of the entry
                                staged)
        --upstream              what pull would bring (synced -> upstream)
        --commit REV, -b BRANCH, --tag TAG
                                with --upstream: what pull with these
                                options would bring (nothing is switched)
        --for-upstream          a patch for `git apply -3` in the upstream
                                repository (upstream paths)

    difftool [PATH...] [-- OPTS]  the same in the configured difftool
        --committed, --cached, --upstream, --commit, -b, --tag  as for diff
        -y, --no-prompt         don't ask before each file (default: ask,
                                like git difftool; difftool.prompt)
        --prompt                ask even with difftool.prompt = false

    restore PATH...             like `git restore`, from the layer below:
                                the entry synced as there (its selection
                                stays), the files its synced upstream
                                version (also of an adaptable file); e.g.
                                to go back after pull -W, discard changes
                                to a file that isn't adaptable, or bring
                                back a missing one; an entry not there goes,
                                with its files; uncommitted content is kept
                                as a blob (`discarded: FILE (git show ID
                                ...)`)
        -S, --staged            restore the index (from HEAD) instead of the
                                working tree (from the index)
        -W, --worktree          restore the working tree (default; with -S:
                                both, from HEAD)

    add URL|SOURCE FILE         link FILE to a file in an upstream repository
                                (SOURCE: exactly that [source]; URL: the
                                source with that URL and branch/tag, else a
                                new one named 'owner/repo' after the URL, with
                                a number appended if taken); the base is the
                                upstream head (or --commit); a FILE that
                                exists must be that version (else refused:
                                --adaptable keeps it, its differences count
                                as adaptations; --overwrite replaces it);
                                a missing FILE is fetched (its directory must
                                exist, as for cp); FILE and
                                .git-filesync are staged like `git add` - a
                                plain `git commit` offers the proposed message
    add URL|SOURCE DIR          link DIR to an upstream directory (-p,
                                default: same as DIR): one [dir] entry; its
                                files are compared as for FILE; as for cp -r,
                                DIR may be new, its parent must exist
        -b, --branch BRANCH     the source's upstream branch (default: its
                                default branch, or that of SOURCE)
        --tag TAG               pin the file to an upstream tag instead of
                                following the branch (a pattern: the newest
                                matching tag on the branch)
        -p, --path PATH         upstream path (default: same as FILE; \\
                                counts as /)
        --include PATTERN       DIR: only files matching (gitignore-like,
                                relative to the upstream directory; repeatable)
        --exclude PATTERN       DIR: skip files matching (repeatable)
        --per-file              DIR: a [file] entry for each file instead;
                                files already linked are skipped
        --commit REV            upstream revision to base FILE on instead
                                of the head
        --overwrite             replace an existing FILE with the upstream
                                version (uncommitted content: as restore)
        --adaptable             local adaptations allowed (default: FILE
                                must stay an exact copy)
        --force                 relink an already linked file (a new entry,
                                as after unlink: --tag, --adaptable as given)
        -W, --worktree          file(s) and entry in the working tree only,
                                nothing staged
        -n, --dry-run           only show what would be linked

    rm PATH...                  remove linked files and their links, staged
                                like `git rm` ([dir]: its files, the own ones
                                stay); refused for files with uncommitted
                                changes
        -f, --force             remove them anyway (their content: as
                                restore)
        -n, --dry-run           only show what would be removed

    unlink PATH...              remove links (the files are kept)
    mv OLD NEW                  move a linked file (git mv), keeping its link;
                                the directory of NEW must exist
    mv OLD... DIR               move several into the existing directory DIR
                                (a [dir] moves with the own files in it)
        -n, --dry-run           (both) only show what would be done

Advanced commands:

    set PATH... OPTIONS         change the link of linked files, like `source`
                                for sources; only .git-filesync is changed
                                (and staged), the synced version is kept
                                where it still applies; pull then syncs
                                (said, if it may have something to do)
    set PATH...                 show it: the set command that sets what the
                                entries have (entered again: no change)
        --list                  the same for all entries
        --source URL|SOURCE     take the files from another upstream (fork,
                                moved repository) or [source] SOURCE
        -b, --branch BRANCH     follow BRANCH (with --source URL: default
                                its default branch); like for add, URL and
                                branch select the [source] - created if
                                needed, or changed if all its files move; one
                                left without files is removed
        --tag TAG               pin to TAG from now on (a pattern: the newest
                                matching tag on the source's branch)
        --no-tag                follow the source's branch again
        -p, --path PATH         another upstream path (one file or
                                directory); its current version becomes
                                the base, as for add (the file stays as it
                                is); a [dir]: a new link then, compared by
                                pull; the same path: no change
        --adaptable, --no-adaptable  allow local adaptations / not any more
        --include, --exclude PATTERN  [dir]: new patterns (repeatable); the
                                files follow at the next pull: those they
                                select now are fetched, those left out
                                deleted (as if changed upstream)
        --no-include, --no-exclude  [dir]: remove the patterns
        -W, --worktree          .git-filesync in the working tree only,
                                nothing staged (with pull -W: a whole try,
                                e.g. a fork)
        -n, --dry-run           only show what would change

    edit                        open .git-filesync in the editor (like `git
                                config --edit`); afterwards it is checked
                                and what changed staged (a merge conflict
                                in it: resolved, the whole file)
        -W, --worktree          nothing staged (also a resolved conflict)

    source                      list the [source]s (-v: with URL, branch,
                                entries)
    source rename OLD NEW       rename a [source] and all references to it
    source set NAME OPTIONS     change a [source] (the branch must exist
                                upstream); without options: show it, as
                                the command that sets it (--list: all)
        --url URL               another URL; the synced versions are looked
                                up there as for set --source
        -b, --branch BRANCH     follow BRANCH, all files of the source
        -W, --worktree          (also rename) .git-filesync in the working
                                tree only, nothing staged
        -n, --dry-run           (also rename) only show what would change
    source map [URL|SOURCE [DIR]]  use the local checkout DIR instead of
                                fetching URL (SOURCE: the URL of that
                                [source]); its branch is used, unpushed
                                commits included; DIR is only read; without
                                DIR: list mappings
        --global                global git config (default: this repository)
        --unset                 remove the mapping for the URL

    cache                       the cache of upstream clones: where, how big,
                                the limits
    cache list                  its clones, most recently used first
    cache prune                 remove clones not used for 90 days (or as
                                configured: filesync.cacheMaxAge DAYS,
                                filesync.cacheMaxSize SIZE; 0/off: none) -
                                also done automatically after a fetch, at
                                most once a day
        --max-age DAYS, --max-size SIZE  other limits (SIZE: 500M, 2G;
                                0: no limit, as configured; everything:
                                cache clear)
        -n, --dry-run           only show what would be removed
    cache clear [-n]            remove all clones
    cache dir                   print its directory (e.g. for CI caching)

    hooks                       the state of the pre-push/post-merge hooks:
                                installed, outdated, not installed, or
                                hooks of other tools without our lines
    hooks install               install the hooks (or update them):
                                reminders about pending syncs, changes
                                not allowed, missing files, errors;
                                pre-push also warns if a
                                pushed file is synced to an upstream commit
                                that isn't on the upstream server
                                (filesync.pushCheck = warn | error, which
                                refuses the push | off); in a pre-push hook
                                shared with git lfs, our lines come first
        --force                 add our lines to existing hooks of other
                                tools, right after the #! line (default:
                                show the lines to add)
    hooks uninstall             remove them again (only our lines from hooks
                                of other tools)
    hook pre-push|post-merge    what the installed hooks run (internal)

    Common options:
        --no-fetch              use the cached state, don't fetch (status,
                                pull, diff/difftool, restore, add, set,
                                source set; restore, diff of local changes
                                and set without --source, -b, --tag, -p
                                fetch anyway only if the cache lacks the
                                branch); an upstream not in the cache yet
                                is cloned anyway
        --remote                ignore mappings (source map) this once, use
                                the upstream URL (same commands; with
                                --no-fetch: the cached state)
        --color[=WHEN], --no-color  always, never or auto (default)

Exit codes: 0 ok, 1 unfinished (pull: conflicts; --exit-code),
2 error, 141 output pipe closed early (reading commands stop, others finish).

Files stored in Git LFS (upstream, in this repository, both or neither) are
handled transparently, as are differing line-ending conventions. Output is
colored like git's (color.filesync / color.ui, --color, NO_COLOR).

Requires Python >= 3.7 and Git >= 2.28 (git-lfs for LFS files).
Works on Linux, macOS and Windows.
Manual: https://github.com/stsichler/git-filesync/blob/main/MANUAL.md
"""

import argparse
import errno
import fnmatch
import inspect
import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import namedtuple
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field, replace as dc_replace
from typing import Optional
from pathlib import Path, PureWindowsPath

__version__ = "0.24.3"
REGISTRY = ".git-filesync"
EXIT_OK, EXIT_PENDING, EXIT_ERROR = 0, 1, 2
EXIT_PIPE = 141           # output pipe closed early (128 + SIGPIPE, like git)
EXIT_REFUSED = 3          # hook pre-push: refuse the push (filesync.pushCheck = error)
HOOK_MARKER = "git-filesync"
MSG_PREFIX = "[filesync] "    # subject of every proposed commit message
# What the installed hooks run. Only EXIT_REFUSED blocks a push - any other
# failure (e.g. git-filesync not installed) never does. git passes the refs to
# push on pre-push's stdin once: the block reads them into a variable and
# restores them for the commands after it (git lfs pre-push needs them too;
# git-assetsync's block does the same with its own variable). Nothing to
# restore if there was nothing: a blank line instead of EOF could confuse them.
REFS_VAR = "git_filesync_refs"
HOOKS = {
    "pre-push": "\n".join([
        f"{REFS_VAR}=$([ $# -eq 0 ] || cat)",     # no arguments: run by hand, no stdin
        f"printf '%s\\n' \"${REFS_VAR}\" | git filesync hook pre-push \"$@\""
        f" || [ $? -ne {EXIT_REFUSED} ] || exit 1",
        f"[ -z \"${REFS_VAR}\" ] || exec <<{REFS_VAR}_end",
        f"${REFS_VAR}",
        f"{REFS_VAR}_end"]),
    "post-merge": 'git filesync hook post-merge "$@" </dev/null || true',
}
# after edit, which changes only .git-filesync
REGISTRY_STAGED = (f'{REGISTRY} staged (use "git filesync status" to see what changes, '
                   '"git filesync pull <file>..." to sync)')
# -W, or changes of entries the index hasn't (see Registry.stage)
WORKTREE_ONLY = f"{REGISTRY} changed in the working tree only"
# after edit in the working tree only: pull -W keeps the try unstaged
REGISTRY_WORKTREE = (f'{WORKTREE_ONLY} (use "git filesync status" to see what changes, '
                     '"git filesync pull -W <file>..." to sync)')
REGISTRY_HEADER = ("# git-filesync: files of this repository that are kept in sync with\n"
                   "# files in other repositories. Maintained by 'git filesync'; [file]\n"
                   "# commit/blob and [dir] commit/tree record the upstream version.\n")


class FsError(Exception):
    pass


# --------------------------------------------------------------------------
# colors
# --------------------------------------------------------------------------

STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
          "cyan": "36", "boldred": "1;31"}
_color = {"out": False, "err": False}
_colorbool = {}       # tty? -> git's answer (the same for stdout, stderr and the help)


def color_wanted(mode, stream, cwd=None):
    """Colors on stream? Like git: --color, NO_COLOR, color.filesync/color.ui."""
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    tty = "true" if stream.isatty() else "false"
    if tty not in _colorbool:
        p = git(["config", "--get-colorbool", "color.filesync", tty], cwd=cwd, check=False)
        _colorbool[tty] = out(p) == "true"
    return _colorbool[tty]


def color_option(argv):
    """The --color / --no-color given in argv (the last one wins), before
    parsing it: the help needs colors decided before argparse prints it."""
    mode = "auto"
    for a in argv:
        if a == "--":
            break
        if a == "--no-color":
            mode = "never"
        elif a.startswith("--color="):
            mode = a[len("--color="):]
    return mode


def setup_colors(mode, cwd=None):
    """Decide per stream like git: --color, NO_COLOR, color.filesync/color.ui."""
    _color["out"], _color["err"] = color_wanted(mode, sys.stdout, cwd), \
        color_wanted(mode, sys.stderr, cwd)
    if os.name == "nt" and (_color["out"] or _color["err"]):
        os.system("")          # enables ANSI escape processing in the Windows console


def paint(text, style, stream="out"):
    if not style or not _color[stream]:
        return text
    return f"\033[{STYLES[style]}m{text}\033[m"


def warn(msg):
    print(f"{paint('warning:', 'yellow', 'err')} {msg}", file=sys.stderr)


def error(msg):
    print(f"{paint('error:', 'boldred', 'err')} {msg}", file=sys.stderr)


class PipeGuard:
    """Wraps sys.stdout / sys.stderr. Once the reader of a pipe is gone
    (`| head`), output goes to the null device: a reading command then
    stops (BrokenPipeError, see stop), a changing one carries on, so it
    never stops halfway. main() then exits with EXIT_PIPE."""
    broken = False      # a pipe broke
    stop = False        # stop the command when it does (reading commands)

    def __init__(self, stream, each=False):
        self._stream = stream
        self._each = each   # flush after each write (stderr: Python < 3.9 buffers it)

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def write(self, text):
        try:
            n = self._stream.write(text)
            if self._each:
                self._stream.flush()
            return n
        except OSError as e:
            self._broken(e)
            return len(text)

    def flush(self):
        try:
            self._stream.flush()
        except OSError as e:
            self._broken(e)

    def _broken(self, e):
        # Windows reports a closed pipe as EINVAL
        if not isinstance(e, BrokenPipeError) and e.errno != errno.EINVAL:
            raise e
        PipeGuard.broken = True
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), self._stream.fileno())
        except (OSError, ValueError):
            pass
        if PipeGuard.stop:
            raise BrokenPipeError(errno.EPIPE, "output pipe closed")


# --------------------------------------------------------------------------
# git plumbing helpers
# --------------------------------------------------------------------------

_clean_env = None


def clean_env():
    """Environment without repository-local GIT_* variables.

    Hooks may run with GIT_DIR & co. set for this repository; commands
    that operate on an upstream repository must not inherit them.
    """
    global _clean_env
    if _clean_env is None:
        p = subprocess.run(["git", "rev-parse", "--local-env-vars"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        names = set(p.stdout.decode().split()) if p.returncode == 0 else set()
        names |= {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                  "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"}
        _clean_env = {k: v for k, v in os.environ.items() if k not in names}
    return _clean_env


# For commands that may contact an upstream server: the blobless cache fetches
# missing file contents lazily, which only protocol v2 allows (v0 refuses
# "wants" of objects not advertised). The default of Git 2.27/2.28, or a
# configured protocol.version=0, would break it; servers without v2 answer
# in v0 anyway. Passed on to the lazy fetch git starts itself.
PROTOCOL_V2 = ["-c", "protocol.version=2"]


def git(args, cwd=None, data=None, check=True, env=None):
    args = [str(a) for a in args]
    p = subprocess.run(["git"] + args, cwd=cwd, input=data,
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        i = 0
        while i < len(args) - 1 and args[i] in ("-c", "-C"):    # options before the command
            i += 2
        raise FsError(f"git {args[i] if args else ''} failed: {err}")
    return p


def chunks(items, n=200):
    """items in slices of n - several paths per git call, but within the
    command line length limit (32 KiB on Windows)."""
    items = list(items)
    return [items[i:i + n] for i in range(0, len(items), n)]


def out(p):
    return p.stdout.decode("utf-8", "replace").strip()


def lit(path):
    """Pathspec matching exactly this path: no wildcards, no magic. Not via
    GIT_LITERAL_PATHSPECS, which would leak into hooks run by `git commit`."""
    return f":(literal){path}"


def cmd_arg(path):
    """A path as pathspec argument in a git command shown to the user."""
    if re.search(r"[*?\[\\]|^:", path):
        path = lit(path)
    return path if re.fullmatch(r"[\w./@+-]+", path) else f'"{path}"'


def upstream_path(s):
    """-p: a path in the upstream repository, in git's form. Backslashes count
    as separators (e.g. a relative path copied from a checkout on Windows);
    upstream file names with a backslash are not supported."""
    return "/".join(p for p in s.replace("\\", "/").split("/") if p not in ("", "."))


def plural(n, word):
    """'1 file' / '2 files'."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def norm_url(url):
    u = url.strip().rstrip("/")
    return u[:-4] if u.endswith(".git") else u


def repo_label(url):
    """'https://github.com/owner/repo.git' -> 'owner/repo', '../repo' -> 'repo'."""
    u = re.sub(r"^(\.\.?/)+", "", url.strip())
    m = re.search(r"((?:[^/:]+/)?[^/:]+?)(?:\.git)?/?$", u)
    return m.group(1) if m else u


def registry_url(url):
    """A URL as written to .git-filesync: '/' for '\\' (a local path given
    the Windows way), so it reads the same on every platform; only
    mappings keep platform paths."""
    return url.replace("\\", "/")


def is_relative_url(url):
    return url.startswith(("./", "../"))


_remote_urls = {}


def resolve_url(url, top):
    """A relative URL (./ or ../) as Git takes it in .gitmodules: relative to
    the URL of the default remote of the repository at top (the remote of
    the current branch's upstream, else origin), or to top itself if it has
    none. Any other URL unchanged."""
    if not is_relative_url(url):
        return url
    if top is None:
        raise FsError(f"relative URL '{url}' needs a repository to resolve against")
    if top not in _remote_urls:
        branch = out(git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=top, check=False))
        remote = branch and out(git(["config", f"branch.{branch}.remote"], cwd=top,
                                    check=False)) or "origin"
        base = out(git(["config", f"remote.{remote}.url"], cwd=top, check=False))
        if not base or not looks_like_url(base) and not os.path.isabs(base):
            base = Path(os.path.abspath(Path(top) / base)).as_posix()
        _remote_urls[top] = base.replace("\\", "/")      # as git cuts it on Windows
    base, rest, colon = _remote_urls[top].rstrip("/"), url, False
    while rest.startswith(("./", "../")):
        if rest.startswith("../"):    # one component off the base, as git does
            i = base.rfind("/")
            if i < 0:
                i = base.rfind(":")
                if i < 0:
                    raise FsError(f"cannot resolve relative URL '{url}' against '{_remote_urls[top]}'")
                colon = True
            base = base[:i]
        rest = rest[3:] if rest.startswith("../") else rest[2:]
    return (base + (":" if colon else "/") + rest).rstrip("/")


def cache_root():
    if os.environ.get("FILESYNC_CACHE"):
        return Path(os.environ["FILESYNC_CACHE"])
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "git-filesync"


# cache clones unused for this many days are removed (filesync.cacheMaxAge),
# checked at most once per CACHE_PRUNE_EVERY seconds; never one used in the
# last CACHE_GRACE seconds. USED_MARKER in a clone: touched on each use.
CACHE_MAX_AGE, CACHE_PRUNE_EVERY, CACHE_GRACE = 90, 86400, 600
USED_MARKER = "filesync-last-used"


def human_size(n):
    """'512 bytes' / '1.2 KiB' / '3.4 MiB' / '1.1 GiB'."""
    for unit in ("bytes", "KiB", "MiB"):
        if n < 1024:
            return f"{n} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


def parse_size(text):
    """Bytes of '500M', '2G', '1.5GiB', '100k', '1000' (1024-based)."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*", text or "", re.I)
    if not m:
        raise FsError(f"'{text}' is not a size like 500M or 2G")
    return int(float(m.group(1)) * 1024 ** " kmgt".index(m.group(2).lower() or " "))


def rmtree(path):
    """Remove a directory tree - also Git's read-only pack files on Windows."""
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def touch_used(d):
    """Note that cache clone d was used now (for cleaning up the cache)."""
    try:
        (d / USED_MARKER).touch()
    except OSError:
        pass


def cache_clones():
    """[(dir, size, last used, url)] of the clones in the cache, most
    recently used first."""
    root = cache_root()
    result = []
    for d in root.glob("*.git") if root.is_dir() else []:
        if not d.is_dir():
            continue
        size = 0
        for base, _, files in os.walk(d):
            for f in files:
                try:
                    size += os.lstat(os.path.join(base, f)).st_size
                except OSError:
                    pass
        used = 0.0
        for f in (d / USED_MARKER, d / "FETCH_HEAD", d):      # older clones: no marker
            try:
                used = f.stat().st_mtime
                break
            except OSError:
                continue
        url = out(git(["-C", d, "config", "remote.origin.url"], env=clean_env(), check=False))
        result.append((d, size, used, url))
    return sorted(result, key=lambda x: x[2], reverse=True)


def cache_limits():
    """(max age in days, max size in bytes) from filesync.cacheMaxAge
    (default CACHE_MAX_AGE) and filesync.cacheMaxSize (default none);
    None = no limit ('0' or 'off')."""
    off = ("0", "off", "false", "no", "never")
    age, size = (out(git(["config", f"filesync.{key}"], check=False)).strip()
                 for key in ("cacheMaxAge", "cacheMaxSize"))
    if not age:
        max_age = CACHE_MAX_AGE
    elif age.lower() in off:
        max_age = None
    elif age.isdigit():
        max_age = int(age)
    else:
        raise FsError(f"filesync.cacheMaxAge: '{age}' is not a number of days")
    return max_age, None if not size or size.lower() in off else parse_size(size)


def prune_cache(max_age, max_size, dry_run=False, grace=True):
    """Remove the clones not used for max_age days, then the least recently
    used until the cache is at most max_size - with grace never one used in
    the last minutes; also leftovers of unfinished clones. Returns the
    removed [(dir, size, last used, url)]. A removed clone is simply cloned
    again when needed."""
    now, removed = time.time(), []
    clones = cache_clones()
    total = sum(size for _, size, _, _ in clones)
    for item in reversed(clones):                 # least recently used first
        d, size, used, _ = item
        if grace and now - used < CACHE_GRACE:
            continue
        if (max_age is not None and now - used > max_age * 86400) or \
                (max_size is not None and total > max_size):
            if not dry_run:
                try:
                    rmtree(d)
                except OSError:
                    continue
            removed.append(item)
            total -= size
    if not dry_run:
        root = cache_root()
        for d in root.glob("*.git.tmp*") if root.is_dir() else []:
            try:
                if now - d.stat().st_mtime > 86400:
                    rmtree(d)
            except OSError:
                pass
    return removed


def auto_prune():
    """After a clone or fetch: clean up the cache by the configured limits,
    at most once a day. Never fails a command."""
    marker = cache_root() / "last-prune"
    try:
        if marker.is_file() and time.time() - marker.stat().st_mtime < CACHE_PRUNE_EVERY:
            return
        max_age, max_size = cache_limits()
        marker.write_text("", encoding="ascii")
        if max_age is not None or max_size is not None:
            prune_cache(max_age, max_size)
    except (FsError, OSError) as e:
        warn(f"cache not cleaned up: {e}")


MAP_REGEX = r"^filesync\..+\.localpath$"


def local_mappings(scope=None, cwd=None):
    """List of (scope, config key, url, dir) from filesync.<url>.localpath
    entries, in git's precedence order (system, global, local: last wins)."""
    args = ["config", "--show-scope"] + ([scope] if scope else []) + ["--get-regexp", MAP_REGEX]
    result = []
    for line in out(git(args, cwd=cwd, check=False)).splitlines():
        sc, _, rest = line.partition("\t")
        key, _, val = rest.partition(" ")
        url = key[len("filesync."):-len(".localpath")]
        result.append((sc, key, url, val))
    return result


def is_repository(d):
    """Is directory d (a mapped checkout) a Git repository?"""
    return git(["-C", d, "rev-parse", "--git-dir"], env=clean_env(), check=False).returncode == 0


def mappings_for(url, scope=None, cwd=None):
    """local_mappings() for this URL only."""
    return [m for m in local_mappings(scope, cwd) if norm_url(m[2]) == norm_url(url)]


# --------------------------------------------------------------------------
# Git LFS
# --------------------------------------------------------------------------

LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"


def lfs_pointer(data):
    """(sha256, size) if data is a Git LFS pointer, else None."""
    if len(data) < 1024 and data.startswith(LFS_HEADER):
        oid = re.search(rb"^oid sha256:([0-9a-f]{64})$", data, re.M)
        size = re.search(rb"^size (\d+)$", data, re.M)
        if oid and size:
            return oid.group(1).decode(), int(size.group(1))
    return None


@contextmanager
def lfs_elsewhere():
    """Options for `git status` in a mapped checkout that keep Git LFS from
    writing into the checkout's .git/lfs: the clean filter (run for files
    with a new timestamp) keeps its temporary files and the objects it
    stores in a temporary store instead. (Not for fetching objects: with
    lfs.storage set, git-lfs looks in the wrong place on a file:// server.)
    Older git-lfs (2.x) also installs its hooks: into a temporary directory."""
    store = tempfile.mkdtemp(prefix="git-filesync-lfs-")
    try:
        yield ["-c", f"lfs.storage={store}", "-c", f"core.hooksPath={store}/hooks"]
    finally:
        rmtree(store)


def lfs_smudge(run, data, path, where):
    """Content behind an LFS pointer, via `git lfs smudge` in that repository
    (local LFS store first, then the repository's LFS server)."""
    p = run(["lfs", "smudge", "--", path], data=data, check=False)
    if p.returncode or lfs_pointer(p.stdout):
        msg = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise FsError(f"'{path}' is stored in Git LFS in {where}, but its content is not "
                      f"available ({msg[-1] if msg else 'is git-lfs installed?'})")
    return p.stdout


# --------------------------------------------------------------------------
# upstream side
# --------------------------------------------------------------------------

def batch_read(git_cmd, blobs, memo):
    """Contents of blobs not in memo yet (keys ('raw', oid)), read with one
    `cat-file --batch`: [(key, content)]. Missing or odd ones are left
    out - reading them one by one reports the error."""
    blobs = [b for b in dict.fromkeys(blobs) if b and ("raw", b) not in memo]
    if not blobs:
        return []
    p = git_cmd(["cat-file", "--batch"], data="".join(b + "\n" for b in blobs).encode(),
                check=False)
    data, pos, found = p.stdout, 0, []
    for b in blobs:
        end = data.find(b"\n", pos)
        head = data[pos:end].split() if end >= 0 else []
        if len(head) != 3 or head[1] != b"blob":
            break
        size = int(head[2])
        found.append((("raw", b), data[end + 1:end + 1 + size]))
        pos = end + 1 + size + 1
    return found


class Source:
    """A Git repository providing the upstream versions of synced files."""

    def __init__(self, workdir, ref, label, local=False, note=None):
        self.dir, self.ref, self.label = Path(workdir), ref, label
        self.local = local   # mapped local checkout: ref is its local branch
        self.note = note     # remark about the ref choice, shown by status
        self.spec = None     # ('branch' | 'tag', name) it was made for (see Context.source)
        self.tag_names: Optional[list] = None   # for a tag pattern: the matching tags ref is at
        self.lfs_server = None  # mapped: () -> repository to fetch missing LFS objects in
        self.offline = False    # never fetch a missing blob (see Context.cached_source)
        self._memo = {}      # answers that don't change during a run (see prefetch)

    def git(self, args, **kw):
        kw.setdefault("env", clean_env())
        if self.offline:          # nothing missing is fetched (see Context.cached_source):
            kw["env"] = dict(kw["env"], GIT_NO_LAZY_FETCH="1")     # Git 2.45+; before, no
            nowhere = self.dir / "no-fetch"                         # transport is allowed
            args = ["-c", "protocol.allow=never", "-c", f"lfs.url={nowhere}"] + list(args)
        return git(PROTOCOL_V2 + ["-C", self.dir] + list(args), **kw)

    def head_ref(self):
        """Full ref name checked out in a local checkout, None if detached."""
        if ("head_ref",) not in self._memo:
            p = self.git(["symbolic-ref", "-q", "HEAD"], check=False)
            self._memo[("head_ref",)] = out(p) if p.returncode == 0 else None
        return self._memo[("head_ref",)]

    def head_desc(self):
        """What a local checkout has checked out: branch name or detached commit."""
        key = ("head_desc",)
        if key not in self._memo:
            p = self.git(["symbolic-ref", "--short", "-q", "HEAD"], check=False)
            if p.returncode == 0:
                self._memo[key] = out(p)
            else:
                p = self.git(["describe", "--tags", "--exact-match", "HEAD"], check=False)
                self._memo[key] = f"detached at {out(p)}" if p.returncode == 0 else \
                    f"detached at {self.short('HEAD')}"
        return self._memo[key]

    def is_published(self, commit):
        """True if commit is on some remote-tracking branch (or there is no remote)."""
        key = ("published", commit)
        if key not in self._memo:
            self.published([commit])
        return self._memo.get(key, True)

    def published(self, commits):
        """Find out at once which of these existing commits are published (see
        is_published): those not listed by `rev-list C... --not --remotes`."""
        commits = [c for c in dict.fromkeys(commits) if ("published", c) not in self._memo]
        if not commits:
            return
        if ("remotes",) not in self._memo:
            self._memo[("remotes",)] = bool(out(self.git(["for-each-ref", "--count=1",
                                                          "refs/remotes/"])))
        if not self._memo[("remotes",)]:
            unpublished = set()
        else:
            p = self.git(["rev-list"] + commits + ["--not", "--remotes"], check=False)
            if p.returncode:
                return            # e.g. an unknown commit: is_published() asks one by one
            unpublished = set(out(p).split())
        for c in commits:
            self._memo[("published", c)] = c not in unpublished

    def has_uncommitted(self, path):
        """Does a local checkout have uncommitted changes to path (a file, or
        a directory: to a file below it, '' = the root)? One `git status`
        for the whole checkout, asked once. The checkout is only read:
        --no-optional-locks keeps git from rewriting its index (`git diff`
        would), lfs_elsewhere Git LFS from writing into its .git/lfs."""
        key = ("uncommitted",)
        status = ["--no-optional-locks", "status", "--porcelain", "-z", "--untracked-files=no",
                  "--no-renames"]
        if key not in self._memo:
            with lfs_elsewhere() as lfs:
                p = self.git(lfs + status, check=False)
            self._memo[key] = {e[3:] for e in p.stdout.decode("utf-8", "replace").split("\0")
                               if e} if p.returncode == 0 else None
        if self._memo[key] is None:
            with lfs_elsewhere() as lfs:
                return bool(out(self.git(lfs + status + ["--", lit(path or ".")], check=False)))
        return any(p == path or not path or p.startswith(path + "/") for p in self._memo[key])

    def resolve(self, rev=None):
        key = ("resolve", rev)
        if key not in self._memo:
            self._memo[key] = self._resolve(rev)
        return self._memo[key]

    def _resolve(self, rev):
        if rev is None:
            cands = [self.ref]
        elif not self.local and not re.fullmatch(r"[0-9a-f]{40,64}|refs/.*", rev):
            # cache clone: branch names refer to the remote-tracking refs
            cands = [f"refs/remotes/origin/{rev}", rev]
        else:
            cands = [rev]
        for c in cands:
            p = self.git(["rev-parse", "--verify", "--quiet", c + "^{commit}"], check=False)
            if p.returncode == 0:
                return out(p)
        return None

    def tip(self):
        """Commit of the branch or tag; one that doesn't exist upstream is an error."""
        commit = self.resolve()
        if not commit:
            raise FsError(ref_missing(self.spec, self))
        return commit

    def require(self, rev):
        """Commit id of rev; an unknown revision is an error."""
        commit = self.resolve(rev)
        if not commit:
            raise FsError(f"unknown revision '{rev}' in {self.label}")
        return commit

    def blob_at(self, commit, path):
        """Blob id of the file at path, None if there is none (or a directory).
        ls-tree needs no blobs, so nothing is fetched in the blobless cache."""
        if ("blob", commit, path) not in self._memo:
            self.blobs_at(commit, [path])
        return self._memo[("blob", commit, path)]

    def blobs_at(self, commit, paths):
        """blob_at() for many paths, with one ls-tree per 200 of them."""
        paths = [p for p in dict.fromkeys(paths) if ("blob", commit, p) not in self._memo]
        for part in chunks(paths):
            p = self.git(["ls-tree", "-z", "--full-tree", commit, "--"] + [lit(x) for x in part],
                         check=False)
            found = {}
            for entry in p.stdout.decode("utf-8", "replace").split("\0"):
                info, _, name = entry.partition("\t")
                if info.split(" ")[1:2] == ["blob"]:
                    found[name] = info.split(" ")[2]
            for x in part:
                self._memo[("blob", commit, x)] = found.get(x)

    def read_blobs(self, blobs):
        """Read these blobs with one `cat-file --batch` (see read_blob)."""
        self._memo.update(batch_read(self.git, blobs, self._memo))

    def check_plain(self, blobs):
        """Find out with one `cat-file --batch` which of these blobs hold
        plain content: no CR and no LFS pointer (see is_plain)."""
        blobs = [b for b in dict.fromkeys(blobs) if b and ("plain", b) not in self._memo]
        self.read_blobs(blobs)
        for b in blobs:
            content = self._memo.get(("raw", b))
            if content is not None:   # missing or odd: is_plain() says "don't know"
                self._memo[("plain", b)] = b"\r" not in content and not lfs_pointer(content)

    def is_plain(self, blob):
        """Plain content (see check_plain), None if not known."""
        return self._memo.get(("plain", blob))

    def commits_exist(self, commits):
        """Find out at once which of these commit ids exist here (see
        resolve), with one `cat-file --batch-check`."""
        commits = [c for c in dict.fromkeys(commits)
                   if re.fullmatch(r"[0-9a-f]{40,64}", c) and ("resolve", c) not in self._memo]
        if not commits:
            return
        p = self.git(["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                     data="".join(c + "\n" for c in commits).encode(), check=False)
        lines = out(p).splitlines()
        if p.returncode or len(lines) != len(commits):
            return                # resolve() asks one by one
        for c, line in zip(commits, lines):
            self._memo[("resolve", c)] = c if line == f"{c} commit" else None

    def prefetch(self, links):
        """Ask at once what evaluate() needs for these links of this source:
        their paths at the tip, whether their synced commits exist (and, in
        a local checkout, are published) and are in the history of the tip,
        the checkout's HEAD versions."""
        tip = self.resolve()
        if not tip:
            return
        paths = [lk.path for lk in links]
        self.blobs_at(tip, paths)
        self.commits_exist(lk.commit for lk in links)
        self.ancestors_of(tip, (lk.commit for lk in links))
        if self.local:
            self.published(lk.commit for lk in links if self.resolve(lk.commit) == lk.commit)
            if not self.ref.startswith("refs/tags/"):
                self.blobs_at("HEAD", paths)

    def read_blob(self, oid):
        """Raw blob - an LFS pointer for files stored in LFS."""
        key = ("raw", oid)
        if key not in self._memo:
            self._memo[key] = self.git(["cat-file", "blob", oid]).stdout
        return self._memo[key]

    def read_content(self, oid, path):
        """Actual file content of a blob: LFS pointers are resolved."""
        data = self.read_blob(oid)
        if lfs_pointer(data):
            key = ("lfs", oid)
            if key not in self._memo:
                self._memo[key] = self.lfs_content(data, path)
            data = self._memo[key]
        return data

    def lfs_content(self, pointer, path):
        """Content behind an LFS pointer. A mapped checkout is only read
        (`git lfs smudge` would write into its .git/lfs, even for objects it
        has): an object in its LFS store is taken from there, a missing one
        is fetched with the cache clone of the source."""
        if not self.local:
            return lfs_smudge(self.git, pointer, path, self.label)
        info = lfs_pointer(pointer)
        if not info:
            raise FsError(f"'{path}' in {self.label}: not a Git LFS pointer")
        oid, size = info
        if ("common",) not in self._memo:
            self._memo[("common",)] = self.dir / out(self.git(["rev-parse", "--git-common-dir"]))
        common = self._memo[("common",)]
        try:
            data = (common / "lfs" / "objects" / oid[:2] / oid[2:4] / oid).read_bytes()
            if len(data) == size and hashlib.sha256(data).hexdigest() == oid:
                return data
        except OSError:
            pass
        if not self.lfs_server:
            raise FsError(f"'{path}' is stored in Git LFS in {self.label}, but its content "
                          "is not there")
        cache = self.lfs_server()
        return lfs_smudge(lambda args, **kw: git(["-C", cache] + args, env=clean_env(), **kw),
                          pointer, path, self.label)

    def short(self, oid):
        """Abbreviated commit id (asked at once for many: shorts)."""
        if ("short", oid) not in self._memo:
            self.shorts([oid])
        return self._memo[("short", oid)]

    def shorts(self, revs):
        """Abbreviated ids of these revisions with one `git show` (`rev-parse
        --short` takes one revision only)."""
        revs = [r for r in dict.fromkeys(revs) if r and ("short", r) not in self._memo]
        if not revs:
            return
        p = self.git(["show", "-s", "--no-show-signature", "--format=%h"] + revs, check=False)
        lines = out(p).splitlines()
        if p.returncode or len(lines) != len(revs):
            for r in revs:      # one by one, so that a bad one fails on its own
                self._memo[("short", r)] = out(self.git(["rev-parse", "--short", r]))
            return
        self._memo.update((("short", r), x) for r, x in zip(revs, lines))

    def dated(self, rev):
        """'a1b2c3d (2026-10-28)' in a proposed commit message: abbreviated
        id and commit date (asked at once for many: dates)."""
        if ("date", rev) not in self._memo:
            self.dates([rev])
        date = self._memo[("date", rev)]
        return f"{self.short(rev)} ({date})" if date else self.short(rev)

    def dates(self, revs):
        """Commit dates (YYYY-MM-DD) of these revisions with one `git show`;
        '' for one that isn't there."""
        revs = [r for r in dict.fromkeys(revs) if r and ("date", r) not in self._memo]
        if not revs:
            return
        p = self.git(["show", "-s", "--no-show-signature", "--format=%cs"] + revs, check=False)
        lines = out(p).splitlines()
        if p.returncode or len(lines) != len(revs):
            for r in revs:      # one by one, so that a bad one fails on its own
                self._memo[("date", r)] = out(self.git(["show", "-s", "--no-show-signature",
                                                        "--format=%cs", r], check=False)).strip()
            return
        self._memo.update((("date", r), x) for r, x in zip(revs, lines))

    def ancestors_of(self, tip, commits):
        """Find out at once which of these existing commits are in the
        history of tip (see is_ancestor): those not listed by
        `rev-list C... --not tip`."""
        commits = [c for c in dict.fromkeys(commits) if re.fullmatch(r"[0-9a-f]{40,64}", c)
                   and ("ancestor", c, tip) not in self._memo and self.resolve(c) == c]
        if not commits:
            return
        p = self.git(["rev-list"] + commits + ["--not", tip], check=False)
        if p.returncode:
            return                # is_ancestor() asks one by one
        off = set(out(p).split())
        for c in commits:
            self._memo[("ancestor", c, tip)] = c not in off

    def is_ancestor(self, a, b):
        key = ("ancestor", a, b)
        if key not in self._memo:
            self._memo[key] = self.git(["merge-base", "--is-ancestor", a, b],
                                       check=False).returncode == 0
        return self._memo[key]

    def branch_refs(self, contains=()):
        """{branch name: ref} of the upstream branches (only those containing
        one of the commits `contains`, if given): the remote-tracking
        branches, in a local checkout overridden by its local branches of the
        same name."""
        key = ("branches",) + tuple(contains)
        if key not in self._memo:
            self._memo[key] = self._branch_refs(contains)
        return self._memo[key]

    def _branch_refs(self, contains):
        prefixes = ["refs/remotes/origin/"] + (["refs/heads/"] if self.local else [])
        refs = out(self.git(["for-each-ref", "--format=%(refname)"]
                            + [x for c in contains for x in ("--contains", c)] + prefixes)).split()
        result = {}
        for prefix in prefixes:          # refs/heads/ last: wins
            for r in refs:
                if r.startswith(prefix) and r != "refs/remotes/origin/HEAD":
                    result[r[len(prefix):]] = r
        return result

    def tags_by_commit(self):
        """{commit: [tag names]} of all tags (annotated ones peeled)."""
        if ("tags",) not in self._memo:
            tag_map = self._memo[("tags",)] = {}
            fmt = "%(objecttype)%09%(objectname)%09%(*objecttype)%09%(*objectname)%09" \
                  "%(refname:strip=2)"
            for line in out(self.git(["for-each-ref", f"--format={fmt}", "refs/tags/"])).splitlines():
                kind, oid, peeled_kind, peeled, name = line.split("\t", 4)
                commit = oid if kind == "commit" else peeled if peeled_kind == "commit" else None
                if commit:
                    tag_map.setdefault(commit, []).append(name)
        return self._memo[("tags",)]

    def is_on_branch(self, tag, branch):
        """Is tag's commit on branch (None: no such tag or branch)?"""
        key = ("on", tag, branch)
        if key not in self._memo:
            base = self.resolve(f"refs/tags/{tag}")
            ref = self.branch_refs().get(branch)
            self._memo[key] = self.is_ancestor(base, ref) if base and ref else None
        return self._memo[key]

    def line_problem(self, tag, branch):
        """Why newer tags than tag can't be looked for on branch; None if
        they can (or the tag doesn't exist, which is reported elsewhere)."""
        on = self.is_on_branch(tag, branch)
        if on is None and self.resolve(f"refs/tags/{tag}"):
            return f"branch '{branch}' not found in {self.label}"
        if on is False:
            others = sorted(self.branch_refs([self.resolve(f"refs/tags/{tag}")]))
            return (f"tag {tag} is not on branch '{branch}' of {self.label}"
                    + (f" (it is on {and_list(others)}; -b selects another branch)"
                       if others else ""))
        return None

    def newest_matching(self, pattern, branch):
        """The tags matching pattern on the newest commit of branch that has
        any, by the commit graph like newer_tags: the first one along the
        branch's first-parent line, from its head back. [] if none."""
        ref = self.branch_refs().get(branch)
        if not ref:
            raise FsError(f"branch '{branch}' not found in {self.label}")
        tags = self.tags_by_commit()
        for c in out(self.git(["rev-list", "--first-parent", ref])).split():
            names = sorted(t for t in tags.get(c, []) if fnmatch.fnmatchcase(t, pattern))
            if names:
                return names
        return []

    def matching_elsewhere(self, pattern):
        """For an error about a pattern: the branches that have tags matching
        it (' (matching tags on maint; -b selects another branch)'), or ''."""
        commits = [c for c, names in self.tags_by_commit().items()
                   if any(fnmatch.fnmatchcase(n, pattern) for n in names)]
        others = sorted(self.branch_refs(commits)) if commits else []
        return (f" (matching tags on {and_list(others)}; -b selects another branch)"
                if others else "")

    def tag_info(self, tag, line, newer=True):
        """(newer tags, problem) for files pinned to tag, with newer tags
        looked for on branch line (their source's); problem: why they can't
        be looked for there. newer=False: only check the branch."""
        problem = line and self.line_problem(tag, line)
        if problem or not newer:
            return [], problem
        return self.newer_tags(tag, line), None

    def newer_tags(self, tag, branch):
        """Tags newer than tag on branch, by their position in the commit
        graph - tag names are opaque, and tags have no reliable date: the
        newest one is on the first tagged commit from the branch head back
        along its first-parent line (a tag on a merged side branch doesn't
        count).
        Returns [(tags of that commit, [branch])], empty if there are none."""
        key = ("newer", tag, branch)
        if key in self._memo:
            return self._memo[key]
        base = self.resolve(f"refs/tags/{tag}")
        refs = {}
        if base and branch:
            ref = self.branch_refs().get(branch)
            refs = {branch: ref} if ref and self.is_ancestor(base, ref) else {}
        tags, found = self.tags_by_commit(), {}
        for name, ref in sorted(refs.items()):
            # the line down to tag; containing tag is monotonic along it, so
            # the first tagged commit decides
            for c in out(self.git(["rev-list", "--first-parent", ref, f"^{base}"])).split():
                if c in tags:
                    if self.is_ancestor(base, c):
                        found.setdefault(tuple(sorted(tags[c])), []).append(name)
                    break
        self._memo[key] = sorted(found.items())
        return self._memo[key]

    def last_change(self, rev, path):
        """Newest commit up to rev that changed path: the commit the file's
        version at rev comes from (same blob, by git's history simplification).
        Recorded as a link's commit, so one file version always gives the same
        entry, whatever else happened on the branch."""
        key = ("last", rev, path)
        if key not in self._memo:
            commit = out(self.git(["rev-list", "-1", rev, "--", lit(path)])) or rev
            # up to that commit, it is the last change too (e.g. pull's first sync)
            self._memo[key] = self._memo[("last", commit, path)] = commit
        return self._memo[key]

    def count(self, old, new, *paths):
        key = ("count", old, new, paths)
        if key not in self._memo:
            self._memo[key] = int(out(self.git(["rev-list", "--count", f"{old}..{new}", "--"]
                                               + [lit(p) for p in paths])))
        return self._memo[key]

    def log(self, rng, *paths):
        return out(self.git(["log", "--reverse", "--no-show-signature", "--format=- %s (%h, %cs)",
                             rng, "--"]
                            + [lit(p) for p in paths]))

    def follow(self, old, tip, path):
        """What became of path, which exists at old but not at tip:
        ('renamed', new path, commit) or ('deleted', path, commit), None if
        unknown. Looks only at the commit that removed it (and at later ones
        for chained renames), so few blobs are needed in the blobless cache."""
        start = old
        for _ in range(20):
            gone = out(self.git(["rev-list", "-1", f"{start}..{tip}", "--", lit(path)],
                                check=False))
            if not gone:
                return None
            p = self.git(["diff-tree", "-r", "-z", "-M", "--name-status", "--diff-filter=RD",
                          "--no-commit-id", f"{gone}^", gone], check=False)
            if p.returncode:
                return None
            items = p.stdout.decode("utf-8", "replace").split("\0")
            new, i = None, 0
            while i < len(items) - 1:
                status = items[i]
                if status.startswith("R"):
                    if items[i + 1] == path:
                        new = items[i + 2]
                    i += 3
                else:
                    i += 2
            if not new:
                return "deleted", path, gone
            if self.blob_at(tip, new):
                return "renamed", new, gone
            path, start = new, gone      # renamed again (or deleted) later
        return None

    def files_below(self, commit, path):
        """Paths of all regular files at or below directory path ('' = root)."""
        p = self.git(["ls-tree", "-r", "-z", "--full-tree", commit]
                     + (["--", lit(path)] if path else []))
        result = []
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name and info.split(" ")[0] in ("100644", "100755"):
                result.append(name)
        return result

    def is_dir(self, commit, path):
        return bool(self.tree_at(commit, path))

    def tree_at(self, rev, path):
        """Tree id of the directory path ('' = the root) at commit rev, None
        if there is none."""
        key = ("tree", rev, path)
        if key not in self._memo:
            p = self.git(["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                         data=f"{rev}:{path}\n".encode(), check=False)
            oid, _, kind = out(p).partition(" ")
            self._memo[key] = oid if p.returncode == 0 and kind == "tree" else None
        return self._memo[key]

    def tree_files(self, tree):
        """{path: blob id} of the regular files in a tree and below it, None
        if the tree isn't there. Needs no blobs (blobless cache)."""
        key = ("files", tree)
        if key not in self._memo:
            p = self.git(["ls-tree", "-r", "-z", tree], check=False)
            files = None
            if p.returncode == 0:
                files = {}
                for entry in p.stdout.decode("utf-8", "replace").split("\0"):
                    info, _, name = entry.partition("\t")
                    if name and info.split(" ")[0] in ("100644", "100755"):
                        files[name] = info.split(" ")[2]
            self._memo[key] = files
        return self._memo[key]

    def files_at(self, rev, path):
        """(tree id, {path below: blob id}) of the directory path at commit
        rev (see tree_files); (None, None) if there is none. What blob_at()
        answers for these files is known then too."""
        tree = self.tree_at(rev, path)
        files = self.tree_files(tree) if tree else None
        for below, oid in (files or {}).items():
            self._memo.setdefault(("blob", rev, up_join(path, below)), oid)
        return tree, files

    def path_history(self, path, max_count):
        """[(commit, blob id)] of commits on the branch touching path, newest
        first (a directory: tree ids; '' = the root)."""
        revs = out(self.git(["rev-list", f"--max-count={max_count}",
                             self.ref, "--", lit(path or ".")])).split()
        if not revs:
            return []
        data = "".join(f"{r}:{path}\n" for r in revs).encode()
        ids = out(self.git(["cat-file", "--batch-check=%(objectname)"],
                           data=data)).splitlines()
        return [(r, o) for r, o in zip(revs, ids) if " " not in o]


class Context:
    """Creates and caches Sources; fetches each upstream repository at most once."""

    def __init__(self, args, repo=None):
        self.repo_top = repo.top if repo else None
        # restore, diff of local changes and set of what doesn't change the
        # upstream version (the patterns: the base tree) only need the synced
        # versions, which never change (a blob missing in the cache is fetched
        # lazily): fetched only if the cache lacks the branch (lazy)
        offline = args.cmd in ("restore", "rm") or \
            args.cmd in ("diff", "difftool") and not args.upstream or \
            args.cmd == "set" and not (args.source or args.branch or args.tag or args.path)
        no_fetch = getattr(args, "no_fetch", False)
        self.remote = getattr(args, "remote", False)     # mappings ignored this once
        self.fetch, self.lazy = not (no_fetch or offline), offline and not no_fetch
        # fetch even for a tag already cached, to learn about newer tags
        self.want_tags = getattr(args, "verbose", False) or args.cmd == "pull"
        self._sources = {}
        self._ready = set()
        self._fetch_failed = set()
        self._cached = {}         # see cached_source
        self._mappings = None

    def source(self, url, ref, name=None, line=None):
        """Source for url and ref (('branch' | 'tag', name)); name is its key
        in .git-filesync (used as label). For a tag, line is the branch of
        the source: a pattern is resolved to the newest matching tag on it.
        A branch that doesn't exist is an error (a tag not on it isn't: see
        tag_info)."""
        url = self.url(url)
        key = (norm_url(url), ref, line if ref[0] == "tag" else None)
        if key not in self._sources:
            try:
                self._sources[key] = self._make(url, ref, name, line)
                self._sources[key].spec = ref
                if self._sources[key].local:     # LFS objects it lacks: via the cache clone
                    self._sources[key].lfs_server = lambda: self._cache(url)
            except FsError as e:      # e.g. a failed clone: not tried again for each file
                self._sources[key] = e
        s = self._sources[key]
        if isinstance(s, FsError):
            raise s
        return s

    def url(self, url):
        """url as git takes it: a relative one resolved (see resolve_url)."""
        return resolve_url(url, self.repo_top)

    def local_path(self, url):
        """Mapped local checkout for url (validated), or None."""
        url = self.url(url)
        if self.remote:
            return None
        if self._mappings is None:
            # repo-local mapping overrides a global one (later entries win)
            self._mappings = {norm_url(u): d for _, _, u, d in
                              local_mappings(cwd=self.repo_top)}
            self._local_ok = {}
        key = norm_url(url)
        if key not in self._local_ok:
            local = self._mappings.get(key)
            path = Path(os.path.expanduser(local)) if local else None
            if path and not is_repository(path):
                warn(f"mapped local checkout {path} is not a Git repository; using {url}")
                path = None
            self._local_ok[key] = path
        return self._local_ok[key]

    def default_branch(self, url):
        """Default branch upstream: from a mapped checkout or the cache
        when possible (works offline), otherwise asked from the server."""
        url = self.url(url)
        local = self.local_path(url)
        if local:
            def symref(ref):
                p = git(["-C", local, "symbolic-ref", "--short", ref], env=clean_env(), check=False)
                return out(p) if p.returncode == 0 else None
            b = symref("refs/remotes/origin/HEAD")
            if b:
                return b[len("origin/"):] if b.startswith("origin/") else b
            b = symref("HEAD")    # only a guess if the checkout has a remote
            if b:
                if out(git(["-C", local, "remote"], env=clean_env(), check=False)):
                    warn(f"default branch of {url} unknown in {local} (origin/HEAD not set); "
                         f"using its checked-out branch '{b}' - use --branch to choose")
                return b
        if self.fetch:
            p = git(PROTOCOL_V2 + ["ls-remote", "--symref", "--", url, "HEAD"], env=clean_env(),
                    check=False)
            m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out(p), re.M)
            if m:
                return m.group(1)
        d = self.cache_dir(url)
        if d.exists():   # HEAD of the bare clone names the remote's default branch
            p = git(["-C", d, "symbolic-ref", "--short", "HEAD"], env=clean_env(), check=False)
            if p.returncode == 0:
                return out(p)
        raise FsError(f"cannot determine default branch of {url}; use --branch")

    def _make(self, url, ref, name=None, line=None):
        kind, branch = ref
        local = self.local_path(url)
        if kind == "tag":
            pattern = is_tag_pattern(branch)
            if pattern and not line:
                raise FsError(f"tag pattern '{branch}' needs a branch to look for it on")
            if local:
                src = Source(local, f"refs/tags/{branch}", f"local checkout {local}", local=True)
            else:         # a pattern: always fetched (lazy: if the branch is missing)
                src = Source(self._cache(url, tag=None if pattern else branch,
                                         need=pattern and f"refs/remotes/origin/{line}"),
                             f"refs/tags/{branch}", name or repo_label(url))
            if pattern:
                src.tag_names = src.newest_matching(branch, line)
                if not src.tag_names:
                    raise FsError(f"no tag matching '{branch}' on branch '{line}' of {src.label}"
                                  + src.matching_elsewhere(branch))
                src.ref = f"refs/tags/{src.tag_names[0]}"
            elif line and line not in src.branch_refs():
                raise FsError(f"branch '{line}' not found in {src.label}")
            return src
        if local:
            # the link's branch as it is in the checkout (incl. unpushed
            # commits) - not whatever happens to be checked out there
            label = f"local checkout {local}"
            if git(["-C", local, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                   env=clean_env(), check=False).returncode == 0:
                return Source(local, f"refs/heads/{branch}", label, local=True)
            return Source(local, f"refs/remotes/origin/{branch}", label, local=True,
                          note=f"no local branch '{branch}' there, using origin/{branch} "
                               "as last fetched")
        return Source(self._cache(url, need=f"refs/remotes/origin/{branch}"),
                      f"refs/remotes/origin/{branch}", name or repo_label(url))

    def cached_source(self, url, ref, name=None):
        """A Source for the base of an entry in a layer below (see
        layer_source): the one of this run if there is one, else the mapped
        checkout or the cache clone as it is - never fetched or cloned (a
        URL changed, not committed yet: the old server may be gone); None if
        there is neither. Its blobs are looked up by id, the ref is not."""
        url = self.url(url)
        key = (norm_url(url), ref)
        found = [s for k, s in self._sources.items() if k[:2] == key and not isinstance(s, FsError)]
        if found:
            return found[0]
        if key not in self._cached:
            local = self.local_path(url)
            d = Path(local) if local else self.cache_dir(url)
            kind, what = ref
            src = Source(d, f"refs/tags/{what}" if kind == "tag" else
                         f"refs/remotes/origin/{what}", name or repo_label(url),
                         local=bool(local)) if d.is_dir() else None
            if src is not None:   # not even a missing blob or LFS object: no lfs_server
                src.offline = True
            self._cached[key] = src
        return self._cached[key]

    @staticmethod
    def cache_dir(url):
        return cache_root() / (hashlib.sha1(norm_url(url).encode()).hexdigest()[:16] + ".git")

    def _cache(self, url, tag=None, need=None):
        """The cache clone of url, fetched once per run - not for a tag
        already there (tags are taken as immutable), unless newer tags are
        of interest (want_tags); with lazy, only if it lacks the ref need."""
        url = self.url(url)
        d = self.cache_dir(url)
        if d in self._ready:
            return d
        env = clean_env()
        fetch = PROTOCOL_V2 + ["fetch", "--quiet", "--prune", "origin",
                 "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*"]
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(f"{d.name}.tmp{os.getpid()}")
            print(paint(f"Cloning {url} (blobless) ...", "dim", "err"), file=sys.stderr)
            try:
                git(PROTOCOL_V2 + ["clone", "--bare", "--quiet", "--filter=blob:none", "--", url, tmp],
                    env=env)
                git(["-C", tmp, "config", "remote.origin.fetch",
                     "+refs/heads/*:refs/remotes/origin/*"], env=env)
                git(["-C", tmp] + fetch, env=env)
                self._drop_heads(tmp)
                try:
                    tmp.rename(d)
                except OSError as e:      # a parallel run may have cloned it meanwhile
                    if not d.is_dir():
                        raise FsError(f"cannot create the cache clone {d}: {e}")
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
        elif tag and not self.want_tags and git(["-C", d, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                         env=env, check=False).returncode == 0:
            touch_used(d)
            return d       # not marked ready: a branch of the same URL still fetches
        elif self.lazy and need and git(["-C", d, "rev-parse", "--verify", "--quiet", need],
                                        env=env, check=False).returncode == 0:
            touch_used(d)
            return d       # not marked ready: another ref may be missing
        elif self.fetch or self.lazy:
            p = git(["-C", d] + fetch, env=env, check=False)
            if p.returncode:
                warn(f"fetching {url} failed, using cached state")
                self._fetch_failed.add(d)
        touch_used(d)
        if self.fetch or self.lazy:
            auto_prune()
        self._ready.add(d)
        return d

    def on_server(self, url, commit):
        """Is commit on url's server - reachable from a branch or tag there,
        whatever is mapped? Fetches the cache clone; None if that fails."""
        url = self.url(url)
        try:
            d = self._cache(url)
        except FsError:
            return None
        if d in self._fetch_failed:
            return None
        p = git(["-C", d, "for-each-ref", "--count=1", "--contains", commit,
                 "refs/remotes/origin/", "refs/tags/"], env=clean_env(), check=False)
        return p.returncode == 0 and bool(out(p))

    @staticmethod
    def _drop_heads(d):
        """Remove refs/heads/* left by the initial bare clone; they are never
        updated by fetch and would shadow the current remote-tracking refs."""
        refs = out(git(["-C", d, "for-each-ref", "--format=%(refname)", "refs/heads/"],
                       env=clean_env())).split()
        if refs:
            data = "".join(f"delete {r}\n" for r in refs).encode()
            git(["-C", d, "update-ref", "--stdin"], data=data, env=clean_env())


# --------------------------------------------------------------------------
# this repository
# --------------------------------------------------------------------------

class Repo:
    def __init__(self):
        p = git(["rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-path", "objects"],
                check=False)
        lines = out(p).splitlines()
        if p.returncode or len(lines) != 3:
            raise FsError("not inside a Git working tree")
        self.top = Path(lines[0]).resolve()
        self.gitdir = Path(lines[1]).resolve()
        self.objects = Path.cwd() / lines[2]      # relative to the current directory
        # shell aliases run in the top-level dir and pass the original
        # subdirectory in GIT_PREFIX. Resolved like top (git names it by its
        # real path): run directly, the current directory may be reached
        # through a subst drive, junction or symlink (Windows keeps that name).
        prefix = os.environ.get("GIT_PREFIX")
        self.base = (Path.cwd() / prefix if prefix else Path.cwd()).resolve()
        self._head = {}           # rel -> blob id in HEAD (None: not there)
        self._dirty = {}          # rel -> differs between HEAD and working tree
        self._plain = {}          # rel -> no content-changing attributes
        self._raw = {}            # blob id -> content (read_blob)
        self._local = {}          # (rel, content hash, size) -> blob id (as_local)
        self._wt = {}             # rel -> blob id of the working file (worktree_blobs)
        self._ids = {}            # (rel, content hash, size) -> blob id (blob_ids)
        self._staged = None       # paths staged differently from HEAD (staged)
        self.layers = {}          # see registry(): {layer: its Registry}
        self.rows = None          # see registry_rows()
        self.ctx: Optional["Context"] = None    # the Context of the run (see staged_as_base)

    def git(self, args, **kw):
        return git(args, cwd=self.top, **kw)

    def registry(self, layer):
        """.git-filesync as HEAD ('head') or the index ('index') has it, read
        once per run (see Registry)."""
        if layer not in self.layers:
            self.layers[layer] = Registry(self, layer)
        return self.layers[layer]

    @contextmanager
    def scratch(self):
        """For commands that only read (status, diff, hooks): the objects
        that comparing in this repository's form or building trees for diff
        writes go to a temporary object directory - the repository's own
        stay readable as an alternate - which is removed afterwards. So
        nothing is written into .git/objects."""
        names = ("GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
        saved = {k: os.environ.get(k) for k in names}
        objects = saved["GIT_OBJECT_DIRECTORY"] or str(self.objects)
        alternates = [objects] + ([saved["GIT_ALTERNATE_OBJECT_DIRECTORIES"]]
                                  if saved["GIT_ALTERNATE_OBJECT_DIRECTORIES"] else [])
        tmp = tempfile.mkdtemp(prefix="git-filesync-objects-")
        os.environ["GIT_OBJECT_DIRECTORY"] = tmp
        os.environ["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.pathsep.join(alternates)
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            rmtree(tmp)

    def prefetch(self, rels):
        """Ask at once, for many files, what head_blob() and is_modified()
        answer: one ls-tree and one diff per 200 files instead of two
        commands per file."""
        rels = list(dict.fromkeys(rels))
        for part in chunks(rels):
            spec = ["--"] + [lit(r) for r in part]
            p = self.git(["ls-tree", "-z", "--full-tree", "HEAD"] + spec, check=False)
            found = {}
            for entry in p.stdout.decode("utf-8", "replace").split("\0"):
                info, _, name = entry.partition("\t")
                if info.split(" ")[1:2] == ["blob"]:
                    found[name] = info.split(" ")[2]
            p2 = self.git(["diff", "--name-only", "-z", "--no-renames", "HEAD"] + spec, check=False)
            if p.returncode or p2.returncode:
                continue          # e.g. no commit yet: asked one by one
            dirty = set(p2.stdout.decode("utf-8", "replace").split("\0"))
            for r in part:
                self._head[r] = found.get(r)
                self._dirty[r] = r in dirty

    def check_plain(self, rels):
        """Find out with one `check-attr` which files have no attributes that
        change content on checkout or checkin beyond line endings (filter,
        ident, working-tree-encoding) - see is_plain."""
        rels = [r for r in dict.fromkeys(rels) if r not in self._plain]
        if not rels:
            return
        attrs = ["filter", "ident", "working-tree-encoding"]
        p = self.git(["check-attr", "-z", "--stdin"] + attrs,
                     data="".join(r + "\0" for r in rels).encode(), check=False)
        if p.returncode:
            return
        items = p.stdout.decode("utf-8", "replace").split("\0")
        plain = dict.fromkeys(rels, True)
        for i in range(0, len(items) - 2, 3):
            path, value = items[i], items[i + 2]
            if path in plain and value not in ("unspecified", "unset"):
                plain[path] = False
        self._plain.update(plain)

    def is_plain(self, rel):
        """No content-changing attributes (see check_plain), None if not known."""
        return self._plain.get(rel)

    def head_blob(self, rel):
        """Blob id of rel in HEAD, None if it isn't there."""
        if rel not in self._head:
            p = self.git(["rev-parse", "--verify", "-q", f"HEAD:{rel}"], check=False)
            self._head[rel] = out(p) if p.returncode == 0 else None
        return self._head[rel]

    def is_modified(self, rel):
        """Uncommitted changes: does the working tree file (like `git diff
        HEAD`) or the staged one differ from HEAD?"""
        if rel not in self._dirty:
            self._dirty[rel] = self.git(["diff", "--quiet", "HEAD", "--", lit(rel)],
                                        check=False).returncode == 1
        return self._dirty[rel] or rel in self.staged()

    def user_path(self, s):
        """A path given by the user, absolute: relative to the current
        directory, '..' resolved by name; symlinks only in its directories,
        not the path itself (a linked file may be a symlink, as for git)."""
        p = Path(os.path.normpath(self.base / s))
        return p.parent.resolve() / p.name if p.name else p.resolve()

    @staticmethod
    def names_dir(s):
        """Does a path given by the user end with a separator, i.e. name a
        directory (as for cp and git mv)?"""
        return s.endswith("/") or os.name == "nt" and s.endswith("\\")

    def rel(self, path):
        """Path relative to the top-level directory (as git names it);
        outside the working tree: '../...', or absolute on another drive."""
        try:
            return Path(os.path.relpath(path, self.top)).as_posix()
        except ValueError:        # Windows: another drive
            return Path(path).as_posix()

    def worktree_blob(self, path, write=False):
        """Blob id of the (clean-filtered) working tree file, None if missing.
        For a file tracked in LFS here, this is the id of its LFS pointer."""
        if not path.is_file():
            return None
        if self.rel(path) in self._wt:          # asked at once before (stored then)
            return self._wt[self.rel(path)]
        args = ["hash-object"] + (["-w"] if write else []) + \
            [f"--path={self.rel(path)}", str(path)]
        return out(self.git(args))

    def read_blob(self, oid):
        if oid not in self._raw:
            self._raw[oid] = self.git(["cat-file", "blob", oid]).stdout
        return self._raw[oid]

    def read_content(self, oid, rel):
        """Actual content of a blob of this repo: LFS pointers are resolved."""
        data = self.read_blob(oid)
        if lfs_pointer(data):
            data = lfs_smudge(self.git, data, rel, "this repository")
        return data

    def store(self, content):
        return out(self.git(["hash-object", "-w", "--stdin", "--no-filters"], data=content))

    def to_worktree(self, content, rel):
        """Convert normalized blob content to this repo's working tree form
        (eol conversion, smudge filters per .gitattributes / core.autocrlf)."""
        return self.git(["cat-file", "--filters", f"--path={rel}", self.store(content)]).stdout

    def as_local(self, content, rel):
        """Blob id that upstream `content` gets when stored in this repo, i.e.
        after this repo's checkout and checkin conversion (eol normalization,
        LFS). Equals the upstream blob id unless the repos store it differently."""
        key = (rel, hashlib.sha1(content).digest(), len(content))
        if key not in self._local:
            work = self.to_worktree(content, rel)
            self._local[key] = out(self.git(["hash-object", "-w", f"--path={rel}", "--stdin"],
                                            data=work))
        return self._local[key]

    def as_local_many(self, items):
        """as_local() for many [(content, rel)] at once (see as_local): stored
        as they are with one command, checked out into a temporary work
        tree - with this repository's .gitattributes along the paths - and
        added from there into a temporary index that holds this index's
        entries (git's rule for CRLF already in the index), so that each
        file is converted exactly as on a checkout and checkin here. Some
        commands for all of them instead of three per file; whatever goes
        wrong is left to as_local() one by one."""
        todo, seen = [], set()
        for content, rel in items:
            key = (rel, hashlib.sha1(content).digest(), len(content))
            if key not in self._local and key not in seen:
                seen.add(key)
                todo.append((key, content, rel))
        while len(todo) > 1:
            batch, rest, rels = [], [], set()     # a path only once per batch
            for item in todo:
                (rest if item[2] in rels else batch).append(item)
                rels.add(item[2])
            todo = rest
            try:
                self._as_local_batch(batch)
            except (FsError, OSError):
                return

    def _as_local_batch(self, batch):
        oids = self.store_many([content for _, content, _ in batch])
        rels = [rel for _, _, rel in batch]
        names = "".join(r + "\0" for r in rels).encode()
        with tempfile.TemporaryDirectory(prefix="git-filesync-") as d:
            wt = Path(d) / "wt"
            wt.mkdir()
            for rel in rels:      # the attributes that apply to rel
                for parent in [Path(rel).parents[i] for i in range(len(Path(rel).parents))]:
                    attrs = self.top / parent / ".gitattributes"
                    if attrs.is_file() and not (wt / parent / ".gitattributes").exists():
                        (wt / parent).mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(attrs, wt / parent / ".gitattributes")

            def tmp_git(args, index, data):
                env = dict(os.environ, GIT_DIR=str(self.gitdir), GIT_WORK_TREE=str(wt),
                           GIT_INDEX_FILE=os.path.join(d, index))
                return git(args, cwd=wt, env=env, data=data)
            tmp_git(["update-index", "-z", "--add", "--index-info"], "checkout",
                    "".join(f"100644 {o}\t{r}\0" for o, r in zip(oids, rels)).encode())
            tmp_git(["checkout-index", "-f", "-z", "--stdin"], "checkout", names)
            found = self._add_in_index(rels, lambda args, data: tmp_git(args, "add", data))
        for (key, _, rel) in batch:
            if rel in found:
                self._local[key] = found[rel]

    def normalize_many(self, items):
        """Prepare normalize() for many [(content, rel)] at once: the
        conversions (as_local_many) and reading the results."""
        items = [(c, r) for c, r in items if not self.plain_content(r, c)]
        self.as_local_many(items)
        self.read_blobs(self._local.get((r, hashlib.sha1(c).digest(), len(c)))
                        for c, r in items)

    def read_blobs(self, oids):
        """Read these blobs of this repo with one `cat-file --batch`."""
        for (_, oid), content in batch_read(self.git, [o for o in oids if o not in self._raw], {}):
            self._raw[oid] = content

    def normalize(self, content, rel):
        """Upstream content as this repo stores it, LFS resolved: the form all
        comparisons and merges use, whatever the eol conventions and LFS use
        upstream and here. Plain content (no CR, no LFS pointer) of a file
        without content-changing attributes is stored as it is (see
        check_plain): no conversion needed."""
        if self.plain_content(rel, content):
            return content
        return self.read_content(self.as_local(content, rel), rel)

    def store_many(self, contents):
        """Store these contents as blobs, as they are, with one git command:
        their ids."""
        if not contents:
            return []
        with tempfile.TemporaryDirectory(prefix="git-filesync-") as d:
            paths = []
            for i, content in enumerate(contents):
                paths.append(os.path.join(d, str(i)))
                Path(paths[-1]).write_bytes(content)
            oids = out(self.git(["hash-object", "-w", "--no-filters", "--stdin-paths"],
                                data="".join(p + "\n" for p in paths).encode())).split()
        if len(oids) != len(contents):
            raise FsError("git hash-object gave an unexpected answer")
        return oids

    def staged(self):
        """staged_changes(), asked once per run (before anything is staged);
        without a commit all of the index."""
        if self._staged is None:
            self._staged = self.staged_changes()
            if self._staged is None:
                self._staged = {r: e[1] for r, e in self.index_entries([]).items()}
        return self._staged

    def staged_changes(self):
        """{path: blob id staged (None: staged for deletion)} of the paths
        whose index entry differs from HEAD - one diff-index for the whole
        index, without the paths (no limit on the command line); None
        without a commit."""
        p = self.git(["diff-index", "--cached", "--raw", "-z", "--no-renames", "HEAD"],
                     check=False)
        if p.returncode:
            return None
        items = p.stdout.decode("utf-8", "replace").split("\0")
        changes = {}
        for info, path in zip(items[0::2], items[1::2]):    # ':mode mode old new status'
            fields = info.split()
            if len(fields) == 5:
                changes[path] = None if fields[4] == "D" else fields[3]
        return changes

    def index_entries(self, rels):
        """{rel: (mode, blob id)} of these files in the index, one command."""
        entries = {}
        p = self.git(["ls-files", "-s", "-z", "--"] + [lit(r) for r in rels], check=False)
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name:
                entries[name] = (info.split(" ")[0], info.split(" ")[1])
        return entries

    def blob_ids(self, files):
        """{rel: blob id} these [(rel, content)] get when written (see
        write_files): content in the form stored here, LFS resolved. Asked
        before: from the cache."""
        def key(r, c):
            return r, hashlib.sha1(c).digest(), len(c)
        todo = [(r, c) for r, c in files if key(r, c) not in self._ids]
        plain = [(r, c) for r, c in todo if self.is_plain(r)]
        for (r, c), oid in zip(plain, self.store_many([c for _, c in plain])):
            self._ids[key(r, c)] = oid
        rest = [(c, r) for r, c in todo if not self.is_plain(r)]
        self.as_local_many(rest)
        for c, r in rest:
            self._ids[key(r, c)] = self.as_local(c, r)
        return {r: self._ids[key(r, c)] for r, c in files}

    def write_files(self, files, stage=True):
        """Put these [(rel, content)] - content in the form stored here, LFS
        resolved - into the working tree (and the index, if stage), converted for it
        as on any checkout (eol, attributes, LFS): each stored as this
        repository stores it - as it is without content-changing attributes
        (see check_plain), else converted (see as_local; LFS: the pointer) -
        then all put there at once (see put_blobs)."""
        if not files:
            return
        ids = self.blob_ids(files)
        self.put_blobs([(r, ids[r]) for r, _ in files], stage)

    def put_blobs(self, entries, stage=True, worktree=True):
        """Put these [(rel, blob id)] - blobs as stored here (LFS pointers
        too) - into the index and/or the working tree, where git converts
        them as on any checkout: a few commands for all of them."""
        if not entries:
            return
        rels, oids = [r for r, _ in entries], [o for _, o in entries]
        if worktree:     # the last line of defense: git would delete what is in the way
            blocked = [f"{r}: {p}" for r in rels for p in [in_the_way(self.top, r)] if p]
            if blocked:
                raise FsError("not written - " + "; ".join(blocked))
            self._wt.clear()
        # an executable file stays one; a symlink or submodule there becomes a file
        modes = {r: e[0] for r, e in self.index_entries(rels).items()
                 if e[0] in ("100644", "100755")}
        info = "".join(f"{modes.get(rel, '100644')} {oid}\t{rel}\0"
                       for rel, oid in zip(rels, oids)).encode()
        names = "".join(r + "\0" for r in rels).encode()
        if stage:
            self.git(["update-index", "-z", "--add", "--index-info"], data=info)
        if worktree:
            if stage:
                self.git(["checkout-index", "-f", "-u", "-z", "--stdin"], data=names)
            else:     # through an index of its own, so that this one stays as it is
                with tempfile.TemporaryDirectory(prefix="git-filesync-") as d:
                    env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
                    self.git(["update-index", "-z", "--add", "--index-info"], data=info,
                             env=env)
                    self.git(["checkout-index", "-f", "-z", "--stdin"], data=names, env=env)

    def worktree_blobs(self, rels):
        """{rel: blob id} of these working tree files as git would store them
        (clean-filtered), via a temporary index (see _add_in_index) instead
        of a hash-object each; those asked before from the cache. Writes the
        blobs: for reading commands (scratch)."""
        # a symlink: git would take the link, not the file (see worktree_blob)
        rels = [r for r in rels if (self.top / r).is_file() and not (self.top / r).is_symlink()]
        todo = [r for r in rels if r not in self._wt]
        if todo:
            with tempfile.TemporaryDirectory(prefix="git-filesync-") as d:
                env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
                self._wt.update(self._add_in_index(
                    todo, lambda args, data: self.git(args, env=env, data=data)))
        return {r: self._wt[r] for r in rels if r in self._wt}

    def _add_in_index(self, rels, run):
        """{rel: blob id} of these files as `git add` stores them (clean
        filters, eol), added into an index that holds this index's entries
        first - for git's rule on CRLF already in the index. run(args, data)
        runs git with that index and the work tree to add from."""
        current = self.index_entries(rels)
        if current:
            run(["update-index", "-z", "--add", "--index-info"],
                "".join(f"{m} {o}\t{r}\0" for r, (m, o) in current.items()).encode())
        run(["add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"],
            "".join(lit(r) + "\0" for r in rels).encode())
        p = run(["ls-files", "-s", "-z"], None)
        wanted, found = set(rels), {}
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name in wanted:
                found[name] = info.split(" ")[1]
        return found

    def plain_content(self, rel, data):
        """Is data, as a file at rel, stored as it is - no content-changing
        attributes, no CR, no LFS pointer? (see check_plain)"""
        return bool(self.is_plain(rel)) and b"\r" not in data and not lfs_pointer(data)

    def fix_eol(self, path):
        """Give a file written here (.git-filesync) the line ends of a
        checkout - by the git attributes and core.autocrlf, so that git
        doesn't warn about them: all LF first, then converted as on a
        checkout. The file is taken to be in that form already."""
        data = path.read_bytes()
        conv = self.to_worktree(data.replace(b"\r\n", b"\n"), self.rel(path))
        if conv != data:
            path.write_bytes(conv)


# --------------------------------------------------------------------------
# .git-filesync
# --------------------------------------------------------------------------

def config_value(value):
    """value as written in a git config file: as it is if that's safe, else
    quoted."""
    if re.fullmatch(r'[^\s"\\#;](?:[^"\\#;\n]*[^\s"\\#;])?', value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


HEADER_RX = re.compile(r'(\s*\[\s*)([A-Za-z][A-Za-z0-9-]*)(\s+)"((?:[^"\\]|\\.)*)"(\s*\]\s*(?:[#;].*)?)')
KEY_RX = re.compile(r"(\s*)([A-Za-z][A-Za-z0-9-]*)(\s*(?:[=#;].*)?)")


def quoted_name(name):
    """A section's name as written in its header: '"src/foo.c"'."""
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def replace_value(line, value):
    """A `key = value` line with another value: indentation, spacing and a
    comment at the end of the line stay as they are. None if the line is
    odd (an unclosed quote)."""
    m = KEY_RX.fullmatch(line)
    if not m:
        return None
    indent, key, rest = m.groups()
    eq = re.match(r"\s*=\s*", rest)
    if not eq:                    # a key without '= value' (boolean): rest is a comment
        return f"{indent}{key} = {config_value(value)}{rest}"
    j, quoted = eq.end(), False
    while j < len(rest):          # the value ends at a comment outside quotes
        if rest[j] == "\\":
            j += 2
            continue
        if rest[j] == '"':
            quoted = not quoted
        elif rest[j] in "#;" and not quoted:
            break
        j += 1
    if quoted:
        return None
    old = rest[eq.end():j]
    return indent + key + rest[:eq.end()] + config_value(value) + old[len(old.rstrip()):] + rest[j:]


def edit_registry(data, pending, drop=(), renames=None):
    """The registry's bytes with these changes - only the lines concerned,
    so that comments and the layout of the file stay:
    drop     {(section, name)}: sections removed - the header, the keys and
             the lines between them; comments and blank lines after the
             last key stay (one may introduce the next section);
    renames  {(section, old name): new name}: only the name in the header
             changes;
    pending  {(section, name, key): value}: a value replaced in its line,
             a new key added after the section's last one, a new section
             appended; value None: the key's line removed.
    None if the file isn't laid out simply enough for that (a section or
    key twice, keys on the header line, an unclosed quote)."""
    renames = renames or {}
    lines = data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        lines[-1] += b"\n"
    headers, keys, last = {}, {}, {}   # section -> its line; (section, key) -> line;
    sect = None                        # section -> its last key line
    for i, raw in enumerate(lines):
        eol = raw[len(raw.rstrip(b"\r\n")):]
        line = raw[:len(raw) - len(eol)].decode("utf-8", "replace")
        m = HEADER_RX.fullmatch(line)
        if m:
            old = (m.group(2).lower(), re.sub(r"\\(.)", r"\1", m.group(4)))
            name = (old[0], renames.get(old, old[1]))
            if name in headers:
                return None
            if name != old:
                lines[i] = (m.group(1) + m.group(2) + m.group(3) + quoted_name(name[1])
                            + m.group(5)).encode() + eol
            headers[name], sect = i, name
            continue
        if re.match(r"\s*\[", line):
            if not re.fullmatch(r"\s*\[[^\]]*\]\s*(?:[#;].*)?", line):
                return None              # keys on the header line (or not understood)
            headers[(None, i)] = i
            sect = None
            continue
        if not line.strip() or re.match(r"\s*[#;]", line) or sect is None:
            continue
        m = KEY_RX.fullmatch(line)
        if not m or (sect, m.group(2).lower()) in keys:
            return None
        keys[(sect, m.group(2).lower())] = i
        last[sect] = i
    if any((s, new) not in headers for (s, _), new in renames.items()):
        return None
    dropped = set()
    for name in drop:
        if name not in headers:
            return None
        dropped.update(range(headers[name], last.get(name, headers[name]) + 1))
    after, appended = {}, {}
    for (s, n, k), v in pending.items():
        sec = (s, n)
        if v is None:
            if sec not in drop and (sec, k) in keys:
                dropped.add(keys[(sec, k)])
            continue
        if sec in drop or sec not in headers:          # (again) a new section
            appended.setdefault(sec, []).append(f"\t{k} = {config_value(v)}\n".encode())
        elif (sec, k) in keys:
            i = keys[(sec, k)]
            eol = lines[i][len(lines[i].rstrip(b"\r\n")):]
            new = replace_value(lines[i][:len(lines[i]) - len(eol)].decode("utf-8", "replace"), v)
            if new is None:
                return None
            lines[i] = new.encode() + eol
        else:
            after.setdefault(last.get(sec, headers[sec]), []).append(
                f"\t{k} = {config_value(v)}\n".encode())
    out_lines = []
    for i, raw in enumerate(lines):
        if i not in dropped:
            out_lines.append(raw)
        out_lines += after.get(i, [])     # also after a removed last key
    for (s, n), texts in appended.items():
        out_lines.append(f"[{s} {quoted_name(n)}]\n".encode())
        out_lines += texts
    return b"".join(out_lines)


def parse_registry(raw):
    """({source: {key: value}}, {file: {key: value}}, {dir: {key: value}})
    from `git config --list -z`."""
    sections = {"source": {}, "file": {}, "dir": {}}
    for item in raw.decode("utf-8", "replace").split("\0"):
        if not item:
            continue
        key, has_val, val = item.partition("\n")
        if not has_val:
            val = "true"     # a key without '= value' is a boolean true in git config
        sect, _, rest = key.partition(".")
        sub, _, name = rest.rpartition(".")
        if sect in sections and sub:
            sections[sect].setdefault(sub, {})[name] = val
    return sections["source"], sections["file"], sections["dir"]


def is_tag_pattern(tag):
    """A tag with * ? or [ is a pattern (like fnmatch): the newest matching
    tag on the source's branch counts."""
    return bool(re.search(r"[*?\[]", tag))


def entry_ref(source, entry):
    """('branch' | 'tag', name) a [file] entry is synced to: its own tag if
    it is pinned, else the branch of its [source]; None if the source has no
    branch (a pinned file needs it too: newer tags are looked for there)."""
    if not source.get("branch"):
        return None
    return ("tag", entry["tag"]) if entry.get("tag") else ("branch", source["branch"])


def warn_tag_line(src, tag, branch):
    """add/set --tag: a warning if the tag isn't on the branch, where newer
    tags are looked for (a pattern is matched on it anyway)."""
    if not src.tag_names:
        _, problem = src.tag_info(tag, branch, newer=False)
        if problem:
            warn(f"{problem}; newer tags can't be found there")


def ref_missing(ref, src):
    """Message for a branch or tag that doesn't exist upstream."""
    return f"{ref[0]} '{ref[1]}' not found in {src.label}"


def ref_text(ref, line=None, names=None):
    """'main' / 'tag v1.2' / 'tag v1.2 on main' - how a link's ref is shown;
    names: the tags a pattern matches now ('tag v1.* = v1.4 on main')."""
    if ref[0] != "tag":
        return ref[1]
    return f"tag {ref[1]}" + (f" = {' = '.join(names)}" if names else "") + \
        (f" on {line}" if line else "")


def and_list(items):
    items = list(items)
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else "".join(items)


def newest_text(newest, line=None):
    """'v1.4' / 'v1.4 on main' / 'v1.2.1 on maint; v1.4 on main' - newer tags
    of a pinned source (see Source.newer_tags); tags on the same commit are
    joined by ' = '. With a line the branch goes without saying."""
    return "; ".join(" = ".join(tags) + ("" if line else f" on {and_list(branches)}")
                     for tags, branches in newest)


def path_problem(rel):
    """Why rel can't be a linked file, None if it can. Entries come from a
    committed file, possibly written by others: a pull must never write
    outside the working tree or into a .git directory."""
    parts = re.split(r"[/\\]", rel)
    if not rel or "\n" in rel or PureWindowsPath(rel).anchor or ".." in parts:
        return "not a path inside the working tree"
    if any(p in ("", ".") for p in parts):
        return "not a normalized path"
    if any(p.lower().rstrip(". ") == ".git" for p in parts):
        return "inside a .git directory"
    if rel == REGISTRY:
        return f"{REGISTRY} itself"
    return None


def in_the_way(top, rel):
    """Why the working tree can't have a file at rel now, None if it can:
    something other than a file there, or a parent that is a file or a
    symbolic link. git would delete what is in the way when writing the
    file (also a directory, with all in it), or write it elsewhere."""
    parts = rel.split("/")
    for i in range(1, len(parts)):
        p = top.joinpath(*parts[:i])
        if p.is_symlink():
            return f"beyond a symbolic link '{'/'.join(parts[:i])}'"
        if not p.exists():
            return None
        if not p.is_dir():
            return f"'{'/'.join(parts[:i])}' is a file, not a directory"
    p = top / rel
    if p.is_dir():
        return "is a directory, not a file"
    if p.exists() and not p.is_file():
        return "is not a regular file"
    return None


def blocked_text(repo, rel, blocked):
    """The error for a linked file that something is in the way of (see in_the_way)."""
    return (f"{blocked} - move it away, or remove the link with "
            f"'git filesync unlink {path_arg(repo, rel)}'")


def is_below(rel, d):
    """Is rel the directory d or below it ('.' = the root)?"""
    return d == "." or rel == d or rel.startswith(d + "/")


def join_rel(d, below):
    """Path of below in directory d of this repository ('.' = the root)."""
    return below if d == "." else f"{d}/{below}"


def registry_path(repo):
    """.git-filesync - refused if it is a symlink: it comes from a commit,
    possibly made by others, and is written to (also: as git writes it)."""
    path = repo.top / REGISTRY
    if path.is_symlink():
        raise FsError(f"{REGISTRY} is a symbolic link - refused (it must be a file)")
    return path


def registry_rows(repo):
    """The index's rows ('mode id stage\\tpath') of .git-filesync, asked
    once until it is staged - an error if it has a merge conflict: its
    layers can't be told apart then."""
    if repo.rows is None:
        p = repo.git(["ls-files", "-s", "-z", "--", lit(REGISTRY)], check=False)
        repo.rows = [r for r in p.stdout.decode("utf-8", "replace").split("\0") if r]
    rows = repo.rows
    if any(r.split()[2] != "0" for r in rows):
        raise FsError(conflict_text(repo))
    return rows


def conflict_text(repo):
    """The error for a merge conflict in .git-filesync: how to resolve it."""
    if not registry_path(repo).exists():      # deleted on one side
        return (f"{REGISTRY} has a merge conflict, deleted on one side - resolve it with "
                f"'git rm {REGISTRY}', or keep it with 'git checkout --theirs {REGISTRY}' "
                "(or --ours) and 'git filesync edit'")
    return (f"{REGISTRY} has a merge conflict - resolve it with 'git filesync edit' "
            f"(or by hand, then 'git add {REGISTRY}')")


def write_registry(path, original, pending, drop, renames, expected):
    """Write the registry file at path: original (bytes) with these changes
    (see edit_registry), editing only the lines concerned - checked by
    reading it back with git, which must give exactly expected (as
    parse_registry); otherwise (an unusual layout) the changes one by one
    with git config."""
    edited = edit_registry(original, pending, drop, renames)
    if edited is not None:
        path.write_bytes(edited)
        p = git(["config", "-f", path, "--list", "-z"], check=False)
        if p.returncode == 0 and same_registry(parse_registry(p.stdout), expected):
            return
    path.write_bytes(original)
    for sect, name in sorted(drop):
        git(["config", "-f", path, "--remove-section", f"{sect}.{name}"])
    for (sect, old), new in renames.items():
        git(["config", "-f", path, "--rename-section", f"{sect}.{old}", f"{sect}.{new}"])
    for (sect, name, k), v in pending.items():
        git(["config", "-f", path] + ([f"{sect}.{name}.{k}", v] if v is not None
                                      else ["--unset-all", f"{sect}.{name}.{k}"]),
            check=v is not None)


def same_registry(a, b):
    """Do two registries ((sources, files, dirs), as parse_registry) have the
    same sections and values? A section without keys counts as none."""
    return all({n: v for n, v in x.items() if v} == {n: v for n, v in y.items() if v}
               for x, y in zip(a, b))


def staged_as_base(repo, reg, rel, oid):
    """Has the index the file (oid: its blob id there, None: none) of the
    synced [file] entry rel as its base - in this repository's form (see
    matches_base), or the file HEAD has for an entry with the same base
    (moved with git mv, see moved_in_head)? Then staging the entry keeps
    the index consistent. A [dir] entry: no (its base isn't looked at)."""
    link = reg.files.get(rel)
    if not link or not oid:
        return False
    e = reg.entry(rel)
    if oid == link.get("blob") or moved_in_head(repo, e, sync_keys(link), oid):
        return True
    src = layer_source(repo, None, e, e) if e.blob else None
    try:
        return src is not None and matches_base(repo, src, rel, e.blob, e.path, oid,
                                                lambda: repo.read_blob(oid))
    except FsError:
        return False


def section_changes(sect, name, was, now):
    """{(sect, name, key): value (None: removed)} - the changes (see
    edit_registry) that make a section with the keys was one with now."""
    return {(sect, name, k): now.get(k) for k in list(now) + [k for k in was if k not in now]
            if now.get(k) != was.get(k)}


def registry_model(reg):
    """{section: {name: {key: value}}} of a Registry, a copy to change (see
    apply_changes)."""
    return {"source": {n: dict(v) for n, v in reg.sources.items()},
            "file": {n: dict(v) for n, v in reg.files.items()},
            "dir": {n: dict(v) for n, v in reg.dirs.items()}}


def apply_changes(model, pending, drop, renames):
    """Change a registry_model() as edit_registry() changes the file."""
    for (s, old), new in renames.items():
        model[s][new] = model[s].pop(old)
    for s, n in drop:
        model[s].pop(n, None)
    for (s, n, k), v in pending.items():
        if v is None:
            model[s].get(n, {}).pop(k, None)
        else:
            model[s].setdefault(n, {})[k] = v


def write_staged(repo, batches):
    """Apply changes [(pending, drop, renames)] (see edit_registry) to the
    staged .git-filesync - only the lines concerned, so that its comments
    and layout stay; all at once, but renames in a batch of their own (see
    Registry._rename). Stored as `git add` would store such a file; removed
    from the index when nothing of ours is left in it. Returns whether the
    index changed (batches may cancel out)."""
    if not batches:
        return False
    rows = registry_rows(repo)
    mode, oid = rows[0].split()[:2] if rows else ("100644", None)
    have = registry_model(repo.registry("index"))
    merged = []               # [pending, drop, renames, expected, sections before]
    for pending, drop, renames in batches:
        prior = {(s, n) for s in have for n in have[s]}
        apply_changes(have, pending, drop, renames)
        expected = tuple({n: dict(v) for n, v in have[s].items()} for s in have)
        if renames or not merged or merged[-1][2]:
            merged.append([dict(pending), set(drop), dict(renames), expected, prior])
            continue
        last = merged[-1]
        last[0] = {k: v for k, v in last[0].items() if k[:2] not in drop}
        last[0].update(pending)
        last[1] |= drop & last[4]     # one new in the batch: only its values go
        last[3] = expected
    repo.layers.pop("index", None)        # read again when asked
    repo.rows = None
    with tempfile.TemporaryDirectory(prefix="git-filesync-") as td:
        path = Path(td) / "registry"
        data = repo.read_blob(oid) if oid else REGISTRY_HEADER.encode()
        for pending, drop, renames, expected, _ in merged:
            write_registry(path, data, pending, drop, renames, expected)
            data = path.read_bytes()
    if not any(v for store in have.values() for v in store.values()):
        if oid:
            repo.git(["update-index", "--force-remove", "--", REGISTRY])
        return bool(oid)
    # as `git add` stores it (its line ends, LF here, as on a checkin)
    new = out(repo.git(["hash-object", "-w", f"--path={REGISTRY}", "--stdin"],
                       data=data.replace(b"\r\n", b"\n")))
    if new == oid:
        return False
    repo.git(["update-index", "--add", "--cacheinfo", f"{mode},{new},{REGISTRY}"])
    return True


def is_synced(values):
    """Has an entry (its keys) a base - commit and blob or tree?"""
    return bool(values.get("commit") or values.get("blob") or values.get("tree"))


class Registry:
    """The repository's .git-filesync: [source], [file] and [dir] sections.
    HEAD, the index and the working tree each have one (layer); commands
    change that of the working tree and stage what they changed (see
    stage)."""

    def __init__(self, repo, layer=None):
        """layer: 'head' or 'index' - the file as HEAD or the index has it,
        only read (empty if none there); else that of the working tree
        (refused while the index has a merge conflict in it)."""
        self.repo = repo
        self.path = registry_path(repo)
        self.sources, self.files, self.dirs = {}, {}, {}
        self.dry_run = bool(layer)    # only change the in-memory state
        # written later, all at once (see flush): pull, add, rm, unlink and
        # set change many entries
        self._pending = {}        # ("file" | "dir" | "source", name, key) -> value, see _set
        self._drop = set()        # (section, name): sections to remove, see remove_file
        self._renames = {}        # (section, old name) -> new name, see _rename
        self.done = []            # what flush wrote, for stage(): [(pending, drop, renames)]
        self.whole = set()        # entries pulled or added: staged whole (see stage)
        # (section, name) -> {key: value}: sync keys the index's entry gets
        # instead of those changed here (see keep_base)
        self.staged_own = {}
        if layer:
            rows = registry_rows(repo) if layer == "index" else None
            if rows == []:
                return            # none in the index
            blob = rows[0].split()[1] if rows else f"HEAD:{REGISTRY}"
            p = repo.git(["config", "--blob", blob, "--list", "-z"], check=False)
            if p.returncode:
                if repo.git(["cat-file", "-e", blob], check=False).returncode:
                    return            # none there (or no HEAD)
                raise FsError(f"{REGISTRY} {'in HEAD' if layer == 'head' else 'as staged'}: "
                              "cannot parse: " + p.stderr.decode("utf-8", "replace").strip()
                              + ("" if layer == "head" else " - fix it with 'git filesync edit'"))
            self.sources, self.files, self.dirs = parse_registry(p.stdout)
            return
        registry_rows(repo)
        if self.path.exists():
            p = git(["config", "-f", self.path, "--list", "-z"], check=False)
            if p.returncode:
                raise FsError(f"{REGISTRY}: cannot parse: "
                              + p.stderr.decode("utf-8", "replace").strip())
            self.sources, self.files, self.dirs = parse_registry(p.stdout)

    def links(self):
        """All entries, [file] and [dir], by path."""
        return sorted([Link(self, rel) for rel in self.files]
                      + [DirLink(self, rel) for rel in self.dirs], key=lambda lk: lk.rel)

    def entry(self, rel):
        """The [file] or [dir] entry for rel, None if there is none."""
        return Link(self, rel) if rel in self.files else \
            DirLink(self, rel) if rel in self.dirs else None

    def store(self, sect):
        return {"file": self.files, "dir": self.dirs, "source": self.sources}[sect]

    def uses(self, name):
        """Rels of the entries ([file] and [dir]) of the [source] name."""
        return sorted(rel for store in (self.files, self.dirs)
                      for rel, v in store.items() if v.get("source") == name)

    def overlapping(self, rel, kind):
        """Entries other than rel that overlap with an entry at rel of this
        kind ('file' | 'dir'): a [dir] holds everything below it, so no
        other entry may be there - nor a [dir] above any entry."""
        others = [r for r in self.files if is_below(r, rel)] if kind == "dir" else []
        others += [d + "/" for d in self.dirs if (d, "dir") != (rel, kind)
                   and (is_below(rel, d) or kind == "dir" and is_below(d, rel))]
        return sorted(others)

    def _set(self, sect, name, key, value):
        """Set (value None: remove) a key of a [file], [dir] or [source] -
        written later (see flush)."""
        store = self.store(sect)
        if value is None:
            if key not in store.get(name, {}):
                return
            del store[name][key]
        else:
            store.setdefault(name, {})[key] = value
        if not self.dry_run:
            self._pending[(sect, name, key)] = value

    def set_file(self, rel, key, value):
        self._set("file", rel, key, value)

    def find_source(self, url, branch, exclude=None):
        """Key of a [source] with url and branch, None if there is none."""
        for name, s in self.sources.items():
            if name != exclude and norm_url(s.get("url", "")) == norm_url(url) \
                    and s.get("branch") == branch:
                return name
        return None

    def new_source_name(self, url):
        """Unused key for a new [source]: 'owner/repo' derived from the URL,
        with a number appended if that key already belongs to another source."""
        base = repo_label(url) or "upstream"
        name, n = base, 2
        while name in self.sources:
            name, n = f"{base}-{n}", n + 1
        return name

    def source_name(self, url, branch):
        """Key of the [source] for url and branch (found by URL, not by key),
        or the key a new one would get."""
        return self.find_source(url, branch) or self.new_source_name(url)

    def add_source(self, url, branch):
        """Key of the [source] for url and branch, created if necessary."""
        found = self.find_source(url, branch)
        if found:
            return found
        name = self.new_source_name(url)
        self._set("source", name, "url", url)
        self._set("source", name, "branch", branch)
        return name

    def set_source(self, name, key, value):
        self._set("source", name, key, value)

    def remove_source(self, name):
        self._remove_section("source", name)
        del self.sources[name]

    def rename_source(self, old, new):
        self._rename("source", old, new)
        for sect in ("file", "dir"):
            for rel, f in self.store(sect).items():
                if f.get("source") == old:
                    self._set(sect, rel, "source", new)

    def kind(self, rel):
        """'file' or 'dir': the section of the entry rel."""
        return "file" if rel in self.files or rel not in self.dirs else "dir"

    def remove_file(self, rel, keep_source=None):
        """Remove a [file] or [dir]; its [source] too when no other entry
        uses it (unless it is keep_source). Removed later, all at once (see
        flush) - rm and unlink remove many."""
        sect = self.kind(rel)
        src = self.store(sect).pop(rel, {}).get("source")
        self._remove_section(sect, rel)
        if src and src != keep_source and src in self.sources and not self.uses(src):
            self.remove_source(src)

    def _remove_section(self, sect, name):
        if self.dry_run:
            return
        # values set before are gone with it
        self._pending = {k: v for k, v in self._pending.items() if k[:2] != (sect, name)}
        self._drop.add((sect, name))

    def _rename(self, sect, old, new):
        """Rename a section: only the name in its header changes."""
        self.flush()              # what is pending still goes by the old name
        store = self.store(sect)
        store[new] = store.pop(old)
        if not self.dry_run:
            self._renames[(sect, old)] = new
            self.flush()

    def rename_file(self, old, new):
        self._rename(self.kind(old), old, new)

    def flush(self):
        """Write what is pending - removed and renamed sections, values (see
        remove_file, _rename, _set) - at once, editing only the lines
        concerned (see edit_registry) instead of one `git config` for each -
        checked by reading it back with git, which must give exactly the
        state here; otherwise (an unusual layout of the file) one by one
        with git. Removals first: a value pending for a removed section was
        set after the removal. Noted for stage()."""
        pending, drop, renames = self._pending, self._drop, self._renames
        self._pending, self._drop, self._renames = {}, set(), {}
        if not (pending or drop or renames):
            return
        self.done.append((pending, drop, renames))
        original = self.path.read_bytes() if self.path.exists() \
            else REGISTRY_HEADER.encode()
        write_registry(self.path, original, pending, drop, renames,
                       (self.sources, self.files, self.dirs))

    def finish(self, stage=True):
        """Write the registry (removed when empty) with the line endings of a
        checkout, and stage what this run changed in it (see stage).
        Returns whether something was staged."""
        self.flush()
        if self.path.exists():
            if not self.sources and not self.files and not self.dirs:
                self.path.unlink()
            else:
                self.repo.fix_eol(self.path)
        if stage:
            return self.stage()
        self.done, self.whole, self.staged_own = [], set(), {}
        return False

    def stage(self):
        """Stage what this run changed (R2): the same changes in the staged
        registry - not the whole file. An entry pulled or added (self.whole)
        is staged as a whole, as they used it, with its [source]: the commit
        describes what its files come from (changes made by hand to it go
        along). Another synced entry the index hasn't comes only with its
        file (see staged_as_base), then whole as well; else a change of it
        stays unstaged. A new link (no base) the index hasn't comes whole.
        Each staged entry has its [source] there; one goes only when no
        staged entry uses it, and one new there only for entries not staged
        isn't staged either. So changes made by hand, and what is only in the working
        tree (pull -W, add -W), stay unstaged. Comments and layout of the
        staged registry stay; it is stored as `git add` would store such a
        file, and removed when nothing of ours is left in it."""
        done, self.done = self.done, []
        whole, self.whole = {r for r in self.whole if self.entry(r)}, set()
        own, self.staged_own = self.staged_own, {}
        if not done and not whole:
            return False
        repo = self.repo
        have = registry_model(repo.registry("index"))
        before = {s: set(have[s]) for s in have}
        used_before = {v.get("source") for s in ("file", "dir") for v in have[s].values()}
        batches, dropped = [], set()

        def apply(pending, drop, renames):
            """Add a change to the staged registry (as for edit_registry)."""
            apply_changes(have, pending, drop, renames)
            batches.append((pending, drop, renames))

        def copy(s, n):
            """A section as the working tree has it."""
            return section_changes(s, n, have[s].get(n, {}), self.store(s).get(n, {}))

        mine = {(self.kind(r), r) for r in whole}
        without = set()           # synced entries whose file the index hasn't
        # (the index's files of the entries it hasn't, asked at once)
        asked = sorted({n for pending, _, _ in done for s, n, _ in pending
                        if s == "file" and n not in have[s] and (s, n) not in mine
                        and is_synced(self.files.get(n, {}))})
        index = {r: e[1] for r, e in repo.index_entries(asked).items()} if asked else {}
        for pending, drop, renames in done:
            p2, d2, r2 = {}, set(), {}
            for (s, old), new in renames.items():
                if old in have[s] and new not in have[s]:
                    r2[(s, old)] = new
                    if s == "source":     # all staged entries of it follow, also others
                        p2.update(((k, n, "source"), new) for k in ("file", "dir")
                                  for n, v in have[k].items() if v.get("source") == old)
            for s, n in drop:
                if n in have[s] and (s, n) not in mine:
                    if s == "source":
                        dropped.add(n)    # unless a staged entry uses it
                    else:
                        d2.add((s, n))
            for (s, n, k), v in pending.items():
                if (s, n) in mine or v is None and k not in have[s].get(n, {}) or \
                        (s, n) in own and k in SYNC_KEYS:
                    continue
                if s != "source" and n not in have[s] and n in self.store(s):
                    # an entry the index hasn't: whole - a synced one only with
                    # its file (asked once), a new link as it is
                    if not is_synced(self.store(s)[n]) or \
                            (s, n) not in without and staged_as_base(repo, self, n,
                                                                    index.get(n)):
                        mine.add((s, n))
                    else:
                        without.add((s, n))
                    continue
                p2[(s, n, k)] = v
            if p2 or d2 or r2:
                apply(p2, d2, r2)
        own = {(s, n, k): v for (s, n), vs in sorted(own.items()) if n in have[s]
               for k, v in vs.items() if have[s][n].get(k) != v}
        if own:
            apply(own, set(), {})
        # the entries staged as a whole, after their [source]
        for s, n in sorted(mine, key=lambda x: x[1]):
            src = self.store(s).get(n, {}).get("source")
            changes = copy("source", src) if src in self.sources else {}
            changes.update(copy(s, n))
            if changes:
                apply(changes, set(), {})
        # what the staged entries use is there; what they don't use may go
        used = {v["source"] for s in ("file", "dir") for v in have[s].values() if v.get("source")}
        need = {}
        for n in sorted(used - set(have["source"])):
            if n in self.sources:
                need.update(copy("source", n))
        # (one goes that this run dropped, made unused, or that is new there)
        gone = {("source", n) for n in have["source"] if n not in used and
                (n in dropped or n in used_before or n not in before["source"])}
        if need or gone:
            apply(need, gone, {})
        return write_staged(repo, batches)


class Link:
    """One [file] entry: a file linked to a file in an upstream repository.
    values: the entry's keys (one not written yet), instead of those in the
    registry."""

    def __init__(self, reg, rel, values=None):
        self.reg, self.rel, self.values = reg, rel, values

    @property
    def v(self):
        return self.values if self.values is not None else self.reg.files.get(self.rel, {})

    @property
    def target(self):
        problem = path_problem(self.rel)
        if problem:
            raise FsError(f"'{self.rel}' in {REGISTRY}: {problem}")
        blocked = in_the_way(self.reg.repo.top, self.rel)
        if blocked:
            raise FsError(f"{self.rel}: {blocked_text(self.reg.repo, self.rel, blocked)}")
        return self.reg.repo.top / self.rel

    @property
    def source(self):
        return self.reg.sources.get(self.name, {})

    name = property(lambda self: self.v.get("source", ""))   # key of the [source]
    url = property(lambda self: self.source.get("url", ""))
    tag = property(lambda self: self.v.get("tag", ""))        # pinned to it (or a pattern)
    ref = property(lambda self: entry_ref(self.source, self.v))   # ('branch' | 'tag', name)
    # a pinned file: the branch of its source, where newer tags (or those
    # matching a pattern) are looked for
    line = property(lambda self: self.source.get("branch") if self.tag else None)
    path = property(lambda self: self.v.get("path", ""))
    commit = property(lambda self: self.v.get("commit", ""))
    blob = property(lambda self: self.v.get("blob", ""))

    @property
    def unsynced(self):
        """A new link, never synced: no base (commit and blob) yet - written
        by hand, e.g. many at once; pull does the first sync, as add would."""
        return not self.commit and not self.blob

    @property
    def adaptable(self):
        """Local adaptations allowed; otherwise the file must stay an exact
        copy of the upstream version (the default)."""
        return self.v.get("adaptable", "").lower() in ("true", "yes", "on", "1")

    def set(self, name, value):
        self.reg.set_file(self.rel, name, value)

    is_dir = False
    shown_rel = property(lambda self: self.rel)       # rel as shown: 'src/' for a [dir]
    only = None       # a [dir] selected by some of its files: their paths (see select_links)


def up_join(path, below):
    """Upstream path of below in the upstream directory path ('' = the root)."""
    return f"{path}/{below}" if path else below


PATTERN_KEYS = ("include", "exclude")


def split_patterns(value):
    """The patterns of an include / exclude value: separated by blanks,
    quoted like in a shell ('*.c' 'my file'; git config itself removes
    "..." before)."""
    try:
        return shlex.split(value)
    except ValueError as e:
        raise FsError(f"cannot read the patterns '{value}': {e}")


def join_patterns(patterns):
    """The value of include / exclude for these patterns (see split_patterns):
    like shlex.join (Python 3.8+), as in git-assetsync."""
    return " ".join(shlex.quote(p) for p in patterns) or None


class DirLink(Link):
    """One [dir] entry: a directory here that holds the files of an upstream
    directory - those its include / exclude patterns select. The base is the
    upstream tree (tree, at commit): the files it lists are the entry's
    files (see Member); all others below the directory are this
    repository's own, which no command touches. values: the entry's keys
    (one not written yet), instead of those in the registry."""
    is_dir = True
    shown_rel = property(lambda self: self.rel.rstrip("/") + "/")

    @property
    def v(self):
        return self.values if self.values is not None else self.reg.dirs.get(self.rel, {})

    def set(self, name, value):
        self.reg._set("dir", self.rel, name, value)

    path = property(lambda self: upstream_path(self.v.get("path", "")))   # '' = the root
    tree = property(lambda self: self.v.get("tree", ""))
    blob = tree
    include = property(lambda self: split_patterns(self.v.get("include", "")))
    exclude = property(lambda self: split_patterns(self.v.get("exclude", "")))
    # set changed the patterns since the sync (see synced_patterns)
    repatterned = property(lambda self: any(f"synced-{k}" in self.v for k in PATTERN_KEYS))

    def synced_patterns(self, k):
        """The patterns (k: 'include' | 'exclude') the entry was synced with,
        which select the files at its base: synced-<k>, which set keeps
        while new ones select other files - until the next pull; else <k>."""
        return split_patterns(self.v.get(f"synced-{k}", self.v.get(k, "")))

    def drop_synced(self):
        """The base now has the current patterns (pull, set -p)."""
        for k in PATTERN_KEYS:
            self.set(f"synced-{k}", None)

    @property
    def unsynced(self):
        return not self.commit and not self.tree

    @property
    def target(self):
        problem = path_problem(self.rel) if self.rel != "." else None
        if problem:
            raise FsError(f"'{self.rel}' in {REGISTRY}: {problem}")
        blocked = in_the_way(self.reg.repo.top, self.rel) if self.rel != "." else None
        if blocked and blocked != "is a directory, not a file":
            raise FsError(f"{self.shown_rel}: {blocked_text(self.reg.repo, self.rel, blocked)}")
        return self.reg.repo.top / self.rel

    def selects(self, below, base=False):
        """Is the upstream file below (relative to the upstream directory)
        one of the entry's, by its patterns (like add DIR, see glob_regex)?
        base: by those it was synced with (see synced_patterns)."""
        if not hasattr(self, "_rx"):
            self._rx = {}
        if base not in self._rx:
            self._rx[base] = [[glob_regex(p) for p in (self.synced_patterns(k) if base
                                                      else getattr(self, k))]
                              for k in PATTERN_KEYS]
        inc, exc = self._rx[base]
        return (not inc or any(r.match(below) for r in inc)) and \
            not any(r.match(below) for r in exc)

    def check_patterns(self):
        """FsError if a pattern can't be read."""
        self.selects("")
        self.selects("", base=True)

    def member(self, below, blob=""):
        return Member(self, below, blob)


class Member(Link):
    """A file of a [dir] entry, as a link of its own: what evaluate(), pull,
    diff and restore do with a linked file applies to it. Its base (blob)
    comes from the entry's upstream tree; without one (blob ''), it is new
    to the entry - like a new link, its first sync compares it with
    upstream (see first_sync)."""

    def __init__(self, dlink, below, blob):
        super().__init__(dlink.reg, join_rel(dlink.rel, below))
        self.dlink, self.below, self._blob = dlink, below, blob

    @property
    def v(self):
        d = self.dlink
        return {"source": d.name, "path": up_join(d.path, self.below), "commit": d.commit,
                "blob": self._blob, "tag": d.tag, "adaptable": d.v.get("adaptable", "")}

    @property
    def unsynced(self):
        return not self._blob

    def set(self, name, value):
        pass                      # the [dir] entry records the base


def select_links(repo, reg, paths, whole=False):
    """Entries for the given files/directories (all entries if none given).
    A file of a [dir] entry (or a directory in it) selects that entry, its
    `only` naming which of its files; whole: for commands that change the
    entry (pull, set, rm, unlink), which take whole entries only."""
    if not paths:
        return reg.links()
    found = {}
    for s in paths:
        rel = repo.rel(repo.user_path(s))
        lk = reg.entry(rel)
        if lk:
            found[rel] = lk
            lk.only = None
            continue
        inside = [d for d in reg.dirs if is_below(rel, d)]
        if inside:
            d = inside[0]
            if whole:
                raise FsError(f"'{rel}' is in the linked directory '{shown(repo, d)}/' - "
                              f"give '{shown(repo, d)}' (the whole entry)")
            if d not in found:
                found[d] = DirLink(reg, d)
                found[d].only = []
            if found[d].only is not None:
                found[d].only.append(rel)
            continue
        under = [lk for lk in reg.links() if rel == "." or lk.rel.startswith(rel + "/")]
        if not under:
            raise FsError(f"'{rel}' is not linked (use 'git filesync add' to link it)")
        for lk in under:
            found.setdefault(lk.rel, lk).only = None
    return sorted(found.values(), key=lambda lk: lk.rel)


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

class BaseUnavailable(FsError):
    pass


def matches_base(repo, src, rel, blob, path, oid, read):
    """Does a blob of this repo (id oid; read() returns its raw bytes) equal
    the upstream version blob of path - the base of the file rel? Raises
    BaseUnavailable if that version can't be read."""
    if oid == blob:
        return True
    if not blob:
        return False
    if repo.is_plain(rel) and src.is_plain(blob):
        # LF-only content without filters here: a checkout and checkin leave
        # it as it is, so only the very same blob matches (no git calls)
        return False
    try:
        ptr = lfs_pointer(src.read_blob(blob))
        if ptr:   # upstream stores it in LFS: compare against the pointer's hash first
            data = read()
            if (hashlib.sha256(data).hexdigest(), len(data)) == ptr or lfs_pointer(data) == ptr:
                return True
        return oid == repo.as_local(src.read_content(blob, path), rel)
    except BaseUnavailable:
        raise
    except FsError as e:
        raise BaseUnavailable(f"synced version {blob[:12]} not available in "
                              f"{src.label}, file counts as modified ({e})")


@dataclass
class FileState:
    """What evaluate() finds out about a linked file."""
    link: object
    rel: str
    old: str                  # synced upstream commit and blob (the base)
    old_blob: str
    new_path: str             # upstream path, the new one if renamed there
    adaptable: bool           # local adaptations allowed (else: an exact copy)
    unsynced: bool = False    # a new link, no base yet (see Link.unsynced)
    error: Optional[str] = None
    warnings: list = field(default_factory=list)
    src: object = None        # Source of the upstream repository
    new: Optional[str] = None  # upstream commit and blob a pull would sync to
    new_blob: Optional[str] = None
    count_args: tuple = ()    # Source.count(*count_args): upstream commits touching
    behind_args: tuple = ()   # the file since the sync, or by how many the branch
                              # went back - counted only when shown (see count)
    has_old: bool = False     # synced commit exists upstream
    lost_old: bool = False    # it doesn't: behind, or history rewritten? (no guess)
    discards: tuple = ((), ())  # a first sync: (working tree, index) paths it overwrites
    staged: bool = False      # the index differs from HEAD: uncommitted changes too
    diverged: bool = False
    moved: Optional[tuple] = None   # ('renamed' | 'deleted', path, commit)
    newest: Optional[list] = None   # newer tags of a pinned source
    committed: Optional[str] = None  # see evaluate()
    worktree: str = "clean"
    local: str = "clean"
    head_blob: Optional[str] = None
    # the layers (R1): the entries in HEAD and the index (None: none there),
    # the staged file (None: none), what the index has that HEAD hasn't and the
    # working tree that the index hasn't (see layer_code), adapted in the index
    entries: tuple = (None, None)
    index_blob: Optional[str] = None
    staged_code: Optional[str] = None
    unstaged_code: Optional[str] = None
    index_adapted: bool = False
    own: tuple = ()           # all layers with a modification of their own (where: the first)
    head_base: Optional[tuple] = None   # HEAD's other base: see head_base()
    bases: tuple = (None, None)   # (blob, upstream path, Source) of the bases in HEAD, the index
    changed: bool = False     # upstream version differs from the base
    pending: bool = False     # something for pull to do
    violation: bool = False   # modified, but not adaptable
    once: Optional[str] = None  # pull --commit/-b/--tag: what is synced to, once
    target: Optional[str] = None    # ... and its revision
    members: list = field(default_factory=list)   # a [dir]: FileStates of its files, at
                                                  # the base and new upstream (DirState)
    base_members = property(lambda self: [m for m in self.members if not m.unsynced])
    # where a modification of its own is (R3: 'index' | 'worktree' | None)
    where = property(lambda self: self.own[0] if self.own else None)

    @property
    def missing(self):
        """The linked file is not in the working tree - never allowed, also
        for an adaptable file: restore it, or remove the link."""
        return self.local == "missing" and not self.error and not self.unsynced

    @property
    def off_track(self):
        """Not a plain update along the history of the branch or tag: older
        than the last sync, history diverged, or the previous sync point
        unknown. pull --all leaves it out; only pull FILE syncs it."""
        return self.lost_old or bool(self.behind_args) or self.diverged

    @property
    def attention(self):
        """Something to report (status --exit-code, hooks)."""
        return bool(self.error or self.pending or self.violation or self.missing)


def synced_label(st):
    """The synced version, as shown: its commit (abbreviated), or the blob
    if the commit isn't known upstream."""
    return st.src.short(st.old) if st.has_old else st.old_blob[:8]


def commits_since(st):
    """Upstream commits touching the file since the sync (see evaluate)."""
    return st.src.count(*st.count_args) if st.count_args else 0


def commits_behind(st):
    """By how many commits touching the file the branch went back."""
    return st.src.count(*st.behind_args) if st.behind_args else 0


def dir_links(ctx, dlink):
    """Member links of a [dir] entry for prefetch(): the files at its base
    and the new ones upstream; none if its source or base isn't there."""
    try:
        src = ctx.source(dlink.url, dlink.ref, dlink.name, dlink.line)
        tip = src.resolve()
        base = {} if dlink.unsynced else dir_base(src, dlink) or {}
        _, files = src.files_at(tip, dlink.path) if tip else (None, None)
        news = [b for b in files or {} if b not in base and dlink.selects(b)]
    except FsError:
        return []
    return [dlink.member(b, o) for b, o in base.items()] + [dlink.member(b) for b in news]


def prefetch(ctx, repo, links, new_links=False):
    """Ask git about many links at once - one command per repository and per
    source instead of several per file, which adds up (starting a process
    is slow on Windows). Only fills caches: evaluate() asks for whatever is
    missing, and reports the errors. new_links (pull): also what the first
    sync of new links compares their files with (see first_sync). A [dir]
    entry counts with its files (members): those at its base and the new
    ones upstream."""
    links = [m for lk in links for m in ([lk] + dir_links(ctx, lk) if lk.is_dir else [lk])]
    links = [lk for lk in links if lk.is_dir or not (
        path_problem(lk.rel) or in_the_way(repo.top, lk.rel))]
    repo.prefetch(lk.rel for lk in links)
    groups = {}
    for lk in links:
        if not (lk.url and lk.ref and lk.path):
            continue
        try:
            src = ctx.source(lk.url, lk.ref, lk.name, lk.line)
        except FsError:
            continue
        groups.setdefault(id(src), (src, []))[1].append(lk)
    for src, lks in groups.values():
        try:
            src.prefetch(lks)
        except FsError:
            pass
    # the base of each link - of a new one (new_links) the version its first
    # sync compares the file with
    bases = {}
    for src, lks in groups.values():
        tip = src.resolve() if new_links else None
        for lk in lks:
            bases[id(lk)] = lk.blob or (tip and src.blob_at(tip, lk.path)) or ""
    # files that differ from their base (adapted, uncommitted changes, not
    # committed yet): their blob ids, and can they be compared without git's
    # filters? (see matches_base)
    differ = [lk for lk in links if bases.get(id(lk)) and (
        repo._head.get(lk.rel) not in (None, bases[id(lk)]) or repo._dirty.get(lk.rel)
        or repo._head.get(lk.rel) is None and (repo.top / lk.rel).is_file())]
    if differ:
        try:
            repo.worktree_blobs([lk.rel for lk in differ if repo._head.get(lk.rel) is None
                                 or repo._dirty.get(lk.rel)])
        except FsError:
            pass
        repo.check_plain(lk.rel for lk in differ)
        ids = {id(lk) for lk in differ}
        items = []
        for src, lks in groups.values():
            mine = [lk for lk in lks if id(lk) in ids]
            try:
                src.check_plain(bases[id(lk)] for lk in mine)
                # those not comparable without git's filters: converted at once
                items += [(src.read_content(bases[id(lk)], lk.path), lk.rel) for lk in mine
                          if not (repo.is_plain(lk.rel) and src.is_plain(bases[id(lk)]))]
            except FsError:
                pass
        repo.as_local_many(items)
    # the bases of the entries in HEAD and the index whose files there differ
    # from them (see local_state; another upstream repository: not here)
    layers, staged = [], repo.staged()
    try:
        for src, lks in groups.values():
            for lk in lks:
                head = repo._head.get(lk.rel)
                for layer, oid in (("head", head), ("index", staged.get(lk.rel, head))):
                    e = layer_entry(repo, lk, layer)
                    if e is not None and not e.unsynced and e.blob != lk.blob and \
                            norm_url(e.url) == norm_url(lk.url) and oid not in (None, e.blob):
                        layers.append((src, e.blob, e.path, lk.rel))
    except FsError:               # (a registry that can't be read: reported by evaluate)
        layers = []
    if layers:
        repo.check_plain(r for _, _, _, r in layers)
        items = []
        for src, _ in groups.values():
            mine = [x for x in layers if x[0] is src]
            try:
                src.check_plain(b for _, b, _, _ in mine)
                items += [(src.read_content(b, p), r) for _, b, p, r in mine
                          if not (repo.is_plain(r) and src.is_plain(b))]
            except FsError:
                pass
        repo.as_local_many(items)


def source_problem(link):
    """Why the entry link has no usable source, None if it has one."""
    if link.source.get("tag"):
        return (f'tag in [source "{link.name}"] is no longer supported: pin the files '
                f"themselves ('tag' in each entry, with 'git filesync edit'), and give "
                "the source its branch")
    if not (link.url and link.ref and link.v.get("path")):
        return f"incomplete entry in {REGISTRY} (needs a source with url and branch, and path)"
    return None


def overlap_text(repo, link, others):
    """The error for an entry that overlaps with others (see Registry.overlapping)."""
    return (f"overlaps with the entry for {and_list(others)} - entries must not overlap; "
            f"remove one with 'git filesync unlink {path_arg(repo, link.rel)}'")


def blob_matcher(repo, src, rel, blob, path, st):
    """matches_base() for the file rel and the upstream version blob (at
    path); a version that can't be read counts as different - with a
    warning in st (the base of an entry in any layer)."""
    def matches(oid, read):
        try:
            return matches_base(repo, src, rel, blob, path, oid, read)
        except BaseUnavailable as e:
            if str(e) not in st.warnings:
                st.warnings.append(str(e))
            return False
    return matches


def base_matcher(repo, src, link, st):
    """matches_base() for the base of link (see blob_matcher)."""
    return blob_matcher(repo, src, link.rel, link.blob, link.path, st)


def layer_entry(repo, link, layer):
    """The entry at link's path in the registry of a layer below the working
    tree ('head', 'index'); None if that has none of its kind. FsError if it
    is incomplete there (e.g. its [source] missing)."""
    e = repo.registry(layer).entry(link.rel)
    if e is None or e.is_dir != link.is_dir:
        return None
    if not (e.url and e.ref and e.v.get("path")):
        where = "in HEAD" if layer == "head" else "as staged"
        raise FsError(f"incomplete entry in {REGISTRY} {where} "
                      "(needs a source with url and branch, and path)")
    return e


def layer_source(repo, src, link, lower):
    """The Source of the base of lower, link's entry in a layer below: src
    (link's, if at hand) - or, in another upstream repository, that one's;
    None if it can't be had (then link's base counts instead)."""
    if src is not None and norm_url(lower.url) == norm_url(link.url):
        return src
    try:
        return repo.ctx.cached_source(lower.url, lower.ref, lower.name) if repo.ctx else None
    except FsError:
        return None


def layer_matcher(repo, src, link, lower, st):
    """matches_base() against the base of lower, link's entry in a layer
    below (see layer_entry; in its own upstream repository, see
    layer_source); None if it has none (not there, a new link): nothing is
    adapted there."""
    if lower is None or lower.unsynced:
        return None
    blob, path, bsrc = layer_base(repo, src, link, lower)
    return blob_matcher(repo, bsrc, link.rel, blob, path, st)


def layer_base(repo, src, link, lower):
    """(blob, upstream path, Source) of the base of lower, link's entry in a
    layer below: in its own upstream repository (see layer_source) - or,
    if that can't be had, link's (src: its Source)."""
    lsrc = layer_source(repo, src, link, lower)
    return (lower.blob, lower.path, lsrc) if lsrc is not None else (link.blob, link.path, src)


def layer_code(lower, upper, below, above):
    """What a layer has of a linked file that the one below hasn't - their
    entries' bases (sync_keys; None: no entry), their files (blob ids;
    None: none): 'A' the entry or the file new, 'U' another base (synced
    otherwise), 'D' the file gone (or the entry: unlinked), 'M' another
    file with the same base; None: the same."""
    if upper is None:
        return None if lower is None else "D"
    if lower is None:
        return "A"
    if upper != lower:
        return "U"
    if above == below:
        return None
    return "D" if above is None else "A" if below is None else "M"


def local_state(repo, st, link, matchers, syncs):
    """The committed, worktree and local respects of a linked file (see
    evaluate) - each layer against its own entry (R1): matchers, syncs for
    HEAD, the index and the working tree - matches_base() against the base
    of the entry there (None: none, nothing adapted) and that base
    (sync_keys; None: no entry). Raises FsError if something is in the way
    of the file. A layer that differs from the one below (file or entry)
    is looked at; one that doesn't is as that one. Its own modification
    (R3: what pull and restore can't get again) is a file there that is
    neither the one below nor its entry's base (in the index also not the
    working tree entry's)."""
    blocked = in_the_way(repo.top, link.rel)
    if blocked:          # not 'missing': restore and pull would delete what is there
        if isinstance(link, Member):      # the entry is what can be unlinked
            raise FsError(f"{link.rel}: {blocked_text(repo, link.dlink.rel, blocked)}")
        raise FsError(blocked_text(repo, link.rel, blocked))
    exists = link.target.is_file()
    head = st.head_blob = repo.head_blob(link.rel)
    # uncommitted changes: in the working tree or staged - what a commit would take
    st.staged = link.rel in repo.staged()
    index = st.index_blob = repo.staged()[link.rel] if st.staged else head
    if not exists:
        st.worktree = "deleted" if head else "missing"
    elif not head:
        st.worktree = "added"
    elif repo.is_modified(link.rel):          # staged changes too
        st.worktree = "modified"
    # (a new link's file the index hasn't differs from it: not hashed)
    work = None if not exists else head if st.worktree == "clean" else \
        "" if st.unsynced and index is None else repo.worktree_blob(link.target)
    (mh, mi, mw), (sh, si, sw) = matchers, syncs

    def adapted(oid, match, read):
        return oid is not None and match is not None and not match(oid, read)
    # (a new link: no base to compare with - HEAD's and the index's entry may have one)
    if head and (not st.unsynced or mh is not None):
        st.committed = "adapted" if adapted(head, mh, lambda: repo.read_blob(head)) \
            else "unmodified"
    st.staged_code = layer_code(sh, si, head, index)
    st.index_adapted = adapted(index, mi, lambda: repo.read_blob(index)) if st.staged_code \
        else st.committed == "adapted"
    # (missing: 'D' where the file goes - here, unless its deletion is staged)
    st.unstaged_code = "D" if not exists and not st.unsynced and index is not None \
        else layer_code(si, sw, index, work)
    if st.unsynced:               # compared with upstream by its first sync
        st.local = "missing" if not exists else "clean"
        return
    own = []
    if st.staged_code:
        # (the base of the working tree's entry, e.g. after pull -W + git add: pull gets it)
        if index not in (None, head) and (mi is None or st.index_adapted) and \
                (mw is None or adapted(index, mw, lambda: repo.read_blob(index))) and \
                not moved_in_head(repo, link, si, index):
            own.append("index")
    if not exists:
        st.local = "missing"
    elif st.unstaged_code:
        st.local = "modified" if adapted(work, mw, link.target.read_bytes) else "clean"
        if work != index and st.local == "modified":
            own.append("worktree")
    else:
        st.local = "modified" if st.index_adapted else "clean"
    st.own = tuple(own)
    st.violation = not st.adaptable and (st.committed == "adapted" or st.index_adapted
                                         or st.local == "modified")


def moved_in_head(repo, link, sync, oid):
    """Is oid the file HEAD has for an entry with the base sync - under
    another name: the file moved (git filesync mv), nothing of its own? Only
    for a [file] entry."""
    if sync is None or link.is_dir or isinstance(link, Member):
        return False
    return any(sync_keys(v) == sync and repo.head_blob(r) == oid
               for r, v in repo.registry("head").files.items())


def head_base(eh, link):
    """(commit, blob or tree, path) of the base HEAD's entry eh has for
    link, what the commit message of a pull goes from (R3) - if it is
    another one than link's, in the same upstream repository; else None."""
    if eh is None or eh.unsynced or norm_url(eh.url) != norm_url(link.url) or \
            sync_keys(eh.v) == sync_keys(link.v):
        return None
    return eh.commit, eh.blob, eh.path


def evaluate(ctx, repo, link):
    """State of a linked file in three independent respects:
    upstream  - synced upstream version vs. current one (changed/behind/
                moved: renamed or deleted upstream)
    committed - committed version vs. synced upstream version
                ('unmodified' | 'adapted' | None if not committed)
    worktree  - working file vs. committed version
                ('clean' | 'modified' | 'deleted' | 'added' | 'missing')
    local     - working file vs. synced upstream version ('clean' | 'modified'
                | 'missing'); what a pull has to merge. A missing file (deleted
                or not, committed or not) is never allowed (see missing)
    A [dir] entry: see evaluate_dir."""
    if link.is_dir:
        return evaluate_dir(ctx, repo, link)
    st = FileState(link=link, rel=link.rel, old=link.commit, old_blob=link.blob,
                   new_path=link.path, adaptable=link.adaptable, unsynced=link.unsynced)
    url, ref, path = link.url, link.ref, link.path
    problem = path_problem(link.rel)
    if problem:
        st.error = (f"{problem} - entry ignored; remove it with "
                    f"'git config -f {REGISTRY} --remove-section \"file.{link.rel}\"'")
        return st
    others = link.reg.overlapping(link.rel, "file")
    if others:
        st.error = overlap_text(repo, link, others)
        return st
    problem = source_problem(link)
    if problem:
        st.error = problem
        return st
    try:
        src = st.src = ctx.source(url, ref, link.name, link.line)
    except FsError as e:
        st.error = str(e)
        return st
    try:          # (a registry of HEAD or the index that can't be read: this entry's error)
        lower = st.entries = (layer_entry(repo, link, "head"), layer_entry(repo, link, "index"))
        st.head_base = head_base(lower[0], link)
        st.bases = tuple(None if e is None or e.unsynced else layer_base(repo, src, link, e)
                         for e in lower)
        local_state(repo, st, link, [layer_matcher(repo, src, link, e, st) for e in lower]
                    + [None if link.unsynced else base_matcher(repo, src, link, st)],
                    [None if e is None else sync_keys(e.v) for e in lower] + [sync_keys(link.v)])
    except FsError as e:
        st.error = str(e)
        return st
    where = f"{ref[0]} '{ref[1]}'"
    try:
        tip = src.tip()
    except FsError as e:
        st.error = str(e)
        return st
    if ref[0] == "tag" and not src.tag_names:      # a pattern: no hints at other tags
        st.newest, problem = src.tag_info(ref[1], link.line, ctx.want_tags)
        if problem:
            st.warnings.append(f"{problem} (where newer tags are looked for)")
    st.has_old = bool(st.old) and src.resolve(st.old) == st.old
    st.new_blob = src.blob_at(tip, path)
    if not st.new_blob:
        st.moved = src.follow(st.old, tip, path) if st.has_old else None
        if not st.moved:
            st.error = (f"'{path}' does not exist in {where} of {src.label} "
                        f"(renamed upstream? fix the path in {REGISTRY})")
            return st
        if st.moved[0] == "deleted":
            st.new = st.moved[2]
            st.pending = True
            return st
        path = st.new_path = st.moved[1]
        st.new_blob = src.blob_at(tip, path)
    track_history(repo, st, src, tip, link.path, path,
                  st.has_old and st.new_blob == st.old_blob and path == link.path)
    st.changed = st.new_blob != st.old_blob
    st.pending = st.changed or bool(st.moved) or st.off_track
    checkout_warnings(st, src, ref, path, lambda: src.blob_at("HEAD", path) != st.new_blob)
    return st


def track_history(repo, st, src, tip, old_path, path, unchanged):
    """The upstream commit a pull records (st.new) - the newest one up to
    tip that changed path - and where it is relative to the synced one:
    behind it, how many commits after it, diverged; or the synced commit
    unknown upstream (lost_old). unchanged: the same version as synced, no
    history to look at - if the synced commit is in the history of tip; if
    not (on another branch, rebased away), the history diverged also with
    the same version."""
    unchanged = unchanged and src.is_ancestor(st.old, tip)
    st.new = st.old if unchanged else src.last_change(tip, path or ".")
    if st.has_old:
        if st.new == st.old:
            pass
        elif src.is_ancestor(st.new, st.old):
            st.behind_args = (st.new, st.old, path or ".")   # branch older than last sync
        else:
            st.count_args = (st.old, st.new, *dict.fromkeys((old_path or ".", path or ".")))
            st.diverged = not src.is_ancestor(st.old, st.new)
    elif not st.unsynced:
        # the source may be behind, or upstream history was rewritten: not
        # guessed - pull --all leaves the file alone, pull FILE syncs it
        st.lost_old = True
        pull = f"'git filesync pull {path_arg(repo, st.rel)}' syncs to its current version"
        # a cache clone asks the server for a commit it lacks: not there
        why = ("if the checkout is behind, update it (or use --remote); otherwise "
               if src.local else "not on the server (history rewritten there, synced from "
               "an unpushed commit or another upstream): ")
        st.warnings.append(f"previous sync point {st.old[:12] or '-'} not found in "
                           f"{src.label} - {why}{pull}")


def checkout_warnings(st, src, ref, path, head_differs):
    """Warnings for a source that is a mapped checkout: the version to sync
    not pushed, another branch checked out (head_differs(): with another
    version of path), uncommitted changes to path."""
    if not src.local:
        return
    what = path + "/" if st.link.is_dir else path
    if src.note:
        st.warnings.append(src.note)
    if not src.is_published(st.new):   # other unpushed commits don't matter
        st.warnings.append(f"'{what}' in {src.label} comes from commit "
                           f"{src.short(st.new)}, which is not pushed")
    if ref[0] == "tag":
        return      # a pinned tag: whatever is checked out doesn't matter
    if src.head_ref() != src.ref:
        if head_differs():
            st.warnings.append(f"{src.label} has {src.head_desc()} checked out; "
                               f"'{what}' there differs from {ref[0]} '{ref[1]}', "
                               "which is what gets synced")
    elif src.has_uncommitted(path):
        st.warnings.append(f"uncommitted changes to '{what}' in {src.label} "
                           "are not synced (commit them first)")


@dataclass
class DirState(FileState):
    """What evaluate_dir() finds out about a [dir] entry: a FileState for
    the entry as a whole, from those of its files (members)."""
    n: int = 0                # files at the base
    no_base: bool = False     # the base tree isn't available: synced like a new link
    new_tree: Optional[str] = None   # upstream tree a pull would sync to
    tip: Optional[str] = None        # ... and the upstream revision it is at
    layer_files: tuple = (None, None)    # the files of the bases in HEAD and the index

    # members by what a pull does with them
    adds = property(lambda self: [m for m in self.members if m.unsynced and m.new_blob])
    dels = property(lambda self: [m for m in self.members if not m.unsynced and not m.new_blob])
    mods = property(lambda self: [m for m in self.members if not m.unsynced and m.new_blob
                                  and m.new_blob != m.old_blob])


def dir_base(src, dlink):
    """{path below: blob id} of the files of a [dir] entry at its base: the
    upstream tree's files the patterns it was synced with select; None if
    the tree isn't there (or the entry has none)."""
    files = src.tree_files(dlink.tree) if dlink.tree else None
    return None if files is None else {b: o for b, o in files.items()
                                       if dlink.selects(b, base=True)}


def dir_members(repo, dlink, base, upstream):
    """FileStates of the members of a [dir] entry: the files at its base
    (base: {path below: blob id}) and the new ones in upstream ({path
    below: blob id}, already selected by the patterns); FsError for one
    that can't be a file here (e.g. .git-filesync)."""
    sts = []
    for below in sorted(set(base) | set(upstream)):
        m = dlink.member(below, base.get(below, ""))
        problem = path_problem(m.rel)
        if problem:
            raise FsError(f"{m.rel}: {problem} - leave it out with --exclude /{below} "
                          f"('git filesync set --exclude ... {path_arg(repo, dlink.rel)}')")
        sts.append(FileState(link=m, rel=m.rel, old=dlink.commit, old_blob=m.blob,
                             new_path=m.path, adaptable=dlink.adaptable, unsynced=m.unsynced,
                             new_blob=upstream.get(below)))
    return sts


def layer_files(src, dlink, lower, base):
    """{path below: blob id} of the files at the base of lower, a [dir]
    entry's entry in a layer below (see layer_entry), src the Source of
    that base (see layer_source); None if it has none (not there, a new
    link). base: those of dlink's base - also if src is None, or if the tree
    isn't there."""
    if lower is None or lower.unsynced:
        return None
    if src is None or sync_keys(lower.v) == sync_keys(dlink.v):
        return base
    try:
        files = dir_base(src, lower)
    except FsError:                       # e.g. bad patterns there: as if the same
        files = None
    return base if files is None else files


def fill_members(repo, st, base, upstream):
    """The members of a [dir] entry (see dir_members), each evaluated as a
    linked file - in each layer against the base of the entry there (see
    local_state) -, and the entry's state from theirs: adapted if one is,
    missing if one is, and so on. FsError if something is in the way of one."""
    dlink = st.link
    st.members = dir_members(repo, dlink, base, upstream)
    lower = st.entries = (layer_entry(repo, dlink, "head"), layer_entry(repo, dlink, "index"))
    st.head_base = head_base(lower[0], dlink)
    srcs = [None if e is None or e.unsynced else layer_source(repo, st.src, dlink, e)
            for e in lower]
    files = st.layer_files = [layer_files(s, dlink, e, base) for s, e in zip(srcs, lower)]
    syncs = [None if e is None else sync_keys(e.v) for e in lower] + [sync_keys(dlink.v)]
    # the bases of the layers below, asked at once (see matches_base)
    own = [(fs, lsrc) for fs, lsrc in zip(files, srcs) if fs is not None and fs is not base]
    if own:
        repo.check_plain(m.rel for m in st.members)
        for fs, lsrc in own:
            try:
                (lsrc or st.src).check_plain(fs.values())
            except FsError:
                pass
    for m in st.members:
        m.src, m.has_old = st.src, st.has_old
        below = m.link.below
        matchers, bases = [], []
        for e, fs, lsrc in zip(lower, files, srcs):
            blob = fs.get(below) if fs is not None else None
            # (its own base, read in its upstream repository - else the working tree's)
            own = e if fs is not None and fs is not base else None
            b = (blob, up_join(own.path if own is not None else dlink.path, below),
                 (lsrc or st.src) if own is not None else st.src) if blob else None
            bases.append(b)
            matchers.append(None if b is None else blob_matcher(repo, b[2], m.rel, b[0], b[1], m))
        m.bases = tuple(bases)
        matchers.append(None if m.unsynced else base_matcher(repo, st.src, m.link, m))
        local_state(repo, m, m.link, matchers,
                    [None if s is None else (s, (fs or {}).get(below, ""))
                     for s, fs in zip(syncs, files + [base])])
    sts, st.n = st.base_members, len(base)
    st.committed = "adapted" if any(m.committed == "adapted" for m in sts) else \
        "unmodified" if any(m.committed for m in sts) else None
    st.local = "missing" if any(m.local == "missing" for m in sts) else \
        "modified" if any(m.local == "modified" for m in sts) else "clean"
    st.worktree = "added" if sts and all(m.worktree == "added" for m in sts) else \
        "modified" if any(m.worktree in ("modified", "added") for m in sts) else "clean"
    st.violation = any(m.violation for m in sts)
    st.index_adapted = any(m.index_adapted for m in sts)
    st.staged = any(m.staged for m in sts)
    st.own = dir_own(sts)

    def code(lower, upper, attr):
        """The entry's code (see layer_code): the base's, else its files'."""
        if upper is None or lower is None or upper != lower:
            return layer_code(lower, upper, None, None)
        codes = {getattr(m, attr) for m in sts}
        return "D" if "D" in codes else "M" if codes & {"M", "A"} else None
    st.staged_code = code(syncs[0], syncs[1], "staged_code")
    st.unstaged_code = code(syncs[1], syncs[2], "unstaged_code")


def dir_own(members):
    """The layers where a [dir] entry has a modification of its own (see
    local_state): where one of its files has."""
    return tuple(layer for layer in ("index", "worktree") if any(layer in m.own for m in members))


def evaluate_dir(ctx, repo, dlink):
    """State of a [dir] entry, in the respects of evaluate() - each of its
    files evaluated as a linked file (see Member), summed up: adapted if one
    is, missing if one is (never allowed, as for a file), and so on.
    Upstream: the files the entry would have after a pull - those of the
    upstream directory its patterns select - against those at its base."""
    st = DirState(link=dlink, rel=dlink.rel, old=dlink.commit, old_blob=dlink.tree,
                  new_path=dlink.path, adaptable=dlink.adaptable, unsynced=dlink.unsynced)
    try:
        dlink.target
        dlink.check_patterns()
    except FsError as e:
        st.error = str(e)
        return st
    others = dlink.reg.overlapping(dlink.rel, "dir")
    problem = overlap_text(repo, dlink, others) if others else source_problem(dlink)
    if problem:
        st.error = problem
        return st
    ref, path = dlink.ref, dlink.path
    try:
        src = st.src = ctx.source(dlink.url, ref, dlink.name, dlink.line)
        tip = src.tip()
    except FsError as e:
        st.error = str(e)
        return st
    if ref[0] == "tag" and not src.tag_names:      # a pattern: no hints at other tags
        st.newest, problem = src.tag_info(ref[1], dlink.line, ctx.want_tags)
        if problem:
            st.warnings.append(f"{problem} (where newer tags are looked for)")
    st.has_old = bool(st.old) and src.resolve(st.old) == st.old
    base = {} if st.unsynced else dir_base(src, dlink)
    if base is None:
        st.no_base, base = True, {}
        st.warnings.append(f"synced tree {dlink.tree[:12]} not found in {src.label}: the "
                           "files of the entry are unknown - 'git filesync pull "
                           f"{path_arg(repo, dlink.rel)}' syncs it as a new link")
    st.tip = tip
    st.new_tree, files = src.files_at(tip, path)
    upstream = {b: o for b, o in (files or {}).items() if dlink.selects(b)}
    try:
        fill_members(repo, st, base, upstream)
    except FsError as e:
        st.error = str(e)
        return st
    if not st.new_tree:           # gone upstream: deleted (not followed if renamed)
        gone = st.has_old and out(src.git(["rev-list", "-1", f"{st.old}..{tip}", "--",
                                           lit(path)], check=False))
        if not gone:
            st.error = (f"'{path}/' does not exist in {ref[0]} '{ref[1]}' of {src.label} "
                        f"(renamed upstream? fix the path in {REGISTRY})")
            return st
        st.new = gone
        for m in st.members:
            m.new = gone
        st.moved, st.pending = ("deleted", path + "/", gone), True
        return st
    st.changed = st.no_base or upstream != base
    track_history(repo, st, src, tip, path, path, st.has_old and not st.changed)
    for m in st.members:
        m.new = st.new
        m.changed = m.new_blob != m.old_blob
    st.pending = st.changed or st.off_track
    checkout_warnings(st, src, ref, path, lambda: src.tree_at("HEAD", path) != st.new_tree)
    return st


def upstream_state(st, note=True):
    """(label, note) of a pending upstream change, None if there is none;
    without note (status -s), the git calls for the note are left out."""
    if st.unsynced:
        return "new", "not synced yet"
    if st.moved:
        kind, path, commit = st.moved
        if not note:
            return kind, None
        if kind == "deleted":
            return "deleted", f"upstream, by {st.src.short(commit)}"
        n = commits_since(st)
        return "renamed", f"{st.link.path} -> {path}" + (f", {plural(n, 'commit')}" if n else "")
    if st.changed or st.off_track:
        if st.behind_args:
            if not note:
                return "older", None
            what = "upstream branch" if st.link.ref[0] == "branch" else f"tag {st.link.ref[1]}"
            behind = commits_behind(st)
            return "older", f"{what} is {plural(behind, 'commit') + ' ' if behind else ''}" \
                "older than last sync"
        if st.has_old and not st.diverged:
            if not note:
                return "pending", None
            n, repat = commits_since(st), st.link.is_dir and st.link.repatterned
            what = ([plural(n, "commit")] if n or not repat else []) + \
                (["patterns changed"] if repat else [])
            return "pending", ", ".join(what) + files_note(st)
        if not st.has_old:
            return "diverged", "previous sync point unknown"
        return "diverged", "history diverged" + ("" if st.changed else ", same version")
    return None


def files_note(st):
    """'; files: 2 new, 1 deleted' - what a pull of a [dir] entry brings."""
    if not st.link.is_dir:
        return ""
    what = [f"{len(ms)} {kind}" for ms, kind in ((st.adds, "new"), (st.dels, "deleted"),
                                                 (st.mods, "changed")) if ms]
    return f"; files: {', '.join(what)}" if what else ""


def of_files(st, members):
    """'2 of 40 files' - the members of a [dir] entry concerned."""
    return f"{len(members)} of {plural(st.n, 'file')}"


def violation_text(st):
    what = (["adapted"] if st.committed == "adapted" else []) + \
        (["uncommitted changes"] if st.worktree != "clean" and st.local == "modified" else [])
    where = f" in {of_files(st, [m for m in st.base_members if m.violation])}" \
        if st.link.is_dir else ""
    return f"{', '.join(what) or 'local modifications'}{where} NOT ALLOWED (not adaptable)"


def missing_members(st):
    return [m for m in st.base_members if m.local == "missing"]


def describe(st):
    """[(text, style)] one-line summary, used for hook output."""
    if st.error:
        return [(f"ERROR: {st.error}", "boldred")]
    parts = []
    up = upstream_state(st)
    if up:
        label, note = up
        parts.append((note if label in ("older", "diverged") else f"upstream {label} ({note})",
                      "yellow"))
    if st.violation:
        parts.append((violation_text(st), "boldred"))
    if st.missing:
        parts.append(((f"{of_files(st, missing_members(st))} " if st.link.is_dir else "")
                      + "MISSING (still linked)", "boldred"))
    return parts or [("up to date", "green")]


def report_error(st):
    """An entry that couldn't be evaluated (status, pull, diff)."""
    error(f"{st.rel}: {st.error}")


def render(parts, stream="out"):
    return ", ".join(paint(t, s, stream) for t, s in parts)


def short_code(st):
    """Three columns like `git status -s` with upstream first: upstream,
    the index against HEAD (what a commit takes) and the working tree
    against the index - A new, U another base, M modified, D missing (see
    layer_code)."""
    if st.error:
        return "E  "
    up = upstream_state(st, note=False)
    x = {"pending": "P", "older": "O", "diverged": "D", "new": "N", "renamed": "R",
         "deleted": "X"}[up[0]] if up else " "
    # (missing: deleted in the working tree - unless the deletion is staged, as git shows it)
    return x + (st.staged_code or " ") + \
        ("D" if st.missing and st.staged_code != "D" else st.unstaged_code or " ")


def short_note(st):
    """'(missing!)', '(adapted)', '(not adaptable!)' - after a line of status -s."""
    if st.missing:
        return "missing!"
    return ", ".join((["adapted"] if st.committed == "adapted" else [])
                     + (["not adaptable!"] if st.violation else [])) or None


def shown_path(repo, path):
    """A path as shown to the user: relative to the current directory if
    possible (not across drives on Windows), else absolute."""
    try:
        return Path(os.path.relpath(path, repo.base)).as_posix()
    except ValueError:            # Windows: another drive
        return Path(path).as_posix()


def shown(repo, rel):
    """Path relative to the current directory, like git status shows it."""
    return shown_path(repo, repo.top / rel)


def shown_entry(repo, link):
    """An entry as shown: its path (see shown), a [dir] with a trailing '/'."""
    name = shown(repo, link.rel)
    return name.rstrip("/") + "/" if link.is_dir else name


def path_arg(repo, rel):
    """A path of this repository as argument in a command shown to the user."""
    return cmd_arg(shown(repo, rel))


def print_short(repo, sts):
    for st in sts:
        code, note = short_code(st), short_note(st)
        if code.strip() or note:
            line = paint(code[0], "yellow") + paint(code[1], "green") + paint(code[2], "red")
            if code[0] == "E":
                line = paint(code, "boldred")
            style = "boldred" if st.missing or st.violation else "cyan"
            print(f"{line} {shown_entry(repo, st.link)}"
                  + (paint(f"  ({note})", style) if note and not st.error else ""))


def link_text(st):
    """Where a linked file comes from, for status -v and pull -v."""
    via = f" via {st.src.label}" if st.src and st.src.local else ""
    adaptable = ", adaptable" if st.adaptable else ""
    newest = f", newest {newest_text(st.newest, st.link.line)}" if st.newest else ""
    names = st.src.tag_names if st.src else None
    path, files = st.link.path, ""
    if st.link.is_dir:
        path, files = up_join(path, ""), ("" if st.unsynced else f", {plural(st.n, 'file')}")
    return (f"from {st.link.name}:{path or '/'} "
            f"({ref_text(st.link.ref, st.link.line, names)}{newest}{files}{adaptable}){via}")


def status_hints(repo):
    """Show hints how to go on (advice.statusHints, as git)?"""
    return out(repo.git(["config", "--type=bool", "advice.statusHints"], check=False)) != "false"


def versions(st, lower, upper):
    """'1a2b3c4 -> 5d6e7f8' - the synced commits of an entry in two layers
    (lower None: not there), as shown for a change between them."""
    def label(e):
        if e is None or e.unsynced:
            return "new" if e is not None else None
        try:
            return st.src.short(e.commit) if e.commit else short_of(e)
        except FsError:
            return short_of(e)
    a, b = label(lower), label(upper)
    return f"{a} -> {b}" if a and b and a != b else b


def print_long(repo, sts, verbose, gone=()):
    """Sections like `git status`; a [dir] entry in one line, with the
    number of its files concerned in the note. gone: the entries only HEAD
    or the index has (see unlinked_states)."""
    hints = status_hints(repo)

    def section(title, hint_lines, rows, style):
        if not rows:
            return
        print(title)
        if hints:
            for h in hint_lines:
                print(f"  ({h})")
        for label, st, note, nstyle in rows:
            line = paint(f"{label + ':':<12}{shown_entry(repo, st.link)}", style)
            print(f"\t{line}" + (f"  {paint('(' + note + ')', nstyle)}" if note else ""))
        print()

    def note(st, members, text=None, style="dim"):
        """(note, style) of a row: for a [dir] the number of its files
        concerned, then text."""
        what = ([of_files(st, members)] if st.link.is_dir else []) + ([text] if text else [])
        return (", ".join(what) or None, style if text else "dim")

    ok = [st for st in sts if not st.error]
    if verbose:
        rows = [("new" if st.unsynced else st.committed or "uncommitted", st,
                 link_text(st), "dim") for st in ok]
        section("Linked files:", [], rows, None)

    up_rows = []
    for st in ok:
        up = upstream_state(st)
        if up:
            up_rows.append((up[0], st, up[1], "yellow" if st.off_track else "dim"))
    section("Upstream changes to sync:",
            ['use "git filesync diff --upstream <file>..." to see what pull would bring',
             'use "git filesync pull <file>..." to sync']
            + (['"git filesync pull --all" leaves out older and diverged ones: sync them by name']
               if any(r[1].off_track for r in up_rows) else [])
            + (['use "git filesync unlink <file>..." to keep files deleted upstream']
               if any(r[0] == "deleted" for r in up_rows) else []),
            up_rows, "yellow")

    not_allowed = "NOT ALLOWED: not adaptable"
    adapted = [st for st in ok if st.committed == "adapted"]
    section("Locally adapted files:",
            ['use "git filesync diff --committed <file>..." to see the adaptations']
            + (['use "git filesync restore -SW <file>..." to discard them, or '
                '"git filesync set --adaptable <file>..." to allow them']
               if any(not st.adaptable for st in adapted) else []),
            [("adapted", st) + note(st, [m for m in st.members if m.committed == "adapted"],
                                    None if st.adaptable else not_allowed, "boldred")
             for st in adapted],
            "cyan")

    missing = [st for st in ok if st.missing]
    section("Missing files:",
            ['use "git filesync restore <file>..." to bring them back (the synced version)',
             'use "git filesync unlink <file>..." to remove the links'],
            [("missing", st) + note(st, missing_members(st), "NOT ALLOWED: still linked",
                                    "boldred") for st in missing],
            "red")

    # what differs between the layers: to be committed, not staged (git's sections)
    labels = {"A": "new file", "U": "updated", "M": "modified", "D": "deleted"}

    def layer_rows(attr, i, adapted):
        """The rows of the entries a layer changes (attr: their code), i: the
        layer's index in (HEAD, index, working tree), adapted(st): there."""
        rows = []
        for st in ok:
            code = getattr(st, attr)
            if not code or code == "D" and st.missing:
                continue
            ms = [m for m in st.base_members if getattr(m, attr)]
            lower = st.entries[i - 1]
            upper = st.link if i == 2 else st.entries[1]
            if code == "D" and upper is None:     # the entry removed there (unlink)
                rows.append(("unlinked", st, None, "dim"))
                continue
            text = not_allowed if not st.adaptable and adapted(st) else \
                "NOT ALLOWED: still linked" if code == "D" else \
                ", ".join([v for v in [versions(st, lower, upper)] if v]
                          + (["adapted"] if adapted(st) else [])) or None \
                if code in "AU" else None
            rows.append((labels[code], st) + note(st, ms, text, "boldred" if code in "MD" else "dim"))
        rows += [({"D": "unlinked", "A": "new file", "U": "updated"}[getattr(st, attr)], st,
                  None, "dim") for st in gone if getattr(st, attr)]
        return sorted(rows, key=lambda r: r[1].rel)
    def restore_hints(rows, opt, what):
        """How to go back: an unlink changed only .git-filesync (git restore)."""
        return ([f'use "git filesync restore {opt}<file>..." to restore {what}']
                if any(r[0] != "unlinked" for r in rows) else []) + \
            ([f'use "git restore {opt}{REGISTRY}" to undo unlinking (all its changes go)']
             if any(r[0] == "unlinked" for r in rows) else [])
    staged = layer_rows("staged_code", 1, lambda st: st.index_adapted)
    section("Changes to be committed:",
            ['use "git commit" to commit them']
            + restore_hints(staged, "-S ", "the index from HEAD"), staged, "green")
    unstaged = layer_rows("unstaged_code", 2, lambda st: st.local == "modified")
    section("Changes not staged for commit:",
            (['use "git filesync pull <file>..." to stage them']
             if any(r[0] in ("updated", "new file") for r in unstaged) else [])
            + (['use "git add <file>..." to stage them']
               if any(r[0] == "modified" for r in unstaged) else [])
            + restore_hints(unstaged, "", "them from the index"), unstaged, "red")
    dirty = staged + unstaged

    warnings = [(st.rel, w) for st in ok for w in st.warnings] + \
        [(m.rel, w) for st in ok if st.link.is_dir for m in st.members for w in m.warnings]
    if warnings:
        print("Warnings:")
        for rel, w in warnings:
            print(f"\t{paint('warning:', 'yellow')} {shown(repo, rel)}: {w}")
        print()

    if not up_rows and len(ok) == len(sts):
        n = sum(st.n if st.link.is_dir else 1 for st in sts)
        files = plural(n, "linked file")
        print("nothing to sync" + ("" if adapted or dirty or missing else
                                   f", {'all ' if n > 1 else ''}{files} unmodified"))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(ctx, repo, args):
    """Like `git status`: exit code 0 unless --exit-code (1 = something to
    sync, a missing file or a change not allowed) or an error (2)."""
    reg = Registry(repo)
    links = select_links(repo, reg, args.paths)
    gone = [] if args.paths else unlinked_states(repo, reg)
    if not links and not gone:
        if not args.short:
            print(f"no linked files ({REGISTRY} not found or empty)")
        return EXIT_OK
    prefetch(ctx, repo, links)
    sts = [evaluate(ctx, repo, link) for link in links]
    check_only(sts)
    attention = [st for st in sts if st.attention]
    rc = EXIT_ERROR if any(st.error for st in sts) else \
        EXIT_PENDING if args.exit_code and attention else EXIT_OK
    for st in sts:
        if st.error:
            report_error(st)
    if args.short:
        print_short(repo, sorted(sts + gone, key=lambda st: st.rel))
        return rc
    # the synced commits of the entries a layer changes (see versions), asked at once
    changed = [st for st in sts if not st.error and st.src and
               {st.staged_code, st.unstaged_code} & {"A", "U"}]
    for src in {id(st.src): st.src for st in changed}.values():
        try:
            src.shorts(e.commit for st in changed if st.src is src
                       for e in st.entries + (st.link,) if e is not None and e.commit
                       and norm_url(e.url) == norm_url(st.link.url))
        except FsError:
            pass                  # (asked one by one, see versions)
    print_long(repo, sts, args.verbose, gone)
    return rc


def unlinked_states(repo, reg):
    """States of the entries HEAD or the index has and the working tree
    hasn't (unlinked, removed there): for status, only their layers' codes -
    the entry gone ('D'), new in the index ('A'), synced otherwise ('U')."""
    try:
        head, index = repo.registry("head"), repo.registry("index")
    except FsError:
        return []
    have = set(reg.files) | set(reg.dirs)
    sts = []
    for rel in sorted({r for x in (head, index) for r in list(x.files) + list(x.dirs)} - have):
        eh, ei = head.entry(rel), index.entry(rel)
        e = ei or eh
        st = FileState(link=e, rel=rel, old=e.commit, old_blob=e.blob, new_path=e.path,
                       adaptable=e.adaptable)
        st.staged_code = layer_code(None if eh is None else sync_keys(eh.v),
                                    None if ei is None else sync_keys(ei.v), None, None)
        st.unstaged_code = "D" if ei is not None else None
        sts.append(st)
    return sts


def merge3(ours, base, theirs, labels):
    with tempfile.TemporaryDirectory() as td:
        files = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            f = Path(td) / name
            f.write_bytes(data)
            files.append(str(f))
        args = ["merge-file"]
        for label in labels:
            args += ["-L", label]
        p = git(args + files, check=False)
        if p.returncode < 0 or p.returncode > 127:
            raise FsError("merge failed: " + p.stderr.decode("utf-8", "replace").strip())
        return p.returncode, Path(files[0]).read_bytes()


def upstream_line(src, url, ref, path):
    """'Upstream: URL (main:lib/foo.c)' in a proposed commit message; for a
    tag pattern the tag it matched."""
    return f"Upstream: {url} ({src.tag_names[0] if src.tag_names else ref[1]}:{path})"


def build_message(st, src, new, new_blob, old_path, path, merged, conflicts, discarded=False):
    link = st.link
    paths = dict.fromkeys((old_path, path))       # old and (if renamed) new path
    # content goes back to the synced upstream version -> restore, not a sync
    verb = "Restore" if new_blob == st.old_blob and discarded else "Sync"
    lines = [f"{MSG_PREFIX}{verb} {st.rel} from {link.name}@{src.dated(new)}", "",
             upstream_line(src, link.url, link.ref, path)]
    if path != old_path:
        lines += ["", f"Renamed upstream: {old_path} -> {path}"]
    lines += history_lines(st, src, new, paths)
    if merged:
        lines += ["", "Merged with local modifications of this repository"
                  + (" (conflicts resolved manually)." if conflicts else ".")]
    if discarded:
        lines += ["", "Local modifications of this repository were discarded."]
    return "\n".join(lines) + "\n"


def history_lines(st, src, new, paths):
    """The upstream commits on paths a sync to new brings (or reverts), for
    its proposed commit message."""
    if new == st.old:
        return []
    if not st.has_old:
        return ["", "Previous sync point unknown; change list not available."]
    old, lines = st.old, []
    if src.is_ancestor(new, old):
        log = src.log(f"{new}..{old}", *paths)
        if log:
            lines += ["", f"Reverts upstream changes after {src.dated(new)}:", log]
    else:
        if not src.is_ancestor(old, new):
            lines += ["", f"Note: {src.dated(new)} is not a descendant of the "
                      f"previous sync point {src.dated(old)}."]
        log = src.log(f"{old}..{new}", *paths)
        if log:
            lines += ["", f"Upstream changes since {src.dated(old)}:", log]
    return lines


def propose_message(repo, msg):
    """Add a proposed commit message to .git/SQUASH_MSG, which a plain `git
    commit` (and IDEs) offer - also to one of git's own (e.g. from merge
    --squash): the commit takes both. Proposals of several commands are
    collected until git removes it (after the next commit, and on reset).
    A copy goes to .git/FILESYNC_MSG, which stays: each proposal rewrites
    it. Returns the copy."""
    squash, copy = repo.gitdir / "SQUASH_MSG", repo.gitdir / "FILESYNC_MSG"
    data = msg.encode("utf-8")
    prev = squash.read_bytes() if squash.exists() else b""
    if data in prev:
        data = prev
    elif prev.strip():
        data = prev.rstrip(b"\n") + b"\n\n" + data
    for f in (squash, copy):
        f.write_bytes(data)
    return copy


def commit_hint(repo, msg):
    """Propose msg for the next commit (see propose_message); the note
    about it, for after the command to commit."""
    copy = shown_path(repo, propose_message(repo, msg))
    return f"(it offers the proposed commit message; a copy stays in {copy})"


def report_staged(repo, name, msg, done):
    """Tell how to commit what a command staged without committing."""
    print(f"{name}: {done}. Commit with:\n    git commit\n{commit_hint(repo, msg)}")


def commit_target(st, rev):
    """(commit, blob, path) a sync to upstream revision rev records (--commit):
    the file at its synced path or, if renamed upstream, at the new one."""
    link, src = st.link, st.src
    new = src.require(rev)
    for path in dict.fromkeys((link.path, st.new_path)):
        blob = src.blob_at(new, path)
        if blob:
            return src.last_change(new, path), blob, path
    raise FsError(f"'{link.path}' does not exist at {rev}")


def check_target_args(args):
    """--commit / -b / --tag (pull, diff --upstream): the upstream version to sync to."""
    if args.commit and (args.branch or args.tag):
        raise FsError("--commit cannot be combined with -b or --tag")
    if args.branch and args.tag:
        raise FsError("-b and --tag cannot be combined")


def target_rev(ctx, link, args):
    """--commit / -b / --tag (pull, diff --upstream): the upstream revision
    to sync to once - that revision, the head of that branch, or the tag.
    The link keeps its own branch or tag."""
    if args.commit:
        return args.commit        # resolved in the link's upstream (commit_target)
    ref = ("tag", args.tag) if args.tag else ("branch", args.branch)
    # a tag pattern: the newest matching tag on the source's branch
    line = link.source.get("branch") if args.tag and is_tag_pattern(args.tag) else None
    src = ctx.source(link.url, ref, link.name, line)
    return src.tip()


def once_text(args):
    """The revision, branch or tag of pull --commit/-b/--tag."""
    return f"commit {args.commit}" if args.commit else f"tag {args.tag}" if args.tag \
        else f"branch {args.branch}"


def target_opts(args):
    """The --commit / -b / --tag options given, for hints."""
    return "".join(f" {opt} {cmd_arg(val)}" for opt, val in (
        ("--commit", args.commit), ("-b", args.branch), ("--tag", args.tag)) if val)


def pull_one(repo, reg, st, args):
    """Sync one file: write it and update its entry; staged, unless it has
    merge conflicts. Returns (its part of the commit message, conflicts),
    or None if there is nothing to do (or only a dry run)."""
    link, src = st.link, st.src
    path = st.new_path                   # differs from link.path if renamed upstream
    new, new_blob = st.new, st.new_blob
    if st.missing:
        rel = path_arg(repo, st.rel)
        raise FsError(f"{st.rel}: missing - bring it back with 'git filesync restore {rel}', "
                      f"or remove the link with 'git filesync unlink {rel}'")
    if st.once:
        new, new_blob, path = commit_target(st, st.target)
    elif st.moved and st.moved[0] == "deleted":
        rel = path_arg(repo, st.rel)
        raise FsError(f"{st.rel}: '{st.moved[1]}' was deleted in {src.label} "
                      f"({src.short(st.moved[2])}) - keep the file with "
                      f"'git filesync unlink {rel}', or delete it too with "
                      f"'git filesync rm {rel}'")
    if st.unsynced:
        return first_sync(repo, st, args, new, path)
    local_mod = st.local == "modified"
    # upstream's version as it is, not merged
    discard = args.overwrite and (local_mod or st.index_adapted)
    dropped = args.overwrite and st.committed == "adapted"   # committed adaptations go
    if st.violation and not args.overwrite and not stale(st):
        rel = path_arg(repo, st.rel)
        ways = f", or sync anyway with 'git filesync pull --overwrite {rel}'" + (
            f"; or allow them with 'git filesync set --adaptable {rel}'"
            if st.worktree == "clean" else f"; only the uncommitted ones: 'git restore -SW {rel}'")
        raise FsError(f"{st.rel}: {violation_text(st)} - inspect with "
                      f"'git filesync diff {rel}'; discard them with "
                      f"'git filesync restore -SW {rel}'{ways}")
    # the index too has what pull gives (with -W: only the working tree counts)
    if new_blob == st.old_blob and path == link.path and new == st.old and not stale(st) \
            and not (discard or dropped) and (args.worktree or staged_as_is(repo, link)):
        print(f"{st.rel}: {paint('up to date', 'green')}"
              + (" (adaptations kept)" if st.committed == "adapted" else ""))
        return None
    # like `git pull`: uncommitted changes are never merged into a sync -
    # with --overwrite, they are discarded (and kept, see save_discarded)
    if local_changes(st) and not args.overwrite:
        rel = path_arg(repo, st.rel)
        raise FsError(f"your local changes to '{st.rel}' would be overwritten by pull - "
                      f"commit or stash them first ('git stash'; 'git restore -SW {rel}' "
                      f"discards them), or take the upstream version with "
                      f"'git filesync pull --overwrite {rel}'")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")

    content, merged, conflicts = sync_content(repo, st, new, new_blob, path,
                                              local_mod and st.adaptable and not discard)

    if args.dry_run:
        lost = args.overwrite and local_changes(st) and loses(repo, st, content, args)
        notes = ([f"{st.once} once"] if st.once else []) + \
            ([f"renamed upstream: {link.path} -> {path}"] if path != link.path else []) + \
            (["discarding adaptations"] if dropped else []) + \
            (["discarding uncommitted changes"] if lost else []) + \
            ([paint(f"{conflicts} merge conflict(s)", "boldred") if conflicts else
              "adaptations merged cleanly"] if merged else [])
        verb = "restore" if new_blob == st.old_blob and (discard or dropped) else "sync"
        print(f"{st.rel}: would {verb} to {link.name}@{src.short(new)}"
              + (f" ({'; '.join(notes)})" if notes else ""))
        if conflicts:
            rel = path_arg(repo, st.rel)
            print(f"hint: compare the adaptations ('git filesync diff {rel}') with the "
                  f"upstream changes ('git filesync diff --upstream{target_opts(args)} {rel}')")
        return None

    old_path = link.path
    if path != old_path:
        link.set("path", path)
    link.set("commit", new)
    link.set("blob", new_blob)
    if args.overwrite and local_changes(st):   # kept by the caller (see save_discarded)
        st.discards = ([st.rel], [st.rel])
    if conflicts:
        print(f"{st.rel}: {paint(f'{conflicts} merge conflict(s)', 'boldred')}")
    else:
        print(f"{st.rel}: {synced_text(args)}" + (" (adaptations merged)" if merged else ""))
    # the file itself is written (and staged) with the others: write_synced;
    # the message goes from what is committed (R3)
    return build_message(message_view(st), src, new, new_blob,
                         st.head_base[2] if st.head_base else old_path, path, merged, conflicts,
                         dropped), conflicts, content


def stale(st):
    """A file that isn't adaptable differs from the base of its entry in the
    index or the working tree, but neither as a committed adaptation nor
    as a modification of its own (R3) - e.g. the file as in HEAD again
    (git restore --staged) after a pull was staged: pull writes it anew,
    nothing is lost."""
    return not st.adaptable and st.committed != "adapted" and st.where is None and \
        (st.index_adapted or st.local == "modified")


def merged_layers(repo, st):
    """pull (R3): in a layer of an adaptable file, the merge of the file of
    the layer below from that one's base to the layer's own - in the index
    also to the working tree's (pull -W, then git add) - is no modification
    of its own: what pull -W wrote, consistent with its entry. Merged again
    to tell (only here, not for status); in the working tree also HEAD's
    (pull, then git restore --staged or git filesync restore -S). st.own
    updated."""
    if not st.adaptable or not st.own:
        return
    work = (st.old_blob, st.link.path, st.src)
    head = (st.head_blob, st.bases[0])
    below = {"index": ([head], [st.bases[1], work], st.index_blob),
             "worktree": (list(dict.fromkeys([(st.index_blob, st.bases[1]), head])), [work], None)}
    own = []
    for layer in st.own:
        lower, targets, have = below[layer]
        have = have or repo.worktree_blob(repo.top / st.rel)
        if not any(oid and base and merges_to(
                repo, st, oid, base, [t for t in targets if t and t[0] and t != base], have)
                   for oid, base in lower):
            own.append(layer)
    st.own = tuple(own)


def merges_to(repo, st, oid, base, targets, have):
    """Is the file have (blob id) the clean merge of the file oid of this
    repository, with base (blob, upstream path, Source), to one of the
    targets?"""
    try:
        ours = repo.read_content(oid, st.rel)
        old = repo.normalize(base[2].read_content(base[0], base[1]), st.rel)
        for t in targets:
            theirs = repo.normalize(t[2].read_content(t[0], t[1]), st.rel)
            conflicts, content = merge3(ours, old, theirs, ["ours", "base", "theirs"])
            if not conflicts and repo.blob_ids([(st.rel, content)])[st.rel] == have:
                return True
    except FsError:
        pass
    return False


def local_changes(st):
    """Uncommitted changes pull would overwrite (as for `git pull`): a
    modification of its own in the index or the working tree (R3, see
    local_state) - not what a pull or restore wrote there, which it gets
    again."""
    return st.where is not None


def message_view(st):
    """st as it is from HEAD's base (st.head_base) - what the proposed
    commit message of a pull goes from (R3)."""
    if not st.head_base:
        return st
    commit = st.head_base[0]
    return dc_replace(st, old=commit, old_blob=st.head_base[1], count_args=(), behind_args=(),
                      has_old=bool(commit) and st.src.resolve(commit) == commit)


def local_content(repo, st):
    """The working tree file's content in this repository's stored form, LFS
    resolved: what pull merges with (its adaptations against its entry's
    base; R3: nothing of its own, else refused)."""
    if st.worktree == "clean":
        return repo.read_content(st.head_blob, st.rel)
    return repo.read_content(repo.worktree_blob(repo.top / st.rel, write=True), st.rel)


def overwrites(st, args):
    """pull --overwrite has something to do even without an upstream
    change: local adaptations, committed, staged or not."""
    return args.overwrite and not st.missing and \
        (st.local == "modified" or st.committed == "adapted" or st.index_adapted)


def synced_text(args):
    """What pull did to a file: synced - or with -W only written."""
    return paint("updated in the working tree only" if args.worktree else "synced", "green")


def loses(repo, st, content, args):
    """Would writing content (None: deleting) discard uncommitted content -
    the working tree file, or the staged one (not with -W)? As the real
    run decides it (see save_discarded)."""
    if not has_content(repo, st.rel, content):
        return True
    oid = repo.staged().get(st.rel, False)
    return oid is not False and not args.worktree and \
        (oid is None or oid != repo.blob_ids([(st.rel, content)])[st.rel])


def has_content(repo, rel, content):
    """Does the working tree file have exactly this content (in the form
    stored here, see Repo.write_files) - nothing lost when it is written?"""
    path = repo.top / rel
    if content is None or not path.is_file():
        return False
    data = path.read_bytes()
    if repo.plain_content(rel, content) and repo.plain_content(rel, data):
        return data == content            # stored as they are (see Repo.plain_content)
    return repo.blob_ids([(rel, content)])[rel] == repo.worktree_blob(path)


def sync_content(repo, st, new, new_blob, path, merge, rel=None, old_path=None):
    """Content of a linked file synced to upstream version new_blob (at
    path, commit new), in this repository's stored form: upstream's, or
    merged with the local adaptations (merge). Returns (content, merged,
    conflicts). rel, old_path: the file and its upstream path if renamed
    (a [dir] entry's file renamed upstream: it moves along)."""
    src, rel = st.src, rel or st.rel
    # all versions in this repo's normalized form, so that differing eol
    # conventions (and LFS) upstream and here don't matter
    theirs = repo.normalize(src.read_content(new_blob, path), rel)
    if not merge:
        return theirs, False, 0
    try:
        base = repo.normalize(src.read_content(st.old_blob, old_path or st.link.path), rel)
    except FsError:
        raise FsError(f"{st.rel}: base version {st.old_blob[:12]} unavailable; "
                      "cannot merge local modifications - 'git filesync pull --overwrite "
                      f"{path_arg(repo, st.rel)}' takes the upstream version, discarding "
                      "them")
    ours = local_content(repo, st)
    conflicts, content = merge3(ours, base, theirs,
                                [f"{rel} (local)", f"upstream {synced_label(st)}",
                                 f"upstream {src.short(new)}"])
    return content, True, conflicts


def first_sync(repo, st, args, new, path):
    """pull of a new link (no base yet, see Link.unsynced) does what add
    would do: the version pulled becomes the base (see find_base); an
    existing file must be that version - else refused as by add:
    --overwrite takes the upstream version, an adaptable file keeps its
    differences as adaptations. Returns as pull_one; content None: the
    existing file is staged as it is."""
    link, src = st.link, st.src
    commit, blob, content, modified, replace = find_base(
        repo, src, new, st.rel, path, link.target, args.overwrite)
    if modified and not st.adaptable:
        rel = path_arg(repo, st.rel)
        raise FsError(f"{st.rel}: not synced yet, and differs from upstream {src.short(new)} - "
                      f"use 'git filesync pull --overwrite {rel}' to take the upstream "
                      f"version, or 'git filesync set --adaptable {rel}' to keep it (the "
                      "differences become local adaptations)")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")
    note = "existing file replaced" if replace else "fetched" if content is not None else \
        "existing file, with local adaptations" if modified else "existing file"
    if args.dry_run:
        once = f"; {st.once} once" if st.once else ""
        print(f"{st.rel}: would sync to {link.name}@{src.short(commit)} "
              f"(not synced yet; {note}{once})")
        return None
    if content is not None:
        content = repo.normalize(content, st.rel)
    # kept by the caller, for all files at once (see save_discarded)
    st.discards = ([st.rel] if replace else [], [st.rel] if args.overwrite else [])
    link.set("commit", commit)
    link.set("blob", blob)
    print(f"{st.rel}: {synced_text(args)} (first sync; {note})")
    plan = [Planned(st.rel, path, commit, blob, content, modified, replace)]
    return build_add_message(plan, src, link.name, link.url, link.ref, path, False,
                             st.adaptable, commit), 0, content


def few(repo, sts, n=3):
    """'a.c, b.c and 2 more' - files named in a message."""
    names = [shown(repo, st.rel) for st in sts]
    return and_list(names) if len(names) <= n else \
        ", ".join(names[:n]) + f" and {len(names) - n} more"


def plan_dir_sync(repo, src, dlink, rev, overwrite):
    """The first sync of a [dir] entry to upstream revision rev, as add
    does it: (commit, tree, [Planned]) - every file of the upstream
    directory the patterns select; a file already here is compared with it
    (see compare_existing). The commit is the last that changed the
    directory, the tree its upstream tree there."""
    path = dlink.path
    tree, files = src.files_at(rev, path)
    if not tree:
        raise FsError(f"no directory '{path or '/'}' in {src.label} at {src.short(rev)}")
    upstream = {b: o for b, o in files.items() if dlink.selects(b)}
    commit = src.last_change(rev, path or ".")
    sts = dir_members(repo, dlink, {}, upstream)
    for m in sts:
        blocked = in_the_way(repo.top, m.rel)
        if blocked:
            raise FsError(f"{m.rel}: {blocked}")
    rels = [m.rel for m in sts]
    here = {r for r in rels if (repo.top / r).is_file()}
    repo.check_plain(here)
    repo.worktree_blobs(here)               # compared at once, not with a git each
    src.check_plain(m.new_blob for m in sts if m.rel in here)
    src.read_blobs(m.new_blob for m in sts if overwrite or m.rel not in here)
    plan = [Planned(m.rel, m.new_path, commit, m.new_blob, *compare_existing(
        repo, src, m.rel, m.new_path, m.new_blob, repo.top / m.rel, overwrite)) for m in sts]
    return commit, tree, plan


def plan_note(plan):
    """'3 files: 2 fetched, 1 existing' - what the first sync of a [dir] does."""
    counts = [(sum(1 for p in plan if p.content is not None and not p.replaced), "fetched"),
              (sum(1 for p in plan if p.content is None and not p.modified), "existing"),
              (sum(1 for p in plan if p.modified), "existing with local modifications"),
              (sum(1 for p in plan if p.replaced), "replaced")]
    what = ", ".join(f"{n} {w}" for n, w in counts if n)
    return plural(len(plan), "file") + (f": {what}" if what else "")


def first_sync_dir(repo, st, args):
    """pull of a new [dir] entry (no base yet, or the base unavailable)
    does what add does (see plan_dir_sync): an existing file that differs
    is refused unless the entry is adaptable (its differences become
    adaptations) or --overwrite. Returns as pull_dir."""
    dlink, src = st.link, st.src
    name = dlink.shown_rel
    commit, tree, plan = plan_dir_sync(repo, src, dlink, st.target if st.once else st.tip,
                                       args.overwrite)
    modified = [p for p in plan if p.modified]
    if modified and not st.adaptable:
        arg = path_arg(repo, dlink.rel)
        raise FsError(f"{name}: not synced yet, and {few(repo, modified)} "
                      f"differ{'s' if len(modified) == 1 else ''} from upstream "
                      f"{src.short(commit)} - use 'git filesync pull --overwrite {arg}' to take "
                      f"the upstream versions, or 'git filesync set --adaptable {arg}' to keep "
                      "them (the differences become local adaptations)")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")
    note = plan_note(plan)
    if args.dry_run:
        once = f"; {st.once} once" if st.once else ""
        print(f"{name}: would sync to {dlink.name}@{src.short(commit)} "
              f"(not synced yet; {note}{once})")
        return None
    # kept by the caller, for all files at once (see save_discarded)
    st.discards = ([p.rel for p in plan if p.replaced],
                   [p.rel for p in plan] if args.overwrite else [])
    dlink.drop_synced()
    dlink.set("commit", commit)
    dlink.set("tree", tree)
    print(f"{name}: {synced_text(args)} (first sync; {note})")
    msg = build_add_message(plan, src, dlink.name, dlink.url, dlink.ref, dlink.path, False,
                            st.adaptable, commit, entry=name)
    contents = {p.rel: None if p.content is None else repo.normalize(p.content, p.rel)
                for p in plan}
    return msg, [], contents, []


def retarget_dir(repo, st, rev):
    """pull --commit / -b / --tag of a [dir] entry: the upstream directory
    at revision rev instead of the head of its branch (or its tag)."""
    dlink, src = st.link, st.src
    new = src.require(rev)
    tree, files = src.files_at(new, dlink.path)
    if not tree:
        raise FsError(f"no directory '{dlink.path or '/'}' at {rev}")
    st.tip, st.new_tree, st.moved = new, tree, None
    base = {m.link.below: m.old_blob for m in st.base_members}
    upstream = {b: o for b, o in files.items() if dlink.selects(b)}
    fill_members(repo, st, base, upstream)
    st.changed = st.no_base or upstream != base
    st.new = src.last_change(new, dlink.path or ".")
    for m in st.members:
        m.new = st.new


def pull_dir(repo, reg, st, args):
    """Sync a [dir] entry - all its files or none: changed ones as pull_one
    does it (adaptations merged), new upstream ones fetched, those deleted
    upstream deleted here; files of this repository below it stay. Returns
    (its part of the commit message, files with merge conflicts, {rel:
    content}, files to delete), or None if there is nothing to do (or only
    a dry run)."""
    dlink, src = st.link, st.src
    name, arg = dlink.shown_rel, path_arg(repo, dlink.rel)
    if st.once:
        retarget_dir(repo, st, st.target)
    elif st.moved:
        raise FsError(f"{name}: '{st.moved[1]}' was deleted in {src.label} "
                      f"({src.short(st.moved[2])}) - keep the files with "
                      f"'git filesync unlink {arg}', or delete them too with "
                      f"'git filesync rm {arg}'")
    if st.unsynced or st.no_base:
        return first_sync_dir(repo, st, args)
    # a missing file is never allowed - unless upstream deleted it too
    missing = [m for m in missing_members(st) if m.new_blob]
    if missing:
        raise FsError(f"{name}: {of_files(st, missing_members(st))} missing "
                      f"({few(repo, missing)}) - bring them back with "
                      "'git filesync restore <file>...', or remove the link with "
                      f"'git filesync unlink {arg}'")
    if st.violation and not args.overwrite and not stale(st):
        ways = f", or sync anyway with 'git filesync pull --overwrite {arg}'" + (
            f"; or allow them with 'git filesync set --adaptable {arg}'"
            if st.worktree == "clean" else "; only the uncommitted ones: 'git restore -SW <file>...'")
        raise FsError(f"{name}: {violation_text(st)} - inspect with "
                      f"'git filesync diff {arg}'; discard them with "
                      f"'git filesync restore -SW {arg}'{ways}")
    back = [m for m in st.base_members if (overwrites(m, args) or stale(m))
            and m.new_blob == m.old_blob]
    dels = [m for m in st.dels if m.local != "missing"]
    # (other patterns, also if they only drop files gone here already: synced-* go)
    as_staged = args.worktree or staged_as_is(repo, dlink)
    if not (st.mods or st.dels or st.adds or back) and st.new == st.old \
            and not dlink.repatterned and as_staged:
        print(f"{name}: {paint('up to date', 'green')}"
              + (" (adaptations kept)" if st.committed == "adapted" else ""))
        return None
    # like `git pull`: uncommitted changes are never merged into a sync -
    # with --overwrite, they are discarded (and kept, see save_discarded)
    # (what pull -W wrote before: the files staged as they are, see below)
    taken = {id(m) for m in st.mods + back + dels}
    restaged = [] if as_staged else [m for m in st.base_members if m.local != "missing"
                                    and id(m) not in taken]
    dirty = [m for m in st.mods + dels + back + restaged if local_changes(m)]
    if dirty and not args.overwrite:
        raise FsError(f"your local changes to {few(repo, dirty)} would be overwritten by "
                      "pull - commit or stash them first ('git stash'; 'git restore -SW "
                      "<file>...' discards them), or take the upstream version with "
                      f"'git filesync pull --overwrite {arg}'")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")
    for m in st.members:
        for w in m.warnings:
            warn(f"{m.rel}: {w}")

    contents, notes, refused = {}, {}, []     # notes: rel -> what happened
    kinds = {}                # rel -> 'new' | 'deleted' | 'renamed' | 'changed', for the summary
    conflicted, discarded = [], []
    # files the patterns no longer select (set changed them) go like those
    # deleted upstream, newly selected ones come like new ones upstream
    base_files, up_files = src.tree_files(dlink.tree) or {}, src.tree_files(st.new_tree) or {}
    gone = {m.rel: "no longer selected by the patterns" if m.link.below in up_files else
            "deleted upstream" for m in st.dels}
    # deleted here and upstream: the deletion staged too, if it isn't yet
    deletes = [m.rel for m in st.dels if m.local == "missing"]
    notes.update((r, f"{gone[r]}, gone here already") for r in deletes)
    kinds.update((r, "deleted") for r in deletes)
    adds = {m.link.below: m for m in st.adds}
    for m in dels:
        if m.local == "modified" and not args.overwrite:
            # adapted, and renamed upstream within the directory: the
            # adaptations move along, as for a linked file
            moved = src.follow(st.old, st.tip, m.link.path) \
                if st.has_old and gone[m.rel] == "deleted upstream" else None
            to = moved and moved[0] == "renamed" and next(
                (a for a in adds.values() if a.link.path == moved[1] and a.local == "missing"),
                None)
            if to:
                del adds[to.link.below]
                contents[to.rel], _, n = sync_content(repo, m, st.new, to.new_blob, to.new_path,
                                                      True, rel=to.rel)
                deletes.append(m.rel)
                notes[to.rel] = f"renamed upstream from {m.rel}, adaptations merged"
                kinds[to.rel] = "renamed"
                if n:
                    conflicted.append(to.rel)
            elif args.force:
                notes[m.rel] = f"{gone[m.rel]}, kept as a file of this repository"
                kinds[m.rel] = "deleted"           # from the entry
            else:
                refused.append((m, f"{gone[m.rel]}, but adapted here"))
            continue
        deletes.append(m.rel)
        notes[m.rel] = gone[m.rel] + (", local adaptations discarded"
                                      if m.committed == "adapted" else "")
        kinds[m.rel] = "deleted"
    for m in adds.values():
        new = "now selected by the patterns" if m.link.below in base_files else \
            "new upstream"
        if m.local == "missing":
            contents[m.rel] = sync_content(repo, m, st.new, m.new_blob, m.new_path, False)[0]
            notes[m.rel], kinds[m.rel] = new, "new"
            continue
        content, modified, replaced = compare_existing(
            repo, src, m.rel, m.new_path, m.new_blob, repo.top / m.rel, args.overwrite)
        if modified and not (args.force and st.adaptable):
            refused.append((m, f"{new}, but another file is here"
                            + ("" if st.adaptable else " (not adaptable: only --overwrite)")))
            continue
        contents[m.rel] = None if content is None else repo.normalize(content, m.rel)
        notes[m.rel] = f"{new}, replacing the file here" if replaced else \
            f"{new}, existing file kept, with local adaptations" if modified else \
            f"{new}, existing file"
        kinds[m.rel] = "new"
        if replaced:
            discarded.append(m.rel)
    if not as_staged and not args.dry_run:
        # the index gets what the working tree has (pull -W before): the
        # files staged as they are, those only the staged entry has go
        todo = [m for m in restaged if m.rel not in contents]
        now = repo.worktree_blobs([m.rel for m in todo])
        for m in todo:            # one of its own: only with --overwrite (see above)
            contents[m.rel] = sync_content(repo, m, st.new, m.new_blob, m.new_path, False)[0] \
                if local_changes(m) else None
            if local_changes(m) or now.get(m.rel) != m.index_blob:    # (for the summary)
                kinds[m.rel] = "new" if m.index_blob is None else "changed"
        for rel in staged_only(repo, dlink, {m.rel for m in st.members}, src):
            if rel not in contents and rel not in deletes:
                deletes.append(rel)
                kinds[rel] = "deleted"
    backs = {id(m) for m in back}
    for m in st.mods + back:
        mod = m.local == "modified"
        discard = args.overwrite and mod
        contents[m.rel], merged, n = sync_content(repo, m, st.new, m.new_blob, m.new_path,
                                                  mod and st.adaptable and not discard)
        dropped = args.overwrite and m.committed == "adapted"     # in the commit
        notes[m.rel] = (f"{n} merge conflict(s)" if n else "adaptations merged") if merged \
            else ("restored, local adaptations discarded" if dropped else "restored") \
            if id(m) in backs else "local adaptations discarded" if dropped else "changed upstream"
        kinds[m.rel] = "changed"
        if n:
            conflicted.append(m.rel)
    if refused:
        raise FsError("".join(f"{m.rel}: {why}\n" for m, why in refused[:-1])
                      + f"{refused[-1][0].rel}: {refused[-1][1]} - use 'git filesync pull "
                      f"--overwrite {arg}' to take what upstream has, or --force to keep "
                      "the files of this repository")
    counts = [(sum(1 for k in kinds.values() if k == w), w)
              for w in ("new", "deleted", "renamed", "changed")]
    summary = ", ".join(f"{n} {w}" for n, w in counts if n) or "no file changed"
    merged = [r for r, v in notes.items() if "merge" in v]
    if args.dry_run:
        lost = any(loses(repo, m, contents.get(m.rel), args)
                   for m in dirty)          # with --overwrite only (see above)
        what = ([f"{st.once} once"] if st.once else []) + [summary] + \
            (["discarding uncommitted changes"] if lost else []) + \
            ([paint(f"merge conflicts in {len(conflicted)}", "boldred") if conflicted else
              "adaptations merged cleanly"] if merged else [])
        print(f"{name}: would sync to {dlink.name}@{src.short(st.new)} ({'; '.join(what)})")
        if conflicted:
            print(f"hint: compare the adaptations ('git filesync diff {arg}') with the "
                  f"upstream changes ('git filesync diff --upstream{target_opts(args)} {arg}')")
        return None
    # kept by the caller, for all files at once (see save_discarded)
    if args.overwrite:      # uncommitted changes discarded too
        changed = {m.rel for m in st.members if m.local == "modified"}
        discarded += [r for r, c in contents.items() if c is not None and r in changed]
    st.discards = (discarded + deletes, discarded + deletes)
    dlink.drop_synced()
    dlink.set("commit", st.new)
    # the directory at that commit (upstream may have changed only files
    # the patterns leave out since: the synced commit stays)
    dlink.set("tree", src.tree_at(st.new, dlink.path) or st.new_tree)
    if conflicted:
        status = paint("merge conflicts in " + few(
            repo, [m for m in st.members if m.rel in conflicted]), "boldred")
    else:
        status = synced_text(args)
    print(f"{name}: {status} ({summary}"
          + (", adaptations merged" if merged and not conflicted else "") + ")")
    msg = None
    if not args.worktree:         # (no proposed message with -W)
        msg = build_dir_message(st, src, head_notes(st, notes) if st.head_base else notes)
    return msg, conflicted, contents, deletes


def head_notes(st, notes):
    """The files of a [dir] entry's pull for its proposed message, named as
    from what is committed (R3), its base in HEAD (st.head_base) - not from
    the working tree's entry, which pull writes from: new, changed or
    deleted between that base and the new one. The notes of what pull does
    to a file beyond that (merged, kept, ...) stay."""
    head = st.layer_files[0] or {}
    after = {m.link.below: m.new_blob for m in st.members if m.new_blob}
    plain = ("new upstream", "changed upstream", "deleted upstream")
    notes = {r: n for r, n in notes.items() if n not in plain}
    for below in sorted(set(head) | set(after)):
        rel = join_rel(st.link.rel, below)
        if rel not in notes and head.get(below) != after.get(below):
            notes[rel] = "new upstream" if below not in head else \
                "deleted upstream" if below not in after else "changed upstream"
    return notes


def build_dir_message(st, src, notes):
    """The proposed commit message of a [dir] entry's sync: the upstream
    commits that changed the directory, and its files that changed."""
    dlink = st.link
    lines = [f"{MSG_PREFIX}Sync {dlink.shown_rel} from {dlink.name}@{src.dated(st.new)}", "",
             upstream_line(src, dlink.url, dlink.ref, up_join(dlink.path, "") or "/")]
    lines += history_lines(message_view(st), src, st.new, [dlink.path or "."])
    if notes:
        lines += [""] + [f"- {rel} ({note})" for rel, note in sorted(notes.items())]
    if any("conflict" in v for v in notes.values()):
        lines += ["", "Merged with local modifications of this repository "
                  "(conflicts resolved manually)."]
    return "\n".join(lines) + "\n"


SYNC_KEYS = ("commit", "blob", "tree", "synced-include", "synced-exclude")


def sync_keys(values):
    """What an entry (its keys; None: none) records of its sync: its base."""
    return None if values is None else tuple(values.get(k, "") for k in SYNC_KEYS)


def staged_as_is(repo, link):
    """Has the index the entry with the base the working tree has (what a
    pull before -W synced it to)? Then, with the files, it is staged."""
    staged = repo.registry("index").store("dir" if link.is_dir else "file").get(link.rel)
    return sync_keys(staged) == sync_keys(link.v)


def staged_only(repo, dlink, mine, src=None):
    """Files of a [dir] entry that only its staged version has (another base
    there, e.g. after pull -W), not among mine (rels), gone from the working
    tree: still in the index, they go with the pull or rm that stages the
    entry. One still there is a file of this repository (pull -W --force
    kept it): it stays. src: dlink's Source, if at hand."""
    staged = repo.registry("index").entry(dlink.rel)
    if staged is None or not staged.is_dir or sync_keys(staged.v) == sync_keys(dlink.v):
        return []
    src = layer_source(repo, src, dlink, staged)      # (in its own upstream repository)
    if src is None:
        return []
    try:
        base = dir_base(src, staged) or {}
    except FsError:
        return []
    rels = [r for r in (join_rel(dlink.rel, b) for b in base)
            if r not in mine and not os.path.lexists(repo.top / r)]
    return sorted(repo.index_entries(rels)) if rels else []


def entries_text(rels):
    """'2 files and 1 directory' - the entries rels ('src/' for a [dir])."""
    dirs = sum(1 for r in rels if r.endswith("/"))
    return and_list([plural(n, w) for n, w in ((len(rels) - dirs, "file"),
                                                (dirs, "directory")) if n])


def pull_message(parts, names, rels):
    """The commit message of a pull: an entry's own message, or for several
    a subject over all and each entry's message as a section of it."""
    if len(parts) == 1:
        return parts[0]
    sources = sorted(set(names))
    what = f"from {sources[0]}" if len(sources) == 1 else f"from {len(sources)} sources"
    return f"{MSG_PREFIX}Sync {entries_text(rels)} {what}\n\n" + \
        "\n".join(m[len(MSG_PREFIX):] if m.startswith(MSG_PREFIX) else m for m in parts)


def newest_hint(rels, tag, line, newest):
    """Hint after pull at newer tags for the files pinned to tag."""
    files = rels[0] if len(rels) == 1 else plural(len(rels), "file")
    return (f"hint: {files} pinned to tag {tag}; the newest tag on branch {line} is "
            f"{newest_text(newest, line)} (use 'git filesync set --tag "
            f"{newest[0][0][0]} <file>...' and pull to switch)")


def write_synced(repo, contents, conflicted=(), stage=True):
    """Write the synced or linked files ({rel: content in this repository's
    stored form}) to the working tree and stage them (unless not stage:
    pull -W), all at once - those with merge conflicts only written (see
    Repo.write_files); content None: an existing file linked (add) or
    synced for the first time, staged as it is - also if ignored, as
    written ones are: linking a file means tracking it."""
    repo.write_files([(r, c) for r, c in contents.items()
                      if c is not None and r not in conflicted], stage)
    repo.write_files([(r, c) for r, c in contents.items() if r in conflicted], stage=False)
    kept = [r for r, c in contents.items() if c is None]
    if kept and stage:
        repo.git(["add", "-f", "--"] + [lit(r) for r in kept])


def nothing_staged(repo, rels):
    """Are these files and .git-filesync staged as they are in HEAD - nothing
    to commit? False without a commit."""
    staged = repo.staged_changes()
    return staged is not None and not staged.keys() & (set(rels) | {REGISTRY})


def report_pull(repo, reg, synced, written):
    """The files a pull synced are staged with their entries (those with
    merge conflicts once resolved), like `git merge --squash`; one proposed
    commit message for all of them, which a plain `git commit` offers.
    written: the files written (and deleted)."""
    reg.finish()
    rels = [rel for rel, _, _, _ in synced]
    msg = pull_message([m for _, _, m, _ in synced], [name for _, name, _, _ in synced], rels)
    name = rels[0] if len(rels) == 1 else entries_text(rels)
    conflicted = [r for _, _, _, c in synced for r in c]
    if conflicted:
        add = " ".join(path_arg(repo, r) for r in conflicted)
        print(f"{paint('merge conflicts', 'boldred')} - resolve them, then run:\n"
              f"    git add {add}\n    git commit\n{commit_hint(repo, msg)}")
        return EXIT_PENDING
    if nothing_staged(repo, written):    # e.g. pull --overwrite of uncommitted changes only
        print(f"{name}: {paint('restored', 'green')} - the same as committed, nothing to commit")
        return EXIT_OK
    report_staged(repo, name, msg, paint("staged", "green"))
    return EXIT_OK


def to_sync(repo, st, args):
    """Has pull something to do for st (by name or with --all): an upstream
    change, adaptations to discard (--overwrite), a stale file to write anew,
    the entry to stage?"""
    return st.pending or overwrites(st, args) or stale(st) or restage(repo, st, args)


def restage(repo, st, args):
    """pull has to stage the entry as the working tree has it (written
    there by pull -W, add -W): not with -W, not for a new link."""
    return not args.worktree and not st.unsynced and not st.missing and \
        not staged_as_is(repo, st.link)


def cmd_pull(ctx, repo, args):
    reg = Registry(repo)
    reg.dry_run = args.dry_run
    if args.all:
        links = reg.links()
    elif args.files:
        links = select_links(repo, reg, args.files, whole=True)
    else:
        raise FsError("specify file(s) or --all")
    if args.all and args.files:
        raise FsError("--all cannot be combined with paths")
    check_target_args(args)
    rc, done, moved = EXIT_OK, 0, False
    once = args.commit or args.branch or args.tag   # another revision, branch or tag, once
    prefetch(ctx, repo, links, new_links=not once)
    newest, synced = {}, []             # synced: (rel, source, message, [conflicted])
    left_out = False                    # pull --all: not synced, but to be seen to
    contents = {}                       # rel -> synced content (normalized form)
    deletes = []                        # files deleted with a [dir] entry's sync
    states = [evaluate(ctx, repo, link) for link in links]
    # what syncing needs, asked at once: upstream contents, short commit ids,
    # attributes of the files here
    repo.check_plain([st.rel for st in states if not st.link.is_dir]
                     + [m.rel for st in states if st.link.is_dir for m in st.members])
    items = []
    ok = [st for st in states if st.src and not st.error]
    # contents only of the files to sync (in the blobless cache, each one
    # may have to be fetched)
    sync = [st for st in ok if to_sync(repo, st, args)
            and not (args.all and not once and st.off_track)]
    files = [m for st in sync for m in (st.members if st.link.is_dir else [st])]
    for src in {id(st.src): st.src for st in ok}.values():
        # (and the bases of the layers below, to merge again: see merged_layers)
        src.read_blobs(b for st in files if st.src is src for b in (st.old_blob, st.new_blob)
                       + (tuple(x[0] for x in st.bases if x and x[2] is src)
                          if st.adaptable and st.own else ()))
        src.shorts(c for st in ok if st.src is src for c in (st.old, st.new))
        src.dates(c for st in sync if st.src is src
                  for c in (st.old if st.has_old else None, st.new,
                            st.head_base[0] if st.head_base else None))
    for st in files:
        try:
            if st.new_blob and st.new_blob != st.old_blob:
                items.append((st.src.read_content(st.new_blob, st.new_path), st.rel))
        except FsError:
            pass
    repo.normalize_many(items)
    for st in sync:               # what pull -W merged: nothing of its own
        for m in st.base_members if st.link.is_dir else [st]:
            merged_layers(repo, m)
        if st.link.is_dir:
            st.own = dir_own(st.base_members)
    for link, st in zip(links, states):
        if st.error:
            report_error(st)
            rc = EXIT_ERROR
            continue
        if st.newest and not once:
            newest.setdefault((link.name, link.tag), (link.tag, link.line, st.newest, []))[3] \
                .append(link.rel)
        # missing, modified but not adaptable, or not a plain update along
        # the history (older, diverged, the previous sync point unknown):
        # only by name (or once to a given revision)
        if args.all and not once and (st.off_track or not (
                to_sync(repo, st, args))):
            why = "missing" if st.missing else "previous sync point not found" \
                if st.lost_old else "older than last sync" if st.behind_args \
                else "history diverged" if st.diverged \
                else "modified, but not adaptable" if st.violation else None
            if why:           # as in git-assetsync
                warn(f"{st.rel}: {why} - left out (see 'git filesync status')")
                left_out = True
            continue
        done += 1
        if args.verbose:
            at = "not synced yet" if st.unsynced else \
                f"synced at {synced_label(st)}"
            print(paint(f"{st.rel}: {link_text(st)}, {at}", "dim"))
        try:
            if once:
                st.target, st.once = target_rev(ctx, link, args), once_text(args)
            before = link.commit
            if link.is_dir:
                result = pull_dir(repo, reg, st, args)
            else:
                result = pull_one(repo, reg, st, args)
                if result:
                    msg, conflicts, content = result
                    result = msg, [st.rel] if conflicts else [], {st.rel: content}, []
            if result:
                reg.whole.add(link.rel)       # staged with its files (see Registry.stage)
                synced.append((link.shown_rel, link.name) + result[:2])
                contents.update(result[2])
                deletes += result[3]
            moved = moved or once and link.commit != before
        except FsError as e:   # report and carry on with the other files
            error(str(e) if str(e).startswith(st.rel) else f"{st.rel}: {e}")
            rc = EXIT_ERROR
    if synced:
        worktree = [r for st in states for r in st.discards[0]]
        index = [] if args.worktree else [r for st in states for r in st.discards[1]]
        # nothing lost where the file gets what it has (e.g. pulled with -W before)
        save_discarded(repo, worktree, index, repo.blob_ids(
            [(r, contents[r]) for r in dict.fromkeys(worktree + index)
             if contents.get(r) is not None]))
        for part in chunks([] if args.worktree else deletes):
            repo.git(["rm", "-q", "-f", "--ignore-unmatch", "--"] + [lit(r) for r in part])
        for r in deletes:
            if (repo.top / r).is_file():       # never added to git, or -W
                (repo.top / r).unlink()
        write_synced(repo, contents, {r for _, _, _, c in synced for r in c},
                     stage=not args.worktree)
        if args.worktree:       # only written, the entries too: each said so
            reg.finish(stage=False)
            rc = max(rc, EXIT_PENDING if any(c for _, _, _, c in synced) else EXIT_OK)
        else:
            rc = max(rc, report_pull(repo, reg, synced, list(contents) + deletes))
    if moved and not args.dry_run and not args.commit and not args.worktree:
        opt = f"--tag {args.tag}" if args.tag else f"-b {args.branch}"
        how = f"'git filesync set <file>... {opt}'"
        print(f"hint: the links still follow their own branch or tag, so 'git filesync pull "
              f"<file>...' goes back; to stay on {once_text(args)}, use {how}")
    if args.all and not done and not left_out and rc == EXIT_OK:
        print(paint("everything up to date", "green"))
    for _, (tag, line, new, rels) in sorted(newest.items()):
        print(newest_hint(rels, tag, line, new))
    return rc


def diff_pairs(ctx, repo, args):
    """(st, name, base, other) blob ids for every linked file with a difference.
    base = last synced upstream version (None: a new link, --upstream);
    other = local file (None if missing),
    or with --upstream the upstream version pull would sync to (with the same
    --commit / -b / --tag; None: deleted there, for a [dir] entry's file).
    All as actual content in this repo's normalized form (LFS resolved), so
    eol conventions and LFS pointers don't show up. A [dir] entry: each of
    its files (or those given), its own files left out."""
    once = args.commit or args.branch or args.tag
    if once and not args.upstream:
        raise FsError("--commit, -b and --tag require --upstream")
    rc = EXIT_OK
    pairs = []
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    check_target_args(args)
    prefetch(ctx, repo, links)
    states, files = [evaluate(ctx, repo, link) for link in links], []
    check_only(states)
    for link, st in zip(links, states):
        if st.error:
            report_error(st)
            rc = EXIT_ERROR
        elif not link.is_dir:
            files.append(st)
        else:
            try:
                if args.upstream and once:
                    retarget_dir(repo, st, target_rev(ctx, link, args))
            except FsError as e:
                error(f"{st.rel}: {e}")
                rc = EXIT_ERROR
                continue
            files += [m for m in st.members if link.only is None
                      or any(is_below(m.rel, o) for o in link.only)]
    repo.check_plain(st.rel for st in files)
    if args.upstream and not once:
        items = []
        for st in files:
            if st.src and st.new_blob and st.new_blob != st.old_blob:
                try:
                    items.append((st.src.read_content(st.new_blob, st.new_path), st.rel))
                except FsError:
                    pass
        repo.normalize_many(items)
    worktree_ids = {}
    if not (args.upstream or args.committed or args.cached):  # the working tree files, at once
        worktree_ids = repo.worktree_blobs(
            st.rel for st in files if st.local not in ("clean", "missing")
            and not repo.plain_content(st.rel, st.link.target.read_bytes()))
        repo.read_blobs(worktree_ids.values())
    for st in files:
        link, member = st.link, isinstance(st.link, Member)
        if args.upstream:
            if once and not member:
                try:
                    st.new, st.new_blob, st.new_path = commit_target(
                        st, target_rev(ctx, link, args))
                except FsError as e:
                    error(f"{st.rel}: {e}")
                    rc = EXIT_ERROR
                    continue
            # unchanged, or deleted upstream (shown for a [dir]'s file)
            if st.new_blob == st.old_blob or not st.new_blob and not member:
                continue
        elif args.cached:             # the index against the base of its entry
            if not st.bases[1] or not st.index_adapted:
                continue
        elif args.committed:
            if st.committed != "adapted":
                continue
        elif st.unsynced:             # no base yet: no local changes against it
            continue
        elif st.local == "clean":
            continue
        # both sides as actual content in this repo's form (LFS resolved),
        # stored all at once below
        try:
            # the base of the layer compared: HEAD's, the index's or the working tree's
            blob, path, bsrc = st.bases[0] or (st.old_blob, link.path, st.src) \
                if args.committed else st.bases[1] if args.cached else \
                (st.old_blob, link.path, st.src)
            try:          # a new link (--upstream): the whole file is new
                base = None if st.unsynced and args.upstream else \
                    repo.normalize(bsrc.read_content(blob, path), st.rel)
            except FsError:
                raise FsError(f"synced version {blob[:12]} unavailable")
            if args.cached:
                other = None if st.index_blob is None else \
                    repo.read_content(st.index_blob, st.rel)
            elif args.upstream:
                other = repo.normalize(st.src.read_content(st.new_blob, st.new_path),
                                       st.rel) if st.new_blob else None
            elif args.committed:
                other = repo.read_content(st.head_blob, st.rel)
            elif st.local == "missing":
                other = None
            else:
                data = link.target.read_bytes()
                other = data if repo.plain_content(st.rel, data) else repo.read_content(
                    worktree_ids.get(st.rel) or repo.worktree_blob(link.target, write=True),
                    st.rel)
        except FsError as e:
            error(f"{st.rel}: {e}")
            rc = EXIT_ERROR
            continue
        name = st.new_path if args.for_upstream else st.rel    # upstream: also after a rename there
        pairs.append((st, name, base, other))
    contents = [c for _, _, base, other in pairs for c in (base, other) if c is not None]
    ids = dict(zip(map(id, contents), repo.store_many(contents)))
    return rc, [(st, name, ids[id(base)] if base is not None else None,
                 ids[id(other)] if other is not None else None)
                for st, name, base, other in pairs]


def make_tree(repo, entries):
    """Tree object with the given (path, blob id) entries, via a temp index."""
    with tempfile.TemporaryDirectory(prefix="filesync-") as td:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(td) / "index"))
        if entries:
            data = "".join(f"100644 {oid}\t{path}\n" for path, oid in entries)
            repo.git(["update-index", "--add", "--index-info"], data=data.encode(), env=env)
        return out(repo.git(["write-tree"], env=env))


def cmd_diff(ctx, repo, args):
    """One `git diff <tree> <tree>` in this repo over all differing files:
    real paths, the repo's diff settings and pager, options after `--`."""
    if args.for_upstream and args.upstream:
        raise FsError("--for-upstream cannot be combined with --upstream")
    rc, pairs = diff_pairs(ctx, repo, args)
    if not pairs:
        return rc
    left = make_tree(repo, [(n, b) for _, n, b, _ in pairs if b])
    right = make_tree(repo, [(n, o) for _, n, _, o in pairs if o])
    if args.for_upstream:
        prefixes = []                  # standard a/ b/: `git apply` upstream
    else:
        prefixes = ["--src-prefix=synced/", "--dst-prefix=" + (
            "upstream/" if args.upstream else "committed/" if args.committed else
            "staged/" if args.cached else "local/")]
    color = {"always": ["--color=always"], "never": ["--no-color"]}.get(args.color, [])
    sys.stdout.flush()
    p = subprocess.run(["git", "diff"] + color + prefixes + args.extra + [left, right],
                       cwd=repo.top)
    if p.returncode in (-13, EXIT_PIPE):       # killed by SIGPIPE: like our own output
        PipeGuard.broken = True
    elif p.returncode > 1:
        rc = EXIT_ERROR
    elif p.returncode == 1 and ("--exit-code" in args.extra or "--quiet" in args.extra):
        rc = max(rc, EXIT_PENDING)      # like `git diff --exit-code`: 1 = differences
    return rc


def difftool_prompting(repo, args):
    """Ask before each file like `git difftool`: unless -y/--no-prompt or
    difftool.prompt=false; --prompt asks anyway (the last of them wins)."""
    if args.prompt is not None:
        return args.prompt
    cfg = out(repo.git(["config", "--type=bool", "difftool.prompt"], check=False))
    return cfg != "false"


def difftool_name(repo, extra):
    for i, a in enumerate(extra):              # -t TOOL / --tool=TOOL passed after --
        if a.startswith("--tool="):
            return a.split("=", 1)[1]
        if a in ("-t", "--tool") and i + 1 < len(extra):
            return extra[i + 1]
    for key in ("diff.tool", "merge.tool"):
        name = out(repo.git(["config", key], check=False))
        if name:
            return name
    return "difftool"


def cmd_difftool(ctx, repo, args):
    """Open each differing file in the configured difftool. Without --upstream
    the real working file is passed, so edits made in the tool are kept."""
    rc, pairs = diff_pairs(ctx, repo, args)
    if not (args.upstream or args.committed or args.cached):
        for st, _, _, other in pairs:
            if other is None:
                print(f"{st.rel}: file missing, nothing to compare", file=sys.stderr)
        pairs = [p for p in pairs if p[3] is not None]
    prompt = difftool_prompting(repo, args)
    tool = difftool_name(repo, args.extra)
    with tempfile.TemporaryDirectory(prefix="filesync-") as td:
        for n, (st, name, base, other) in enumerate(pairs, 1):
            if prompt:
                print(f"\nViewing ({n}/{len(pairs)}): '{st.rel}'")
                print(f"Launch '{tool}' [Y/n/q]? ", end="", flush=True)
                answer = sys.stdin.readline()
                if not answer or answer.strip().lower().startswith("q"):   # EOF or quit
                    print()
                    break
                if answer.strip().lower().startswith("n"):
                    continue
            src = st.src

            def tmpfile(label, oid):
                f = Path(td) / label / Path(name).name    # keep the extension
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(repo.to_worktree(repo.read_blob(oid), st.rel) if oid else b"")
                return str(f)
            left = tmpfile("not-synced-yet" if st.unsynced else
                           f"synced-{synced_label(st)}", base)
            if args.upstream:
                right = tmpfile(f"upstream-{src.short(st.new)}", other)
            elif args.committed:
                right = tmpfile("committed-HEAD", other)
            elif args.cached:
                right = tmpfile("staged", other)
            else:
                right = str(st.link.target)
            subprocess.run(["git", "difftool", "--no-index", "-y"] + args.extra + [left, right],
                           cwd=repo.top)
    return rc


def glob_regex(pattern):
    """Regex for a gitignore-like pattern, matched against a path relative to
    the upstream directory: without a '/' it matches a name at any depth, a
    leading or inner '/' anchors it, a trailing '/' matches directories only;
    '*' and '?' don't match '/', '**/' matches any number of directories. A
    matching directory stands for everything below it."""
    dir_only = pattern.endswith("/")
    pat = pattern.strip("/")
    anchored = "/" in pattern.rstrip("/")
    rx, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            rx, i = rx + "(?:[^/]*/)*", i + 3
        elif pat.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif pat[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif pat[i] == "?":
            rx, i = rx + "[^/]", i + 1
        elif pat[i] == "[" and "]" in pat[i + 2:]:
            j = pat.index("]", i + 2)
            cls = pat[i + 1:j]
            rx += "[" + ("^" + cls[1:] if cls.startswith("!") else cls).replace("\\", "\\\\") + "]"
            i = j + 1
        else:
            rx, i = rx + re.escape(pat[i]), i + 1
    return re.compile(("" if anchored else "(?:.*/)?") + rx
                      + ("/.*" if dir_only else "(?:/.*)?") + r"\Z", re.S)


def add_ref(ctx, reg, args, hint=None):
    """(url, branch, name) of the source for add and set --source: the
    [source] named by args.source (-b may only repeat its branch), or for a
    URL the one with that URL and branch - name None, found or created
    later. hint: what to do instead of another -b for a named source."""
    if args.source in reg.sources:            # name of an existing [source]
        s = reg.sources[args.source]
        if not s.get("branch"):
            raise FsError(f'[source "{args.source}"] in {REGISTRY} needs a branch')
        if args.branch and args.branch != s["branch"]:
            raise FsError(f"source '{args.source}' follows {s['branch']}, not {args.branch} - "
                          + (hint or "give the URL to link to another branch, or change the "
                             f"source's branch with 'git filesync source set "
                             f"{args.source} -b {args.branch}'"))
        return s.get("url", ""), s["branch"], args.source
    url = registry_url(args.source)
    require_url(reg.repo, url)
    return url, args.branch or ctx.default_branch(url), None


def find_base(repo, src, rev, rel, path, target, overwrite=False):
    """Base of a file to link: upstream path's version at rev (the branch
    head, or --commit). Returns (commit, blob, content to write or None,
    modified, replaced): a missing file gets that version, an existing one
    keeps its content - its differences count as adaptations - unless
    overwrite and it differs (or can't be compared): then it is replaced."""
    blob = src.blob_at(rev, path)
    if not blob:
        raise FsError(f"no file '{path}' in {src.label} at {src.short(rev)}")
    return (src.last_change(rev, path), blob) + \
        compare_existing(repo, src, rel, path, blob, target, overwrite)


def compare_existing(repo, src, rel, path, blob, target, overwrite=False):
    """A file to link to upstream version blob (at path): (content to write
    or None, modified, replaced) - see find_base."""
    cur = repo.worktree_blob(target)
    if cur is None:
        return src.read_content(blob, path), False, False
    try:
        modified = not matches_base(repo, src, rel, blob, path, cur, target.read_bytes)
    except BaseUnavailable:
        if not overwrite:
            raise FsError(f"{rel}: upstream version {blob[:12]} not available, can't compare "
                          "the existing file with it")
        modified = True
    if overwrite and modified:     # replaced only if it differs
        return src.read_content(blob, path), False, True
    return None, modified, False


# a file to link: its path here, upstream path, base commit and blob, content to
# write (None: the existing file is kept), whether it differs from the base,
# whether an existing file is replaced (--overwrite)
Planned = namedtuple("Planned", "rel path commit blob content modified replaced")


def build_add_message(plan, src, name, url, ref, mpath, relink, adaptable, at, entry=None):
    """Commit message for add; plan: [Planned]; at: the upstream revision a
    directory was linked at; entry: a [dir] entry ('src/') with all the
    files of plan."""
    fetched = all(p.content is not None and not p.replaced for p in plan)
    subject_ref = f"{name}@{src.dated(plan[0].commit if plan else at)}"
    if entry:
        path = mpath.rstrip("/") + "/" if mpath else "/"
        what = f"Add {entry} from" if fetched else f"{'Relink' if relink else 'Link'} {entry} to"
    elif len(plan) == 1:
        rel, path = plan[0].rel, plan[0].path
        what = f"Add {rel} from" if fetched else f"{'Relink' if relink else 'Link'} {rel} to"
    else:
        path = mpath.rstrip("/") + "/" if mpath else "/"
        what = f"Add {len(plan)} files from" if fetched else f"Link {len(plan)} files to"
        subject_ref = f"{name}@{src.dated(at)}"
    lines = [f"{MSG_PREFIX}{what} {subject_ref}", "", upstream_line(src, url, ref, path)]
    if len(plan) > 1 or entry and plan:
        lines.append("")
        for p in plan:
            notes = (["replaced"] if p.replaced else [] if p.content is not None else
                     ["existing"]) + (["local modifications"] if p.modified else [])
            lines.append(f"- {p.rel}" + (f" ({', '.join(notes)})" if notes else ""))
    if len(plan) == 1 and plan[0].modified and not entry:
        lines += ["", "Contains local modifications of this repository."]
    if len(plan) == 1 and plan[0].replaced and not entry:
        lines += ["", "The existing file was replaced by the upstream version."]
    if adaptable:
        lines += ["", "Adaptable: local adaptations allowed."]
    return "\n".join(lines) + "\n"


def cmd_add(ctx, repo, args):
    reg = Registry(repo)
    target = repo.user_path(args.file)
    rel = repo.rel(target)
    problem = path_problem(rel) if rel != "." else None
    if problem:
        raise FsError(f"cannot link '{rel}': {problem}")
    url, branch, named = add_ref(ctx, reg, args)
    ref = ("tag", args.tag) if args.tag else ("branch", branch)
    line = branch if args.tag else None
    src = ctx.source(url, ref, named or reg.source_name(url, branch), line)
    head = src.tip()
    at = src.require(args.commit) if args.commit else None    # --commit: given base
    if args.tag:
        warn_tag_line(src, args.tag, branch)
    path = upstream_path(args.path if args.path else rel)
    patterns = args.include or args.exclude
    upstream_file = bool(path) and not patterns and bool(src.blob_at(at or head, path))
    if repo.names_dir(args.file) and upstream_file:
        require_dir(repo, target, rel)          # FILE/: an existing directory, like cp
    if target.is_dir() and upstream_file:       # like cp: into the directory
        target = target / Path(path).name
        rel = repo.rel(target)
    if target.is_dir() or patterns or not upstream_file and src.is_dir(at or head, path):
        # like cp -r: DIR may be new, the directory it goes into must exist
        require_dir(repo, target if target.is_dir() else target.parent, rel)
        if not args.per_file:
            return add_dir(repo, reg, args, src, (url, branch, named), ref, line, at or head,
                           rel, path, target)
        plan, relink = plan_dir(repo, reg, src, args, at or head, rel, path, target)
        if not plan:
            return EXIT_OK
    else:
        if args.per_file:
            raise FsError(f"--per-file: '{path}' in {src.label} is a file, not a directory")
        relink = rel in reg.files
        if relink and not args.force:
            raise FsError(f"'{rel}' is already linked (use --force to relink)")
        if target.is_dir():
            raise FsError(f"cannot link '{rel}': is a directory")
        others = reg.overlapping(rel, "file")
        if others:
            raise FsError(f"cannot link '{rel}': it is in the linked directory {others[0]}")
        require_dir(repo, target.parent, rel)   # like cp
        plan = [Planned(rel, path, *find_base(repo, src, at or head, rel, path, target,
                                              args.overwrite))]
    # an existing file must be the upstream version - unless it may be adapted
    modified = [p for p in plan if p.modified]
    if modified:
        base = src.short(at or head)
        what = modified[0].rel if len(plan) == 1 else \
            plural(len(modified), "existing file") + (f" below {rel}" if rel != "." else "")
        if not args.adaptable:
            it = "it" if len(modified) == 1 else "them"
            raise FsError("".join(f"{p.rel}: differs from upstream {base}\n" for p in modified[:-1])
                          + f"{modified[-1].rel}: differs from upstream {base} - use --adaptable "
                          f"to keep {it} (the differences become local adaptations), --overwrite "
                          f"to take the upstream version, or --commit to base {it} on another one")
        warn(f"{what} differ{'s' if len(modified) == 1 else ''} from upstream {base}; "
             "the differences count as local adaptations")
    rels = [p.rel for p in plan]
    name = named or reg.source_name(url, branch)
    shown_ref = ref_text(ref, line, src.tag_names)
    if args.dry_run:
        for p in plan:
            note = "replacing the existing file" if p.replaced else \
                "fetched" if p.content is not None else \
                "with local modifications" if p.modified else "existing file"
            print(f"would link {p.rel} -> {name}:{p.path} ({shown_ref}), "
                  f"{note}, based on {src.short(p.commit)}")
        return EXIT_OK

    repo.check_plain(rels)
    repo.normalize_many([(p.content, p.rel) for p in plan if p.content is not None])
    save_discarded(repo, [p.rel for p in plan if p.replaced],
                   rels if args.overwrite and not args.worktree else [])
    contents = {}         # rel -> content in this repository's form; None: kept
    for p in plan:
        if p.rel in reg.files:
            reg.remove_file(p.rel, keep_source=named)
        name = named or reg.add_source(url, branch)
        link = Link(reg, p.rel)
        for k, v in (("source", name), ("path", p.path), ("commit", p.commit), ("blob", p.blob)):
            link.set(k, v)
        if args.tag:
            link.set("tag", args.tag)
        if args.adaptable:
            link.set("adaptable", "true")
        contents[p.rel] = None if p.content is None else repo.normalize(p.content, p.rel)
    write_synced(repo, contents, stage=not args.worktree)
    reg.whole.update(rels)        # staged with their files (see Registry.stage)
    reg.finish(stage=not args.worktree)
    only = " - in the working tree only" if args.worktree else ""
    for p in plan:                # said once it is done
        print(f"{paint('linked', 'green')} {p.rel} -> {name}:{p.path} ({shown_ref}){only}")
    if args.worktree:
        return EXIT_OK
    if nothing_staged(repo, rels):
        print(f"{rel}: link{'s' if len(rels) > 1 else ''} and "
              f"file{'s' if len(rels) > 1 else ''} unchanged, nothing to commit")
        return EXIT_OK
    # staged only, like git add; the proposed message is prepared for the commit
    msg = build_add_message(plan, src, name, url, ref, path, relink, args.adaptable, at or head)
    msg_name = rels[0] if len(rels) == 1 else (rel if rel != "." else "root")
    report_staged(repo, msg_name, msg, paint("staged", "green"))
    return EXIT_OK


def add_dir(repo, reg, args, src, where, ref, line, at, rel, path, target):
    """add DIR: one [dir] entry for the files of the upstream directory path
    (at revision at) that --include / --exclude select; an existing file
    there is compared with its upstream version as for add FILE (see
    plan_dir_sync). where: (url, branch, name of the [source] or None)."""
    url, branch, named = where
    if target.exists() and not target.is_dir():
        raise FsError(f"'{rel}' is a file, but '{path or '/'}' in {src.label} is a directory")
    if path and not src.is_dir(at, path):
        raise FsError(f"no directory '{path}' in {src.label} at {src.short(at)}")
    shown_rel = rel.rstrip("/") + "/"
    others = reg.overlapping(rel, "dir")
    if others:
        raise FsError(f"cannot link '{shown_rel}': overlaps with the entry for "
                      f"{and_list(others)} - entries must not overlap (unlink those first; "
                      "their files stay)")
    relink = rel in reg.dirs
    if relink and not args.force:
        raise FsError(f"'{shown_rel}' is already linked (use --force to relink)")
    name = named or reg.source_name(url, branch)
    values = {"source": name, "path": path or "/", "include": join_patterns(args.include or []),
              "exclude": join_patterns(args.exclude or []), "tag": args.tag,
              "adaptable": "true" if args.adaptable else None}
    values = {k: v for k, v in values.items() if v}
    draft = DirLink(reg, rel, values)
    commit, tree, plan = plan_dir_sync(repo, src, draft, at, args.overwrite)
    if not plan:
        print(f"no files to link below '{path or '/'}' in {src.label}")
        return EXIT_OK
    modified = [p for p in plan if p.modified]
    if modified:
        base = src.short(at)
        if not args.adaptable:
            it = "it" if len(modified) == 1 else "them"
            raise FsError("".join(f"{p.rel}: differs from upstream {base}\n" for p in modified[:-1])
                          + f"{modified[-1].rel}: differs from upstream {base} - use --adaptable "
                          f"to keep {it} (the differences become local adaptations), --overwrite "
                          f"to take the upstream version, or --commit to base {it} on another one")
        warn(f"{plural(len(modified), 'existing file')} below {shown_rel} "
             f"differ{'s' if len(modified) == 1 else ''} from upstream {base}; the "
             "differences count as local adaptations")
    shown_ref = ref_text(ref, line, src.tag_names)
    up = up_join(path, "") or "/"
    if args.dry_run:
        print(f"would link {shown_rel} -> {name}:{up} ({shown_ref}), {plan_note(plan)}, "
              f"based on {src.short(commit)}")
        return EXIT_OK
    rels = [p.rel for p in plan]
    repo.check_plain(rels)
    repo.normalize_many([(p.content, p.rel) for p in plan if p.content is not None])
    save_discarded(repo, [p.rel for p in plan if p.replaced],
                   rels if args.overwrite and not args.worktree else [])
    if relink:
        reg.remove_file(rel, keep_source=named)
    values["source"] = name = named or reg.add_source(url, branch)
    entry = DirLink(reg, rel)
    for k, v in list(values.items()) + [("commit", commit), ("tree", tree)]:
        entry.set(k, v)
    write_synced(repo, {p.rel: None if p.content is None else repo.normalize(p.content, p.rel)
                        for p in plan}, stage=not args.worktree)
    reg.whole.add(rel)            # staged with its files (see Registry.stage)
    reg.finish(stage=not args.worktree)
    print(f"{paint('linked', 'green')} {shown_rel} -> {name}:{up} ({shown_ref}), "
          f"{plural(len(plan), 'file')}" + (" - in the working tree only" if args.worktree else ""))
    if args.worktree:
        return EXIT_OK
    if nothing_staged(repo, rels):
        print(f"{shown_rel}: link and files unchanged, nothing to commit")
        return EXIT_OK
    msg = build_add_message(plan, src, name, url, ref, path, relink, args.adaptable, at,
                            entry=shown_rel)
    report_staged(repo, shown_rel, msg, paint("staged", "green"))
    return EXIT_OK


def require_dir(repo, path, rel):
    """add puts rel into an existing directory path only, like cp: a
    mistyped directory isn't created."""
    if path.exists() and not path.is_dir():
        raise FsError(f"cannot add '{rel}': '{repo.rel(path)}' is not a directory")
    if not path.is_dir():
        raise FsError(f"directory '{repo.rel(path)}' does not exist")


def plan_dir(repo, reg, src, args, at, rel, path, target):
    """Files to link for add DIR: every file below the upstream directory path
    at revision at that matches --include/--exclude, as rel/<path below>;
    already linked files are skipped unless --force. Returns (plan, relink)."""
    if target.exists() and not target.is_dir():
        raise FsError(f"'{rel}' is a file, but '{path or '/'}' in {src.label} is a directory")
    if path and not src.is_dir(at, path):
        raise FsError(f"no directory '{path}' in {src.label} at {src.short(at)}")
    include = [glob_regex(p) for p in args.include or []]
    exclude = [glob_regex(p) for p in args.exclude or []]
    todo, skipped = [], []
    for mpath in src.files_below(at, path):
        below = mpath[len(path) + 1:] if path else mpath
        if include and not any(r.match(below) for r in include) or \
                any(r.match(below) for r in exclude):
            continue
        r = below if rel == "." else f"{rel}/{below}"
        problem = path_problem(r)
        if problem or (repo.top / r).is_dir():
            warn(f"skipping {r}: {problem or 'is a directory'}")
        elif reg.overlapping(r, "file"):
            raise FsError(f"cannot link '{r}': it is in the linked directory "
                          f"{reg.overlapping(r, 'file')[0]}")
        elif r in reg.files and not args.force:
            skipped.append(r)
        else:
            todo.append((r, mpath))
    if skipped:
        print(f"{plural(len(skipped), 'file')} already linked, "
              "skipped (use --force to relink)")
    if not todo:
        if not skipped:
            print(f"no files to link below '{path or '/'}' in {src.label}")
        return [], False
    # asked at once: the blobs, and the contents of the files to fetch
    src.blobs_at(at, [p for _, p in todo])
    src.read_blobs([src.blob_at(at, p) for r, p in todo
                    if args.overwrite or not (repo.top / r).is_file()])
    plan = [Planned(r, p, *find_base(repo, src, at, r, p, repo.top / r, args.overwrite))
            for r, p in todo]
    return plan, any(r in reg.files for r, _ in todo)


def save_discarded(repo, worktree, index=(), written=None):
    """Before restore, rm -f or --overwrite replace or delete files - in the
    working tree (paths worktree) and/or the index (paths index): content
    that would be lost - not in HEAD, nor where the index or the working
    tree stays, nor what is written there (written: {rel: blob id}) - is
    kept as a blob (a staged version already is one), and the command
    tells how to get it back (`git show ID > FILE`). Like with `git
    restore`, the files are discarded anyway."""
    worktree, index = list(dict.fromkeys(worktree)), set(index)
    # {rel: {blob ids}} of what isn't lost there
    written = {r: v if isinstance(v, set) else {v} for r, v in (written or {}).items()}
    paths = list(dict.fromkeys(worktree + sorted(index)))
    if not paths:
        return
    repo.prefetch(paths)
    staged = {r: e[1] for r, e in repo.index_entries(paths).items()}
    current = repo.worktree_blobs([r for r in paths if (repo.top / r).is_file()])
    lost = [r for r in worktree if r in current and current[r] not in
            {repo.head_blob(r), None if r in index else staged.get(r)} | written.get(r, set())]
    # a staged version still in the working tree stays there or is kept with it
    gone = [r for r in paths if r in index and staged.get(r)
            and staged[r] not in {repo.head_blob(r), current.get(r)} | written.get(r, set())]
    # kept as the working tree file would be (eol, LFS), so `git show ID >
    # FILE` gives it back exactly; as stored if git can't convert it
    content = {r: (repo.top / r).read_bytes() for r in lost}
    for r in gone:
        p = repo.git(["cat-file", "--filters", f"--path={r}", staged[r]], check=False)
        if p.returncode == 0:
            content[(r, "staged")] = p.stdout
    keys = list(content)
    ids = dict(zip(keys, repo.store_many([content[k] for k in keys])))
    for rel, how, oid in sorted([(r, "", ids[r]) for r in lost]
                                + [(r, ", as staged", ids.get((r, "staged"), staged[r]))
                                   for r in gone]):
        print(f"{paint('discarded:', 'yellow')} {rel}{how} (git show {oid[:12]} to get it back)")


def restore_values(ctx, entry, lower):
    """{key: value (None: none)} of the sync keys (SYNC_KEYS) that make
    entry synced as lower, its entry in the layer below, is - its selection
    stays (as after set; synced-include / -exclude: the patterns of lower's
    base where they differ). In another upstream repository the base gets the
    commit it has there, as for set (see keep_base)."""
    values = {k: lower.v.get(k) for k in SYNC_KEYS}
    if lower.is_dir and entry.is_dir:   # the patterns lower's base was synced with (see set)
        for k in PATTERN_KEYS:
            synced = lower.synced_patterns(k)
            values[f"synced-{k}"] = None if synced == getattr(entry, k) else \
                join_patterns(synced) or ""
    if values["commit"] and norm_url(lower.url) != norm_url(entry.url):
        values["commit"] = translated(ctx.source(entry.url, entry.ref, entry.name, entry.line),
                                      entry, lower.commit, lower.blob,
                                      entry.path) or values["commit"]
    return values


def entry_files(ctx, e):
    """{rel: (Source, blob, upstream path)} of the files at the base of the
    entry e (in any layer; None: no entry); FsError if they aren't known."""
    if e is None or e.unsynced:
        return {}
    src = ctx.source(e.url, e.ref, e.name, e.line)
    if not e.is_dir:
        return {e.rel: (src, e.blob, e.path)}
    base = dir_base(src, e)
    if base is None:
        raise FsError(f"synced tree {e.tree[:12]} not found in {src.label}")
    return {join_rel(e.rel, b): (src, o, up_join(e.path, b)) for b, o in base.items()}


def cmd_restore(ctx, repo, args):
    """Like `git restore`, from the layer below (R2): the working tree from
    the index, with -S the index from HEAD, with -S -W both from HEAD. For
    each entry the layer gets what the layer below has: the entry synced
    as there (its sync keys; the selection stays, see restore_values) -
    none there: the entry goes -, the files of that base as it gives them,
    the synced version (also of an adaptable file: its adaptations go,
    said); other files of its own entry what that layer has there (a file
    of this repository), or none (they go). Only some files of a [dir]
    given: those, the entry stays. Content that goes is kept (see
    save_discarded). The files are written all at once (see
    Repo.put_blobs)."""
    reg = Registry(repo)
    worktree = args.worktree or not args.staged
    below = "head" if args.staged else "index"
    sides = (["index"] if args.staged else []) + (["worktree"] if worktree else [])
    rc, plans = EXIT_OK, []
    for entry in select_links(repo, reg, args.files):
        try:
            lower = layer_entry(repo, entry, below)
            # nothing synced anywhere: nothing to restore (only in the working
            # tree, as after add -W: restore -S says so, see below)
            here = [entry if side == "worktree" else layer_entry(repo, entry, "index")
                    for side in sides]
            if entry.unsynced and all(e is None or e.unsynced for e in here + [lower]):
                raise FsError("not synced yet, nothing to restore - sync it with "
                              f"'git filesync pull {path_arg(repo, entry.rel)}'")
            if entry.only is not None and (lower is None or any(
                    e is not None and sync_keys(e.v) != sync_keys(lower.v) for e in here)):
                # (its files from that base would not be the entry's)
                where = "HEAD" if args.staged else "the index"
                raise FsError((f"not in {where}" if lower is None else
                               f"synced otherwise than in {where}")
                              + f" - restore {entry.shown_rel} as a whole")
            mine = {}             # the files of the entries in the layers restored
            for side in sides:
                mine.update(entry_files(ctx, entry if side == "worktree"
                                        else layer_entry(repo, entry, "index")))
            base = entry_files(ctx, lower)
            if entry.only is not None:        # some files of a [dir]
                def given(r):
                    return any(is_below(r, o) for o in entry.only)
                for o in entry.only:
                    if not any(is_below(r, o) for r in set(base) | set(mine)):
                        raise FsError(not_linked_text(o, entry))
                mine = {r: v for r, v in mine.items() if given(r)}
                base = {r: v for r, v in base.items() if given(r)}
            for r in set(mine) | set(base):   # what is in the way: only if written
                problem = path_problem(r) or worktree and in_the_way(repo.top, r)
                if problem:
                    raise FsError(f"{r}: {problem}")
            plans.append((entry, lower, base, sorted(set(mine) - set(base)), mine))
        except FsError as e:
            error(str(e) if str(e).startswith(entry.rel) else f"{entry.rel}: {e}")
            rc = EXIT_ERROR
    # the bases in this repository's form, read and converted at once
    for src in {id(s): s for _, _, base, _, _ in plans for s, _, _ in base.values()}.values():
        src.read_blobs(o for _, _, base, _, _ in plans for s, o, _ in base.values() if s is src)
        try:              # (a commit not there: see short_of below)
            src.shorts(lw.commit for _, lw, base, _, _ in plans
                       for s, _, _ in list(base.values())[:1] if s is src)
        except FsError:
            pass
    repo.check_plain(r for _, _, base, _, _ in plans for r in base)
    raw, raw_mine = {}, {}        # contents: of the bases below, of the layers restored
    for entry, _, base, _, mine in list(plans):
        try:
            got = {r: src.read_content(o, path) for r, (src, o, path) in base.items()}
            # the bases of the layers restored: pull gets them again, nothing lost
            got_mine = {r: src.read_content(o, path) for r, (src, o, path) in mine.items()
                        if r not in base or base[r][1:] != (o, path)}
        except FsError as e:
            error(f"{entry.rel}: base version unavailable ({e})")
            plans = [p for p in plans if p[0] is not entry]
            rc = EXIT_ERROR
            continue
        raw.update(got)
        raw_mine.update(got_mine)
    repo.normalize_many([(c, r) for d in (raw, raw_mine) for r, c in d.items()])
    ids = repo.blob_ids([(r, repo.normalize(c, r)) for r, c in raw.items()])
    known = repo.blob_ids([(r, repo.normalize(c, r)) for r, c in raw_mine.items()])
    index = repo.index_entries([r for _, _, base, others, _ in plans for r in list(base) + others])
    others_below = {r: (index[r][1] if r in index else None) if below == "index"
                    else repo.head_blob(r) for _, _, _, others, _ in plans for r in others}
    now = repo.worktree_blobs([r for _, _, base, others, _ in plans for r in list(base) + others]) \
        if worktree else {}
    write, unstage, delete, said, hints, staged_ops, removed = [], [], [], [], [], [], set()
    for entry, lower, base, others, _ in plans:
        want = {r: ids[r] for r in base}
        want.update((r, others_below[r]) for r in others)
        changed = set()
        for side in sides:
            have = now if side == "worktree" else {r: e[1] for r, e in index.items()}
            for r, oid in sorted(want.items()):
                if have.get(r) == oid:
                    continue
                changed.add(side)
                if oid is None:
                    (delete if side == "worktree" else unstage).append(r)
                else:
                    write.append((r, oid, side))
        # adaptations the layer below has that go: said, with how to get them back
        written = {r for r, _, _ in write}
        adapted = entry.adaptable and sorted(r for r in base if r in written and (
            repo.head_blob(r) if args.staged else index.get(r, (None, None))[1])
            not in (None, ids[r]))
        if adapted:
            again = "-SW " if args.staged and worktree else "-S " if args.staged else ""
            hints.append(f"{entry.shown_rel}: adaptations removed"
                         + (f" in {plural(len(adapted), 'file')}" if entry.is_dir else "")
                         + f" (still {'committed' if args.staged else 'staged'}: "
                         f"'git restore {again}<file>...' brings them back)")
        if entry.only is None:            # the entry itself
            if "worktree" in sides:
                if lower is None:
                    reg.remove_file(entry.rel)
                    changed.add("worktree")
                else:
                    for k, v in restore_values(ctx, entry, lower).items():
                        if entry.v.get(k) != v:   # ("" for synced-*: no patterns)
                            entry.set(k, v)
                            changed.add("worktree")
            if "index" in sides:
                ops = staged_entry_ops(repo, entry, lower, ctx)
                if ops:
                    staged_ops.append(ops)
                    changed.add("index")
                    if lower is None:
                        removed.add(entry.rel)
        if lower is None and entry.only is None and changed:
            what = {"index": "unstaged", "worktree": "removed"}[sides[0]] if len(sides) == 1 \
                else "removed and unstaged"
            said.append(f"{entry.shown_rel}: {paint(what, 'green')} (not in "
                        f"{'HEAD' if args.staged else 'the index'} yet)")
        elif changed and lower is not None:
            what = {("index",): "restored in the index", ("worktree",): "restored"}.get(
                tuple(sorted(changed)), "restored and staged")
            src = next(iter(base.values()))[0] if base else None
            try:
                at = src.short(lower.commit) if src and lower.commit else short_of(lower)
            except FsError:       # e.g. upstream history rewritten
                at = short_of(lower)
            name = entry.shown_rel if entry.only is None else \
                ", ".join(shown(repo, o) for o in entry.only)
            said.append(f"{name}: {paint(what, 'green')} "
                        + (f"({lower.name}@{at})" if at else "(not synced yet)"))
        else:
            said.append(f"{entry.shown_rel}: nothing to restore")
    sw = [r for r, _, side in write if side == "worktree"] + delete
    si = [r for r, _, side in write if side == "index"] + unstage
    # (a file git doesn't track goes as discarded, also one pull -W only found there)
    save_discarded(repo, sw, si, dict({r: {ids.get(r), known.get(r)} for r in delete
                                       if r in index or repo.head_blob(r)},
                                      **{r: {o, ids.get(r), known.get(r)}
                                         for r, o, side in write if side == "worktree"}))
    both = {r for r, _, side in write if side == "worktree"} & \
        {r for r, _, side in write if side == "index"}
    try:                      # the working tree first: if that fails, nothing else changes
        repo.put_blobs(sorted({(r, o) for r, o, side in write if r in both}), stage=True)
        repo.put_blobs([(r, o) for r, o, side in write if side == "worktree" and r not in both],
                       stage=False)
    except FsError as e:
        error(str(e))
        return EXIT_ERROR
    repo.put_blobs([(r, o) for r, o, side in write if side == "index" and r not in both],
                   worktree=False)
    for r in delete:
        if (repo.top / r).is_file():
            (repo.top / r).unlink()
    if unstage:
        repo.git(["update-index", "-z", "--force-remove", "--stdin"],
                 data="\0".join(unstage).encode("utf-8"))
    reg.finish(stage=False)
    write_staged(repo, [b for b in staged_ops + [unused_staged_sources(repo, removed, staged_ops)]
                        if any(b)])
    for line in said + hints:
        print(line)
    return rc


def short_of(e):
    """The synced commit of an entry, abbreviated ('' if not synced)."""
    return e.commit[:7] if e.commit else e.blob[:8]


def staged_entry_ops(repo, entry, lower, ctx):
    """Changes (pending, drop, renames; see edit_registry) of the staged
    registry that give it the entry as lower (HEAD's; None: none) has it:
    synced as there where the index has the entry (restore_values); else
    lower's section copied, with its [source] where the index hasn't it;
    no lower: the entry removed (its [source]: see unused_staged_sources)."""
    staged = repo.registry("index")
    ei = layer_entry(repo, entry, "index")
    if lower is None:
        return ({}, {("dir" if ei.is_dir else "file", ei.rel)}, {}) if ei is not None else None
    sect = "dir" if lower.is_dir else "file"
    if ei is not None:
        pending = {(sect, ei.rel, k): v for k, v in restore_values(ctx, ei, lower).items()
                   if ei.v.get(k) != v}
        return (pending, set(), {}) if pending else None
    values = dict(lower.v)
    if lower.name and lower.name not in staged.sources:
        pending = {("source", lower.name, k): v for k, v in lower.source.items()}
    else:                 # its [source] there, maybe with another URL: synced as there
        pending = {}
        values.update(restore_values(ctx, type(lower)(staged, lower.rel, dict(lower.v)), lower))
    pending.update(((sect, lower.rel, k), v) for k, v in values.items() if v is not None)
    return pending, set(), {}


def unused_staged_sources(repo, removed, ops):
    """Changes that remove the [source]s of the staged registry only the
    entries removed (their paths) used - not those the other changes (ops,
    see staged_entry_ops) give an entry."""
    staged = repo.registry("index")
    names = {(staged.files.get(r) or staged.dirs.get(r) or {}).get("source") for r in removed}
    users = {v.get("source") for store in (staged.files, staged.dirs)
             for r, v in store.items() if r not in removed}
    users |= {v for pending, _, _ in ops for (sect, _, k), v in pending.items()
              if sect in ("file", "dir") and k == "source"}
    return {}, {("source", n) for n in names - users - {None} if n in staged.sources}, {}


def not_linked_text(rel, dlink):
    """The error for a path in a [dir] entry that isn't one of its files."""
    return (f"'{rel}' is not linked (in the linked directory '{dlink.shown_rel}', but not "
            "one of its files)")


def check_only(sts):
    """status, diff: a path given in a [dir] entry must be one of its files
    (or a directory with some) - one of this repository's own isn't linked."""
    for st in sts:
        for o in (st.link.only or []) if not st.error else []:
            if not any(is_below(m.rel, o) for m in st.members):
                raise FsError(not_linked_text(o, st.link))


def dir_files(ctx, repo, links):
    """(exit code, links): [dir] entries replaced by their files at the
    base (Member) - those of `only` if it names some - for commands that
    act on the files (restore, rm); errors reported."""
    rc, result = EXIT_OK, []
    for link in links:
        if not link.is_dir:
            result.append(link)
            continue
        if link.unsynced:
            result.append(link)          # reported by the command
            continue
        try:
            src = ctx.source(link.url, link.ref, link.name, link.line)
            base = dir_base(src, link)
            if base is None:
                raise FsError(f"synced tree {link.tree[:12]} not found in {src.label}")
        except FsError as e:
            error(f"{link.shown_rel}: {e}")
            rc = EXIT_ERROR
            continue
        ms = [link.member(b, o) for b, o in sorted(base.items())]
        for o in link.only or []:
            if not any(is_below(m.rel, o) for m in ms):
                error(not_linked_text(o, link))
                rc = EXIT_ERROR
        result += [m for m in ms if link.only is None or any(is_below(m.rel, o)
                                                              for o in link.only)]
    return rc, result


def cmd_unlink(ctx, repo, args):
    reg = Registry(repo)
    links = select_links(repo, reg, args.files, whole=True)
    for link in links:
        if args.dry_run:
            print(f"would unlink {link.shown_rel}")
            continue
        reg.remove_file(link.rel)
        print(f"{paint('unlinked', 'green')} {link.shown_rel} "
              f"({'files' if link.is_dir else 'file'} kept)")
    if not args.dry_run:
        reg.finish()
    return EXIT_OK


def cmd_rm(ctx, repo, args):
    """Like `git rm`: remove the links and the files, both staged - of a
    [dir] entry the files at its base, its own stay. Refused (for all) if
    a file has uncommitted changes, unless -f; a committed adaptation is no
    reason to refuse. A file that is gone already is fine."""
    reg = Registry(repo)
    entries = select_links(repo, reg, args.files, whole=True)
    rc, links = dir_files(ctx, repo, entries)
    if rc:
        return rc
    links = [lk for lk in links if not lk.is_dir]     # a new [dir]: none of its own yet
    for link in links:
        link.target               # refused (for all) if something is in the way
    # of a [dir] entry staged with another base: the files only that has, too
    extra = {e.rel: staged_only(repo, e, {lk.rel for lk in links})
             for e in entries if e.is_dir and not e.unsynced}
    paths = [lk.rel for lk in links] + [r for rs in extra.values() for r in rs]
    repo.prefetch(paths)
    if not args.force:
        dirty = [r for r in paths if (repo.top / r).exists() and
                 (repo.head_blob(r) is None or repo.is_modified(r))]
        if dirty:
            raise FsError("".join(f"{r}: has uncommitted changes\n" for r in dirty[:-1])
                          + f"{dirty[-1]}: has uncommitted changes - use -f to remove "
                          f"{'it' if len(dirty) == 1 else 'them'} anyway")
    if args.dry_run:
        for link in entries:
            print(f"would remove {link.shown_rel}" + dir_note(link, links, extra))
        return EXIT_OK
    save_discarded(repo, paths, paths)
    for part in chunks(paths):
        repo.git(["rm", "-q", "-f", "--ignore-unmatch", "--"] + [lit(r) for r in part])
    for link in links:
        if link.target.is_file():       # never added to git
            link.target.unlink()
    for link in entries:
        reg.remove_file(link.rel)
        note = dir_note(link, links, extra)
        if link.is_dir and link.target.is_dir() and any(link.target.iterdir()):
            note = note[:-1] + "; files of this repository stay)"     # the own ones
        print(f"{paint('removed', 'green')} {link.shown_rel}{note}")
    reg.finish()
    return EXIT_OK


def dir_note(link, files, extra):
    """' (3 files)' - the files of a [dir] entry among files, and those only
    its staged entry has (extra: {rel: [paths]}), for rm."""
    if not link.is_dir:
        return ""
    n = sum(1 for f in files if isinstance(f, Member) and f.dlink.rel == link.rel) + \
        len(extra.get(link.rel, []))
    return f" ({plural(n, 'file')})"


def cmd_mv(ctx, repo, args):
    """mv OLD NEW, or like git mv several linked files into an existing
    directory: mv OLD... DIR - all checked first, then all moved."""
    reg = Registry(repo)
    target = repo.user_path(args.dst)
    if len(args.src) > 1 and not target.is_dir():          # like git mv
        raise FsError(f"destination '{repo.rel(target)}' is not a directory")
    moves = {}                    # old -> (new, its path)
    for arg in args.src:
        old = repo.rel(repo.user_path(arg))
        link = reg.entry(old)
        if not link:
            inside = [d for d in reg.dirs if is_below(old, d)]
            raise FsError(f"'{old}' is in the linked directory '{inside[0]}/' - move that "
                          "one" if inside else f"'{old}' is not linked")
        if old == ".":
            raise FsError("cannot move the root directory")
        link.target                              # nothing in the way at OLD
        dst = target
        if repo.names_dir(args.dst) and not dst.is_dir():      # NEW/: like git mv
            raise FsError(f"destination directory does not exist, source={old}, "
                          f"destination={repo.rel(dst)}/")
        if dst.is_dir():
            dst = dst / Path(old).name
        new = repo.rel(dst)
        problem = path_problem(new) or in_the_way(repo.top, new)
        if problem:
            raise FsError(f"cannot move to '{new}': {problem}")
        if any(new == n for n, _ in moves.values()):              # like git mv
            raise FsError(f"multiple sources for the same target, source={old}, destination={new}")
        if reg.entry(new) or dst.exists():
            raise FsError(f"'{new}' already exists")
        others = reg.overlapping(new, reg.kind(old))
        if others:
            raise FsError(f"cannot move to '{new}': would overlap with the entry for "
                          f"{and_list(others)} - entries must not overlap")
        if not dst.parent.is_dir():                  # like git mv
            raise FsError(f"destination directory does not exist, source={old}, destination={new}")
        moves[old] = (new, dst)
    if args.dry_run:
        for old, (new, _) in moves.items():
            print(f"would move {old} -> {new}")
        return EXIT_OK
    indexed = repo.index_entries(list(moves))       # of a [dir]: the files in it
    tracked = [old for old in moves if any(is_below(e, old) for e in indexed)]
    renamed = []                 # untracked files moved - back if anything fails
    try:
        for old, (new, dst) in moves.items():
            if old not in tracked and (repo.top / old).exists():
                (repo.top / old).rename(dst)
                renamed.append((old, dst))
        for part in chunks(tracked):    # git mv into DIR, or OLD to NEW
            repo.git(["mv", "--"] + part + [repo.rel(target) if len(args.src) > 1
                                            else moves[part[0]][0]])
    except (OSError, FsError) as e:
        for old, dst in reversed(renamed):
            dst.rename(repo.top / old)
        raise FsError(f"nothing moved: {e}")
    for old, (new, _) in moves.items():
        reg.rename_file(old, new)
    reg.finish()
    for old, (new, _) in moves.items():
        d = "/" if reg.kind(new) == "dir" else ""
        print(f"{paint('moved', 'green')} {old}{d} -> {new}{d} (link kept)")
    return EXIT_OK


def commit_in(src, commit, blob, path):
    """The commit of a synced version (commit, blob, upstream path) in
    another upstream (a fork, a moved repository): the recorded one if it
    is there, else the newest commit on the branch that has the blob at the
    path; None if the version isn't there."""
    if commit and src.resolve(commit) == commit:
        return commit
    for rev, oid in src.path_history(path, 5000):
        if oid == blob:
            return rev
    return None


def translated(src, link, commit, blob, path):
    """commit_in for a base of link (in any layer) - asked once per run
    (restore -SW, set: for each layer); if src hasn't it, a warning: the
    previous sync point counts as unknown."""
    key = ("translated", link.rel, commit, blob, path)
    if key not in src._memo:
        src._memo[key] = commit_in(src, commit, blob, path)
        if not src._memo[key]:
            warn(f"{link.rel}: synced version {blob[:12]} not found in {src.label}; its "
                 "previous sync point counts as unknown - sync it with "
                 f"'git filesync pull {path_arg(link.reg.repo, link.rel)}'")
    return src._memo[key]


def keep_base(src, link, source=None):
    """A link moves to another upstream (src): its synced version stays the
    base, with the commit it has there (see translated) - or, if src doesn't
    have it, a warning: the previous sync point counts as unknown. A new
    link (not synced yet) has none. The index's entry at another base (e.g.
    after pull -W) keeps its own, translated the same way (R2) - if it moves
    too: source, the [source] that moves (source set), if it uses that."""
    reg = link.reg
    ei = layer_entry(reg.repo, link, "index")
    if ei is not None and sync_keys(ei.v) != sync_keys(link.v):
        moves = not ei.unsynced and (source is None or ei.name == source)
        commit = translated(src, link, ei.commit, ei.blob, ei.path) if moves else None
        reg.staged_own[("dir" if link.is_dir else "file", link.rel)] = \
            {"commit": commit} if commit else {}
    if link.unsynced:
        return
    commit = translated(src, link, link.commit, link.blob, link.path)
    if commit and commit != link.commit:
        link.set("commit", commit)


def shows(args, given, changes, what, everything):
    """Whether set / source set only show (nothing to change given; --list:
    all of them, everything); FsError for arguments that don't fit."""
    if args.list and (given or changes):
        raise FsError(f"--list shows all {everything}: give nothing else")
    if not given and not args.list:
        raise FsError(f"give {what}" + ("" if changes else " (or --list for all)"))
    return not changes


def source_words(s, url_opt):
    """URL and branch of the [source] s as options of a command shown."""
    q = shlex.quote
    return ([url_opt, q(s["url"])] if s.get("url") else []) + \
        (["-b", q(s["branch"])] if s.get("branch") else [])


def set_command(repo, lk):
    """The set command for what the entry lk has - every aspect, also those
    not set (--no-tag), so that it serves as a template for others; entered
    again, it changes nothing."""
    q = shlex.quote
    words = ["git", "filesync", "set", q(shown_entry(repo, lk))] + \
        source_words(lk.source, "--source")
    words += ["--tag", q(lk.tag)] if lk.tag else ["--no-tag"]
    words += ["-p", q(lk.path or "/"),
              "--adaptable" if lk.adaptable else "--no-adaptable"]
    for k in PATTERN_KEYS if lk.is_dir else ():
        words += [w for p in getattr(lk, k) for w in (f"--{k}", q(p))] or [f"--no-{k}"]
    return " ".join(words)


def cmd_set(ctx, repo, args):
    """Change the link of linked files - their source (URL and branch), tag,
    upstream path, whether it is adaptable, a [dir] entry's patterns.
    Without any of these: show them, as the set command that sets them. A
    file uses the [source] with its URL and branch: found, created, or - when
    all files of a source move - that source changed; one left without
    files is removed. Only .git-filesync is changed (and staged; -W: in the
    working tree only); the synced version (the base) is kept where it
    still applies: for another branch or tag of the same upstream, and for
    another upstream that has it (a fork, a moved repository); with another
    path it is looked up like for add. Other patterns take effect at the
    next pull (see set_patterns)."""
    patterns = args.include or args.exclude or args.no_include or args.no_exclude
    changes = args.source or args.branch or args.tag or args.no_tag or args.path or \
        args.adaptable is not None or patterns
    reg = Registry(repo)
    if shows(args, args.files, changes, "the linked files or directories", "entries"):
        for lk in reg.links() if args.list else select_links(repo, reg, args.files, whole=True):
            print(set_command(repo, lk))
        return EXIT_OK
    reg.dry_run = args.dry_run
    links = select_links(repo, reg, args.files, whole=True)
    if args.path and len(links) != 1:
        raise FsError("-p requires exactly one file or directory")
    if patterns and not all(lk.is_dir for lk in links):
        raise FsError("--include and --exclude are for linked directories only, not for "
                      + and_list([lk.rel for lk in links if not lk.is_dir]))
    for lk in links:
        if not lk.source.get("branch") or lk.source.get("tag"):
            raise FsError(f"{lk.rel}: its [source \"{lk.name}\"] in {REGISTRY} needs a url "
                          "and a branch (and no tag)")
    would = "would: " if args.dry_run else ""
    changed = False
    # another upstream path (the same one, also written differently: no change)
    path = upstream_path(args.path) if args.path else None
    new_path = path is not None and path != upstream_path(links[0].path)
    if args.source or args.branch:
        # the source the files are to use: URL and branch (like add)
        url = branch = None
        if args.source:
            url, branch, _ = add_ref(ctx, reg, args, "give the URL with -b, or -b alone "
                                                     "for the files' upstream")
        groups = {}
        for lk in links:
            target = (url, branch) if args.source else (lk.url, args.branch)
            if (norm_url(lk.url), lk.source.get("branch")) != (norm_url(target[0]), target[1]):
                groups.setdefault((lk.name,) + target, []).append(lk)
        for (old, url_, branch_), lks in groups.items():
            name = reg.find_source(url_, branch_)
            src = ctx.source(url_, ("branch", branch_), name or old)
            src.tip()
            if not name and set(source_files(reg, old)) <= {lk.rel for lk in lks}:
                # all files of the source move to a new place: the source itself
                # changes, keeping its name (like source set --url / -b)
                for key, value in (("url", url_), ("branch", branch_)):
                    if reg.sources[old].get(key) != value:
                        print(f"{would}source {old}: {key} {reg.sources[old].get(key)} -> {value}")
                        reg.set_source(old, key, value)
                name = old
            name = name or reg.add_source(url_, branch_)
            for lk in lks:
                if norm_url(url_) != norm_url(lk.url) and not new_path:
                    keep_base(src, lk)
                if lk.name != name:
                    lk.set("source", name)
                    print(f"{would}{lk.shown_rel}: source {old} -> {name}")
            if name != old and old in reg.sources and not source_files(reg, old):
                reg.remove_source(old)
            changed = True
    if args.tag or args.no_tag:
        for lk in links:
            if (lk.tag or None) == (args.tag or None):
                continue
            if args.tag:          # a tag (or pattern) not upstream is an error
                ref = ("tag", args.tag)
                src = ctx.source(lk.url, ref, lk.name, lk.source.get("branch"))
                src.tip()
                warn_tag_line(src, args.tag, lk.source.get("branch"))
            lk.set("tag", args.tag or None)
            print(f"{would}{lk.shown_rel}: " + (f"tag {args.tag}" if args.tag else
                                          f"follows branch {lk.source.get('branch')}"))
            changed = True
    if new_path:
        lk, ei = links[0], layer_entry(repo, links[0], "index")
        if not args.worktree and not lk.is_dir and ei is not None and \
                sync_keys(ei.v) != sync_keys(lk.v):
            # (its new base is found for the working tree's file, not the index's)
            arg = path_arg(repo, lk.rel)
            raise FsError(f"{lk.rel}: synced otherwise in the index (e.g. after pull -W) - "
                          f"first stage it with 'git filesync pull {arg}', or go back with "
                          f"'git filesync restore {arg}'")
        changed = set_path(ctx, repo, lk, path, would) or changed
    if args.adaptable is not None:
        for lk in links:
            if lk.adaptable != args.adaptable:
                lk.set("adaptable", "true" if args.adaptable else None)
                print(f"{would}{lk.shown_rel}: "
                      f"{'adaptable' if args.adaptable else 'not adaptable'}")
                changed = changed or "adaptable"
    if patterns:
        for lk in links:
            changed = set_patterns(ctx, lk, args, would) or changed
    if not changed:
        print("nothing to change")
    elif not args.dry_run:
        # only adaptable changed: nothing for pull to do (known offline)
        print(pending_note(repo, changed != "adaptable", reg.finish(stage=not args.worktree)))
    return EXIT_OK


def pending_note(repo, pending, staged):
    """What set and source set say at the end: staged, or in the working tree
    only - and if pull may have something to do, so, with how
    (advice.statusHints); after a change in the working tree only that is
    pull -W, which keeps the try unstaged."""
    done = f"{REGISTRY} staged" if staged else WORKTREE_ONLY
    if not pending:
        return done
    pull = "pull" if staged else "pull -W"
    return f"{done} - pending until {pull}" + \
        (f' (use "git filesync {pull} <file>..." to sync)' if status_hints(repo) else "")


def set_path(ctx, repo, lk, path, would):
    """set -p: another upstream path. A [dir] entry becomes a new link (its
    files aren't those there: pull compares them, see first_sync_dir); a
    file takes the path's current version as its base, as for add."""
    src = ctx.source(lk.url, lk.ref, lk.name, lk.line)
    head = src.tip()
    if lk.is_dir:
        if not src.is_dir(head, path):
            raise FsError(f"no directory '{path or '/'}' in {src.label} at {src.short(head)}")
        print(f"{would}{lk.shown_rel}: path {up_join(lk.path, '') or '/'} -> "
              f"{up_join(path, '') or '/'}" + ("" if lk.unsynced else
                                               " (not synced yet: pull compares the files)"))
        lk.set("path", path or "/")
        lk.set("commit", None)
        lk.set("tree", None)
        lk.drop_synced()
        return True
    if lk.unsynced:               # no base yet: pull takes the path's version
        if not src.blob_at(head, path):
            raise FsError(f"no file '{path}' in {src.label} at {src.short(head)}")
        commit, blob, modified = "", "", False
    else:
        commit, blob, _, modified, _ = find_base(repo, src, head, lk.rel, path, lk.target)
    print(f"{would}{lk.rel}: path {lk.path} -> {path}"
          + (f", based on {src.short(commit)}" if commit else "")
          + (", with local modifications" if modified else ""))
    for k, v in (("path", path), ("commit", commit), ("blob", blob)):
        if v:
            lk.set(k, v)
    return True


def set_patterns(ctx, lk, args, would):
    """set --include / --exclude (--no-...) of a [dir] entry: only the
    registry changes; pull then applies them like a change upstream - files
    they newly select fetched, those they no longer select deleted. Until
    then the base keeps the patterns it was synced with, written to
    synced-include / synced-exclude while the new ones select other files
    of its tree (see DirLink.synced_patterns). Shows what the next pull does
    with them. Returns whether something changes."""
    new = {k: [] if getattr(args, f"no_{k}") else getattr(args, k) or getattr(lk, k)
           for k in PATTERN_KEYS}
    keys = [k for k in PATTERN_KEYS if new[k] != getattr(lk, k)]
    if not keys:
        return False
    draft = DirLink(lk.reg, lk.rel, dict(lk.v, **{k: join_patterns(v) or ""
                                                   for k, v in new.items()}))
    draft.check_patterns()
    synced = {k: lk.synced_patterns(k) for k in PATTERN_KEYS}
    files = None if lk.unsynced else \
        ctx.source(lk.url, lk.ref, lk.name, lk.line).tree_files(lk.tree)
    counts = None
    if files is not None:         # (without a base, pull compares all files)
        before = {b for b in files if lk.selects(b, base=True)}
        after = {b for b in files if draft.selects(b)}
        counts = len(after - before), len(before - after)
    lines = [f"{lk.shown_rel}: {k} {join_patterns(getattr(lk, k)) or '(none)'} -> "
             f"{join_patterns(new[k]) or '(none)'}" for k in keys]
    if counts:
        lines[-1] += f" (at the next pull: {counts[0]} new, {counts[1]} deleted)"
    print("\n".join(would + line for line in lines))
    for k in keys:
        lk.set(k, join_patterns(new[k]))
    # only while they make a difference (unknown without the base tree)
    differs = any(counts) if counts else not lk.unsynced
    for k in PATTERN_KEYS:
        if differs and new[k] != synced[k]:
            if f"synced-{k}" not in lk.v:
                lk.set(f"synced-{k}", join_patterns(synced[k]) or "")
        else:
            lk.set(f"synced-{k}", None)
    return True


def shell():
    """sh to run a command line the way git does (e.g. the editor): from
    PATH, or else the one of Git for Windows (<git>/mingw64/libexec/git-core
    -> <git>/bin/sh.exe)."""
    sh = shutil.which("sh")
    if sh:
        return sh
    root = Path(out(git(["--exec-path"]))).parents[2]
    for cand in (root / "bin" / "sh.exe", root / "usr" / "bin" / "sh.exe"):
        if cand.exists():
            return str(cand)
    raise FsError("no sh found to run the editor")


def registry_problems(reg):
    """What a hand-edited .git-filesync lacks: messages for entries that
    status would report as broken (and unused sources)."""
    problems = []
    for name, s in sorted(reg.sources.items()):
        if not s.get("url"):
            problems.append(f'[source "{name}"] has no url')
        if not s.get("branch"):
            problems.append(f'[source "{name}"] has no branch')
        if s.get("tag"):
            problems.append(f'[source "{name}"] has a tag - no longer supported: pin the '
                            "files themselves (tag in their [file] entries)")
        if not source_files(reg, name):
            problems.append(f'[source "{name}"] is not used by any file')
    for rel, v in sorted(reg.files.items()):
        what = f'[file "{rel}"]'
        problem = path_problem(rel)
        if problem:
            problems.append(f"{what}: {problem}")
        if v.get("source", "") not in reg.sources:
            problems.append(f"{what}: no [source \"{v.get('source', '')}\"]")
        if not v.get("path"):
            problems.append(f"{what} has no path")
        if bool(v.get("commit")) != bool(v.get("blob")):
            problems.append(f"{what} has only one of commit and blob (both: the synced "
                            "version; neither: a new link, synced by pull)")
        others = reg.overlapping(rel, "file")
        if others:
            problems.append(f"{what} is in the linked directory {others[0]}")
    for rel, v in sorted(reg.dirs.items()):
        what = f'[dir "{rel}"]'
        problem = path_problem(rel) if rel != "." else None
        if problem:
            problems.append(f"{what}: {problem}")
        if v.get("source", "") not in reg.sources:
            problems.append(f"{what}: no [source \"{v.get('source', '')}\"]")
        if not v.get("path"):
            problems.append(f"{what} has no path ('/' for the upstream root)")
        if bool(v.get("commit")) != bool(v.get("tree")):
            problems.append(f"{what} has only one of commit and tree (both: the synced "
                            "version; neither: a new link, synced by pull)")
        others = [o for o in reg.overlapping(rel, "dir") if o.endswith("/")]
        if others:
            problems.append(f"{what} overlaps with the entry for {and_list(others)}")
        try:
            DirLink(reg, rel).check_patterns()
        except FsError as e:
            problems.append(f"{what}: {e}")
    return problems


def cmd_edit(ctx, repo, args):
    """Open .git-filesync in the editor (like `git config --edit`), then
    check it and stage the sections that changed in it (see Registry.stage);
    a merge conflict in it: resolved there, the whole file staged (deleted
    or emptied there: its removal) - as when the staged one can't be read.
    -W: nothing staged, also not a resolved conflict."""
    path = registry_path(repo)
    try:
        registry_rows(repo)
        conflict = False
    except FsError:
        conflict = True
    broken = False                # the staged one can't be read
    if not conflict:
        try:
            repo.registry("index")
        except FsError:
            broken = True
    if not path.exists():
        raise FsError(conflict_text(repo) if conflict else
                      f"no {REGISTRY} yet - link files with 'git filesync add'")
    before = path.read_bytes()
    p = git(["config", "-f", path, "--list", "-z"], check=False)
    old = parse_registry(p.stdout) if not p.returncode else ({}, {}, {})
    if p.returncode and not conflict:     # can't be read: what changed is against the index
        try:
            staged = repo.registry("index")
            old = (staged.sources, staged.files, staged.dirs)
        except FsError:
            pass
    # the editor git would use (GIT_EDITOR, core.editor, VISUAL, EDITOR), run
    # like git runs it - not via `git config --edit`, which exits with 0 even
    # if the editor fails
    editor = out(repo.git(["var", "GIT_EDITOR"]))
    if subprocess.run([shell(), "-c", f'{editor} "$@"', editor, REGISTRY],
                      cwd=repo.top).returncode:
        raise FsError("the editor failed; nothing staged")
    if path.exists() and path.read_bytes() == before and not (conflict or broken):
        print(f"{REGISTRY}: no changes")
        return EXIT_OK
    if conflict or broken:
        done = "conflict resolved" if conflict else "staged as a whole (the staged one " \
            "couldn't be read)"
        p = git(["config", "-f", path, "--list", "-z"], check=False) if path.exists() else None
        if p is not None and (p.returncode or
                              re.search(rb"^(<<<<<<<|>>>>>>>)", path.read_bytes(), re.M)):
            raise FsError(f"{REGISTRY} still has conflicts or can't be parsed - not staged; "
                          "fix it with 'git filesync edit'")
        repo.rows = None
        gone = p is None or not any(parse_registry(p.stdout))   # deleted or emptied: it goes
        if gone and path.exists():
            path.unlink()
        if args.worktree and not conflict and path.exists() and path.read_bytes() == before:
            print(f"{REGISTRY}: no changes")
            return EXIT_OK
        if args.worktree:         # in the working tree only; git add/rm stages it
            what = ("conflict resolved" + (" - removed" if gone else "")) if conflict else \
                "removed" if gone else "changed"
            print(f"{REGISTRY}: {what} in the working tree only - "
                  f"'git {'rm' if gone else 'add'} {REGISTRY}' stages it")
            return EXIT_OK
        if gone:
            repo.git(["rm", "-q", "--cached", "--", REGISTRY])
            print(f"{REGISTRY}: {done} - removed and staged" if conflict else
                  f"{REGISTRY}: removed and staged")
            return EXIT_OK
        repo.git(["add", "--", REGISTRY])
        print(f"{REGISTRY}: {done} and staged" if conflict else f"{REGISTRY}: {done}")
        return EXIT_OK
    try:
        reg = Registry(repo)
    except FsError as e:
        raise FsError(f"{e} - not staged; fix it with 'git filesync edit'")
    for problem in registry_problems(reg):
        warn(f"{REGISTRY}: {problem}")
    pending, drop = {}, set()         # what changed, staged as such (see Registry.stage)
    for sect, was, now in zip(("source", "file", "dir"), old, (reg.sources, reg.files, reg.dirs)):
        for name in sorted(set(was) | set(now)):
            if name not in now:
                drop.add((sect, name))
                continue
            pending.update(section_changes(sect, name, was.get(name, {}), now[name]))
    if not (pending or drop):
        print(f"{REGISTRY}: only comments or layout changed - nothing staged")
        return EXIT_OK
    reg.done.append((pending, drop, {}))
    print(REGISTRY_STAGED if reg.finish(stage=not args.worktree) else REGISTRY_WORKTREE)
    return EXIT_OK


def source_files(reg, name):
    """The entries ([file] and [dir]) of the [source] name."""
    return reg.uses(name)


def source_command(name, s):
    """The source set command for what the [source] s has (like set_command)."""
    return " ".join(["git", "filesync", "source", "set", shlex.quote(name)]
                    + source_words(s, "--url"))


def cmd_source(ctx, repo, args):
    """Like `git remote`: list, rename and change the [source]s - which
    add and set create as needed, and remove when no file uses them. Only
    .git-filesync is changed (and staged; -W: in the working tree only);
    `pull` then syncs the files."""
    reg = Registry(repo)
    action = args.action
    if not action:
        for name, s in sorted(reg.sources.items()):
            if not args.verbose:
                print(name)
                continue
            used = [r + "/" if r in reg.dirs else r for r in source_files(reg, name)]
            print(f"{name}\t{s.get('url', '')} ({s.get('branch') or 'branch missing'}, "
                  f"{entries_text(used) or '0 files'})")
        return EXIT_OK
    changes = action == "set" and (args.url or args.branch)
    show = action == "set" and shows(args, args.name, changes, "the name of a source", "sources")
    if args.name and args.name not in reg.sources:
        raise FsError(f"no source '{args.name}' in {REGISTRY}"
                      + (f" (known: {', '.join(sorted(reg.sources))})" if reg.sources else ""))
    if show:
        for name in sorted(reg.sources) if args.list else [args.name]:
            print(source_command(name, reg.sources[name]))
        return EXIT_OK
    reg.dry_run = args.dry_run
    would = "would: " if args.dry_run else ""
    s = reg.sources[args.name]
    if action == "rename":
        if args.value in reg.sources:
            raise FsError(f"source '{args.value}' already exists")
        if not args.value or "\n" in args.value:
            raise FsError("invalid source name")
        if args.dry_run:
            print(f"would rename {args.name} -> {args.value}")
            return EXIT_OK
        reg.rename_source(args.name, args.value)
        print(f"{paint(f'renamed {args.name} -> {args.value}', 'green')}; "
              + pending_note(repo, False, reg.finish(stage=not args.worktree)))
        return EXIT_OK
    url, branch = registry_url(args.url or s.get("url", "")), args.branch or s.get("branch")
    keys = [(k, v) for k, v in (("url", url), ("branch", branch)) if v != s.get(k)]
    if not keys:
        print("nothing to change")
        return EXIT_OK
    other = reg.find_source(url, branch, exclude=args.name)
    if other:
        raise FsError(f"source '{other}' already has this URL and branch {branch} - "
                      f"move the files to it with 'git filesync set FILE... --source {other}'")
    if url and branch:            # as for set: the branch must exist upstream
        src = ctx.source(url, ("branch", branch), args.name)
        src.tip()
        if norm_url(url) != norm_url(s.get("url", "")):
            for rel in source_files(reg, args.name):
                keep_base(src, reg.entry(rel), args.name)
    for k, v in keys:
        print(f"{would}source {args.name}: {k} {s.get(k) or '(none)'} -> {v}")
        reg.set_source(args.name, k, v)
    if not args.dry_run:
        print(pending_note(repo, bool(source_files(reg, args.name)),
                           reg.finish(stage=not args.worktree)))
    return EXIT_OK


def print_mappings(maps, url=None):
    """Print mappings with their scope; entries shadowed by a later one
    (e.g. a global mapping overridden by the repo's own) are marked."""
    effective = {norm_url(u): i for i, (_, _, u, _) in enumerate(maps)}
    shown = 0
    for i, (sc, _, u, d) in enumerate(maps):
        if url and norm_url(u) != norm_url(url):
            continue
        note = "" if effective[norm_url(u)] == i else paint("   (overridden)", "dim")
        print(f"{paint(f'[{sc}]', 'cyan')} {u} -> {d}{note}")
        shown += 1
    if not shown:
        print("no mappings" + (f" for {url}" if url else ""))


def looks_like_url(s):
    """'scheme://...', scp-like 'host:path' (also 'C:/...') or relative
    ('./', '../') - never taken as the name of a [source]."""
    return "://" in s or is_relative_url(s) or bool(re.match(r"[^/]+:", s))


def map_url(repo, arg, setting):
    """The URL map works on: arg, or the url of the [source] named arg in this
    repository's .git-filesync (a URL-like arg is always a URL). When
    setting a mapping, an arg that is neither (nor an existing path, which
    git takes as a URL too) is refused - most likely a mistyped name. A
    relative URL is resolved (see resolve_url): mappings are for absolute
    URLs."""
    if not arg or looks_like_url(arg):
        return arg and resolve_url(arg, repo and repo.top)
    if repo:
        source = Registry(repo).sources.get(arg)
        if source is not None:
            if not source.get("url"):
                raise FsError(f"[source \"{arg}\"] in {REGISTRY} has no url")
            return resolve_url(source["url"], repo.top)
    if setting:
        require_url(repo, arg)
    return arg


def require_url(repo, arg):
    """Refuse an arg that isn't a [source] (checked before) and is neither
    URL-like nor an existing path (which git takes as a URL too) - most
    likely a mistyped or removed source name."""
    if not looks_like_url(arg) and not (repo.base if repo else Path.cwd()).joinpath(arg).exists():
        where = f"a [source] in {REGISTRY}" if repo else "a [source] (not inside a repository)"
        raise FsError(f"'{arg}' is neither a URL nor {where}")


def cmd_map(args, repo):
    """Map an upstream URL to a local checkout. Default scope is the current
    repository's config, so different repositories can use different
    checkouts of the same upstream; --global applies to all repositories.
    Instead of the URL, the name of a [source] may be given."""
    top = repo.top if repo else None
    args.url = map_url(repo, args.url, bool(args.dir))
    if not args.dir and not args.unset:      # listing: all scopes visible here
        print_mappings(local_mappings(cwd=top), args.url)
        return EXIT_OK
    if not args.url:
        raise FsError("--unset needs the URL (or source) of the mapping to remove")
    if args.glob:
        scope = "--global"
    elif repo:
        scope = "--local"
    else:
        raise FsError("not inside a Git repository; use --global for a global mapping")
    name = scope[2:]
    matching = [k for _, k, _, _ in mappings_for(args.url, scope, cwd=top)]
    if args.unset:
        if not matching:
            print(f"no {name} mapping for {args.url}")
            return EXIT_OK
        for k in matching:
            git(["config", scope, "--unset-all", k], cwd=top)
        print(f"removed {name} mapping for {args.url}")
        rest = mappings_for(args.url, cwd=top)
        if rest:
            print(f"now using [{rest[-1][0]}] {rest[-1][3]}")
        return EXIT_OK
    base = repo.base if repo else Path.cwd()
    # as given, only made absolute: a junction, subst or network drive, or
    # symlink on the way stays ('..' by name, as Windows does)
    d = Path(os.path.abspath(base / os.path.expanduser(args.dir)))
    if not is_repository(d):
        raise FsError(f"{d} is not a Git repository")
    for k in matching:
        git(["config", scope, "--unset-all", k], cwd=top)
    git(["config", scope, f"filesync.{args.url}.localpath", str(d)], cwd=top)
    print(f"{paint(f'[{name}]', 'cyan')} {args.url} -> {d}")
    if scope == "--global" and repo:
        own = mappings_for(args.url, "--local", cwd=top)
        if own:
            warn(f"this repository has its own mapping ({own[-1][3]}), which takes precedence")
    return EXIT_OK


def describe_clone(item):
    _, size, used, url = item
    return (f"{human_size(size):>10}  {time.strftime('%Y-%m-%d', time.localtime(used))}  "
            f"{url or paint('(URL unknown)', 'dim')}")


def cmd_cache(args):
    """Show, list and clean up the cache of upstream clones (shared by all
    repositories of this user)."""
    root = cache_root()
    action = args.action
    if action == "dir":
        print(root)
        return EXIT_OK
    if action == "list":
        clones = cache_clones()
        for item in clones:
            print(describe_clone(item))
        if not clones:
            print(f"the cache is empty ({root})")
        return EXIT_OK
    if action in ("prune", "clear"):
        if action == "clear":
            removed = prune_cache(None, 0, args.dry_run, grace=False)
        else:
            max_age, max_size = cache_limits()
            # 0: no limit, as in the configuration (everything: cache clear)
            if args.max_age is not None:
                max_age = args.max_age or None
            if args.max_size is not None:
                max_size = parse_size(args.max_size) or None
            if max_age is None and max_size is None:
                print("no limits set (filesync.cacheMaxAge, filesync.cacheMaxSize, "
                      "--max-age, --max-size) - nothing to do")
                return EXIT_OK
            removed = prune_cache(max_age, max_size, args.dry_run)
        verb = "would remove" if args.dry_run else "removed"
        for item in removed:
            print(f"{verb} {describe_clone(item).lstrip()}")
        size = sum(s for _, s, _, _ in removed)
        recent = action == "prune" and any(time.time() - used < CACHE_GRACE
                                           for _, _, used, _ in cache_clones())
        print(f"{verb} {plural(len(removed), 'clone')} ({human_size(size)}) from the cache"
              + (" - clones used in the last minutes are kept" if recent else ""))
        return EXIT_OK
    clones = cache_clones()
    max_age, max_size = cache_limits()
    print(f"{root}: {plural(len(clones), 'clone')}, {human_size(sum(s for _, s, _, _ in clones))}")
    limits = ([f"clones unused for {max_age} days"] if max_age is not None else []) + \
        ([f"the least recently used above {human_size(max_size)}"] if max_size is not None else [])
    print("cleaned up automatically: " + (" and ".join(limits) if limits else "never")
          + " (filesync.cacheMaxAge, filesync.cacheMaxSize)")
    return EXIT_OK


def hook_reminders(ctx, repo):
    """Terse notes on stderr about linked files needing attention: something
    to sync, a change not allowed, a missing file, an error."""
    links = Registry(repo).links()
    prefetch(ctx, repo, links)
    sts = [evaluate(ctx, repo, link) for link in links]
    attention = [st for st in sts if st.attention]
    for st in attention:
        print(f"filesync: {paint(st.rel, 'yellow', 'err')}: {render(describe(st), 'err')}",
              file=sys.stderr)
    if any(st.pending and not st.off_track for st in attention):
        print("filesync: run 'git filesync pull <file>' to sync", file=sys.stderr)
    if any(st.off_track for st in attention):
        print("filesync: 'pull --all' leaves out older and diverged files: pull them by name",
              file=sys.stderr)
    if any(st.violation for st in attention):
        print("filesync: see 'git filesync status' and 'git filesync diff <file>' "
              "for changes not allowed", file=sys.stderr)
    if any(st.missing for st in attention):
        print("filesync: run 'git filesync restore <file>' to bring a missing file back, "
              "or 'git filesync unlink <file>' to remove its link", file=sys.stderr)


def pushed_revs(hook_args):
    """(commits a push sends, commits the remote has there): from the
    pre-push hook's stdin ('<local ref> <local sha> <remote ref> <remote
    sha>' per ref; deletions skipped). Run by hand - git always passes the
    remote's name and URL: (HEAD, nothing). (Not stdin.isatty(): on Windows
    that's also true for NUL, i.e. </dev/null.)"""
    if not hook_args or sys.stdin is None:
        return ["HEAD"], []
    revs, remote = [], []
    for line in sys.stdin:
        parts = line.split()
        if len(parts) == 4 and parts[1].strip("0"):
            revs.append(parts[1])
            if parts[3].strip("0"):
                remote.append(parts[3])
    return revs, remote


def registry_blobs(repo, revs):
    """The distinct versions (blob ids) of .git-filesync at these revisions,
    asked with one command - usually a few for many branches; revisions
    without one (or not here) are left out."""
    revs = list(dict.fromkeys(revs))
    if not revs:
        return []
    p = repo.git(["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                 data="".join(f"{r}:{REGISTRY}\n" for r in revs).encode(), check=False)
    return list(dict.fromkeys(line.split()[0] for line in out(p).splitlines()
                              if line.endswith(" blob")))


def registry_entries(repo, blob):
    """[(url, synced commit, rel)] of the links in a version (blob id) of
    .git-filesync (none if it isn't readable)."""
    p = repo.git(["config", "--blob", blob, "--list", "-z"], check=False)
    if p.returncode:
        return []
    sources, files, dirs = parse_registry(p.stdout)
    entries = []
    for rel, v in sorted(list(files.items()) + [(d + "/", v) for d, v in dirs.items()]):
        url = sources.get(v.get("source", ""), {}).get("url")
        if url and v.get("commit"):
            entries.append((url, v["commit"], rel))
    return entries


def push_check(ctx, repo, hook_args):
    """pre-push: links in the pushed commits whose synced upstream commit is
    not on the upstream server (e.g. pulled from an unpushed commit of a
    mapped checkout) - others couldn't find their base. Entries the remote
    already has (in the commits the push replaces, or on its remote-tracking
    branches) were checked when they were pushed and are skipped, so a push
    usually needs no request upstream. Warns on stderr; True if such a link
    was found."""
    revs, remote = pushed_revs(hook_args)
    if hook_args:
        remote += out(repo.git(["for-each-ref", "--format=%(objectname)",
                                f"refs/remotes/{hook_args[0]}/"], check=False)).split()
    known = {(norm_url(url), commit) for blob in registry_blobs(repo, remote)
             for url, commit, _ in registry_entries(repo, blob)}
    found = {}       # (url, commit) -> [rels]
    for blob in registry_blobs(repo, revs):
        for url, commit, rel in registry_entries(repo, blob):
            if (norm_url(url), commit) in known:
                continue
            rels = found.setdefault((url, commit), [])
            if rel not in rels:
                rels.append(rel)
    unpushed = False
    for (url, commit), rels in found.items():
        on = ctx.on_server(url, commit)
        if on:
            continue
        what = paint(", ".join(rels), "yellow", "err")
        if on is None:
            print(f"filesync: {what}: cannot check whether upstream commit {commit[:12]} "
                  f"is on the server ({url} not reachable)", file=sys.stderr)
        else:
            print(f"filesync: {what}: synced from upstream commit {commit[:12]}, which is "
                  f"not on the server ({url}) - push it there first", file=sys.stderr)
            unpushed = True
    return unpushed


def cmd_hook(ctx, repo, args):
    """Run by the installed hooks (HOOKS). Reminders on stderr; pre-push also
    checks the pushed commits (filesync.pushCheck = warn | error | off).
    Exit code EXIT_REFUSED only to refuse a push."""
    hook_reminders(ctx, repo)
    if args.name != "pre-push":
        return EXIT_OK
    mode = out(repo.git(["config", "filesync.pushCheck"], check=False)).lower() or "warn"
    if mode not in ("warn", "error", "off"):
        warn(f"filesync.pushCheck: unknown value '{mode}', using 'warn'")
        mode = "warn"
    if mode == "off" or not push_check(ctx, repo, args.hook_args):
        return EXIT_OK
    if mode == "error":
        print(paint("filesync: push refused (filesync.pushCheck = error)", "boldred", "err"),
              file=sys.stderr)
        return EXIT_REFUSED
    print("filesync: pushing anyway (refuse such pushes: git config filesync.pushCheck error)",
          file=sys.stderr)
    return EXIT_OK


def hook_dir(repo, action=None):
    """The directory of the hooks; with core.hooksPath set, a warning that
    action (e.g. 'installing into') may affect other repositories too."""
    hp = out(repo.git(["config", "core.hooksPath"], check=False))
    if hp:
        hookdir = Path(os.path.expanduser(hp))
        if not hookdir.is_absolute():
            hookdir = repo.top / hookdir
        if action:
            warn(f"core.hooksPath is set; {action} {hookdir} "
                 "(may affect other repositories using it)")
    else:
        hookdir = Path(out(repo.git(["rev-parse", "--git-path", "hooks"])))
        if not hookdir.is_absolute():
            hookdir = repo.top / hookdir
    return hookdir


def hook_snippet(cmd):
    return (f"# {HOOK_MARKER}: reminders about linked files; blocks a push only "
            "with filesync.pushCheck = error\n"
            f"{cmd}\n")


def is_our_hook_line(line):
    s = line.strip()
    return REFS_VAR in s or s.startswith((f"# {HOOK_MARKER}:", "git filesync hook "))


def only_ours(rest):
    """Are these the lines of a hook file without our lines, one that we
    wrote (nothing else in it)?"""
    return all(ln.strip() in ("", "#!/bin/sh", "exit 0") for ln in rest)


def cmd_hooks(repo, args):
    """hooks without an action: the state of each of our hooks."""
    hookdir = hook_dir(repo)
    if out(repo.git(["config", "core.hooksPath"], check=False)):
        print(f"hooks directory: {hookdir} (core.hooksPath)")
    for name, cmd in HOOKS.items():
        f = hookdir / name
        text = f.read_bytes().decode("utf-8", "replace") if f.is_file() else None
        if text is None:
            state = paint("not installed", "dim") + " (install with 'git filesync hooks install')"
        elif hook_snippet(cmd) in text:
            state = paint("installed", "green")
        elif any(is_our_hook_line(ln) for ln in text.splitlines()):
            state = paint("outdated", "yellow") + \
                " (update with 'git filesync hooks install')"
        else:
            state = paint("hook of another tool, without our lines", "yellow") + \
                " (add them with 'git filesync hooks install --force')"
        print(f"{name}: {state}")
    return EXIT_OK


def cmd_install_hooks(repo, args):
    hookdir = hook_dir(repo, "installing into")
    hookdir.mkdir(parents=True, exist_ok=True)
    for name, cmd in HOOKS.items():
        f = hookdir / name
        snippet = hook_snippet(cmd)
        if f.exists():
            text = f.read_bytes().decode("utf-8", "replace")
            lines = text.splitlines(keepends=True)
            at = next((i for i, ln in enumerate(lines) if is_our_hook_line(ln)), None)
            if at is None and args.force:
                # right after the shebang: before commands that read the pushed
                # refs from stdin (git lfs pre-push), or an exec/exit at the end
                at = 1 if lines and lines[0].startswith("#!") else 0
                f.write_bytes("".join(lines[:at] + [snippet] + lines[at:]).encode("utf-8"))
                print(f"{name}: {paint('lines added to the existing hook', 'green')}")
                continue
            if at is None:
                where = (", before commands that read the pushed refs from stdin "
                         "(e.g. git lfs pre-push)") if name == "pre-push" else ""
                print(f"{name}: {paint('hook exists', 'yellow')}, add these lines to {f}"
                      f"{where}:\n{snippet}"
                      "(or run 'git filesync hooks install --force' to add them)")
                continue
            rest = [ln for ln in lines if not is_our_hook_line(ln)]
            if only_ours(rest):
                new = "#!/bin/sh\n" + snippet     # one we wrote: without the old exit 0
            else:                                 # replace our lines, in the same place
                new = "".join(rest[:at] + [snippet] + rest[at:])
            if new == text:
                print(f"{name}: already installed")
            else:
                f.write_bytes(new.encode("utf-8"))
                print(f"{name}: {paint('updated', 'green')}")
            continue
        # no exit 0 at the end: lines appended later (e.g. by git lfs) must run
        f.write_bytes(("#!/bin/sh\n" + snippet).encode())
        f.chmod(0o755)
        print(f"{name}: {paint('installed', 'green')}")
    return EXIT_OK


def cmd_uninstall_hooks(repo, args):
    """Remove our hooks. A hook file that only contains our snippet is deleted;
    in other hook files only our lines are removed, the rest stays untouched."""
    hookdir = hook_dir(repo, "removing from")
    for name in HOOKS:
        f = hookdir / name
        if not f.is_file():
            print(f"{name}: {paint('not installed', 'dim')}")
            continue
        lines = f.read_bytes().decode("utf-8", "replace").splitlines(keepends=True)
        rest = [ln for ln in lines if not is_our_hook_line(ln)]
        if len(rest) == len(lines):
            print(f"{name}: {paint('not installed', 'dim')} (existing hook left unchanged)")
            continue
        if only_ours(rest):
            f.unlink()
            print(f"{name}: {paint('removed', 'green')}")
        else:
            f.write_bytes("".join(rest).encode("utf-8"))
            print(f"{name}: {paint('git-filesync lines removed', 'green')}, rest of hook kept")
    return EXIT_OK


# --------------------------------------------------------------------------

def add_command(sub, name, **kw):
    """A (sub)command whose -h repeats its summary from the command list
    (unless it has a description of its own)."""
    hlp = kw.get("help")
    if hlp:
        kw["description"] = kw.get("description") or hlp[0].upper() + hlp[1:] + "."
    return sub.add_parser(name, **kw)


class Parser(argparse.ArgumentParser):
    """A command's parser: argparse shows an optional value as '--color
    [WHEN]', but it is taken only as --color=WHEN, like git (see run) -
    the usage and the help say so."""
    def format_usage(self):
        return equals_value(super().format_usage())

    def format_help(self):
        return equals_value(super().format_help())


def equals_value(text):
    """'--color [WHEN]' -> '--color[=WHEN]', also with argparse's colors."""
    esc = r"((?:\x1b\[[0-9;]*m)*)"
    return re.sub(rf"--color{esc} {esc}\[{esc}WHEN{esc}\]", r"--color\1\2[=\3WHEN\4]", text)


BASIC_COMMANDS = ("status", "pull", "diff", "difftool", "restore", "add", "rm", "unlink", "mv")


class NoTheme:
    """argparse's color theme before Python 3.14: no colors."""
    def __getattr__(self, name):
        return ""


class MainParser(argparse.ArgumentParser):
    """The top-level parser: usage line and the grouped command list (basic
    commands first, the rest in the order they were defined, `hook` last)
    in argparse's own colors - which exist from Python 3.14 on."""
    sub: "argparse._SubParsersAction"    # the subparsers action, set once the commands exist

    def theme(self):
        return getattr(self._get_formatter(), "_theme", None) or NoTheme()

    def format_usage(self):
        t = self.theme()
        return (f"{t.usage}usage: {t.reset}{t.prog}{self.prog}{t.reset} "
                f"[{t.summary_short_option}-h{t.reset}] "
                f"[{t.summary_long_option}--version{t.reset}] "
                f"{t.summary_action}<command>{t.reset} ...\n")

    def format_help(self):
        t = self.theme()
        width = max(shutil.get_terminal_size().columns - 2, 40)
        helps = {a.dest: a.help or "" for a in self.sub._choices_actions
                 if a.help != argparse.SUPPRESS}

        def group(title, names):
            lines = [f"{t.heading}{title}:{t.reset}"]
            for n in names:
                text = textwrap.wrap(helps[n], width - 20) or [""]
                lines.append(f"  {t.action}{n}{t.reset}{' ' * (18 - len(n))}{text[0]}")
                lines += [" " * 20 + x for x in text[1:]]
            return "\n".join(lines)
        advanced = [n for n in helps if n not in BASIC_COMMANDS]
        return (self.format_usage() + "\n" + super().format_help()
                + "\n" + group("basic commands", BASIC_COMMANDS)
                + "\n\n" + group("advanced commands", advanced)
                + "\n\nWithout a command: status. 'git filesync <command> -h' describes a "
                  "command\nand lists its options.\n")


def main(argv=None):
    """Run a command (see run) with output through PipeGuard: exit code
    EXIT_PIPE if a pipe broke and nothing else went wrong."""
    PipeGuard.broken = PipeGuard.stop = False
    if not isinstance(sys.stdout, PipeGuard):
        sys.stdout, sys.stderr = PipeGuard(sys.stdout), PipeGuard(sys.stderr, each=True)
    rc = run(argv)
    PipeGuard.stop = False           # the command is done
    sys.stdout.flush()
    sys.stderr.flush()
    return EXIT_PIPE if PipeGuard.broken and rc == EXIT_OK else rc


def run(argv=None):
    for stream in (sys.stdout, sys.stderr):
        # LF line ends like git's output, also on Windows (no CRLF translation);
        # not there if the stream was replaced (e.g. by a test harness)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(errors="replace", newline="\n")

    colorp = argparse.ArgumentParser(add_help=False)
    colorp.add_argument("--color", nargs="?", const="always", default="auto", metavar="WHEN",
                        choices=["always", "never", "auto"],
                        help="colored output: always, never or auto (default)")
    colorp.add_argument("--no-color", dest="color", action="store_const", const="never",
                        help="same as --color=never")
    common = argparse.ArgumentParser(add_help=False, parents=[colorp])

    def registry_worktree(parser):        # set, edit, source rename/set
        parser.add_argument("-W", "--worktree", action="store_true",
                            help=f"change {REGISTRY} in the working tree only, nothing staged")
    common.add_argument("--no-fetch", action="store_true",
                        help="do not fetch upstream repositories, use cached state")
    common.add_argument("--remote", action="store_true",
                        help="ignore mappings (source map) this once, use the upstream URL")

    argv = list(sys.argv[1:] if argv is None else argv)
    # like git: --color takes a value only as --color=WHEN; alone it is
    # always, and what follows is no value of it (status --color a.c)
    end = argv.index("--") if "--" in argv else len(argv)
    argv = [a if a != "--color" else "--color=always" for a in argv[:end]] + argv[end:]
    # the help in colors exactly when the output on stdout would be colored
    # (argparse has colors from Python 3.14 on, and checks the terminal too)
    color: dict = {"color": color_wanted(color_option(argv), sys.stdout)} \
        if "color" in inspect.signature(argparse.ArgumentParser).parameters else {}
    ap = MainParser(prog="git filesync", usage=argparse.SUPPRESS,
                    description="Keep single files in sync between Git repositories.", **color)
    ap.add_argument("--version", action="version", version=f"git-filesync {__version__}")
    sub = ap.sub = ap.add_subparsers(dest="cmd", metavar="<command>", prog="git filesync",
                                     parser_class=Parser)

    p = add_command(sub, "status", parents=[common], help="show sync state of linked files")
    p.add_argument("paths", nargs="*", metavar="PATH", help="linked files or directories (default: all)")
    p.add_argument("-s", "--short", action="store_true",
                   help="short format: upstream / committed / working tree columns")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also list all linked files with their sources")
    p.add_argument("--exit-code", action="store_true",
                   help="exit with 1 if something is to sync, a linked file is missing, or a "
                        "file that isn't adaptable is modified")

    p = add_command(sub, "pull", parents=[common], help="sync file(s) from upstream")
    p.add_argument("files", nargs="*", metavar="PATH", help="linked files or directories")
    p.add_argument("--all", action="store_true", help="sync all files with something to sync")
    p.add_argument("--commit", metavar="REV", help="sync to this upstream revision, once (as -b)")
    p.add_argument("-b", "--branch", help="sync to the head of this upstream branch, once (the "
                                          "files keep following their own branch or tag)")
    p.add_argument("--tag", help="sync to this upstream tag, once (as -b)")
    p.add_argument("--overwrite", action="store_true",
                   help="discard local adaptations instead of merging them, and uncommitted "
                        "changes (kept: 'git show')")
    p.add_argument("-W", "--worktree", action="store_true",
                   help="files and entries in the working tree only, nothing staged (to try a "
                        "newer version)")
    p.add_argument("--force", action="store_true",
                   help="linked directory: keep a file of this repository that pull would "
                        "delete (adapted, deleted upstream) or replace (new upstream)")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="only report what would happen (incl. merge conflicts)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="before each file: where it comes from and the version synced so far")

    for name, hlp, desc in (
            ("diff", "show local modifications against the synced upstream version", None),
            # in the command list right after diff; on its own (-h) it needs to say more
            ("difftool", "same in the configured difftool",
             "Show local modifications against the synced upstream version in the "
             "configured difftool.")):
        p = add_command(sub, name, parents=[common], help=hlp, description=desc,
                        epilog="Options after '--' are passed to git " + name + ".")
        p.add_argument("files", nargs="*", metavar="PATH",
                       help="linked files or directories (default: all)")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--upstream", action="store_true",
                       help="show what 'pull' would bring instead of the local modifications "
                            "(synced -> current upstream)")
        g.add_argument("--committed", action="store_true",
                       help="only the committed adaptations (synced -> HEAD)")
        g.add_argument("--cached", "--staged", dest="cached", action="store_true",
                       help="the index instead of the working tree (against the base of "
                            "the entry the index has)")
        p.add_argument("--commit", metavar="REV",
                       help="with --upstream: as for pull, synced -> REV")
        p.add_argument("-b", "--branch", help="with --upstream: as for pull, synced -> BRANCH")
        p.add_argument("--tag", help="with --upstream: as for pull, synced -> TAG")
        if name == "diff":
            p.add_argument("--for-upstream", action="store_true",
                           help="a patch for 'git apply' in the upstream repository: "
                                "upstream paths (not with --upstream)")
        else:
            p.add_argument("-y", "--no-prompt", dest="prompt", action="store_const", const=False,
                           help="don't ask before launching the tool for each file")
            p.add_argument("--prompt", action="store_const", const=True,
                           help="ask before each file even with difftool.prompt=false")

    p = add_command(sub, "add", parents=[common], help="link a file (or a directory) "
                                                     "to the upstream repository")
    p.add_argument("source", metavar="URL|SOURCE", help="upstream URL or name of a [source] in "
                   + REGISTRY)
    p.add_argument("file", metavar="FILE|DIR",
                   help="file in this repository (fetched from upstream if missing), or a "
                        "directory: all files below the upstream directory are linked")
    p.add_argument("-b", "--branch", help="the source's upstream branch (default: remote HEAD; "
                                          "with SOURCE: its branch)")
    p.add_argument("--tag", help="pin the file to this upstream tag instead of following the "
                                 "branch; a pattern (* ? [...]): the newest matching tag on it")
    p.add_argument("-p", "--path", help="upstream path (default: same as here)")
    p.add_argument("--include", metavar="PATTERN", action="append",
                   help="directory: only files matching PATTERN (gitignore-like; repeatable)")
    p.add_argument("--exclude", metavar="PATTERN", action="append",
                   help="directory: skip files matching PATTERN (repeatable)")
    p.add_argument("--per-file", action="store_true",
                   help="directory: link each file on its own ([file] entries) instead of the "
                        "directory ([dir]: pull also adds and deletes files)")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be linked")
    p.add_argument("--commit", metavar="REV", help="upstream revision to base the file on "
                                                    "instead of the head")
    p.add_argument("--overwrite", action="store_true",
                   help="replace an existing file with the upstream version")
    p.add_argument("--force", action="store_true", help="relink an already linked file")
    p.add_argument("--adaptable", action="store_true",
                   help="local adaptations allowed (default: the file must stay an exact copy)")
    p.add_argument("-W", "--worktree", action="store_true",
                   help="file(s) and entry in the working tree only, nothing staged")

    p = add_command(sub, "set", parents=[common], help="change the link of linked files: source, "
                                                     "tag, path, adaptable, patterns (without "
                                                     "options: show it)")
    p.add_argument("files", nargs="*", metavar="PATH", help="linked files or directories")
    p.add_argument("--list", action="store_true",
                   help="show the set command for each entry, one per line")
    p.add_argument("--source", metavar="URL|SOURCE",
                   help="take the files from another upstream (a fork, a moved repository), "
                        "or the [source] SOURCE; the synced version is kept")
    p.add_argument("-b", "--branch", help="follow BRANCH (with --source URL: of that upstream, "
                                          "default: its default branch); like for add, it "
                                          "selects the source, which is created if needed")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--tag", help="pin to this upstream tag (a pattern: the newest matching tag "
                                 "on the source's branch), without syncing")
    g.add_argument("--no-tag", action="store_true",
                   help="follow the source's branch again, without syncing")
    p.add_argument("-p", "--path", help="another upstream path (one file or directory); its "
                                        "current version becomes the base, as for add")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--adaptable", action="store_const", const=True,
                   help="allow local adaptations")
    g.add_argument("--no-adaptable", dest="adaptable", action="store_const", const=False,
                   help="the files must stay exact copies again (the default)")
    for k, what in (("include", "only files matching PATTERN"),
                    ("exclude", "skip files matching PATTERN")):
        g = p.add_mutually_exclusive_group()
        g.add_argument(f"--{k}", metavar="PATTERN", action="append",
                       help=f"linked directory: {what} (repeatable; replaces the patterns; "
                            "the files follow at the next pull)")
        g.add_argument(f"--no-{k}", action="store_true", help=f"linked directory: no {k} "
                                                               "patterns")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would change")
    registry_worktree(p)

    p = add_command(sub, "edit", parents=[colorp], help=f"open {REGISTRY} in the editor, then "
                                                      "check it and stage what changed")
    registry_worktree(p)

    p = add_command(sub, "restore", parents=[common],
                    help="like 'git restore': entries and files back to the layer below "
                         "(the index, HEAD), the synced upstream version")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-S", "--staged", action="store_true",
                   help="restore the index (from HEAD) instead of the working tree (from the "
                        "index)")
    p.add_argument("-W", "--worktree", action="store_true",
                   help="restore the working tree (the default; with -S: both, from HEAD)")

    p = add_command(sub, "rm", parents=[colorp],
                    help="remove linked files and their links, like 'git rm'")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-f", "--force", action="store_true",
                   help="also remove files with uncommitted changes")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be removed")

    p = add_command(sub, "unlink", parents=[colorp], help="remove links (the files are kept)")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be unlinked")

    p = add_command(sub, "mv", parents=[colorp], help="move linked files, keeping their links")
    p.add_argument("src", metavar="OLD", nargs="+", help="linked file(s)")
    p.add_argument("dst", metavar="NEW", help="new path or existing directory (for several "
                   "files: an existing directory)")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be moved")

    p = add_command(sub, "source", parents=[colorp], help="list or change the [source]s "
                                                        "(like 'git remote')")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list with URL, branch and file count")
    actions = p.add_subparsers(dest="action", metavar="ACTION")
    a = add_command(actions, "rename", parents=[colorp],
                    help="rename a source and all references to it")
    a.add_argument("name", metavar="OLD", help="key of the [source]")
    a.add_argument("value", metavar="NEW")
    a.add_argument("-n", "--dry-run", action="store_true", help="only show what would change")
    registry_worktree(a)
    # checks the branch upstream
    a = add_command(actions, "set", parents=[common],
                    help="change the URL or branch of a source (without options: show them)")
    a.add_argument("name", nargs="?", metavar="NAME", help="key of the [source]")
    a.add_argument("--url", help="another URL, e.g. after upstream moved")
    a.add_argument("-b", "--branch", help="follow BRANCH - for all files of the source; pinned "
                                          "ones look for newer tags (or those of a pattern) on it")
    a.add_argument("--list", action="store_true",
                   help="show the command for each source, one per line")
    a.add_argument("-n", "--dry-run", action="store_true", help="only show what would change")
    registry_worktree(a)
    a = add_command(actions, "map", parents=[colorp],
                    help="use a local checkout for an upstream URL (this repo's config; "
                         "--global for all repos)")
    a.add_argument("url", nargs="?", metavar="URL|SOURCE",
                   help="upstream URL, or the name of a [source] for its URL "
                        "(without DIR: list its mappings)")
    a.add_argument("dir", nargs="?", metavar="DIR", help="local checkout of the upstream repository")
    a.add_argument("--unset", action="store_true", help="remove the mapping for the URL")
    a.add_argument("--global", dest="glob", action="store_true",
                   help="use the global git config instead of this repository's")

    p = add_command(sub, "cache", parents=[colorp],
                       help="show, list or clean up the cache of upstream clones")
    actions = p.add_subparsers(dest="action", metavar="ACTION")
    add_command(actions, "list", parents=[colorp],
                help="the clones, most recently used first: size, last used, URL",
                description="List the cached clones, most recently used first: size, "
                            "last used, URL.")
    a = add_command(actions, "prune", parents=[colorp],
                           help="remove clones not used for a while (default: the configured "
                                "limits, filesync.cacheMaxAge / cacheMaxSize)")
    a.add_argument("--max-age", type=int, metavar="DAYS",
                   help="clones not used for DAYS days")
    a.add_argument("--max-size", metavar="SIZE",
                   help="then the least recently used, down to SIZE (e.g. 500M, 2G)")
    a.add_argument("-n", "--dry-run", action="store_true", help="only show what would be removed")
    a = add_command(actions, "clear", parents=[colorp], help="remove all clones")
    a.add_argument("-n", "--dry-run", action="store_true", help="only show what would be removed")
    add_command(actions, "dir", parents=[colorp], help="print the cache's directory")

    p = add_command(sub, "hooks", parents=[colorp],
                    help="show, install or remove the pre-push/post-merge hooks")
    actions = p.add_subparsers(dest="action", metavar="ACTION")
    a = add_command(actions, "install", parents=[colorp],
                    help="install the hooks, or update them")
    a.add_argument("--force", action="store_true",
                   help="add our lines to existing hooks of other tools (right after the #! line)")
    add_command(actions, "uninstall", parents=[colorp],
                help="remove the hooks (only our lines from hooks of other tools)")
    # what the installed hooks run - not in the command list
    p = add_command(sub, "hook", parents=[colorp], help=argparse.SUPPRESS,
                    description="Run the checks of an installed hook (called by the hooks).")
    p.add_argument("name", choices=list(HOOKS))
    p.add_argument("hook_args", nargs=argparse.REMAINDER, help="the hook's arguments")

    sub.help = argparse.SUPPRESS      # MainParser lists the commands in groups

    extra = []
    if argv and argv[0] in ("diff", "difftool") and "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["status"])
    args.extra = extra
    args.for_upstream = getattr(args, "for_upstream", False)
    try:
        try:
            repo = Repo()
        except FsError:
            repo = None
        setup_colors(args.color, repo.top if repo else None)
        if args.cmd == "source" and args.action == "map":     # also outside a repository
            return cmd_map(args, repo)
        if args.cmd == "cache":               # also outside a repository
            return cmd_cache(args)
        if repo is None:
            raise FsError("not inside a Git working tree")
        if args.cmd == "hooks":
            return {None: cmd_hooks, "install": cmd_install_hooks,
                    "uninstall": cmd_uninstall_hooks}[args.action](repo, args)
        if args.cmd == "hook":
            args.no_fetch = args.name == "post-merge"    # pre-push: online anyway
        ctx = repo.ctx = Context(args, repo)
        reading = args.cmd in ("status", "diff", "difftool", "hook") or \
            args.cmd == "source" and not args.action
        if not reading and args.cmd != "edit":    # edit repairs it; others would stop
            repo.registry("index")                # halfway (see Registry.stage)
        PipeGuard.stop = reading
        with repo.scratch() if reading else nullcontext():
            return {"status": cmd_status, "pull": cmd_pull, "add": cmd_add, "set": cmd_set,
                    "edit": cmd_edit, "restore": cmd_restore, "rm": cmd_rm,
                    "unlink": cmd_unlink, "mv": cmd_mv, "source": cmd_source,
                    "diff": cmd_diff, "difftool": cmd_difftool,
                    "hook": cmd_hook}[args.cmd](ctx, repo, args)
    except FsError as e:
        error(str(e))
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:     # a reading command, its output piped into e.g. `head`
        PipeGuard.broken = True
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
