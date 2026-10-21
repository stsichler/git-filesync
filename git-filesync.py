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
        branch = main          ; followed - or, with a tag, where newer tags
        tag = v1.2             ; are looked for; optional: pinned to the tag
                               ; (with * ? [...]: the newest matching tag
                               ; on the branch)
    [file "src/foo.c"]
        source = owner/lib
        path = lib/foo.c       ; path in the upstream repository
        strict = true          ; optional: no local modifications allowed
        commit = <upstream commit of the last sync>
        blob = <blob id of the upstream file at that commit>

A link records the upstream version the file is based on (commit/blob);
local adaptations on top of it are allowed and kept by a 3-way merge on
pull, unless the file is marked strict.

Commands (run inside the repository; without a command: status).
PATH may be a file or a directory (= all linked files below it); options
follow the command. Only pull commits; the other commands stage (restore:
with -S), like their git namesakes.

Basic commands:

    status [PATH...]            state of the linked files like `git status`:
                                upstream changes to sync, committed
                                adaptations, uncommitted changes
        -s, --short             short format: upstream/committed/worktree
                                columns (upstream: P pending, O older,
                                D diverged, R renamed, X deleted
                                upstream, N new; E error)
        -v, --verbose           also list all linked files with their sources
                                (pinned ones with the newest tag: the first
                                tagged commit after theirs on the branch's
                                first-parent line - on every branch with
                                the tag unless the source names one)
        --exit-code             exit 1 if something is to sync or a strict
                                file is modified

    pull PATH... | --all        sync to the upstream version of the file and
                                commit with a message listing the upstream
                                commits since the last sync; adaptations are
                                merged, uncommitted changes refused; a file
                                renamed upstream is followed, one
                                deleted there is reported
        --all                   all files with something to sync
        --commit REV            sync to this upstream revision (one file;
                                also backwards)
        -b, --branch BRANCH     sync to the head of BRANCH, once: the files
                                keep following their own branch or tag
                                (to switch: set -b/--tag, source set-*)
        --tag TAG               sync to TAG, once (as -b)
        --overwrite             discard local adaptations instead of merging
        --autostash             set uncommitted changes aside, re-apply after
        --no-edit               commit without opening the editor
        --no-commit             only stage; a plain `git commit` offers the
                                proposed message (via .git/SQUASH_MSG)
        --dry-run               only report what would happen (incl.
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
        -y, --no-prompt         don't ask before each file (default: ask if
                                no files are given)
        --prompt                ask even for explicitly given files

    restore PATH...             restore files to the synced upstream version
                                (the base), like `git restore`; e.g. to
                                discard adaptations of a strict file
        -S, --staged            restore the index instead of the working tree
        -W, --worktree          restore the working tree (default; with -S:
                                both)

    add FILE URL|SOURCE         link FILE to a file in an upstream repository
                                (SOURCE: exactly that [source]; URL: the
                                source with that URL and branch/tag, else a
                                new one named 'owner/repo' after the URL, with
                                a number appended if taken); the base is the
                                upstream head (or --commit): an existing FILE
                                is kept, its differences count as adaptations;
                                a missing FILE is fetched; FILE and
                                .git-filesync are staged like `git add` - a
                                plain `git commit` offers the proposed message
    add DIR URL|SOURCE          link every file below an upstream directory
                                (-p, default: same as DIR) as DIR/...; files
                                already linked are skipped
        -b, --branch BRANCH     upstream branch (default: its default
                                branch or that of SOURCE); with --tag: the
                                branch to look for newer tags on
        --tag TAG               pin to an upstream tag instead of a branch
                                (a pattern: the newest matching tag on -b)
        -p, --path PATH         upstream path (default: same as FILE; \\
                                counts as /)
        --include PATTERN       DIR: only files matching (gitignore-like,
                                relative to the upstream directory; repeatable)
        --exclude PATTERN       DIR: skip files matching (repeatable)
        --commit REV            upstream revision to base FILE on instead
                                of the head
        --overwrite             replace an existing FILE with the upstream
                                version
        --strict                FILE must stay an exact copy
        --force                 relink an already linked file
        -n, --dry-run           only show what would be linked

    rm PATH...                  remove linked files and their links, staged
                                like `git rm`; refused for files with
                                uncommitted changes
        -f, --force             remove them anyway
        -n, --dry-run           only show what would be removed

    unlink PATH...              remove links (the files are kept)
    mv OLD NEW                  move a linked file (git mv), keeping its link
        -n, --dry-run           (both) only show what would be done

Advanced commands:

    set PATH... OPTIONS         change the link of linked files, like `source`
                                for sources; only .git-filesync is changed
                                (and staged), the synced version is kept
                                where it still applies
        --source URL|SOURCE     another upstream (fork, moved repository) or
                                [source]; a source whose files are all given
                                is changed itself
        -b, --branch BRANCH     as for add; without --source: follow BRANCH
                                from now on (sync with pull)
        --tag TAG               as for add; without --source: pin to TAG
                                from now on; the source's branch (or -b)
                                stays the one to look for newer tags on;
                                a source whose files are all given is
                                changed itself, otherwise the files move to
                                a source with that URL, branch and tag
        -p, --path PATH         another upstream path (one file); its
                                current version becomes the base, as for add
        --strict, --no-strict   mark as strict / allow adaptations again
        -n, --dry-run           only show what would change

    edit                        open .git-filesync in the editor (like `git
                                config --edit`); afterwards it is checked
                                and staged

    source                      list the [source]s (-v: with URL, ref, newest
                                tag if pinned, files)
    source rename OLD NEW       rename a [source] and all references to it
    source set-url NAME URL     change the URL of a [source]
    source set-branch NAME BRANCH  follow BRANCH; if pinned to a tag: look
                                for newer tags on BRANCH only (--unset
                                instead of BRANCH: on all branches)
    source set-tag NAME TAG     pin to TAG (a branch stays, for newer tags);
                                a tag is taken as immutable: fetched only if
                                missing; a pattern (* ? [...]) follows the
                                newest matching tag on the branch
    source set-tag NAME --unset  remove the tag: follow the branch again
    source map [URL|SOURCE [DIR]]  use the local checkout DIR instead of
                                fetching URL (SOURCE: the URL of that
                                [source]); its branch is used, unpushed
                                commits included; without DIR: list mappings
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
        --older-than DAYS, --max-size SIZE  other limits (SIZE: 500M, 2G)
        -n, --dry-run           only show what would be removed
    cache clear [-n]            remove all clones
    cache dir                   print its directory (e.g. for CI caching)

    install-hooks               install pre-push/post-merge hooks (or update
                                them): reminders about pending syncs, strict
                                violations, errors; pre-push also warns if a
                                pushed file is synced to an upstream commit
                                that isn't on the upstream server
                                (filesync.pushCheck = warn | error, which
                                refuses the push | off); in a pre-push hook
                                shared with git lfs, our lines come first
        --force                 add our lines to existing hooks of other
                                tools, right after the #! line (default:
                                show the lines to add)
    uninstall-hooks             remove them again
    hook pre-push|post-merge    what the installed hooks run

    Common options:
        --no-fetch              use the cached state, don't fetch (status,
                                pull, diff, difftool, add, set, source -v)
        --remote                ignore local checkout mappings (same commands)
        --color[=WHEN], --no-color  always, never or auto (default)

Exit codes: 0 ok, 1 unfinished (conflicts, not committed, --exit-code),
2 error.

Files stored in Git LFS (upstream, in this repository, both or neither) are
handled transparently, as are differing line-ending conventions. Output is
colored like git's (color.filesync / color.ui, --color, NO_COLOR).

Requires Python >= 3.7 and Git >= 2.28 (git-lfs for LFS files).
Works on Linux, macOS and Windows.
Manual: https://github.com/stsichler/git-filesync/blob/main/MANUAL.md
"""

import argparse
import fnmatch
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

__version__ = "0.11.1"
REGISTRY = ".git-filesync"
EXIT_OK, EXIT_PENDING, EXIT_ERROR = 0, 1, 2
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


def setup_colors(mode, cwd=None):
    """Decide per stream like git: --color, NO_COLOR, color.filesync/color.ui."""
    def want(stream):
        if mode == "always":
            return True
        if mode == "never" or os.environ.get("NO_COLOR"):
            return False
        tty = "true" if stream.isatty() else "false"
        p = git(["config", "--get-colorbool", "color.filesync", tty], cwd=cwd, check=False)
        return out(p) == "true"
    _color["out"], _color["err"] = want(sys.stdout), want(sys.stderr)
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

class Source:
    """A Git repository providing the upstream versions of synced files."""

    def __init__(self, workdir, ref, label, local=False, note=None):
        self.dir, self.ref, self.label = Path(workdir), ref, label
        self.local = local   # mapped local checkout: ref is its local branch
        self.note = note     # remark about the ref choice, shown by status
        self.tag_names = None   # for a tag pattern: the matching tags ref is at
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
        diff` for the whole checkout, asked once."""
        key = ("uncommitted",)
        if key not in self._memo:
            p = self.git(["diff", "--name-only", "-z", "--no-renames", "HEAD"], check=False)
            self._memo[key] = set(p.stdout.decode("utf-8", "replace").split("\0")) \
                if p.returncode == 0 else None
        if self._memo[key] is None:
            return self.git(["diff", "--quiet", "HEAD", "--", lit(path)],
                            check=False).returncode == 1
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

    def check_plain(self, blobs):
        """Find out with one `cat-file --batch` which of these blobs hold
        plain content: no CR and no LFS pointer (see is_plain)."""
        blobs = [b for b in dict.fromkeys(blobs) if b and ("plain", b) not in self._memo]
        if not blobs:
            return
        p = self.git(["cat-file", "--batch"], data="".join(b + "\n" for b in blobs).encode(),
                     check=False)
        data, pos = p.stdout, 0
        for b in blobs:
            end = data.find(b"\n", pos)
            head = data[pos:end].split() if end >= 0 else []
            if len(head) != 3 or head[1] != b"blob":
                return            # missing or odd: is_plain() says "don't know"
            size = int(head[2])
            content = data[end + 1:end + 1 + size]
            self._memo[("plain", b)] = b"\r" not in content and not lfs_pointer(content)
            pos = end + 1 + size + 1

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
        return self.git(["cat-file", "blob", oid]).stdout

    def read_content(self, oid, path):
        """Actual file content of a blob: LFS pointers are resolved."""
        data = self.read_blob(oid)
        if lfs_pointer(data):
            data = lfs_smudge(self.git, data, path, self.label)
        return data

    def short(self, oid):
        return out(self.git(["rev-parse", "--short", oid]))

    def is_ancestor(self, a, b):
        key = ("ancestor", a, b)
        if key not in self._memo:
            self._memo[key] = self.git(["merge-base", "--is-ancestor", a, b],
                                       check=False).returncode == 0
        return self._memo[key]

    def branch_refs(self, contains=None):
        """{branch name: ref} of the upstream branches (only those containing
        commit `contains`, if given): the remote-tracking branches, in a local
        checkout overridden by its local branches of the same name."""
        prefixes = ["refs/remotes/origin/"] + (["refs/heads/"] if self.local else [])
        refs = out(self.git(["for-each-ref", "--format=%(refname)"]
                            + (["--contains", contains] if contains else []) + prefixes)).split()
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
            return f"tag {tag} is not on branch '{branch}' of {self.label}"
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

    def tag_info(self, tag, line, newer=True):
        """(newer tags, problem) for a source pinned to tag that looks for
        newer tags on branch line (None: all branches); problem: why they
        can't be looked for there. newer=False: only check the branch."""
        problem = line and self.line_problem(tag, line)
        if problem or not newer:
            return [], problem
        return self.newer_tags(tag, line), None

    def newer_tags(self, tag, branch=None):
        """Tags newer than tag, by their position in the commit graph - tag
        names are opaque, and tags have no reliable date. On a branch, the
        newest tag after tag is on the first tagged commit of its first-
        parent line (a tag on a merged side branch doesn't count). Looked for
        on branch only, or on every branch containing tag. Returns
        [(tags of that commit, [branches])], empty if there are none."""
        key = ("newer", tag, branch)
        if key in self._memo:
            return self._memo[key]
        base = self.resolve(f"refs/tags/{tag}")
        refs = {}
        if base and branch:
            ref = self.branch_refs().get(branch)
            refs = {branch: ref} if ref and self.is_ancestor(base, ref) else {}
        elif base:
            refs = self.branch_refs(contains=base)
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
        return int(out(self.git(["rev-list", "--count", f"{old}..{new}", "--"]
                                + [lit(p) for p in paths])))

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
        self.fetch = not getattr(args, "no_fetch", False)
        self.force_remote = getattr(args, "remote", False)
        # fetch even for a tag already cached, to learn about newer tags
        self.want_tags = getattr(args, "verbose", False) or args.cmd in ("pull", "source")
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
            except FsError as e:      # e.g. a failed clone: not tried again for each file
                self._sources[key] = e
        s = self._sources[key]
        if isinstance(s, FsError):
            raise s
        return s

    def local_path(self, url):
        """Mapped local checkout for url (validated), or None."""
        if self.force_remote:
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
            else:         # a pattern: always fetched, for new matching tags
                src = Source(self._cache(url, tag=None if pattern else branch),
                             f"refs/tags/{branch}", name or repo_label(url))
            if pattern:
                src.tag_names = src.newest_matching(branch, line)
                if not src.tag_names:
                    raise FsError(f"no tag matching '{branch}' on branch '{line}' of {src.label}")
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
        return Source(self._cache(url), f"refs/remotes/origin/{branch}",
                      name or repo_label(url))

    @staticmethod
    def cache_dir(url):
        return cache_root() / (hashlib.sha1(norm_url(url).encode()).hexdigest()[:16] + ".git")

    def _cache(self, url, tag=None):
        """The cache clone of url, fetched once per run - not for a tag
        already there (tags are taken as immutable), unless newer tags are
        of interest (want_tags)."""
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
                tmp.rename(d)
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
        elif tag and not self.want_tags and git(["-C", d, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                         env=env, check=False).returncode == 0:
            touch_used(d)
            return d       # not marked ready: a branch of the same URL still fetches
        elif self.fetch:
            p = git(["-C", d] + fetch, env=env, check=False)
            if p.returncode:
                warn(f"fetching {url} failed, using cached state")
                self._fetch_failed.add(d)
            self._drop_heads(d)
        touch_used(d)
        if self.fetch:
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
        p = git(["rev-parse", "--show-toplevel"], check=False)
        if p.returncode:
            raise FsError("not inside a Git working tree")
        self.top = Path(out(p)).resolve()
        self.gitdir = Path(out(git(["rev-parse", "--absolute-git-dir"])))
        # shell aliases run in the top-level dir and pass the original
        # subdirectory in GIT_PREFIX
        prefix = os.environ.get("GIT_PREFIX")
        self.base = Path.cwd() / prefix if prefix else Path.cwd()
        self._head = {}           # rel -> blob id in HEAD (None: not there)
        self._dirty = {}          # rel -> differs between HEAD and working tree
        self._plain = {}          # rel -> no content-changing attributes

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
        objects = saved["GIT_OBJECT_DIRECTORY"] or str(
            self.top / out(self.git(["rev-parse", "--git-path", "objects"])))
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
        return (self.base / s).resolve()

    def rel(self, path):
        return Path(os.path.relpath(Path(path).resolve(), self.top)).as_posix()

    def worktree_blob(self, path, write=False):
        """Blob id of the (clean-filtered) working tree file, None if missing.
        For a file tracked in LFS here, this is the id of its LFS pointer."""
        if not path.is_file():
            return None
        args = ["hash-object"] + (["-w"] if write else []) + \
            [f"--path={self.rel(path)}", str(path)]
        return out(self.git(args))

    def read_blob(self, oid):
        return self.git(["cat-file", "blob", oid]).stdout

    def read_content(self, oid, rel):
        """Actual content of a blob of this repo: LFS pointers are resolved."""
        data = self.read_blob(oid)
        if lfs_pointer(data):
            data = lfs_smudge(self.git, data, rel, "this repository")
        return data

    def content_id(self, oid, rel):
        """Blob id of the actual content (differs from oid for an LFS pointer)."""
        data = self.read_blob(oid)
        if not lfs_pointer(data):
            return oid
        return self.store(self.read_content(oid, rel))

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
        work = self.to_worktree(content, rel)
        return out(self.git(["hash-object", "-w", f"--path={rel}", "--stdin"], data=work))

    def normalize(self, content, rel):
        """Upstream content as this repo stores it, LFS resolved: the form all
        comparisons and merges use, whatever the eol conventions and LFS use
        upstream and here."""
        return self.read_content(self.as_local(content, rel), rel)

    def state_file(self, prefix, name):
        """.git/<prefix><name> for state kept between commands (name made
        safe as a file name)."""
        return self.gitdir / (prefix + re.sub(r"[^A-Za-z0-9._-]", "_", name))

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


def source_spec(source):
    """The ref keys of a [source] (or of what a command asks for):
    {'branch': B} follows B, {'tag': T} is pinned to T, {'tag': T,
    'branch': B} is pinned to T and looks for newer tags on B only."""
    return {k: source[k] for k in ("branch", "tag") if source.get(k)}


def is_tag_pattern(tag):
    """A tag with * ? or [ is a pattern (like fnmatch): the newest matching
    tag on the source's branch counts."""
    return bool(re.search(r"[*?\[]", tag))


def source_ref(source):
    """('branch' | 'tag', name) the files of a [source] are synced to: its tag
    if it is pinned, else its branch; None if it has neither."""
    branch, tag = source.get("branch"), source.get("tag")
    if tag:
        return ("tag", tag)
    return ("branch", branch) if branch else None


def source_line(source):
    """Branch of a pinned [source]: the only one newer tags are looked for on
    (None: all branches). A source that isn't pinned follows its branch."""
    return source.get("branch") if source.get("tag") else None


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


def spec_text(spec):
    """'branch main' / 'tag v1.2' / 'tag v1.2 on main' - for messages."""
    ref = source_ref(spec)
    assert ref, "a spec has a branch or a tag"
    return ref_text(ref, source_line(spec)) if ref[0] == "tag" else f"branch {ref[1]}"


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


class Registry:
    """The repository's .git-filesync: [source] and [file] sections."""

    def __init__(self, repo):
        self.repo = repo
        self.path = repo.top / REGISTRY
        self.sources, self.files = {}, {}
        self.dry_run = False      # only change the in-memory state
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
        if not self.path.exists():
            self.path.write_bytes(REGISTRY_HEADER.encode())
        git(["config", "-f", self.path] + list(args))

    def set_file(self, rel, name, value):
        """Set (value None: remove) a key of a [file]."""
        if value is None:
            if name in self.files.get(rel, {}):
                self._cfg("--unset-all", f"file.{rel}.{name}")
                del self.files[rel][name]
        else:
            self._cfg(f"file.{rel}.{name}", value)
            self.files.setdefault(rel, {})[name] = value

    def find_source(self, url, spec, exclude=None, any_line=False):
        """Key of a [source] with url and exactly the ref keys of spec. With
        any_line, a source pinned to spec's tag is taken whatever branch it
        looks for newer tags on (one without a branch first)."""
        cands = [name for name, s in self.sources.items()
                 if name != exclude and norm_url(s.get("url", "")) == norm_url(url)]
        for name in cands:
            if source_spec(self.sources[name]) == spec:
                return name
        if any_line and spec.get("tag"):
            for name in cands:
                if self.sources[name].get("tag") == spec["tag"]:
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

    def source_name(self, url, spec, any_line=False):
        """Key of the [source] for url+spec (found by URL, not by key),
        or the key a new one would get."""
        return self.find_source(url, spec, any_line=any_line) or self.new_source_name(url)

    def add_source(self, url, spec, any_line=False):
        """Key of the [source] for url+spec, created if necessary."""
        name = self.find_source(url, spec, any_line=any_line)
        if name:
            return name
        name = self.new_source_name(url)
        self._cfg(f"source.{name}.url", url)
        self.sources[name] = {"url": url}
        self.set_spec(name, spec)
        return name

    def set_spec(self, name, spec):
        """Set the branch/tag keys of a [source] to spec."""
        for key in ("branch", "tag"):
            self.set_source(name, key, spec.get(key))

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
        (unless it is keep_source)."""
        src = self.files.pop(rel, {}).get("source")
        self._cfg("--remove-section", f"file.{rel}")
        if src and src != keep_source and src in self.sources and \
                not any(f.get("source") == src for f in self.files.values()):
            self._cfg("--remove-section", f"source.{src}")
            del self.sources[src]

    def rename_file(self, old, new):
        self._cfg("--rename-section", f"file.{old}", f"file.{new}")
        self.files[new] = self.files.pop(old)

    def finish(self):
        """Fix line endings and stage the registry (or its removal when empty)."""
        if self.path.exists():
            if not self.sources and not self.files:
                self.path.unlink()
            else:
                self.repo.fix_eol(self.path)
        self.repo.git(["add", "-A", "--", REGISTRY])

    def uncommitted(self):
        """[file] entries that differ from the committed .git-filesync in what
        they record about the file. Which [source] they belong to doesn't
        count: a changed source may go into any commit."""
        p = self.repo.git(["config", "--blob", f"HEAD:{REGISTRY}", "--list", "-z"], check=False)
        head = parse_registry(p.stdout)[1] if p.returncode == 0 else {}

        def base(entry):
            return None if entry is None else {k: v for k, v in entry.items() if k != "source"}
        return {rel for rel in set(head) | set(self.files)
                if base(head.get(rel)) != base(self.files.get(rel))}


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
    ref = property(lambda self: source_ref(self.source))     # ('branch' | 'tag', name)
    line = property(lambda self: source_line(self.source))   # branch of a pinned source
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
    count: int = 0            # upstream commits touching the file since the sync
    behind: int = 0           # ... or by how many the branch went back
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
        for src, lks in groups.values():
            try:
                src.check_plain(lk.blob for lk in lks if id(lk) in ids)
            except FsError:
                pass


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
    if not (url and ref and path):
        st.error = (f"incomplete entry in {REGISTRY} (needs a source with url and "
                    "either branch or tag, and path)")
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
            st.behind = src.count(st.new, st.old, path)   # branch older than last sync
        else:
            st.count = src.count(st.old, st.new, *dict.fromkeys((link.path, path)))
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
        return "renamed", f"{st.link.path} -> {path}" + (f", {plural(st.count, 'commit')}" if st.count else "")
    if st.changed:
        if st.behind:
            what = "upstream branch" if st.link.ref[0] == "branch" else f"tag {st.link.ref[1]}"
            return "older", f"{what} is {plural(st.behind, 'commit')} older than last sync"
        if st.has_old and not st.diverged:
            return "pending", plural(st.count, "commit")
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
    y = "A" if st.committed == "adapted" else " "
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


def check_other_entries(reg, rels, args):
    """One commit = these files + their entries; other uncommitted entries
    would end up in it without their files."""
    if args.no_commit:
        return
    others = reg.uncommitted() - set(rels)
    if others:
        raise FsError(f"{REGISTRY} has uncommitted changes for {', '.join(sorted(others))}"
                      " - commit them first, or use --no-commit to stage everything "
                      "and commit together")


def message_file(repo, name, msg, rels=None):
    """Keep the proposed commit message in .git/FILESYNC_MSG_<name>; returns
    the file and the command that commits the files (default: name) and
    their entries with it."""
    msgfile = repo.state_file("FILESYNC_MSG_", name)
    msgfile.write_bytes(msg.encode("utf-8"))
    paths = " ".join(path_arg(repo, r) for r in ([name] if rels is None else rels) + [REGISTRY])
    return msgfile, f'git commit -e -F "{shown_path(repo, msgfile)}" -- {paths}'


def propose_message(repo, msg):
    """Also put a proposed commit message into .git/SQUASH_MSG, which a plain
    `git commit` (and IDEs) offer; git removes it after the next commit.
    Proposals of several commands are collected. A SQUASH_MSG of git's own
    (e.g. from merge --squash) is left alone. Returns True if done."""
    squash = repo.gitdir / "SQUASH_MSG"
    ours = repo.state_file("FILESYNC_", "SQUASH_MSG")     # copy of what we wrote
    if squash.exists():
        prev = squash.read_text(encoding="utf-8", errors="replace")
        if not ours.exists() or ours.read_text(encoding="utf-8", errors="replace") != prev:
            return False
        if msg in prev:
            return True
        msg = prev.rstrip("\n") + "\n\n" + msg
    for f in (squash, ours):
        f.write_bytes(msg.encode("utf-8"))
    return True


def commit_hint(repo, name, msg, rels=None):
    """(command, note) for committing staged changes with the proposed
    message: a plain `git commit` if the message could be prepared for it
    (see propose_message), otherwise one with a message file."""
    if propose_message(repo, msg):
        # git drops SQUASH_MSG after any commit (also one that didn't use
        # it) and on reset; our copy stays until the next proposal
        copy = shown_path(repo, repo.state_file("FILESYNC_", "SQUASH_MSG"))
        return "git commit", f"it offers the proposed commit message; a copy stays in {copy}"
    _, cmd = message_file(repo, name, msg, rels)
    return cmd, "a plain 'git commit' won't offer the proposed message: .git/SQUASH_MSG is in use"


def report_staged(repo, name, msg, done, rels=None, how="Commit with"):
    """Tell how to commit what a command staged without committing."""
    cmd, note = commit_hint(repo, name, msg, rels)
    print(f"{name}: {done}. {how}:\n    {cmd}\n({note})")


def commit_staged(repo, name, msg, args, done, rels=None):
    """Commit the staged files (default: name) and their entries with the
    proposed message (in the editor unless --no-edit). With --no-commit,
    leave them staged and tell how to commit. done: e.g. 'synced and staged'."""
    rels = [name] if rels is None else rels
    if args.no_commit:
        report_staged(repo, name, msg, paint(done, "green"), rels)
        return EXIT_OK
    msgfile, _ = message_file(repo, name, msg, rels)
    cmd = ["git", "commit", "-F", str(msgfile)] + ([] if args.no_edit else ["-e"]) + \
        ["--"] + [lit(r) for r in rels] + [REGISTRY]
    if subprocess.run(cmd, cwd=repo.top).returncode:
        report_staged(repo, name, msg, paint("commit not done", "yellow")
                      + "; changes stay staged", rels, "Commit later with")
        return EXIT_PENDING
    msgfile.unlink()
    return EXIT_OK


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
    # like `git pull`: uncommitted changes are never merged into a sync
    # commit; --autostash sets them aside and re-applies them afterwards
    dirty = st.worktree in ("modified", "deleted", "added")
    stash = None
    if dirty and args.autostash:
        if st.worktree != "modified":
            raise FsError(f"{st.rel}: --autostash can't set aside a {st.worktree} file")
        stash = repo.read_content(repo.worktree_blob(link.target, write=True), st.rel)
    local_mod = st.committed == "adapted" if stash is not None else st.local == "modified"
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
        return EXIT_OK
    if dirty and stash is None:
        raise FsError(f"your local changes to '{st.rel}' would be overwritten by pull - "
                      "commit or stash them first, or use --autostash "
                      f"('git restore {path_arg(repo, st.rel)}' discards them)")
    check_other_entries(reg, [st.rel], args)
    for w in st.warnings:
        warn(f"{st.rel}: {w}")

    # all versions in this repo's normalized form, so that differing eol
    # conventions (and LFS) upstream and here don't matter
    theirs = repo.normalize(src.read_content(new_blob, path), st.rel)
    merged, conflicts = False, 0
    if local_mod and not discard:
        base = local_equiv(repo, src, st.old_blob, st.rel, link.path)
        if not base:
            raise FsError(f"{st.rel}: base version {st.old_blob[:12]} unavailable; "
                          "cannot merge local modifications")
        base = repo.read_content(base, st.rel)
        ours = repo.read_content(st.head_blob if stash is not None else
                                  repo.worktree_blob(link.target, write=True), st.rel)
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
              "adaptations merged cleanly"] if merged else []) + \
            (["uncommitted changes set aside and re-applied"] if stash is not None else [])
        verb = "restore" if new_blob == st.old_blob and discard else "sync"
        print(f"{st.rel}: would {verb} to {link.name}@{src.short(new)}"
              + (f" ({'; '.join(notes)})" if notes else ""))
        if conflicts:
            rel = path_arg(repo, st.rel)
            print(f"hint: compare the adaptations ('git filesync diff {rel}') with the "
                  f"upstream changes ('git filesync diff --upstream{target_opts(args)} {rel}')")
        return EXIT_OK

    old_path = link.path
    link.target.parent.mkdir(parents=True, exist_ok=True)
    link.target.write_bytes(repo.to_worktree(content, st.rel))
    if path != old_path:
        link.set("path", path)
    link.set("commit", new)
    link.set("blob", new_blob)
    reg.finish()

    msg = build_message(st, src, new, new_blob, old_path, path, merged, conflicts, discard)
    if conflicts:
        if stash is not None:
            stashfile = repo.state_file("FILESYNC_STASH_", st.rel)
            stashfile.write_bytes(repo.to_worktree(stash, st.rel))
            print(f"{st.rel}: autostash kept in {shown_path(repo, stashfile)} (not re-applied because of the conflicts)")
        cmd, note = commit_hint(repo, st.rel, msg)
        print(f"{st.rel}: {paint(f'{conflicts} merge conflict(s)', 'boldred')}. "
              f"Resolve them, then run:\n    git add {path_arg(repo, st.rel)}\n    {cmd}\n({note})")
        return EXIT_PENDING
    repo.git(["add", "--", lit(st.rel)])
    rc = commit_staged(repo, st.rel, msg, args, "synced and staged")
    if stash is not None:
        # re-apply the stashed uncommitted changes on top of the synced version
        head = repo.read_content(st.head_blob, st.rel)
        c2, data = merge3(content, head, stash, [f"{st.rel} (synced)", f"{st.rel} (HEAD)",
                                                 f"{st.rel} (autostash)"])
        link.target.write_bytes(repo.to_worktree(data, st.rel))
        if c2:
            print(f"{st.rel}: {paint(f'applying autostash resulted in {c2} conflict(s)', 'boldred')}"
                  " - resolve them in the working tree")
            rc = EXIT_PENDING
        else:
            print(f"{st.rel}: {paint('applied autostash', 'green')} (uncommitted changes restored)")
    return rc


def switch_spec(source, args):
    """The ref keys set -b/--tag switch a [source] to: --tag pins, keeping
    the branch the source has (or -b) as the one to look for newer tags on;
    -b alone follows that branch."""
    if not args.tag:
        return {"branch": args.branch}
    spec = {"tag": args.tag}
    branch = args.branch or source.get("branch")
    if branch:
        spec["branch"] = branch
    return spec


def move_to_source(reg, name, lks, url, spec, named=None):
    """Point links lks of [source] name at the source with url and spec -
    or exactly at [source] named. If lks are all files of the source and no
    such source exists, the source itself is changed; otherwise they move
    to it (found or created) and the source is split, or removed when left
    without files. Returns a description of the change."""
    source = reg.sources[name]
    old_url, old = source.get("url", ""), source_spec(source)
    new_repo = norm_url(url) != norm_url(old_url)

    def text(u, sp):
        return f"{u} ({spec_text(sp)})" if new_repo else spec_text(sp)
    target = named or reg.find_source(url, spec, exclude=name)
    if not target and set(source_files(reg, name)) == {lk.rel for lk in lks}:
        if new_repo:
            reg.set_source(name, "url", url)
        reg.set_spec(name, spec)
        return f"Switch {name} from {text(old_url, old)} to {text(url, spec)}"
    target = target or reg.add_source(url, spec)
    for lk in lks:
        reg.set_file(lk.rel, "source", target)
    rest = len(source_files(reg, name))
    if not rest:
        reg.remove_source(name)
    desc = (f"Move {', '.join(lk.rel for lk in lks)} from {name} ({text(old_url, old)}) "
            f"to {target} ({text(url, spec)})")
    return desc + (f"; {name} keeps {plural(rest, 'other file')}" if rest else "")


def newest_hint(name, tag, line, newest):
    """Hint after pull at newer tags of a pinned source."""
    switch = f"'git filesync source set-tag {name} {{}}' and pull to switch"
    if len(newest) > 1:
        return (f"hint: {name} is pinned to tag {tag}; newer tags: {newest_text(newest)} "
                f"(use {switch.format('TAG')}, 'git filesync source set-branch {name} "
                "BRANCH' to look on one branch only)")
    where = f" on branch {line}" if line else ""
    return (f"hint: {name} is pinned to tag {tag}; the newest tag{where} is "
            f"{newest_text(newest, line)} (use {switch.format(newest[0][0][0])})")


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
    newest = {}
    for link in links:
        st = evaluate(ctx, repo, link)
        if st.error:
            report_error(st)
            rc = EXIT_ERROR
            continue
        if st.newest and not once:
            newest.setdefault(link.name, (link.ref[1], link.line, st.newest))
        if args.all and not st.pending and not once:
            continue
        done += 1
        if args.verbose:
            synced = st.src.short(st.old) if st.has_old else link.blob[:8]
            print(paint(f"{st.rel}: {link_text(st)}, synced at {synced}", "dim"))
        try:
            if once:
                st.target, st.once = target_rev(ctx, link, args), once_text(args)
            before = link.commit
            rc = max(rc, pull_one(repo, reg, st, args))
            moved = moved or once and Link(reg, link.rel).commit != before
        except FsError as e:   # report and carry on with the other files
            error(str(e) if str(e).startswith(st.rel) else f"{st.rel}: {e}")
            rc = EXIT_ERROR
    if moved and not args.dry_run:
        opt = f"--tag {args.tag}" if args.tag else f"-b {args.branch}"
        print(f"hint: the links still follow their own branch or tag, so a plain pull goes "
              f"back; to stay on {once_text(args)}, use 'git filesync set {opt} <file>...'")
    if args.all and not done and rc == EXIT_OK:
        print(paint("everything up to date", "green"))
    for name, (tag, line, new) in sorted(newest.items()):
        print(newest_hint(name, tag, line, new))
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
    for link in links:
        st = evaluate(ctx, repo, link)
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
        try:
            base = local_equiv(repo, st.src, st.old_blob, st.rel, link.path)
            if not base:
                raise FsError(f"synced version {st.old_blob[:12]} unavailable")
            base = repo.content_id(base, st.rel)
            if args.upstream:
                other = repo.store(repo.normalize(st.src.read_content(st.new_blob,
                                                                        st.new_path), st.rel))
            elif args.committed:
                other = repo.content_id(st.head_blob, st.rel)
            elif st.local == "missing":
                other = None
            else:
                other = repo.content_id(repo.worktree_blob(link.target, write=True), st.rel)
        except FsError as e:
            error(f"{st.rel}: {e}")
            rc = EXIT_ERROR
            continue
        name = link.path if args.for_upstream else st.rel
        pairs.append((st, name, base, other))
    return rc, pairs


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
    p = subprocess.run(["git", "diff"] + color + prefixes + args.extra + [left, right],
                       cwd=repo.top)
    if p.returncode > 1:
        rc = EXIT_ERROR
    elif p.returncode == 1 and ("--exit-code" in args.extra or "--quiet" in args.extra):
        rc = max(rc, EXIT_PENDING)      # like `git diff --exit-code`: 1 = differences
    return rc


def difftool_prompting(repo, args):
    """Ask before each file like `git difftool`: by default only when no files
    were given; -y/--no-prompt and difftool.prompt=false turn it off,
    --prompt turns it on."""
    if args.prompt:
        return True
    if args.no_prompt or args.files:
        return False
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
    """(url, spec, name) for add. The name of a [source]: exactly that source,
    whatever its branch or tag (-b/--tag may only repeat it). A URL: an
    existing source only if URL and branch/tag match (name None; found or
    created later) - with --tag but no -b, whatever branch it looks for
    newer tags on."""
    given = source_spec({"tag": args.tag, "branch": args.branch})
    if args.source in reg.sources:            # name of an existing [source]
        s = reg.sources[args.source]
        spec = source_spec(s)
        if not source_ref(s):
            raise FsError(f'[source "{args.source}"] in {REGISTRY} needs a branch or tag')
        if given and (given != spec if "tag" not in given else
                      given["tag"] != spec.get("tag")
                      or given.get("branch", spec.get("branch")) != spec.get("branch")):
            raise FsError(f"source '{args.source}' {spec_desc(spec)}, not {spec_desc(given)} - "
                          "give the URL to link to another branch or tag, or change the "
                          "source with 'git filesync source set-branch / set-tag'")
        return s.get("url", ""), spec, args.source
    if given.get("tag") and is_tag_pattern(given["tag"]) and not given.get("branch"):
        given["branch"] = ctx.default_branch(args.source)    # a pattern needs a branch
    return args.source, given or {"branch": ctx.default_branch(args.source)}, None


def spec_desc(spec):
    """'follows main' / 'is pinned to v1.2' / 'is pinned to v1.2 on main'."""
    if not spec.get("tag"):
        return f"follows {spec['branch']}"
    return f"is pinned to {spec['tag']}" + (f" on {spec['branch']}" if spec.get("branch") else "")


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
    url, spec, named = add_ref(ctx, reg, args)
    ref = source_ref(spec)
    assert ref, "add_ref gives a branch or a tag"
    any_line = "branch" not in spec    # --tag without -b: any branch to look on
    src = ctx.source(url, ref, named or reg.source_name(url, spec, any_line), source_line(spec))
    head = src.resolve()
    if not head:
        raise FsError(ref_missing(ref, src))
    at = src.require(args.commit) if args.commit else None    # --commit: given base
    if not src.tag_names:
        _, problem = src.tag_info(ref[1], source_line(spec), newer=False)
        if problem:
            warn(f"{problem}; newer tags can't be found there")
    path = upstream_path(args.path if args.path else rel)
    patterns = args.include or args.exclude
    upstream_file = bool(path) and not patterns and bool(src.blob_at(head, path))
    if target.is_dir() and upstream_file:       # like cp: into the directory
        target = target / Path(path).name
        rel = repo.rel(target)
    if target.is_dir() or patterns or not upstream_file and src.is_dir(head, path):
        plan, relink = plan_dir(repo, reg, src, args, at or head, rel, path, target)
        if not plan:
            return EXIT_OK
    else:
        relink = rel in reg.files
        if relink and not args.force:
            raise FsError(f"'{rel}' is already linked (use --force to relink)")
        if target.is_dir():
            raise FsError(f"cannot link '{rel}': is a directory")
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
    name = named or reg.source_name(url, spec, any_line)
    shown_ref = ref_text(ref, source_line(reg.sources.get(name) or spec), src.tag_names)
    if args.dry_run:
        for p in plan:
            note = "replacing the existing file" if p.replaced else \
                "fetched" if p.content is not None else \
                "with local modifications" if p.modified else "existing file"
            print(f"would link {p.rel} -> {name}:{p.path} ({shown_ref}), "
                  f"{note}, based on {src.short(p.commit)}")
        return EXIT_OK

    for p in plan:
        if p.rel in reg.files:
            reg.remove_file(p.rel, keep_source=named)
        name = named or reg.add_source(url, spec, any_line)
        link = Link(reg, p.rel)
        for k, v in (("source", name), ("path", p.path), ("commit", p.commit), ("blob", p.blob)):
            link.set(k, v)
        if args.strict:
            link.set("strict", "true")
        if p.content is not None:
            link.target.parent.mkdir(parents=True, exist_ok=True)
            link.target.write_bytes(repo.to_worktree(repo.normalize(p.content, p.rel), p.rel))
        # the link commit contains the file as it is in the working tree
        repo.git(["add", "--", lit(p.rel)])
        print(f"{paint('linked', 'green')} {p.rel} -> {name}:{p.path} ({shown_ref})")
    reg.finish()
    if repo.git(["diff", "--cached", "--quiet", "HEAD", "--"] + [lit(r) for r in rels]
                 + [REGISTRY], check=False).returncode == 0:
        print(f"{rel}: link{'s' if len(rels) > 1 else ''} and "
              f"file{'s' if len(rels) > 1 else ''} unchanged, nothing to commit")
        return EXIT_OK
    # staged only, like git add; the proposed message is prepared for the commit
    msg = build_add_message(plan, src, name, url, ref, path, relink, args.strict, at or head)
    msg_name = rels[0] if len(rels) == 1 else (rel if rel != "." else "root")
    report_staged(repo, msg_name, msg, paint("staged", "green"), rels)
    return EXIT_OK


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
    plan = [Planned(r, p, *find_base(repo, src, at, r, p, repo.top / r, args.overwrite))
            for r, p in todo]
    return plan, any(r in reg.files for r, _ in todo)


def index_entry(repo, rel):
    """(mode, blob) of rel in the index; (mode in HEAD or a plain file's, None)
    if it isn't there."""
    entry = out(repo.git(["ls-files", "-s", "--", lit(rel)], check=False)).split(" ")
    if len(entry) > 1:
        return entry[0], entry[1]
    mode = out(repo.git(["ls-tree", "HEAD", "--", lit(rel)], check=False)).split(" ")[0]
    return mode or "100644", None


def cmd_restore(ctx, repo, args):
    """Like `git restore`, with the synced upstream version (the base the
    entry records) as the source: the working tree files (default), with -S
    their index entries instead, with -S -W both. .git-filesync stays as it is."""
    reg = Registry(repo)
    links = select_links(repo, reg, args.files)
    worktree = args.worktree or not args.staged
    done = "restored and staged" if worktree and args.staged else \
        "restored in the index" if args.staged else "restored"
    rc = EXIT_OK
    for link in links:
        try:
            src = ctx.source(link.url, link.ref, link.name, link.line)
            base = local_equiv(repo, src, link.blob, link.rel, link.path)
            if not base:
                raise FsError(f"{link.rel}: base version {link.blob[:12]} unavailable")
            fix_tree = worktree and repo.worktree_blob(link.target) != base
            mode, staged = index_entry(repo, link.rel) if args.staged else (None, None)
            fix_index = args.staged and staged != base
            if not (fix_tree or fix_index):
                print(f"{link.rel}: nothing to restore")
                continue
            if fix_tree:
                link.target.parent.mkdir(parents=True, exist_ok=True)
                link.target.write_bytes(repo.to_worktree(repo.read_content(base, link.rel),
                                                         link.rel))
            if fix_index:
                repo.git(["update-index", "--add", "--cacheinfo", f"{mode},{base},{link.rel}"])
        except FsError as e:   # report and carry on with the other files
            error(str(e))
            rc = EXIT_ERROR
            continue
        at = src.short(link.commit) if link.commit else link.blob[:8]
        print(f"{link.rel}: {paint(done, 'green')} ({link.name}@{at})")
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
    for link in links:
        if args.dry_run:
            print(f"would remove {link.rel}")
            continue
        repo.git(["rm", "-q", "-f", "--ignore-unmatch", "--", lit(link.rel)])
        if link.target.is_file():       # never added to git
            link.target.unlink()
        reg.remove_file(link.rel)
        print(f"{paint('removed', 'green')} {link.rel}")
    if not args.dry_run:
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
    if args.dry_run:
        print(f"would move {old} -> {new}")
        return EXIT_OK
    if repo.git(["ls-files", "--error-unmatch", "--", lit(old)], check=False).returncode == 0:
        dst.parent.mkdir(parents=True, exist_ok=True)
        repo.git(["mv", "--", old, new])
    elif (repo.top / old).exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
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


def cmd_set(ctx, repo, args):
    """Change the link of linked files - their source, upstream path or strict
    flag - like 'source' does for sources. Only .git-filesync is changed
    (and staged); the synced version (the base) is kept where it still
    applies: for another branch or tag of the same upstream, and for another
    upstream that has it (a fork, a moved repository); with another path it
    is looked up like for add."""
    if not (args.source or args.branch or args.tag or args.path or args.strict is not None):
        raise FsError("nothing to change: give --source, -b/--tag, -p or --strict/--no-strict")
    reg = Registry(repo)
    reg.dry_run = args.dry_run
    links = select_links(repo, reg, args.files)
    if args.path and len(links) != 1:
        raise FsError("-p requires exactly one file")
    would = "would: " if args.dry_run else ""
    changed = False
    given = add_ref(ctx, reg, args) if args.source else None    # (url, spec, named)
    groups = {}
    for lk in links:
        groups.setdefault(lk.name, []).append(lk)
    for name, lks in groups.items():
        source = reg.sources.get(name)
        if not source or not source_ref(source):
            raise FsError(f"{lks[0].rel}: its [source \"{name}\"] in {REGISTRY} needs a url "
                          "and a branch or tag")
        if given:
            url, spec, named = given
        elif args.branch or args.tag:
            url, spec, named = source.get("url", ""), switch_spec(source, args), None
            if is_tag_pattern(spec.get("tag", "")) and not spec.get("branch"):
                spec["branch"] = ctx.default_branch(url)     # a pattern needs a branch
        else:
            continue
        if named == name or not named and norm_url(url) == norm_url(source.get("url", "")) \
                and spec == source_spec(source):
            continue
        ref = source_ref(spec)
        src = ctx.source(url, ref, named or name, source_line(spec))
        if not src.resolve():
            raise FsError(ref_missing(ref, src))
        new_repo = norm_url(url) != norm_url(source.get("url", ""))
        print(would + move_to_source(reg, name, lks, url, spec, named))
        changed = True
        if new_repo and not args.path:
            for lk in lks:      # same synced version, possibly another commit
                commit = commit_in(src, lk)
                if not commit:
                    warn(f"{lk.rel}: synced version {lk.blob[:12]} not found in {src.label}; "
                         "its previous sync point counts as unknown")
                elif commit != lk.commit:
                    lk.set("commit", commit)
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
        if not source_ref(s):
            problems.append(f'[source "{name}"] has neither branch nor tag')
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
    path = repo.top / REGISTRY
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
    """Like `git remote`: list, rename and change the [source]s. Only
    .git-filesync is changed (and staged); `pull` then syncs the files."""
    reg = Registry(repo)
    action = args.action
    if not action:
        for name, s in sorted(reg.sources.items()):
            if not args.verbose:
                print(name)
                continue
            ref, line = source_ref(s), source_line(s)
            n = len(source_files(reg, name))
            newest, shown = "", ref_text(ref, line) if ref else "branch or tag missing"
            if ref and ref[0] == "tag":
                try:
                    src = ctx.source(s.get("url", ""), ref, name, line)
                    if src.tag_names:          # a pattern: what it is at now
                        shown = ref_text(ref, line, src.tag_names)
                    else:
                        tags, _ = src.tag_info(ref[1], line)
                        newest = f", newest {newest_text(tags, line)}" if tags else ""
                except FsError as e:
                    warn(f"{name}: {e}")
            print(f"{name}\t{s.get('url', '')} ({shown}{newest}, {plural(n, 'file')})")
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
        url, old = s.get("url", ""), source_spec(s)
        spec = dict(old)
        if action == "set-url":
            url = args.value
        elif action == "set-branch" and bool(args.unset) == bool(args.value):
            raise FsError("give either BRANCH or --unset")
        elif action == "set-branch" and args.value:
            spec["branch"] = args.value
        elif action == "set-branch":
            if not spec.get("tag"):
                raise FsError(f"source '{args.name}' is not pinned to a tag; it needs its branch")
            if is_tag_pattern(spec["tag"]):
                raise FsError(f"source '{args.name}' follows the tag pattern '{spec['tag']}', "
                              "which needs its branch")
            spec.pop("branch", None)
        elif bool(args.unset) == bool(args.value):
            raise FsError("give either TAG or --unset")
        elif args.value:
            spec["tag"] = args.value
            if is_tag_pattern(args.value) and not spec.get("branch"):
                spec["branch"] = ctx.default_branch(url)     # a pattern needs a branch
        elif not spec.get("branch"):
            raise FsError(f"source '{args.name}' has no branch to follow; set one first with "
                          f"'git filesync source set-branch {args.name} BRANCH'")
        else:
            spec.pop("tag", None)
        other = reg.find_source(url, spec, exclude=args.name) if source_ref(spec) else None
        if other:
            raise FsError(f"source '{other}' already has this URL and {spec_text(spec)} - "
                          f"move the files to it with 'git filesync set FILE... --source {other}'")
        if action == "set-url":
            reg.set_source(args.name, "url", url)
            done = f"{args.name}: url {url}"
        else:
            reg.set_spec(args.name, spec)
            done = f"{args.name}: {spec_text(spec)}" + \
                (f" (was {spec_text(old)})" if source_ref(old) and old != spec else "")
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
            if args.older_than is not None:
                max_age = args.older_than
            if args.max_size is not None:
                max_size = parse_size(args.max_size)
            if max_age is None and max_size is None:
                print("no limits set (filesync.cacheMaxAge, filesync.cacheMaxSize) - nothing to do")
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


def hook_dir(repo, action):
    hp = out(repo.git(["config", "core.hooksPath"], check=False))
    if hp:
        hookdir = Path(os.path.expanduser(hp))
        if not hookdir.is_absolute():
            hookdir = repo.top / hookdir
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
    return REFS_VAR in s or s.startswith((f"# {HOOK_MARKER}:", "git filesync hook ",
                                          "git filesync status --hook"))  # the latter: before 0.7


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
                      "(or run 'git filesync install-hooks --force' to add them)")
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


def command_list(sub):
    """--help: the commands with their summaries, basic ones first (the
    rest in the order they were defined, `hook` last)."""
    width = max(shutil.get_terminal_size().columns - 2, 40)
    helps = {a.dest: a.help for a in sub._choices_actions}

    def group(title, names):
        lines = [f"{title}:"]
        for n in names:
            lines += textwrap.wrap(helps[n], width, initial_indent=f"  {n:<18}",
                                   subsequent_indent=" " * 20)
        return "\n".join(lines)
    advanced = [n for n in helps if n not in BASIC_COMMANDS]
    return group("basic commands", BASIC_COMMANDS) + "\n\n" + group("advanced commands", advanced)


def main(argv=None):
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
    common.add_argument("--remote", action="store_true",
                        help="ignore local checkout mappings, use the remote URL")

    ap = argparse.ArgumentParser(prog="git filesync",
                                 description="Keep single files in sync between Git repositories.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"git-filesync {__version__}")
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")

    p = add_command(sub, "status", parents=[common], help="show sync state of linked files")
    p.add_argument("paths", nargs="*", help="files or directories (default: all)")
    p.add_argument("-s", "--short", action="store_true",
                   help="short format: upstream / committed / working tree columns")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also list all linked files with their sources")
    p.add_argument("--exit-code", action="store_true",
                   help="exit with 1 if something is to sync or a strict file is modified")

    p = add_command(sub, "pull", parents=[common], help="sync file(s) from upstream")
    p.add_argument("files", nargs="*", help="files or directories")
    p.add_argument("--all", action="store_true", help="sync all files with something to sync")
    p.add_argument("--commit", metavar="REV", help="sync to this upstream revision (exactly one file)")
    p.add_argument("-b", "--branch", help="sync to the head of this upstream branch, once (the "
                                          "files keep following their own branch or tag)")
    p.add_argument("--tag", help="sync to this upstream tag, once (as -b)")
    p.add_argument("--no-edit", action="store_true", help="commit without opening the editor")
    p.add_argument("--no-commit", action="store_true",
                   help="only stage; a plain 'git commit' offers the proposed message")
    p.add_argument("--overwrite", action="store_true",
                   help="discard local adaptations instead of merging them")
    p.add_argument("--autostash", action="store_true",
                   help="set uncommitted changes aside and re-apply them after the sync")
    p.add_argument("--dry-run", action="store_true",
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
        p.add_argument("files", nargs="*", help="files or directories (default: all)")
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
            p.add_argument("-y", "--no-prompt", action="store_true",
                           help="don't ask before launching the tool for each file")
            p.add_argument("--prompt", action="store_true",
                           help="ask before each file even if files are given")

    p = add_command(sub, "add", parents=[common], help="link a file (or all files of a directory) "
                                                     "to the upstream repository")
    p.add_argument("file", metavar="FILE|DIR",
                   help="file in this repository (fetched from upstream if missing), or a "
                        "directory: all files below the upstream directory are linked")
    p.add_argument("source", metavar="URL|SOURCE", help="upstream URL or name of a [source] in "
                   + REGISTRY)
    p.add_argument("-b", "--branch", help="upstream branch (default: remote HEAD, or the ref of "
                                          "SOURCE); with --tag: the branch to look for newer "
                                          "tags on")
    p.add_argument("--tag", help="pin to this upstream tag instead of following a branch; a "
                                 "pattern (* ? [...]): the newest matching tag on the branch")
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
                                                     "upstream path, strict")
    p.add_argument("files", nargs="+", metavar="PATH", help="linked files or directories")
    p.add_argument("--source", metavar="URL|SOURCE",
                   help="link to another upstream (URL) or [source]; the synced version is kept")
    p.add_argument("-b", "--branch", help="upstream branch (as for add); without --source: "
                                          "switch to following it, without syncing")
    p.add_argument("--tag", help="pin to this upstream tag (as for add); without --source: "
                                 "switch to it, without syncing")
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

    p = add_command(sub, "restore", parents=[common],
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
    p.add_argument("files", nargs="+", help="files or directories")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be unlinked")

    p = add_command(sub, "mv", parents=[colorp], help="move a linked file, keeping its link")
    p.add_argument("src", metavar="OLD", help="linked file")
    p.add_argument("dst", metavar="NEW", help="new path or existing directory")
    p.add_argument("-n", "--dry-run", action="store_true", help="only show what would be moved")

    p = add_command(sub, "source", parents=[common], help="list or change the [source]s "
                                                        "(like 'git remote')")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list with URL, branch or tag (and newest tag), and file count")
    actions = p.add_subparsers(dest="action", metavar="ACTION")
    for name, arg, hlp in (("rename", "NEW", "rename a source and all references to it"),
                           ("set-url", "URL", "change the URL of a source"),
                           ("set-branch", "BRANCH", "follow BRANCH; for a source pinned to a "
                                                    "tag: look for newer tags on BRANCH only "
                                                    "(--unset: on all branches)"),
                           ("set-tag", "TAG", "pin to TAG (a branch stays the one to look "
                                              "for newer tags on; a pattern: the newest "
                                              "matching tag on it); --unset: follow the "
                                              "branch again")):
        a = add_command(actions, name, parents=[colorp], help=hlp)
        a.add_argument("name", metavar="NAME" if name != "rename" else "OLD",
                       help="key of the [source]")
        if name in ("set-tag", "set-branch"):
            a.add_argument("value", metavar=arg, nargs="?")
            a.add_argument("--unset", action="store_true",
                           help="remove the tag: follow the source's branch again"
                           if name == "set-tag" else "remove the branch of a pinned source: "
                           "look for newer tags on all branches")
        else:
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

    p = add_command(sub, "install-hooks", parents=[colorp],
                    help="install the pre-push/post-merge hooks")
    p.add_argument("--force", action="store_true",
                   help="add our lines to existing hooks (right after the #! line)")
    add_command(sub, "uninstall-hooks", parents=[colorp], help="remove the hooks again",
                description="Remove the pre-push/post-merge hooks of git-filesync.")
    p = add_command(sub, "hook", parents=[colorp], help="what the installed hooks run",
                    description="Run the checks of an installed hook (called by the hooks).")
    p.add_argument("name", choices=list(HOOKS))
    p.add_argument("hook_args", nargs=argparse.REMAINDER, help="the hook's arguments")

    ap.epilog = command_list(sub) + (
        "\n\nWithout a command: status. 'git filesync <command> -h' describes a command\n"
        "and lists its options.")
    # the grouped list instead of argparse's; hiding that hides <command> in the usage too
    sub.help = argparse.SUPPRESS
    ap.usage = "git filesync [-h] [--version] <command> ..."

    argv = list(sys.argv[1:] if argv is None else argv)
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
        if args.cmd == "install-hooks":
            return cmd_install_hooks(repo, args)
        if args.cmd == "uninstall-hooks":
            return cmd_uninstall_hooks(repo, args)
        if args.cmd == "hook":
            args.no_fetch = args.name == "post-merge"    # pre-push: online anyway
        ctx = Context(args, repo)
        reading = args.cmd in ("status", "diff", "difftool", "hook") or \
            args.cmd == "source" and not args.action
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
    except BrokenPipeError:
        # output piped into e.g. `head`, which exited early
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
