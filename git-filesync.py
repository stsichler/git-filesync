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
        strict = true          ; optional: no local modifications allowed
        commit = <upstream commit of the last sync>
        blob = <blob id of the upstream file at that commit>

A link records the upstream version the file is based on (commit/blob);
local adaptations on top of it are allowed and kept by a 3-way merge on
pull, unless the file is marked strict.

Commands (run inside the repository; without a command: status).
PATH may be a file or a directory (= all linked files below it); options
follow the command. No command commits: they stage (restore: with -S), like
their git namesakes, and propose a commit message that a plain `git commit`
offers (.git/SQUASH_MSG; a copy stays in .git/FILESYNC_MSG) - committing
is up to you.

Basic commands:

    status [PATH...]            state of the linked files like `git status`:
                                upstream changes to sync, committed
                                adaptations, uncommitted changes
        -s, --short             short format: upstream/committed/worktree
                                columns (upstream: P pending, O older,
                                D diverged, R renamed, X deleted
                                upstream, N new; E error; committed: M
                                adapted)
        -v, --verbose           also list all linked files with their sources
                                (pinned ones with the newest tag: the first
                                tagged commit after theirs on the source
                                branch's first-parent line)
        --exit-code             exit 1 if something is to sync or a strict
                                file is modified

    pull PATH... | --all        sync to the upstream version of the files and
                                stage them, like `git merge --squash`; the
                                proposed message lists the upstream commits
                                since the last sync per file; adaptations
                                are merged (conflicts: resolve, then git
                                add), uncommitted
                                changes refused; a file renamed upstream is
                                followed, one deleted there is reported
        --all                   all files with something to sync
        --commit REV            sync to this upstream revision (one file;
                                also backwards)
        -b, --branch BRANCH     sync to the head of BRANCH, once: the files
                                keep following their own branch or tag
                                (to switch: set -b/--tag)
        --tag TAG               sync to TAG, once (as -b)
        --overwrite             discard local adaptations instead of merging
        -n, --dry-run           only report what would happen (incl.
                                merge conflicts); change nothing
        -v, --verbose           before each file: where it comes from (as
                                status -v) and the version synced so far

    diff [PATH...] [-- OPTS]    local changes vs. the synced upstream version
                                (one `git diff`, OPTS passed to it)
        --committed             only committed adaptations (synced -> HEAD)
        --upstream              what pull would bring (synced -> upstream)
        --commit REV, -b BRANCH, --tag TAG
                                with --upstream: what pull with these
                                options would bring (nothing is switched)
        --for-upstream          a patch for `git apply -3` in the upstream
                                repository (upstream paths)

    difftool [PATH...] [-- OPTS]  the same in the configured difftool
        --committed, --upstream, --commit, -b, --tag  as for diff
        -y, --no-prompt         don't ask before each file (default: ask,
                                like git difftool; difftool.prompt)
        --prompt                ask even with difftool.prompt = false

    restore PATH...             restore files to the synced upstream version
                                (the base), like `git restore`; e.g. to
                                discard adaptations of a strict file;
                                uncommitted content is kept as a blob
                                (`discarded: FILE (git show ID ...)`)
        -S, --staged            restore the index instead of the working tree
        -W, --worktree          restore the working tree (default; with -S:
                                both)

    add URL|SOURCE FILE         link FILE to a file in an upstream repository
                                (SOURCE: exactly that [source]; URL: the
                                source with that URL and branch/tag, else a
                                new one named 'owner/repo' after the URL, with
                                a number appended if taken); the base is the
                                upstream head (or --commit): an existing FILE
                                is kept, its differences count as adaptations;
                                a missing FILE is fetched (its directory must
                                exist, as for cp); FILE and
                                .git-filesync are staged like `git add` - a
                                plain `git commit` offers the proposed message
    add URL|SOURCE DIR          link every file below an upstream directory
                                (-p, default: same as DIR) as DIR/...; files
                                already linked are skipped; as for cp -r, DIR
                                may be new, its parent must exist
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
        --commit REV            upstream revision to base FILE on instead
                                of the head
        --overwrite             replace an existing FILE with the upstream
                                version (uncommitted content: as restore)
        --strict                FILE must stay an exact copy
        --force                 relink an already linked file
        -n, --dry-run           only show what would be linked

    rm PATH...                  remove linked files and their links, staged
                                like `git rm`; refused for files with
                                uncommitted changes
        -f, --force             remove them anyway (their content: as
                                restore)
        -n, --dry-run           only show what would be removed

    unlink PATH...              remove links (the files are kept)
    mv OLD NEW                  move a linked file (git mv), keeping its link;
                                the directory of NEW must exist
        -n, --dry-run           (both) only show what would be done

Advanced commands:

    set PATH... OPTIONS         change the link of linked files, like `source`
                                for sources; only .git-filesync is changed
                                (and staged), the synced version is kept
                                where it still applies
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
        -p, --path PATH         another upstream path (one file); its
                                current version becomes the base, as for add
        --strict, --no-strict   mark as strict / allow adaptations again
        -n, --dry-run           only show what would change

    edit                        open .git-filesync in the editor (like `git
                                config --edit`); afterwards it is checked
                                and staged

    source                      list the [source]s (-v: with URL, branch,
                                files)
    source rename OLD NEW       rename a [source] and all references to it
    source set-url NAME URL     change the URL of a [source]; the synced
                                versions are looked up there as for set
                                --source
    source set-branch NAME BRANCH  follow BRANCH, all files of the source
                                (set-url, set-branch: the branch must exist
                                upstream)
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
        --older-than DAYS, --max-size SIZE  other limits (SIZE: 500M, 2G;
                                0: no limit, as configured; all: cache clear)
        -n, --dry-run           only show what would be removed
    cache clear [-n]            remove all clones
    cache dir                   print its directory (e.g. for CI caching)

    hooks                       the state of the pre-push/post-merge hooks:
                                installed, outdated, not installed, or
                                hooks of other tools without our lines
    hooks install               install the hooks (or update them):
                                reminders about pending syncs, strict
                                violations, errors; pre-push also warns if a
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
                                pull, diff/difftool --upstream, add, set,
                                source set-url/set-branch; restore and diff
                                of local changes never fetch)
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
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import namedtuple
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

__version__ = "0.17.0"
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
REGISTRY_HEADER = ("# git-filesync: files of this repository that are kept in sync with\n"
                   "# files in other repositories. Maintained by 'git filesync'; [file]\n"
                   "# commit/blob record the upstream version each file is based on.\n")


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
    """'https://github.com/owner/repo.git' -> 'owner/repo'."""
    m = re.search(r"([^/:]+/[^/:]+?)(?:\.git)?/?$", url.strip())
    return m.group(1) if m else url


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
        self.tag_names = None   # for a tag pattern: the matching tags ref is at
        self.lfs_server = None  # mapped: () -> repository to fetch missing LFS objects in
        self._memo = {}      # answers that don't change during a run (see prefetch)

    def git(self, args, **kw):
        kw.setdefault("env", clean_env())
        return git(PROTOCOL_V2 + ["-C", self.dir] + list(args), **kw)

    def head_ref(self):
        """Full ref name checked out in a local checkout, None if detached."""
        if ("head_ref",) not in self._memo:
            p = self.git(["symbolic-ref", "-q", "HEAD"], check=False)
            self._memo[("head_ref",)] = out(p) if p.returncode == 0 else None
        return self._memo[("head_ref",)]

    def head_desc(self):
        """What a local checkout has checked out: branch name or detached commit."""
        p = self.git(["symbolic-ref", "--short", "-q", "HEAD"], check=False)
        if p.returncode == 0:
            return out(p)
        p = self.git(["describe", "--tags", "--exact-match", "HEAD"], check=False)
        return f"detached at {out(p)}" if p.returncode == 0 else \
            f"detached at {self.short('HEAD')}"

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
        if not out(self.git(["for-each-ref", "--count=1", "refs/remotes/"])):
            unpublished = set()
        else:
            p = self.git(["rev-list"] + commits + ["--not", "--remotes"], check=False)
            if p.returncode:
                return            # e.g. an unknown commit: is_published() asks one by one
            unpublished = set(out(p).split())
        for c in commits:
            self._memo[("published", c)] = c not in unpublished

    def has_uncommitted(self, path):
        """Does a local checkout have uncommitted changes to path? One `git
        status` for the whole checkout, asked once. The checkout is only read:
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
                return bool(out(self.git(lfs + status + ["--", lit(path)], check=False)))
        return path in self._memo[key]

    def resolve(self, rev=None):
        key = ("resolve", rev)
        if key not in self._memo:
            self._memo[key] = self._resolve(rev)
        return self._memo[key]

    def _resolve(self, rev):
        if rev is None:
            cands = [self.ref]
        elif not self.local and not re.fullmatch(r"[0-9a-f]{40,64}", rev):
            # cache clone: branch names refer to the remote-tracking refs
            cands = [f"refs/remotes/origin/{rev}", rev]
        else:
            cands = [rev]
        for c in cands:
            p = self.git(["rev-parse", "--verify", "--quiet", c + "^{commit}"], check=False)
            if p.returncode == 0:
                return out(p)
        return None

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
        a local checkout, are published), the checkout's HEAD versions."""
        tip = self.resolve()
        if not tip:
            return
        paths = [lk.path for lk in links]
        self.blobs_at(tip, paths)
        self.commits_exist(lk.commit for lk in links)
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
        oid, size = lfs_pointer(pointer)
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
        """Abbreviated ids of these revisions with one `rev-parse --short`."""
        revs = [r for r in dict.fromkeys(revs) if r and ("short", r) not in self._memo]
        if not revs:
            return
        p = self.git(["rev-parse", "--short"] + revs, check=False)
        lines = out(p).splitlines()
        if p.returncode or len(lines) != len(revs):
            for r in revs:      # one by one, so that a bad one fails on its own
                self._memo[("short", r)] = out(self.git(["rev-parse", "--short", r]))
            return
        self._memo.update((("short", r), x) for r, x in zip(revs, lines))

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
        newest tag after tag is on the first tagged commit of the branch's
        first-parent line (a tag on a merged side branch doesn't count).
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
        return out(self.git(["rev-list", "-1", rev, "--", lit(path)])) or rev

    def count(self, old, new, *paths):
        key = ("count", old, new, paths)
        if key not in self._memo:
            self._memo[key] = int(out(self.git(["rev-list", "--count", f"{old}..{new}", "--"]
                                               + [lit(p) for p in paths])))
        return self._memo[key]

    def log(self, rng, *paths):
        return out(self.git(["log", "--reverse", "--format=- %s (%h)", rng, "--"]
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
        p = self.git(["cat-file", "-t", f"{commit}:{path}"], check=False)
        return p.returncode == 0 and out(p) == "tree"

    def path_history(self, path, max_count):
        """[(commit, blob id)] of commits on the branch touching path, newest first."""
        revs = out(self.git(["rev-list", f"--max-count={max_count}",
                             self.ref, "--", lit(path)])).split()
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
        # restore, and diff of local changes, only need the synced versions,
        # which never change (a blob missing in the cache is fetched lazily):
        # fetched only if the cache lacks the branch (lazy)
        offline = args.cmd == "restore" or \
            args.cmd in ("diff", "difftool") and not args.upstream
        no_fetch = getattr(args, "no_fetch", False)
        self.fetch, self.lazy = not (no_fetch or offline), offline and not no_fetch
        # fetch even for a tag already cached, to learn about newer tags
        self.want_tags = getattr(args, "verbose", False) or args.cmd == "pull"
        self._sources = {}
        self._ready = set()
        self._fetch_failed = set()
        self._mappings = None

    def source(self, url, ref, name=None, line=None):
        """Source for url and ref (('branch' | 'tag', name)); name is its key
        in .git-filesync (used as label). For a tag, line is the branch of
        the source: a pattern is resolved to the newest matching tag on it.
        A branch that doesn't exist is an error (a tag not on it isn't: see
        tag_info)."""
        key = (norm_url(url), ref, line if ref[0] == "tag" else None)
        if key not in self._sources:
            try:
                self._sources[key] = self._make(url, ref, name, line)
                if self._sources[key].local:     # LFS objects it lacks: via the cache clone
                    self._sources[key].lfs_server = lambda: self._cache(url)
            except FsError as e:      # e.g. a failed clone: not tried again for each file
                self._sources[key] = e
        s = self._sources[key]
        if isinstance(s, FsError):
            raise s
        return s

    def local_path(self, url):
        """Mapped local checkout for url (validated), or None."""
        if self._mappings is None:
            # repo-local mapping overrides a global one (later entries win)
            self._mappings = {norm_url(u): d for _, _, u, d in
                              local_mappings(cwd=self.repo_top)}
            self._local_ok = {}
        key = norm_url(url)
        if key not in self._local_ok:
            local = self._mappings.get(key)
            path = Path(os.path.expanduser(local)) if local else None
            if path and git(["-C", path, "rev-parse", "--git-dir"], env=clean_env(),
                            check=False).returncode:
                warn(f"mapped local checkout {path} is not a Git repository; using {url}")
                path = None
            self._local_ok[key] = path
        return self._local_ok[key]

    def default_branch(self, url):
        """Default branch upstream: from a mapped checkout or the cache
        when possible (works offline), otherwise asked from the server."""
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

    @staticmethod
    def cache_dir(url):
        return cache_root() / (hashlib.sha1(norm_url(url).encode()).hexdigest()[:16] + ".git")

    def _cache(self, url, tag=None, need=None):
        """The cache clone of url, fetched once per run - not for a tag
        already there (tags are taken as immutable), unless newer tags are
        of interest (want_tags); with lazy, only if it lacks the ref need."""
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
        self.gitdir = Path(lines[1])
        self.objects = Path.cwd() / lines[2]      # relative to the current directory
        # shell aliases run in the top-level dir and pass the original
        # subdirectory in GIT_PREFIX
        prefix = os.environ.get("GIT_PREFIX")
        self.base = Path.cwd() / prefix if prefix else Path.cwd()
        self._head = {}           # rel -> blob id in HEAD (None: not there)
        self._dirty = {}          # rel -> differs between HEAD and working tree
        self._plain = {}          # rel -> no content-changing attributes
        self._raw = {}            # blob id -> content (read_blob)
        self._local = {}          # (rel, content hash, size) -> blob id (as_local)

    def git(self, args, **kw):
        return git(args, cwd=self.top, **kw)

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
        """Does the working tree file differ from HEAD (like `git diff HEAD`)?"""
        if rel not in self._dirty:
            self._dirty[rel] = self.git(["diff", "--quiet", "HEAD", "--", lit(rel)],
                                        check=False).returncode == 1
        return self._dirty[rel]

    def user_path(self, s):
        """A path given by the user, absolute: relative to the current
        directory, '..' resolved by name; symlinks only in its directories,
        not the path itself (a linked file may be a symlink, as for git)."""
        p = Path(os.path.normpath(self.base / s))
        return p.parent.resolve() / p.name if p.name else p.resolve()

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
            current = self.index_entries(rels)
            if current:
                tmp_git(["update-index", "-z", "--add", "--index-info"], "add",
                        "".join(f"{m} {o}\t{r}\0" for r, (m, o) in current.items()).encode())
            tmp_git(["add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"], "add",
                    "".join(lit(r) + "\0" for r in rels).encode())
            p = tmp_git(["ls-files", "-s", "-z"], "add", None)
        found = {}
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name:
                found[name] = info.split(" ")[1]
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
        for (_, oid), content in batch_read(self.git, oids, {("raw", o): 1 for o in self._raw}):
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

    def index_entries(self, rels):
        """{rel: (mode, blob id)} of these files in the index, one command."""
        entries = {}
        p = self.git(["ls-files", "-s", "-z", "--"] + [lit(r) for r in rels], check=False)
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name:
                entries[name] = (info.split(" ")[0], info.split(" ")[1])
        return entries

    def write_files(self, files, stage=True, worktree=True):
        """Put these [(rel, content)] - content in the form stored here, LFS
        resolved - into the index and/or the working tree, converted for it
        as on any checkout (eol, attributes, LFS): each stored as this
        repository stores it - as it is without content-changing attributes
        (see check_plain), else converted (see as_local; LFS: the pointer) -
        then all put there at once (see put_blobs)."""
        if not files:
            return
        plain = [(r, c) for r, c in files if self.is_plain(r)]
        ids = dict(zip([r for r, _ in plain], self.store_many([c for _, c in plain])))
        rest = [(c, r) for r, c in files if r not in ids]
        self.as_local_many(rest)
        ids.update((r, self.as_local(c, r)) for c, r in rest)
        self.put_blobs([(r, ids[r]) for r, _ in files], stage, worktree)

    def put_blobs(self, entries, stage=True, worktree=True):
        """Put these [(rel, blob id)] - blobs as stored here (LFS pointers
        too) - into the index and/or the working tree, where git converts
        them as on any checkout: a few commands for all of them."""
        if not entries:
            return
        rels, oids = [r for r, _ in entries], [o for _, o in entries]
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
        (clean-filtered), via a temporary index - with this index's entries,
        for git's rule on CRLF already in the index - instead of a
        hash-object each. Writes the blobs: for reading commands (scratch)."""
        rels = [r for r in rels if (self.top / r).is_file()]
        if not rels:
            return {}
        with tempfile.TemporaryDirectory(prefix="git-filesync-") as d:
            env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
            current = self.index_entries(rels)
            if current:
                self.git(["update-index", "-z", "--add", "--index-info"], env=env,
                         data="".join(f"{m} {o}\t{r}\0" for r, (m, o) in current.items()).encode())
            self.git(["add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"], env=env,
                     data="".join(lit(r) + "\0" for r in rels).encode())
            p = self.git(["ls-files", "-s", "-z"], env=env)
        found = {}
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name in rels:
                found[name] = info.split(" ")[1]
        return found

    def plain_content(self, rel, data):
        """Is data, as a file at rel, stored as it is - no content-changing
        attributes, no CR, no LFS pointer? (see check_plain)"""
        return bool(self.is_plain(rel)) and b"\r" not in data and not lfs_pointer(data)

    def fix_eol(self, path):
        """Rewrite a file written by `git config -f` (LF) in working tree form,
        so core.autocrlf repositories don't warn about it."""
        data = path.read_bytes().replace(b"\r\n", b"\n")
        conv = self.to_worktree(data, self.rel(path))
        if conv != path.read_bytes():
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


def edit_registry(data, pending, drop=()):
    """The registry's bytes with the sections in drop ({("file" | "source",
    name)}) removed - like `git config --remove-section`: from the header
    to the next section - and pending ({(rel, key): value}) written into the
    [file "rel"] sections: a value replaced in its `key = value` line, a new
    key added at the end of its section, a new section appended. None if
    the file isn't laid out simply enough for that (a section or key twice,
    a value with quotes or a comment, keys on the header line)."""
    lines = data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        lines[-1] += b"\n"
    sections, current, keys = {}, None, {}     # rel -> [first, last line]; (rel, key) -> line
    headers = {}                    # (section, name) -> its line; None: any other header
    for i, raw in enumerate(lines):
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        m = re.fullmatch(r'\s*\[\s*([A-Za-z][A-Za-z0-9-]*)\s+"((?:[^"\\]|\\.)*)"\s*\]\s*', line)
        if m:
            name = (m.group(1).lower(), re.sub(r"\\(.)", r"\1", m.group(2)))
            if name in headers:
                return None
            headers[name] = i
            current = name[1] if name[0] == "file" and name not in drop else None
            if current is not None:
                sections[current] = [i, i]
            continue
        if re.match(r"\s*\[", line):
            headers[(None, i)] = i
            current = None
            continue
        if current is None or not line.strip() or re.match(r"\s*[#;]", line):
            continue
        m = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9-]*)\s*(?:=\s*(.*?))?\s*", line)
        if not m:
            return None
        key = (current, m.group(1).lower())
        if key in keys or key in pending and m.group(2) is not None \
                and m.group(2) != config_value(m.group(2)):
            return None      # twice, or a value we wouldn't write like that
        keys[key] = i
        sections[current][1] = i
    starts = sorted(headers.values()) + [len(lines)]
    dropped = set()
    for name in drop:
        if name not in headers:
            return None
        first = headers[name]
        dropped.update(range(first, next(j for j in starts if j > first)))
    after, appended = {}, {}
    for (rel, k), v in pending.items():
        text = f"\t{k} = {config_value(v)}\n".encode()
        if (rel, k) in keys:
            i = keys[(rel, k)]
            raw = lines[i]
            lines[i] = raw[:len(raw) - len(raw.lstrip())] + text.lstrip(b"\t")[:-1] + \
                raw[len(raw.rstrip(b"\r\n")):]
        elif rel in sections:
            after.setdefault(sections[rel][1], []).append(text)
        else:
            appended.setdefault(rel, []).append(text)
    out_lines = []
    for i, raw in enumerate(lines):
        if i not in dropped:
            out_lines.append(raw)
            out_lines += after.get(i, [])
    for rel, texts in appended.items():
        name = rel.replace("\\", "\\\\").replace('"', '\\"')
        out_lines.append(f'[file "{name}"]\n'.encode())
        out_lines += texts
    return b"".join(out_lines)


def parse_registry(raw):
    """({source: {key: value}}, {file: {key: value}}) from `git config --list -z`."""
    sources, files = {}, {}
    for item in raw.decode("utf-8", "replace").split("\0"):
        if not item:
            continue
        key, has_val, val = item.partition("\n")
        if not has_val:
            val = "true"     # a key without '= value' is a boolean true in git config
        sect, _, rest = key.partition(".")
        sub, _, name = rest.rpartition(".")
        if sect == "source" and sub:
            sources.setdefault(sub, {})[name] = val
        elif sect == "file" and sub:
            files.setdefault(sub, {})[name] = val
    return sources, files


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


def registry_path(repo):
    """.git-filesync - refused if it is a symlink: it comes from a commit,
    possibly made by others, and is written to (also: as git writes it)."""
    path = repo.top / REGISTRY
    if path.is_symlink():
        raise FsError(f"{REGISTRY} is a symbolic link - refused (it must be a file)")
    return path


class Registry:
    """The repository's .git-filesync: [source] and [file] sections."""

    def __init__(self, repo):
        self.repo = repo
        self.path = registry_path(repo)
        self.sources, self.files = {}, {}
        self.dry_run = False      # only change the in-memory state
        self._pending = {}        # (rel, key) -> new commit/blob id, see set_file
        self._drop = set()        # ("file" | "source", name): sections to remove, see remove_file
        if self.path.exists():
            p = git(["config", "-f", self.path, "--list", "-z"], check=False)
            if p.returncode:
                raise FsError(f"{REGISTRY}: cannot parse: "
                              + p.stderr.decode("utf-8", "replace").strip())
            self.sources, self.files = parse_registry(p.stdout)

    def links(self):
        return [Link(self, rel) for rel in sorted(self.files)]

    def _cfg(self, *args):
        if self.dry_run:
            return
        self.flush()
        if not self.path.exists():
            self.path.write_bytes(REGISTRY_HEADER.encode())
        git(["config", "-f", self.path] + list(args))

    def set_file(self, rel, name, value):
        """Set (value None: remove) a key of a [file]. Values are written
        later, all at once (see flush) - pull, add and set change several
        keys of many files."""
        if value is not None and not self.dry_run:
            self._pending[(rel, name)] = value
            self.files.setdefault(rel, {})[name] = value
            return
        if value is None:
            if name in self.files.get(rel, {}):
                self._cfg("--unset-all", f"file.{rel}.{name}")
                del self.files[rel][name]
        else:
            self._cfg(f"file.{rel}.{name}", value)
            self.files.setdefault(rel, {})[name] = value

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
        self._cfg(f"source.{name}.url", url)
        self._cfg(f"source.{name}.branch", branch)
        self.sources[name] = {"url": url, "branch": branch}
        return name

    def set_source(self, name, key, value):
        """Set (value None: remove) a key of a [source]."""
        if value is None:
            if key in self.sources[name]:
                self._cfg("--unset-all", f"source.{name}.{key}")
                del self.sources[name][key]
        else:
            self._cfg(f"source.{name}.{key}", value)
            self.sources[name][key] = value

    def remove_source(self, name):
        self._cfg("--remove-section", f"source.{name}")
        del self.sources[name]

    def rename_source(self, old, new):
        self._cfg("--rename-section", f"source.{old}", f"source.{new}")
        self.sources[new] = self.sources.pop(old)
        for rel, f in self.files.items():
            if f.get("source") == old:
                self.set_file(rel, "source", new)

    def remove_file(self, rel, keep_source=None):
        """Remove a [file]; its [source] too when no other file uses it
        (unless it is keep_source). Removed later, all at once (see flush)
        - rm and unlink remove many."""
        src = self.files.pop(rel, {}).get("source")
        self._remove_section("file", rel)
        if src and src != keep_source and src in self.sources and \
                not any(f.get("source") == src for f in self.files.values()):
            self._remove_section("source", src)
            del self.sources[src]

    def _remove_section(self, sect, name):
        if self.dry_run:
            return
        if sect == "file":        # values set before are gone with it
            self._pending = {k: v for k, v in self._pending.items() if k[0] != name}
        self._drop.add((sect, name))

    def rename_file(self, old, new):
        self._cfg("--rename-section", f"file.{old}", f"file.{new}")
        self.files[new] = self.files.pop(old)

    def flush(self):
        """Remove the sections and write the [file] values pending (see
        remove_file, set_file) at once, editing the file directly instead of
        one `git config` for each - checked by reading it back with git,
        which must give exactly the state here; otherwise (an unusual layout
        of the file) one by one with git. Removals first: a value pending
        for a removed [file] was set after the removal."""
        pending, self._pending = self._pending, {}
        drop, self._drop = self._drop, set()
        if not (pending or drop):
            return
        original = self.path.read_bytes() if self.path.exists() \
            else REGISTRY_HEADER.encode()
        edited = edit_registry(original, pending, drop)
        if edited is not None:
            self.path.write_bytes(edited)
            p = git(["config", "-f", self.path, "--list", "-z"], check=False)
            if p.returncode == 0 and parse_registry(p.stdout) == (self.sources, self.files):
                return
        self.path.write_bytes(original)
        for sect, name in sorted(drop):
            git(["config", "-f", self.path, "--remove-section", f"{sect}.{name}"])
        for (rel, k), v in pending.items():
            git(["config", "-f", self.path, f"file.{rel}.{k}", v])

    def finish(self):
        """Fix line endings and stage the registry (or its removal when empty)."""
        self.flush()
        if self.path.exists():
            if not self.sources and not self.files:
                self.path.unlink()
            else:
                self.repo.fix_eol(self.path)
        self.repo.git(["add", "-A", "--", REGISTRY])


class Link:
    """One [file] entry: a file linked to a file in an upstream repository."""

    def __init__(self, reg, rel):
        self.reg, self.rel = reg, rel

    @property
    def v(self):
        return self.reg.files.get(self.rel, {})

    @property
    def target(self):
        problem = path_problem(self.rel)
        if problem:
            raise FsError(f"'{self.rel}' in {REGISTRY}: {problem}")
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
    def strict(self):
        """The file must stay an exact copy of the upstream version."""
        return self.v.get("strict", "").lower() in ("true", "yes", "on", "1")

    def set(self, name, value):
        self.reg.set_file(self.rel, name, value)


def select_links(repo, reg, paths):
    """Links for the given files/directories (all links if none given)."""
    if not paths:
        return reg.links()
    result = []
    for s in paths:
        rel = repo.rel(repo.user_path(s))
        if rel in reg.files:
            result.append(Link(reg, rel))
            continue
        under = [lk for lk in reg.links() if rel == "." or lk.rel.startswith(rel + "/")]
        if not under:
            raise FsError(f"'{rel}' is not linked (use 'git filesync add' to link it)")
        result += under
    seen, unique = set(), []
    for lk in result:
        if lk.rel not in seen:
            seen.add(lk.rel)
            unique.append(lk)
    return unique


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

def local_equiv(repo, src, blob, rel, path):
    """Upstream blob as this repo would store it; None if unavailable."""
    if not blob:
        return None
    try:
        return repo.as_local(src.read_content(blob, path), rel)
    except FsError:
        return None


class BaseUnavailable(FsError):
    pass


def matches_base(repo, src, link, oid, read):
    """Does a blob of this repo (id oid; read() returns its raw bytes) equal
    the synced upstream version, i.e. the base recorded in .git-filesync?
    Raises BaseUnavailable if that version can't be read."""
    if oid == link.blob:
        return True
    if not link.blob:
        return False
    if repo.is_plain(link.rel) and src.is_plain(link.blob):
        # LF-only content without filters here: a checkout and checkin leave
        # it as it is, so only the very same blob matches (no git calls)
        return False
    try:
        ptr = lfs_pointer(src.read_blob(link.blob))
        if ptr:   # upstream stores it in LFS: compare against the pointer's hash first
            data = read()
            if (hashlib.sha256(data).hexdigest(), len(data)) == ptr or lfs_pointer(data) == ptr:
                return True
        return oid == repo.as_local(src.read_content(link.blob, link.path), link.rel)
    except BaseUnavailable:
        raise
    except FsError as e:
        raise BaseUnavailable(f"synced version {link.blob[:12]} not available in "
                              f"{src.label}, file counts as modified ({e})")


@dataclass
class FileState:
    """What evaluate() finds out about a linked file."""
    link: object
    rel: str
    old: str                  # synced upstream commit and blob (the base)
    old_blob: str
    new_path: str             # upstream path, the new one if renamed there
    strict: bool
    error: Optional[str] = None
    warnings: list = field(default_factory=list)
    src: object = None        # Source of the upstream repository
    new: Optional[str] = None  # upstream commit and blob a pull would sync to
    new_blob: Optional[str] = None
    count_args: tuple = ()    # Source.count(*count_args): upstream commits touching
    behind_args: tuple = ()   # the file since the sync, or by how many the branch
                              # went back - counted only when shown (see count)
    has_old: bool = False     # synced commit exists upstream
    diverged: bool = False
    moved: Optional[tuple] = None   # ('renamed' | 'deleted', path, commit)
    newest: Optional[list] = None   # newer tags of a pinned source
    committed: Optional[str] = None  # see evaluate()
    worktree: str = "clean"
    local: str = "clean"
    head_blob: Optional[str] = None
    changed: bool = False     # upstream version differs from the base
    pending: bool = False     # something for pull to do
    violation: bool = False   # strict file modified
    once: Optional[str] = None  # pull -b/--tag: the branch or tag synced to, once
    target: Optional[str] = None    # ... and its commit


def commits_since(st):
    """Upstream commits touching the file since the sync (see evaluate)."""
    return st.src.count(*st.count_args) if st.count_args else 0


def commits_behind(st):
    """By how many commits touching the file the branch went back."""
    return st.src.count(*st.behind_args) if st.behind_args else 0


def prefetch(ctx, repo, links):
    """Ask git about many links at once - one command per repository and per
    source instead of several per file, which adds up (starting a process
    is slow on Windows). Only fills caches: evaluate() asks for whatever is
    missing, and reports the errors."""
    links = [lk for lk in links if not path_problem(lk.rel)]
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
    # files that differ from their base (adapted, uncommitted changes): can
    # they be compared without git's filters? (see matches_base)
    differ = [lk for lk in links if lk.blob and repo._head.get(lk.rel) not in (None, lk.blob)
              or repo._dirty.get(lk.rel)]
    if differ:
        repo.check_plain(lk.rel for lk in differ)
        ids = {id(lk) for lk in differ}
        items = []
        for src, lks in groups.values():
            try:
                src.check_plain(lk.blob for lk in lks if id(lk) in ids)
                # those not comparable without git's filters: converted at once
                items += [(src.read_content(lk.blob, lk.path), lk.rel) for lk in lks
                          if id(lk) in ids and not (repo.is_plain(lk.rel)
                                                   and src.is_plain(lk.blob))]
            except FsError:
                pass
        repo.as_local_many(items)


def evaluate(ctx, repo, link):
    """State of a linked file in three independent respects:
    upstream  - synced upstream version vs. current one (changed/behind/
                moved: renamed or deleted upstream)
    committed - committed version vs. synced upstream version
                ('unmodified' | 'adapted' | None if not committed)
    worktree  - working file vs. committed version
                ('clean' | 'modified' | 'deleted' | 'added' | 'missing')
    local     - working file vs. synced upstream version ('clean' | 'modified'
                | 'missing'); what a pull has to merge"""
    st = FileState(link=link, rel=link.rel, old=link.commit, old_blob=link.blob,
                   new_path=link.path, strict=link.strict)
    url, ref, path = link.url, link.ref, link.path
    problem = path_problem(link.rel)
    if problem:
        st.error = (f"{problem} - entry ignored; remove it with "
                    f"'git config -f {REGISTRY} --remove-section \"file.{link.rel}\"'")
        return st
    if link.source.get("tag"):
        st.error = (f'tag in [source "{link.name}"] is no longer supported: pin the files '
                    f"themselves ('tag' in each [file], with 'git filesync edit'), and give "
                    "the source its branch")
        return st
    if not (url and ref and path):
        st.error = (f"incomplete entry in {REGISTRY} (needs a source with url and branch, "
                    "and path)")
        return st
    try:
        src = st.src = ctx.source(url, ref, link.name, link.line)
    except FsError as e:
        st.error = str(e)
        return st

    def base_matches(oid, read):
        try:
            return matches_base(repo, src, link, oid, read)
        except BaseUnavailable as e:
            if str(e) not in st.warnings:
                st.warnings.append(str(e))
            return False
    try:
        exists = link.target.is_file()
        head = st.head_blob = repo.head_blob(link.rel)
        if head:
            st.committed = "unmodified" if base_matches(
                head, lambda: repo.read_blob(head)) else "adapted"
        if not exists:
            st.worktree = "deleted" if head else "missing"
        elif not head:
            st.worktree = "added"
        elif repo.is_modified(link.rel):
            st.worktree = "modified"
        if not exists:
            st.local = "missing"
        elif st.worktree == "clean":
            st.local = "clean" if st.committed == "unmodified" else "modified"
        elif base_matches(repo.worktree_blob(link.target), link.target.read_bytes):
            st.local = "clean"
        else:
            st.local = "modified"
    except FsError as e:
        st.error = str(e)
        return st
    st.violation = st.strict and (st.committed == "adapted" or st.local == "modified")
    where = f"{ref[0]} '{ref[1]}'"
    tip = src.resolve()
    if not tip:
        st.error = ref_missing(ref, src)
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
    if st.has_old and st.new_blob == st.old_blob and path == link.path:
        st.new = st.old           # unchanged upstream: no history to look at
    else:
        st.new = src.last_change(tip, path)    # not the tip: what a pull records
    if st.has_old:
        if st.new == st.old:
            pass
        elif src.is_ancestor(st.new, st.old):
            st.behind_args = (st.new, st.old, path)   # branch older than last sync
        else:
            st.count_args = (st.old, st.new, *dict.fromkeys((link.path, path)))
            st.diverged = not src.is_ancestor(st.old, st.new)
    else:
        st.warnings.append(f"last synced commit {st.old[:12] or '-'} not found in "
                           f"{src.label} (unpushed?)")
    st.changed = st.new_blob != st.old_blob
    # a file deleted in the working tree is an uncommitted change, not a sync
    st.pending = st.changed or bool(st.moved) or st.worktree == "missing"
    if src.local:
        if src.note:
            st.warnings.append(src.note)
        if not src.is_published(st.new):   # other unpushed commits don't matter
            st.warnings.append(f"'{path}' in {src.label} comes from commit "
                               f"{src.short(st.new)}, which is not pushed")
        if ref[0] == "tag":
            return st   # a pinned tag: whatever is checked out doesn't matter
        if src.head_ref() != src.ref:
            if src.blob_at("HEAD", path) != st.new_blob:
                st.warnings.append(f"{src.label} has {src.head_desc()} checked out; "
                                   f"'{path}' there differs from {where}, "
                                   "which is what gets synced")
        elif src.has_uncommitted(path):
            st.warnings.append(f"uncommitted changes to '{path}' in {src.label} "
                               "are not synced (commit them first)")
    return st


def upstream_state(st):
    """(label, note) of a pending upstream change, None if there is none."""
    if st.moved:
        kind, path, commit = st.moved
        if kind == "deleted":
            return "deleted", f"upstream, by {st.src.short(commit)}"
        n = commits_since(st)
        return "renamed", f"{st.link.path} -> {path}" + (f", {plural(n, 'commit')}" if n else "")
    if st.changed:
        behind = commits_behind(st)
        if behind:
            what = "upstream branch" if st.link.ref[0] == "branch" else f"tag {st.link.ref[1]}"
            return "older", f"{what} is {plural(behind, 'commit')} older than last sync"
        if st.has_old and not st.diverged:
            return "pending", plural(commits_since(st), "commit")
        return "changed", "history diverged" if st.has_old else "previous sync point unknown"
    if st.worktree == "missing":
        return "new", "not in the working tree yet"
    return None


def violation_text(st):
    what = (["adapted"] if st.committed == "adapted" else []) + \
        (["uncommitted changes"] if st.worktree != "clean" and st.local == "modified" else [])
    return f"{', '.join(what) or 'local modifications'} NOT ALLOWED (strict)"


def describe(st):
    """[(text, style)] one-line summary, used for hook output."""
    if st.error:
        return [(f"ERROR: {st.error}", "boldred")]
    parts = []
    up = upstream_state(st)
    if up:
        label, note = up
        parts.append((f"{note}" if label == "older" else f"upstream {label} ({note})", "yellow"))
    if st.violation:
        parts.append((violation_text(st), "boldred"))
    return parts or [("up to date", "green")]


def report_error(st):
    """An entry that couldn't be evaluated (status, pull, diff)."""
    error(f"{st.rel}: {st.error}")


def render(parts, stream="out"):
    return ", ".join(paint(t, s, stream) for t, s in parts)


def short_code(st):
    """Three columns like `git status -s`: upstream, committed, working tree."""
    if st.error:
        return "E  "
    up = upstream_state(st)
    x = {"pending": "P", "older": "O", "changed": "D", "new": "N", "renamed": "R",
         "deleted": "X"}[up[0]] if up else " "
    y = "M" if st.committed == "adapted" else " "     # like git's index column
    z = {"modified": "M", "deleted": "D", "added": "?"}.get(st.worktree, " ")
    return x + y + z


def shown_path(repo, path):
    """A path outside the working tree (e.g. in .git) as shown to the user:
    relative to the current directory if possible."""
    try:
        return Path(os.path.relpath(path, repo.base)).as_posix()
    except ValueError:            # Windows: another drive
        return Path(path).as_posix()


def shown(repo, rel):
    """Path relative to the current directory, like git status shows it."""
    return Path(os.path.relpath(repo.top / rel, repo.base)).as_posix()


def path_arg(repo, rel):
    """A path of this repository as argument in a command shown to the user."""
    return cmd_arg(shown(repo, rel))


def print_short(repo, sts):
    for st in sts:
        code = short_code(st)
        if code.strip() or st.violation:
            line = paint(code[0], "yellow") + paint(code[1], "cyan") + paint(code[2], "red")
            if code[0] == "E":
                line = paint(code, "boldred")
            print(f"{line} {shown(repo, st.rel)}" + (paint("  (strict!)", "boldred") if st.violation else ""))


def link_text(st):
    """Where a linked file comes from, for status -v and pull -v."""
    via = f" via {st.src.label}" if st.src and st.src.local else ""
    strict = ", strict" if st.strict else ""
    newest = f", newest {newest_text(st.newest, st.link.line)}" if st.newest else ""
    names = st.src.tag_names if st.src else None
    return (f"from {st.link.name}:{st.link.path} "
            f"({ref_text(st.link.ref, st.link.line, names)}{newest}{strict}){via}")


def print_long(repo, sts, verbose):
    """Sections like `git status`."""
    hints = out(repo.git(["config", "--type=bool", "advice.statusHints"], check=False)) != "false"

    def section(title, hint_lines, rows, style):
        if not rows:
            return
        print(title)
        if hints:
            for h in hint_lines:
                print(f"  ({h})")
        for label, rel, note, nstyle in rows:
            line = paint(f"{label + ':':<12}{shown(repo, rel)}", style)
            print(f"\t{line}" + (f"  {paint('(' + note + ')', nstyle)}" if note else ""))
        print()

    ok = [st for st in sts if not st.error]
    if verbose:
        rows = [(st.committed or "uncommitted", st.rel, link_text(st), "dim") for st in ok]
        section("Linked files:", [], rows, None)

    up_rows = []
    for st in ok:
        up = upstream_state(st)
        if up:
            up_rows.append((up[0], st.rel, up[1], "dim"))
    section("Upstream changes to sync:",
            ['use "git filesync diff --upstream <file>..." to see what pull would bring',
             'use "git filesync pull <file>..." to sync']
            + (['use "git filesync unlink <file>..." to keep files deleted upstream']
               if any(r[0] == "deleted" for r in up_rows) else []),
            up_rows, "yellow")

    strict_note = ("NOT ALLOWED: strict", "boldred")
    adapted = [st for st in ok if st.committed == "adapted"]
    section("Locally adapted files:",
            ['use "git filesync diff --committed <file>..." to see the adaptations']
            + (['use "git filesync restore -SW <file>..." to discard them']
               if any(st.strict for st in adapted) else []),
            [("adapted", st.rel) + (strict_note if st.strict else (None, None)) for st in adapted],
            "cyan")

    labels = {"modified": "modified", "deleted": "deleted", "added": "new file"}
    dirty = [st for st in ok if st.worktree in labels]
    section("Uncommitted changes:",
            ['use "git filesync diff <file>..." to see all local changes',
             'use "git restore <file>..." to discard uncommitted changes'],
            [(labels[st.worktree], st.rel) +
             (strict_note if st.strict and st.local == "modified" else (None, None))
             for st in dirty], "red")

    warnings = [(st.rel, w) for st in ok for w in st.warnings]
    if warnings:
        print("Warnings:")
        for rel, w in warnings:
            print(f"\t{paint('warning:', 'yellow')} {shown(repo, rel)}: {w}")
        print()

    if not up_rows and len(ok) == len(sts):
        n = len(sts)
        files = plural(n, "linked file")
        print("nothing to sync" + ("" if adapted or dirty else
                                   f", {'all ' if n > 1 else ''}{files} unmodified"))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(ctx, repo, args):
    """Like `git status`: exit code 0 unless --exit-code (1 = something to
    sync or a strict violation) or an error (2)."""
    reg = Registry(repo)
    links = select_links(repo, reg, args.paths)
    if not links:
        if not args.short:
            print(f"no linked files ({REGISTRY} not found or empty)")
        return EXIT_OK
    prefetch(ctx, repo, links)
    sts = [evaluate(ctx, repo, link) for link in links]
    attention = [st for st in sts if st.error or st.pending or st.violation]
    rc = EXIT_ERROR if any(st.error for st in sts) else \
        EXIT_PENDING if args.exit_code and attention else EXIT_OK
    for st in sts:
        if st.error:
            report_error(st)
    if args.short:
        print_short(repo, sts)
    else:
        print_long(repo, sts, args.verbose)
    return rc


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


def build_message(st, src, new, new_blob, old_path, path, merged, conflicts, discarded=False):
    link = st.link
    paths = dict.fromkeys((old_path, path))       # old and (if renamed) new path
    # content goes back to the synced upstream version -> restore, not a sync
    verb = "Restore" if new_blob == st.old_blob and discarded else "Sync"
    refname = src.tag_names[0] if src.tag_names else link.ref[1]   # a pattern: the tag
    lines = [f"{MSG_PREFIX}{verb} {st.rel} from {link.name}@{src.short(new)}", "",
             f"Upstream: {link.url} ({refname}:{path})"]
    if path != old_path:
        lines += ["", f"Renamed upstream: {old_path} -> {path}"]
    if new == st.old:
        pass
    elif st.has_old:
        old = st.old
        if src.is_ancestor(new, old) and new != old:
            log = src.log(f"{new}..{old}", *paths)
            if log:
                lines += ["", f"Reverts upstream changes after {src.short(new)}:", log]
        else:
            if not src.is_ancestor(old, new):
                lines += ["", f"Note: {src.short(new)} is not a descendant of the "
                          f"previous sync point {src.short(old)}."]
            log = src.log(f"{old}..{new}", *paths)
            if log:
                lines += ["", f"Upstream changes since {src.short(old)}:", log]
    else:
        lines += ["", "Previous sync point unknown; change list not available."]
    if merged:
        lines += ["", "Merged with local modifications of this repository"
                  + (" (conflicts resolved manually)." if conflicts else ".")]
    if discarded:
        lines += ["", "Local modifications of this repository were discarded."]
    return "\n".join(lines) + "\n"


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


def check_target_args(args, links):
    """--commit / -b / --tag (pull, diff --upstream): the upstream version to sync to."""
    if args.commit and (args.branch or args.tag):
        raise FsError("--commit cannot be combined with -b or --tag")
    if args.branch and args.tag:
        raise FsError("-b and --tag cannot be combined")
    if args.commit and len(links) != 1:
        raise FsError("--commit requires exactly one file")


def target_rev(ctx, link, args):
    """-b / --tag (pull, diff --upstream): the upstream commit to sync to
    once - the head of that branch, or the tag. The link keeps its own."""
    ref = ("tag", args.tag) if args.tag else ("branch", args.branch)
    # a tag pattern: the newest matching tag on the source's branch
    line = link.source.get("branch") if args.tag and is_tag_pattern(args.tag) else None
    src = ctx.source(link.url, ref, link.name, line)
    rev = src.resolve()
    if not rev:
        raise FsError(ref_missing(ref, src))
    return rev


def once_text(args):
    """The branch or tag of pull -b/--tag."""
    return f"tag {args.tag}" if args.tag else f"branch {args.branch}"


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
    if args.commit or st.once:
        new, new_blob, path = commit_target(st, args.commit or st.target)
    elif st.moved and st.moved[0] == "deleted":
        rel = path_arg(repo, st.rel)
        raise FsError(f"{st.rel}: '{st.moved[1]}' was deleted in {src.label} "
                      f"({src.short(st.moved[2])}) - keep the file with "
                      f"'git filesync unlink {rel}', or delete it too with "
                      f"'git filesync rm {rel}'")
    local_mod = st.local == "modified"
    discard = args.overwrite and local_mod
    if st.strict and local_mod and not discard:
        rel = path_arg(repo, st.rel)
        raise FsError(f"{st.rel}: {violation_text(st)} - inspect with "
                      f"'git filesync diff {rel}'; discard them with "
                      f"'git filesync restore -SW {rel}', or sync anyway with "
                      f"'git filesync pull --overwrite {rel}'; or allow them with "
                      f"'git filesync set --no-strict {rel}'")
    if new_blob == st.old_blob and path == link.path and st.worktree != "missing" \
            and not discard:
        print(f"{st.rel}: {paint('up to date', 'green')}"
              + (" (adaptations kept)" if st.committed == "adapted" else ""))
        return None
    # like `git pull`: uncommitted changes are never merged into a sync
    if st.worktree in ("modified", "deleted", "added"):
        raise FsError(f"your local changes to '{st.rel}' would be overwritten by pull - "
                      "commit or stash them first ('git stash'; "
                      f"'git restore {path_arg(repo, st.rel)}' discards them)")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")

    # all versions in this repo's normalized form, so that differing eol
    # conventions (and LFS) upstream and here don't matter
    theirs = repo.normalize(src.read_content(new_blob, path), st.rel)
    merged, conflicts = False, 0
    if local_mod and not discard:
        try:
            base = repo.normalize(src.read_content(st.old_blob, link.path), st.rel)
        except FsError:
            raise FsError(f"{st.rel}: base version {st.old_blob[:12]} unavailable; "
                          "cannot merge local modifications")
        ours = repo.read_content(st.head_blob, st.rel)   # no uncommitted changes here
        old_label = src.short(st.old) if st.has_old else st.old_blob[:8]
        conflicts, content = merge3(ours, base, theirs,
                                    [f"{st.rel} (local)", f"upstream {old_label}",
                                     f"upstream {src.short(new)}"])
        merged = True
    else:
        content = theirs

    if args.dry_run:
        notes = ([f"{st.once} once"] if st.once else []) + \
            ([f"renamed upstream: {link.path} -> {path}"] if path != link.path else []) + \
            (["discarding adaptations"] if discard else []) + \
            ([paint(f"{conflicts} merge conflict(s)", "boldred") if conflicts else
              "adaptations merged cleanly"] if merged else [])
        verb = "restore" if new_blob == st.old_blob and discard else "sync"
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
    if conflicts:
        print(f"{st.rel}: {paint(f'{conflicts} merge conflict(s)', 'boldred')}")
    else:
        print(f"{st.rel}: {paint('synced', 'green')}"
              + (" (adaptations merged)" if merged else ""))
    # the file itself is written (and staged) with the others: write_synced
    return build_message(st, src, new, new_blob, old_path, path, merged, conflicts,
                         discard), conflicts, content


def pull_message(parts, names):
    """The commit message of a pull: a file's own message, or for several
    files a subject over all and each file's message as a section of it."""
    if len(parts) == 1:
        return parts[0]
    sources = sorted(set(names))
    what = f"from {sources[0]}" if len(sources) == 1 else f"from {len(sources)} sources"
    return f"{MSG_PREFIX}Sync {len(parts)} files {what}\n\n" + \
        "\n".join(m[len(MSG_PREFIX):] if m.startswith(MSG_PREFIX) else m for m in parts)


def newest_hint(rels, tag, line, newest):
    """Hint after pull at newer tags for the files pinned to tag."""
    files = rels[0] if len(rels) == 1 else plural(len(rels), "file")
    return (f"hint: {files} pinned to tag {tag}; the newest tag on branch {line} is "
            f"{newest_text(newest, line)} (use 'git filesync set --tag "
            f"{newest[0][0][0]} <file>...' and pull to switch)")


def write_synced(repo, contents, conflicted):
    """Write the synced files ({rel: content in this repository's stored
    form}) to the working tree and stage them - those with merge conflicts
    only written (see Repo.write_files)."""
    repo.write_files([(r, c) for r, c in contents.items() if r not in conflicted])
    repo.write_files([(r, c) for r, c in contents.items() if r in conflicted], stage=False)


def report_pull(repo, reg, synced):
    """The files a pull synced are staged with their entries (those with
    merge conflicts once resolved), like `git merge --squash`; one proposed
    commit message for all of them, which a plain `git commit` offers."""
    reg.finish()
    rels = [rel for rel, _, _, _ in synced]
    msg = pull_message([m for _, _, m, _ in synced], [name for _, name, _, _ in synced])
    name = rels[0] if len(rels) == 1 else plural(len(rels), "file")
    conflicted = [rel for rel, _, _, c in synced if c]
    if conflicted:
        add = " ".join(path_arg(repo, r) for r in conflicted)
        print(f"{paint('merge conflicts', 'boldred')} - resolve them, then run:\n"
              f"    git add {add}\n    git commit\n{commit_hint(repo, msg)}")
        return EXIT_PENDING
    report_staged(repo, name, msg, paint("synced and staged", "green"))
    return EXIT_OK


def cmd_pull(ctx, repo, args):
    reg = Registry(repo)
    reg.dry_run = args.dry_run
    if args.all:
        links = reg.links()
    elif args.files:
        links = select_links(repo, reg, args.files)
    else:
        raise FsError("specify file(s) or --all")
    check_target_args(args, links)
    rc, done, moved = EXIT_OK, 0, False
    once = args.branch or args.tag      # sync to another branch or tag, once
    prefetch(ctx, repo, links)
    newest, synced = {}, []             # synced: (rel, source, message, conflicts)
    contents = {}                       # rel -> synced content (normalized form)
    selected = [lk.rel for lk in links]
    states = [evaluate(ctx, repo, link) for link in links]
    # what syncing needs, asked at once: upstream contents, short commit ids,
    # attributes of the files here
    repo.check_plain(selected)
    items = []
    ok = [st for st in states if st.src and not st.error]
    for src in {id(st.src): st.src for st in ok}.values():
        src.read_blobs(b for st in ok if st.src is src for b in (st.old_blob, st.new_blob))
        src.shorts(c for st in ok if st.src is src for c in (st.old, st.new))
    for st in ok:
        try:
            if st.new_blob and st.new_blob != st.old_blob:
                items.append((st.src.read_content(st.new_blob, st.new_path), st.rel))
        except FsError:
            pass
    repo.normalize_many(items)
    for link, st in zip(links, states):
        if st.error:
            report_error(st)
            rc = EXIT_ERROR
            continue
        if st.newest and not once:
            newest.setdefault((link.name, link.tag), (link.tag, link.line, st.newest, []))[3] \
                .append(link.rel)
        if args.all and not st.pending and not once:
            continue
        done += 1
        if args.verbose:
            at = st.src.short(st.old) if st.has_old else link.blob[:8]
            print(paint(f"{st.rel}: {link_text(st)}, synced at {at}", "dim"))
        try:
            if once:
                st.target, st.once = target_rev(ctx, link, args), once_text(args)
            before = link.commit
            result = pull_one(repo, reg, st, args)
            if result:
                synced.append((st.rel, link.name) + result[:2])
                contents[st.rel] = result[2]
            moved = moved or once and Link(reg, link.rel).commit != before
        except FsError as e:   # report and carry on with the other files
            error(str(e) if str(e).startswith(st.rel) else f"{st.rel}: {e}")
            rc = EXIT_ERROR
    if synced:
        write_synced(repo, contents, {rel for rel, _, _, c in synced if c})
        rc = max(rc, report_pull(repo, reg, synced))
    if moved and not args.dry_run:
        opt = f"--tag {args.tag}" if args.tag else f"-b {args.branch}"
        how = f"'git filesync set <file>... {opt}'"
        print(f"hint: the links still follow their own branch or tag, so a plain pull goes "
              f"back; to stay on {once_text(args)}, use {how}")
    if args.all and not done and rc == EXIT_OK:
        print(paint("everything up to date", "green"))
    for _, (tag, line, new, rels) in sorted(newest.items()):
        print(newest_hint(rels, tag, line, new))
    return rc


def diff_pairs(ctx, repo, args):
    """(st, name, base, other) blob ids for every linked file with a difference.
    base = last synced upstream version; other = local file (None if missing),
    or with --upstream the upstream version pull would sync to (with the same
    --commit / -b / --tag). All as actual content in this repo's normalized
    form (LFS resolved), so eol conventions and LFS pointers don't show up."""
    if (args.commit or args.branch or args.tag) and not args.upstream:
        raise FsError("--commit, -b and --tag require --upstream")
    rc = EXIT_OK
    pairs = []
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    check_target_args(args, links)
    prefetch(ctx, repo, links)
    repo.check_plain(lk.rel for lk in links)
    states = [evaluate(ctx, repo, link) for link in links]
    if args.upstream and not (args.commit or args.branch or args.tag):
        items = []
        for st in states:
            if st.src and not st.error and st.new_blob and st.new_blob != st.old_blob:
                try:
                    items.append((st.src.read_content(st.new_blob, st.new_path), st.rel))
                except FsError:
                    pass
        repo.normalize_many(items)
    worktree_ids = {}
    if not (args.upstream or args.committed):     # the working tree files, read at once
        worktree_ids = repo.worktree_blobs(
            st.rel for st in states if not st.error and st.local not in ("clean", "missing")
            and not repo.plain_content(st.rel, st.link.target.read_bytes()))
        repo.read_blobs(worktree_ids.values())
    for link, st in zip(links, states):
        if st.error:
            report_error(st)
            rc = EXIT_ERROR
            continue
        if args.upstream:
            if args.commit or args.branch or args.tag:
                try:
                    rev = args.commit or target_rev(ctx, link, args)
                    st.new, st.new_blob, st.new_path = commit_target(st, rev)
                except FsError as e:
                    error(f"{st.rel}: {e}")
                    rc = EXIT_ERROR
                    continue
            if not st.new_blob or st.new_blob == st.old_blob:   # unchanged or deleted
                continue
        elif args.committed:
            if st.committed != "adapted":
                continue
        elif st.local == "clean":
            continue
        # both sides as actual content in this repo's form (LFS resolved),
        # stored all at once below
        try:
            try:
                base = repo.normalize(st.src.read_content(st.old_blob, link.path), st.rel)
            except FsError:
                raise FsError(f"synced version {st.old_blob[:12]} unavailable")
            if args.upstream:
                other = repo.normalize(st.src.read_content(st.new_blob, st.new_path), st.rel)
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
        name = link.path if args.for_upstream else st.rel
        pairs.append((st, name, base, other))
    contents = [c for _, _, base, other in pairs for c in (base, other) if c is not None]
    ids = dict(zip(map(id, contents), repo.store_many(contents)))
    return rc, [(st, name, ids[id(base)], ids[id(other)] if other is not None else None)
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
    left = make_tree(repo, [(n, b) for _, n, b, _ in pairs])
    right = make_tree(repo, [(n, o) for _, n, _, o in pairs if o])
    if args.for_upstream:
        prefixes = []                  # standard a/ b/: `git apply` upstream
    else:
        prefixes = ["--src-prefix=synced/", "--dst-prefix=" + (
            "upstream/" if args.upstream else "committed/" if args.committed else "local/")]
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
    if not (args.upstream or args.committed):
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
                f.write_bytes(repo.to_worktree(repo.read_blob(oid), st.rel))
                return str(f)
            left = tmpfile(f"synced-{src.short(st.old) if st.has_old else st.old_blob[:8]}", base)
            if args.upstream:
                right = tmpfile(f"upstream-{src.short(st.new)}", other)
            elif args.committed:
                right = tmpfile("committed-HEAD", other)
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


def add_ref(ctx, reg, args):
    """(url, branch, name) of the source for add: the [source] named by
    args.source (-b may only repeat its branch), or for a URL the one with
    that URL and branch - name None, found or created later."""
    if args.source in reg.sources:            # name of an existing [source]
        s = reg.sources[args.source]
        if not s.get("branch"):
            raise FsError(f'[source "{args.source}"] in {REGISTRY} needs a branch')
        if args.branch and args.branch != s["branch"]:
            raise FsError(f"source '{args.source}' follows {s['branch']}, not {args.branch} - "
                          "give the URL to link to another branch, or change the source's "
                          f"branch with 'git filesync source set-branch {args.source} "
                          f"{args.branch}'")
        return s.get("url", ""), s["branch"], args.source
    return args.source, args.branch or ctx.default_branch(args.source), None


def find_base(repo, src, rev, rel, path, target, overwrite=False):
    """Base of a file to link: upstream path's version at rev (the branch
    head, or --commit). Returns (commit, blob, content to write or None,
    modified, replaced): a missing file gets that version, an existing one
    keeps its content - its differences count as adaptations - unless
    overwrite."""
    blob = src.blob_at(rev, path)
    if not blob:
        raise FsError(f"no file '{path}' in {src.label} at {src.short(rev)}")
    commit = src.last_change(rev, path)
    cur = repo.worktree_blob(target)
    if cur is None or overwrite:
        return commit, blob, src.read_content(blob, path), False, cur is not None
    try:
        modified = not matches_base(repo, src, SimpleNamespace(blob=blob, path=path, rel=rel),
                                    cur, target.read_bytes)
    except BaseUnavailable:
        modified = False
    return commit, blob, None, modified, False


# a file to link: its path here, upstream path, base commit and blob, content to
# write (None: the existing file is kept), whether it differs from the base,
# whether an existing file is replaced (--overwrite)
Planned = namedtuple("Planned", "rel path commit blob content modified replaced")


def build_add_message(plan, src, name, url, ref, mpath, relink, strict, at):
    """Commit message for add; plan: [Planned]; at: the upstream revision a
    directory was linked at."""
    fetched = all(p.content is not None and not p.replaced for p in plan)
    subject_ref = f"{name}@{src.short(plan[0].commit)}"
    if len(plan) == 1:
        rel, path = plan[0].rel, plan[0].path
        what = f"Add {rel} from" if fetched else f"{'Relink' if relink else 'Link'} {rel} to"
    else:
        path = mpath.rstrip("/") + "/" if mpath else "/"
        what = f"Add {len(plan)} files from" if fetched else f"Link {len(plan)} files to"
        subject_ref = f"{name}@{src.short(at)}"
    refname = src.tag_names[0] if src.tag_names else ref[1]     # a pattern: the tag
    lines = [f"{MSG_PREFIX}{what} {subject_ref}", "", f"Upstream: {url} ({refname}:{path})"]
    if len(plan) > 1:
        lines.append("")
        for p in plan:
            notes = (["replaced"] if p.replaced else [] if p.content is not None else
                     ["existing"]) + (["local modifications"] if p.modified else [])
            lines.append(f"- {p.rel}" + (f" ({', '.join(notes)})" if notes else ""))
    if len(plan) == 1 and plan[0].modified:
        lines += ["", "Contains local modifications of this repository."]
    if len(plan) == 1 and plan[0].replaced:
        lines += ["", "The existing file was replaced by the upstream version."]
    if strict:
        lines += ["", "Strict: must stay an exact copy of the upstream version."]
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
    head = src.resolve()
    if not head:
        raise FsError(ref_missing(ref, src))
    at = src.require(args.commit) if args.commit else None    # --commit: given base
    if args.tag and not src.tag_names:
        _, problem = src.tag_info(args.tag, branch, newer=False)
        if problem:
            warn(f"{problem}; newer tags can't be found there")
    path = upstream_path(args.path if args.path else rel)
    patterns = args.include or args.exclude
    upstream_file = bool(path) and not patterns and bool(src.blob_at(at or head, path))
    if target.is_dir() and upstream_file:       # like cp: into the directory
        target = target / Path(path).name
        rel = repo.rel(target)
    if target.is_dir() or patterns or not upstream_file and src.is_dir(at or head, path):
        # like cp -r: DIR may be new, the directory it goes into must exist
        require_dir(repo, target if target.is_dir() else target.parent)
        plan, relink = plan_dir(repo, reg, src, args, at or head, rel, path, target)
        if not plan:
            return EXIT_OK
    else:
        relink = rel in reg.files
        if relink and not args.force:
            raise FsError(f"'{rel}' is already linked (use --force to relink)")
        if target.is_dir():
            raise FsError(f"cannot link '{rel}': is a directory")
        require_dir(repo, target.parent)        # like cp
        plan = [Planned(rel, path, *find_base(repo, src, at or head, rel, path, target,
                                              args.overwrite))]
    modified = [p for p in plan if p.modified]
    if modified:
        what = modified[0].rel if len(plan) == 1 else \
            plural(len(modified), "existing file") + (f" below {rel}" if rel != "." else "")
        warn(f"{what} differ{'s' if len(modified) == 1 else ''} from upstream "
             f"{src.short(at or head)}; the differences count as local adaptations (use "
             "--overwrite to take the upstream version, or --commit to choose another one)")
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
    save_discarded(repo, [p.rel for p in plan if p.replaced])
    fetched = []          # (rel, content in this repository's form) to write
    for p in plan:
        if p.rel in reg.files:
            reg.remove_file(p.rel, keep_source=named)
        name = named or reg.add_source(url, branch)
        link = Link(reg, p.rel)
        for k, v in (("source", name), ("path", p.path), ("commit", p.commit), ("blob", p.blob)):
            link.set(k, v)
        if args.tag:
            link.set("tag", args.tag)
        if args.strict:
            link.set("strict", "true")
        if p.content is not None:
            fetched.append((p.rel, repo.normalize(p.content, p.rel)))
        print(f"{paint('linked', 'green')} {p.rel} -> {name}:{p.path} ({shown_ref})")
    # fetched files written and staged at once; existing ones staged as
    # they are in the working tree
    repo.write_files(fetched)
    done = {r for r, _ in fetched}
    if any(r not in done for r in rels):
        repo.git(["add", "--"] + [lit(r) for r in rels if r not in done])
    reg.finish()
    if repo.git(["diff", "--cached", "--quiet", "HEAD", "--"] + [lit(r) for r in rels]
                 + [REGISTRY], check=False).returncode == 0:
        print(f"{rel}: link{'s' if len(rels) > 1 else ''} and "
              f"file{'s' if len(rels) > 1 else ''} unchanged, nothing to commit")
        return EXIT_OK
    # staged only, like git add; the proposed message is prepared for the commit
    msg = build_add_message(plan, src, name, url, ref, path, relink, args.strict, at or head)
    msg_name = rels[0] if len(rels) == 1 else (rel if rel != "." else "root")
    report_staged(repo, msg_name, msg, paint("staged", "green"))
    return EXIT_OK


def require_dir(repo, path):
    """add and mv put a file into an existing directory only, like cp and
    git mv: a mistyped directory isn't created."""
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


def save_discarded(repo, rels, keep_index=False):
    """Before restore, add --overwrite or rm -f overwrite or delete these
    working tree files: the content of those with uncommitted changes - in
    neither HEAD nor, if it stays, the index - is kept as a blob exactly as
    it is, and the command tells how to get it back (`git show ID > FILE`).
    Like with `git restore`, the files are discarded anyway."""
    rels = [r for r in rels if (repo.top / r).is_file()]
    if not rels:
        return
    repo.prefetch(rels)
    index = repo.index_entries(rels) if keep_index else {}
    current = repo.worktree_blobs(rels)
    lost = [r for r in rels if current.get(r) not in
            (repo.head_blob(r), index.get(r, (None, None))[1])]
    for rel, oid in zip(lost, repo.store_many([(repo.top / r).read_bytes() for r in lost])):
        print(f"{paint('discarded:', 'yellow')} {rel} (git show {oid[:12]} to get it back)")


def cmd_restore(ctx, repo, args):
    """Like `git restore`, with the synced upstream version (the base the
    entry records) as the source: the working tree files (default), with -S
    their index entries instead, with -S -W both. .git-filesync stays as it is.
    The files are written all at once (see Repo.put_blobs); plain content
    of files without content-changing attributes is compared without git."""
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    worktree = args.worktree or not args.staged
    done = "restored and staged" if worktree and args.staged else \
        "restored in the index" if args.staged else "restored"
    rc = EXIT_OK
    srcs, bases = {}, {}           # rel -> Source, base content in this repo's form
    repo.check_plain(lk.rel for lk in links)
    for link in links:
        try:
            srcs[link.rel] = ctx.source(link.url, link.ref, link.name, link.line)
        except FsError as e:
            error(str(e))
            rc = EXIT_ERROR
    for src in {id(s): s for s in srcs.values()}.values():
        src.read_blobs(lk.blob for lk in links if srcs.get(lk.rel) is src)
        src.shorts(lk.commit for lk in links if srcs.get(lk.rel) is src)
    for link in links:
        if link.rel not in srcs:
            continue
        try:
            content = srcs[link.rel].read_content(link.blob, link.path)
            if repo.plain_content(link.rel, content):
                bases[link.rel] = content
        except FsError:
            pass          # the file goes the long way, which reports it
    items = []
    for lk in links:
        if lk.rel in srcs and lk.rel not in bases:
            try:
                items.append((srcs[lk.rel].read_content(lk.blob, lk.path), lk.rel))
            except FsError:
                pass
    repo.as_local_many(items)
    plain = [lk for lk in links if lk.rel in bases]
    oids = dict(zip([lk.rel for lk in plain], repo.store_many([bases[lk.rel] for lk in plain])))
    index = repo.index_entries([lk.rel for lk in links]) if args.staged else {}
    fixes, said = [], []           # (link, base, fix tree, fix index); said: what to print
    for link in links:
        if link.rel not in srcs:
            continue
        src = srcs[link.rel]
        try:
            if link.rel in bases:
                base = oids[link.rel]
                data = link.target.read_bytes() if link.target.is_file() else None
                # differs if not the same without CR (eol conversion aside)
                cur = None if data is None else base if data == bases[link.rel] else \
                    "" if repo.plain_content(link.rel, data) else repo.worktree_blob(link.target)
            else:
                base = local_equiv(repo, src, link.blob, link.rel, link.path)
                if not base:
                    raise FsError(f"{link.rel}: base version {link.blob[:12]} unavailable")
                cur = repo.worktree_blob(link.target)
            fix_tree = worktree and cur != base
            fix_index = args.staged and index.get(link.rel, (None, None))[1] != base
            if not (fix_tree or fix_index):
                said.append(f"{link.rel}: nothing to restore")
                continue
            fixes.append((link, base, fix_tree, fix_index))     # written below, all at once
            at = src.short(link.commit) if link.commit else link.blob[:8]
            said.append(f"{link.rel}: {paint(done, 'green')} ({link.name}@{at})")
        except FsError as e:   # report and carry on with the other files
            error(str(e))
            rc = EXIT_ERROR
    save_discarded(repo, [lk.rel for lk, _, fix_tree, _ in fixes if fix_tree],
                   keep_index=not args.staged)
    for tree, index in ((True, True), (True, False), (False, True)):
        repo.put_blobs([(lk.rel, base) for lk, base, fix_tree, fix_index in fixes
                        if (fix_tree, fix_index) == (tree, index)], stage=index, worktree=tree)
    for line in said:
        print(line)
    return rc


def cmd_unlink(ctx, repo, args):
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    for link in links:
        if args.dry_run:
            print(f"would unlink {link.rel}")
            continue
        reg.remove_file(link.rel)
        print(f"{paint('unlinked', 'green')} {link.rel} (file kept)")
    if not args.dry_run:
        reg.finish()
    return EXIT_OK


def cmd_rm(ctx, repo, args):
    """Like `git rm`: remove the links and the files, both staged. Refused
    (for all) if a file has uncommitted changes, unless -f; a committed
    adaptation is no reason to refuse. A file that is gone already is fine."""
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    repo.prefetch([lk.rel for lk in links])
    if not args.force:
        dirty = [lk.rel for lk in links if lk.target.exists() and
                 (repo.head_blob(lk.rel) is None or repo.is_modified(lk.rel))]
        if dirty:
            raise FsError("".join(f"{r}: has uncommitted changes\n" for r in dirty[:-1])
                          + f"{dirty[-1]}: has uncommitted changes - use -f to remove "
                          f"{'it' if len(dirty) == 1 else 'them'} anyway")
    if args.dry_run:
        for link in links:
            print(f"would remove {link.rel}")
        return EXIT_OK
    save_discarded(repo, [lk.rel for lk in links])
    for part in chunks(lk.rel for lk in links):
        repo.git(["rm", "-q", "-f", "--ignore-unmatch", "--"] + [lit(r) for r in part])
    for link in links:
        if link.target.is_file():       # never added to git
            link.target.unlink()
        reg.remove_file(link.rel)
        print(f"{paint('removed', 'green')} {link.rel}")
    reg.finish()
    return EXIT_OK


def cmd_mv(ctx, repo, args):
    reg = Registry(repo)
    old = repo.rel(repo.user_path(args.src))
    if old not in reg.files:
        raise FsError(f"'{old}' is not linked")
    dst = repo.user_path(args.dst)
    if dst.is_dir():
        dst = dst / Path(old).name
    new = repo.rel(dst)
    problem = path_problem(new)
    if problem:
        raise FsError(f"cannot move to '{new}': {problem}")
    if new in reg.files or dst.exists():
        raise FsError(f"'{new}' already exists")
    require_dir(repo, dst.parent)                # like git mv
    if args.dry_run:
        print(f"would move {old} -> {new}")
        return EXIT_OK
    if repo.git(["ls-files", "--error-unmatch", "--", lit(old)], check=False).returncode == 0:
        repo.git(["mv", "--", old, new])
    elif (repo.top / old).exists():
        (repo.top / old).rename(dst)
    reg.rename_file(old, new)
    reg.finish()
    print(f"{paint('moved', 'green')} {old} -> {new} (link kept)")
    return EXIT_OK


def commit_in(src, link):
    """The commit of a link's synced version in another upstream (a fork, a
    moved repository): the recorded one if it is there, else the newest
    commit on the branch that has the synced blob at the path; None if the
    version isn't there."""
    if link.commit and src.resolve(link.commit) == link.commit:
        return link.commit
    for rev, oid in src.path_history(link.path, 5000):
        if oid == link.blob:
            return rev
    return None


def keep_base(src, link):
    """A link moves to another upstream (src): its synced version stays the
    base, with the commit it has there (see commit_in) - or, if src doesn't
    have it, a warning: the previous sync point counts as unknown."""
    commit = commit_in(src, link)
    if not commit:
        warn(f"{link.rel}: synced version {link.blob[:12]} not found in "
             f"{src.label}; its previous sync point counts as unknown")
    elif commit != link.commit:
        link.set("commit", commit)


def cmd_set(ctx, repo, args):
    """Change the link of linked files - their source (URL and branch), tag,
    upstream path or strict flag. A file uses the [source] with its URL and
    branch: found, created, or - when all files of a source move - that
    source changed; one left without files is removed. Only .git-filesync
    is changed (and staged); the synced version (the base) is kept where it
    still applies: for another branch or tag of the same upstream, and for
    another upstream that has it (a fork, a moved repository); with another
    path it is looked up like for add."""
    if not (args.source or args.branch or args.tag or args.no_tag or args.path
            or args.strict is not None):
        raise FsError("nothing to change: give --source, -b, --tag/--no-tag, -p or "
                      "--strict/--no-strict")
    reg = Registry(repo)
    reg.dry_run = args.dry_run
    links = select_links(repo, reg, args.files)
    if args.path and len(links) != 1:
        raise FsError("-p requires exactly one file")
    for lk in links:
        if not lk.source.get("branch") or lk.source.get("tag"):
            raise FsError(f"{lk.rel}: its [source \"{lk.name}\"] in {REGISTRY} needs a url "
                          "and a branch (and no tag)")
    would = "would: " if args.dry_run else ""
    changed = False
    if args.source or args.branch:
        # the source the files are to use: URL and branch (like add)
        if args.source in reg.sources:
            url, branch = reg.sources[args.source].get("url", ""), \
                reg.sources[args.source].get("branch")
            if not branch:
                raise FsError(f'[source "{args.source}"] in {REGISTRY} needs a branch')
            if args.branch and args.branch != branch:
                raise FsError(f"source '{args.source}' follows {branch}, not {args.branch} - "
                              "give the URL with -b, or -b alone for the files' upstream")
        elif args.source:
            url, branch = args.source, args.branch or ctx.default_branch(args.source)
        groups = {}
        for lk in links:
            target = (url, branch) if args.source else (lk.url, args.branch)
            if (norm_url(lk.url), lk.source.get("branch")) != (norm_url(target[0]), target[1]):
                groups.setdefault((lk.name,) + target, []).append(lk)
        for (old, url_, branch_), lks in groups.items():
            name = reg.find_source(url_, branch_)
            src = ctx.source(url_, ("branch", branch_), name or old)
            if not src.resolve():
                raise FsError(ref_missing(("branch", branch_), src))
            if not name and set(source_files(reg, old)) <= {lk.rel for lk in lks}:
                # all files of the source move to a new place: the source itself
                # changes, keeping its name (like source set-url / set-branch)
                for key, value in (("url", url_), ("branch", branch_)):
                    if reg.sources[old].get(key) != value:
                        print(f"{would}source {old}: {key} {reg.sources[old].get(key)} -> {value}")
                        reg.set_source(old, key, value)
                name = old
            name = name or reg.add_source(url_, branch_)
            for lk in lks:
                if norm_url(url_) != norm_url(lk.url) and not args.path:
                    keep_base(src, lk)
                if lk.name != name:
                    lk.set("source", name)
                    print(f"{would}{lk.rel}: source {old} -> {name}")
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
                if not src.resolve():
                    raise FsError(ref_missing(ref, src))
                if not src.tag_names:
                    _, problem = src.tag_info(args.tag, lk.source.get("branch"), newer=False)
                    if problem:
                        warn(f"{problem}; newer tags can't be found there")
            lk.set("tag", args.tag or None)
            print(f"{would}{lk.rel}: " + (f"tag {args.tag}" if args.tag else
                                          f"follows branch {lk.source.get('branch')}"))
            changed = True
    if args.path:
        lk = links[0]
        src = ctx.source(lk.url, lk.ref, lk.name, lk.line)
        head = src.resolve()
        if not head:
            raise FsError(ref_missing(lk.ref, src))
        path = upstream_path(args.path)
        commit, blob, _, modified, _ = find_base(repo, src, head, lk.rel, path, lk.target)
        if (path, commit, blob) != (lk.path, lk.commit, lk.blob):
            print(f"{would}{lk.rel}: path {lk.path} -> {path}, based on {src.short(commit)}"
                  + (", with local modifications" if modified else ""))
            for k, v in (("path", path), ("commit", commit), ("blob", blob)):
                lk.set(k, v)
            changed = True
    if args.strict is not None:
        for lk in links:
            if lk.strict != args.strict:
                lk.set("strict", "true" if args.strict else None)
                print(f"{would}{lk.rel}: {'strict' if args.strict else 'not strict'}")
                changed = True
    if not changed:
        print("nothing to change")
    elif not args.dry_run:
        reg.finish()
        print(f'{REGISTRY} staged (use "git filesync status" to see what changes, '
              '"git filesync pull <file>..." to sync)')
    return EXIT_OK


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
        if not (v.get("commit") and v.get("blob")):
            problems.append(f"{what} lacks commit or blob (the synced version)")
    return problems


def cmd_edit(ctx, repo, args):
    """Open .git-filesync in the editor (like `git config --edit`), then
    check and stage it."""
    path = registry_path(repo)
    if not path.exists():
        raise FsError(f"no {REGISTRY} yet - link files with 'git filesync add'")
    before = path.read_bytes()
    # the editor git would use (GIT_EDITOR, core.editor, VISUAL, EDITOR), run
    # like git runs it - not via `git config --edit`, which exits with 0 even
    # if the editor fails
    editor = out(repo.git(["var", "GIT_EDITOR"]))
    if subprocess.run([shell(), "-c", f'{editor} "$@"', editor, REGISTRY],
                      cwd=repo.top).returncode:
        raise FsError("the editor failed; nothing staged")
    if path.exists() and path.read_bytes() == before:
        print(f"{REGISTRY}: no changes")
        return EXIT_OK
    try:
        reg = Registry(repo)
    except FsError as e:
        raise FsError(f"{e} - not staged; fix it with 'git filesync edit'")
    for problem in registry_problems(reg):
        warn(f"{REGISTRY}: {problem}")
    reg.finish()
    print(f'{REGISTRY} staged (use "git filesync status" to see what changes, '
          '"git filesync pull <file>..." to sync)')
    return EXIT_OK


def source_files(reg, name):
    return sorted(rel for rel, f in reg.files.items() if f.get("source") == name)


def cmd_source(ctx, repo, args):
    """Like `git remote`: list, rename and change the [source]s - which
    add and set create as needed, and remove when no file uses them. Only
    .git-filesync is changed (and staged); `pull` then syncs the files."""
    reg = Registry(repo)
    action = args.action
    if not action:
        for name, s in sorted(reg.sources.items()):
            if not args.verbose:
                print(name)
                continue
            n = len(source_files(reg, name))
            print(f"{name}\t{s.get('url', '')} ({s.get('branch') or 'branch missing'}, "
                  f"{plural(n, 'file')})")
        return EXIT_OK
    if args.name not in reg.sources:
        raise FsError(f"no source '{args.name}' in {REGISTRY}"
                      + (f" (known: {', '.join(sorted(reg.sources))})" if reg.sources else ""))
    s = reg.sources[args.name]
    if action == "rename":
        if args.value in reg.sources:
            raise FsError(f"source '{args.value}' already exists")
        if not args.value or "\n" in args.value:
            raise FsError("invalid source name")
        reg.rename_source(args.name, args.value)
        done = f"renamed {args.name} -> {args.value}"
    else:
        url, branch = s.get("url", ""), s.get("branch")
        key = "url" if action == "set-url" else "branch"
        if key == "url":
            url = args.value
        else:
            branch = args.value
        other = reg.find_source(url, branch, exclude=args.name)
        if other:
            raise FsError(f"source '{other}' already has this URL and branch {branch} - "
                          f"move the files to it with 'git filesync set FILE... --source {other}'")
        if url and branch:        # as for set: the branch must exist upstream
            src = ctx.source(url, ("branch", branch), args.name)
            if not src.resolve():
                raise FsError(ref_missing(("branch", branch), src))
            if key == "url" and norm_url(url) != norm_url(s.get("url", "")):
                for rel in source_files(reg, args.name):
                    keep_base(src, Link(reg, rel))
        old = s.get(key)
        reg.set_source(args.name, key, args.value)
        done = f"{args.name}: {key} {args.value}" + (f" (was {old})" if old and old != args.value
                                                     else "")
    reg.finish()
    print(f"{paint(done, 'green')}; {REGISTRY} staged")
    files = source_files(reg, args.value if action == "rename" else args.name)
    if action != "rename" and files:
        print(f'  (use "git filesync status" to see what changes for its '
              f'{plural(len(files), "linked file")}, "git filesync pull <file>..." to sync them)')
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
    """'scheme://...' or scp-like 'host:path' (also 'C:/...') - never taken
    as the name of a [source]."""
    return "://" in s or bool(re.match(r"[^/]+:", s))


def map_url(repo, arg, setting):
    """The URL map works on: arg, or the url of the [source] named arg in this
    repository's .git-filesync (a URL-like arg is always a URL). When
    setting a mapping, an arg that is neither (nor an existing path, which
    git takes as a URL too) is refused - most likely a mistyped name."""
    if not arg or looks_like_url(arg):
        return arg
    if repo:
        source = Registry(repo).sources.get(arg)
        if source is not None:
            if not source.get("url"):
                raise FsError(f"[source \"{arg}\"] in {REGISTRY} has no url")
            return source["url"]
    if setting and not (repo.base if repo else Path.cwd()).joinpath(arg).exists():
        where = f"a [source] in {REGISTRY}" if repo else "a [source] (not inside a repository)"
        raise FsError(f"'{arg}' is neither a URL nor {where}")
    return arg


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
    d = (base / os.path.expanduser(args.dir)).resolve()
    if git(["-C", d, "rev-parse", "--git-dir"], env=clean_env(), check=False).returncode:
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
            if args.older_than is not None:
                max_age = args.older_than or None
            if args.max_size is not None:
                max_size = parse_size(args.max_size) or None
            if max_age is None and max_size is None:
                print("no limits set (filesync.cacheMaxAge, filesync.cacheMaxSize, "
                      "--older-than, --max-size) - nothing to do")
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
    to sync, a strict violation, an error."""
    links = Registry(repo).links()
    prefetch(ctx, repo, links)
    sts = [evaluate(ctx, repo, link) for link in links]
    attention = [st for st in sts if st.error or st.pending or st.violation]
    for st in attention:
        print(f"filesync: {paint(st.rel, 'yellow', 'err')}: {render(describe(st), 'err')}",
              file=sys.stderr)
    if any(st.pending for st in attention):
        print("filesync: run 'git filesync pull <file>' to sync", file=sys.stderr)
    if any(st.violation for st in attention):
        print("filesync: see 'git filesync status' and 'git filesync diff <file>' "
              "for strict violations", file=sys.stderr)


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


def registry_entries(repo, rev):
    """[(url, synced commit, rel)] of the links in .git-filesync at rev
    (none if it has no readable one, or rev isn't here)."""
    p = repo.git(["config", "--blob", f"{rev}:{REGISTRY}", "--list", "-z"], check=False)
    if p.returncode:
        return []
    sources, files = parse_registry(p.stdout)
    entries = []
    for rel, v in sorted(files.items()):
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
    known = {(norm_url(url), commit) for rev in dict.fromkeys(remote)
             for url, commit, _ in registry_entries(repo, rev)}
    found = {}       # (url, commit) -> [rels]
    for rev in revs:
        for url, commit, rel in registry_entries(repo, rev):
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
            if all(ln.strip() in ("", "#!/bin/sh", "exit 0") for ln in rest):
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
        if all(ln.strip() in ("", "#!/bin/sh", "exit 0") for ln in rest):
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


BASIC_COMMANDS = ("status", "pull", "diff", "difftool", "restore", "add", "rm", "unlink", "mv")


class NoTheme:
    """argparse's color theme before Python 3.14: no colors."""
    def __getattr__(self, name):
        return ""


class MainParser(argparse.ArgumentParser):
    """The top-level parser: usage line and the grouped command list (basic
    commands first, the rest in the order they were defined, `hook` last)
    in argparse's own colors - which exist from Python 3.14 on."""
    sub = None        # the subparsers action, set once the commands exist

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
        helps = {a.dest: a.help for a in self.sub._choices_actions
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
    colorp.add_argument("--color", nargs="?", const="always", default="auto",
                        choices=["always", "never", "auto"], help="colored output (default: auto)")
    colorp.add_argument("--no-color", dest="color", action="store_const", const="never",
                        help="same as --color=never")
    common = argparse.ArgumentParser(add_help=False, parents=[colorp])
    common.add_argument("--no-fetch", action="store_true",
                        help="do not fetch upstream repositories, use cached state")

    argv = list(sys.argv[1:] if argv is None else argv)
    # like git: --color takes a value only as --color=WHEN; alone it is
    # always, and what follows is no value of it (status --color a.c)
    end = argv.index("--") if "--" in argv else len(argv)
    argv = [a if a != "--color" else "--color=always" for a in argv[:end]] + argv[end:]
    # the help in colors exactly when the output on stdout would be colored
    # (argparse has colors from Python 3.14 on, and checks the terminal too)
    color = {"color": color_wanted(color_option(argv), sys.stdout)} \
        if "color" in inspect.signature(argparse.ArgumentParser).parameters else {}
    ap = MainParser(prog="git filesync", usage=argparse.SUPPRESS,
                    description="Keep single files in sync between Git repositories.", **color)
    ap.add_argument("--version", action="version", version=f"git-filesync {__version__}")
    sub = ap.sub = ap.add_subparsers(dest="cmd", metavar="<command>", prog="git filesync",
                                     parser_class=argparse.ArgumentParser)

    p = add_command(sub, "status", parents=[common], help="show sync state of linked files")
    p.add_argument("paths", nargs="*", metavar="PATH", help="linked files or directories (default: all)")
    p.add_argument("-s", "--short", action="store_true",
                   help="short format: upstream / committed / working tree columns")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also list all linked files with their sources")
    p.add_argument("--exit-code", action="store_true",
                   help="exit with 1 if something is to sync or a strict file is modified")

    p = add_command(sub, "pull", parents=[common], help="sync file(s) from upstream")
    p.add_argument("files", nargs="*", metavar="PATH", help="linked files or directories")
    p.add_argument("--all", action="store_true", help="sync all files with something to sync")
    p.add_argument("--commit", metavar="REV", help="sync to this upstream revision (exactly one file)")
    p.add_argument("-b", "--branch", help="sync to the head of this upstream branch, once (the "
                                          "files keep following their own branch or tag)")
    p.add_argument("--tag", help="sync to this upstream tag, once (as -b)")
    p.add_argument("--overwrite", action="store_true",
                   help="discard local adaptations instead of merging them")
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
        p.add_argument("--commit", metavar="REV",
                       help="with --upstream: as for pull, synced -> REV (exactly one file)")
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

    p = add_command(sub, "add", parents=[common], help="link a file (or all files of a directory) "
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
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be linked")
    p.add_argument("--commit", metavar="REV", help="upstream revision to base the file on "
                                                    "instead of the head")
    p.add_argument("--overwrite", action="store_true",
                   help="replace an existing file with the upstream version")
    p.add_argument("--force", action="store_true", help="relink an already linked file")
    p.add_argument("--strict", action="store_true",
                   help="file must stay an exact copy (no local modifications)")

    p = add_command(sub, "set", parents=[common], help="change the link of linked files: source, "
                                                     "tag, upstream path, strict")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
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
    p.add_argument("-p", "--path", help="another upstream path (one file); its current "
                                        "version becomes the base, as for add")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--strict", action="store_const", const=True,
                   help="the files must stay exact copies")
    g.add_argument("--no-strict", dest="strict", action="store_const", const=False,
                   help="allow local adaptations again")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would change")

    add_command(sub, "edit", parents=[colorp], help=f"open {REGISTRY} in the editor, then check "
                                                  "and stage it")

    p = add_command(sub, "restore", parents=[colorp],
                    help="restore files to the synced upstream version, like 'git restore'")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-S", "--staged", action="store_true",
                   help="restore the index instead of the working tree")
    p.add_argument("-W", "--worktree", action="store_true",
                   help="restore the working tree (the default; with -S: both)")

    p = add_command(sub, "rm", parents=[colorp],
                    help="remove linked files and their links, like 'git rm'")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-f", "--force", action="store_true",
                   help="also remove files with uncommitted changes")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be removed")

    p = add_command(sub, "unlink", parents=[colorp], help="remove links (the files are kept)")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be unlinked")

    p = add_command(sub, "mv", parents=[colorp], help="move a linked file, keeping its link")
    p.add_argument("src", metavar="OLD", help="linked file")
    p.add_argument("dst", metavar="NEW", help="new path or existing directory")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be moved")

    p = add_command(sub, "source", parents=[colorp], help="list or change the [source]s "
                                                        "(like 'git remote')")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list with URL, branch and file count")
    actions = p.add_subparsers(dest="action", metavar="ACTION")
    for name, arg, hlp in (("rename", "NEW", "rename a source and all references to it"),
                           ("set-url", "URL", "change the URL of a source"),
                           ("set-branch", "BRANCH", "follow BRANCH - for all files of the "
                                                    "source; pinned ones look for newer tags "
                                                    "(or those of a pattern) on it")):
        # set-url / set-branch check the branch upstream
        a = add_command(actions, name, parents=[colorp if name == "rename" else common], help=hlp)
        a.add_argument("name", metavar="NAME" if name != "rename" else "OLD",
                       help="key of the [source]")
        a.add_argument("value", metavar=arg)
    a = add_command(actions, "map", parents=[colorp],
                    help="use a local checkout for an upstream URL (this repo's config; "
                         "--global for all repos)")
    a.add_argument("url", nargs="?", metavar="URL|SOURCE",
                   help="upstream URL, or the name of a [source] for its URL "
                        "(without DIR: list its mappings)")
    a.add_argument("dir", nargs="?", help="local checkout of the upstream repository")
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
    a.add_argument("--older-than", type=int, metavar="DAYS",
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
        ctx = Context(args, repo)
        reading = args.cmd in ("status", "diff", "difftool", "hook") or \
            args.cmd == "source" and not args.action
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
