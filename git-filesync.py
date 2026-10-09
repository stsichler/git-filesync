#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT-0
# Copyright (c) 2026 Stefan Sichler - https://github.com/stsichler/git-filesync
# Developed together with Claude (Anthropic).
"""
git-filesync - keep individual files in sync between Git repositories.

The "slave" repository lists its synced files in .git-filesync at its root
(git-config format, like .gitmodules), each linked to a file in a "master"
repository:

    [source "lib"]
        url = https://github.com/owner/lib.git
        branch = main
    [file "src/foo.c"]
        source = lib
        path = lib/foo.c       ; path in the master
        strict = true          ; optional: no local modifications allowed
        commit = <master commit of the last sync>
        blob = <blob id of the master's file at that commit>

A link records the master version the file is based on (commit/blob);
local adaptations on top of it are allowed and kept by a 3-way merge on
pull, unless the file is marked strict.

Commands (run inside the slave repository; without a command: status).
PATH may be a file or a directory (= all linked files below it); options
follow the command.

    status [PATH...]            state of the linked files like `git status`:
                                upstream changes to sync, committed
                                adaptations, uncommitted changes
        -s, --short             short format: upstream/committed/worktree
                                columns
        -v, --verbose           also list all linked files with their sources
        --exit-code             exit 1 if something is to sync or a strict
                                file is modified
        --hook                  terse output on stderr (for git hooks)

    pull PATH... | --all        sync to the master's version of the file and
                                commit with a message listing the master
                                commits since the last sync; adaptations are
                                merged, uncommitted changes refused
        --all                   all files with something to sync
        --commit REV            sync to this master revision (one file;
                                also backwards)
        --overwrite             discard local adaptations instead of merging
        --autostash             set uncommitted changes aside, re-apply after
        --no-edit               commit without opening the editor
        --no-commit             only stage; print the commit command

    diff [PATH...] [-- OPTS]    local changes vs. the synced master version
                                (one `git diff`, OPTS passed to it)
        --committed             only committed adaptations (synced -> HEAD)
        --upstream              what pull would bring (synced -> master)
        --master-paths          master paths, for `git apply -3` in the master

    difftool [PATH...] [-- OPTS]  the same in the configured difftool
        --committed, --upstream as for diff
        -y, --no-prompt         don't ask before each file (default: ask if
                                no files are given)
        --prompt                ask even for explicitly given files

    add FILE URL|SOURCE         link FILE to a file in a master repository
                                (URL or name of a [source]); an existing FILE's
                                master version is detected, a missing FILE
                                is fetched; changes are staged
        -b, --branch BRANCH     master branch (default: master's default
                                branch or that of SOURCE)
        -p, --path PATH         path in the master (default: same as FILE)
        --commit REV            master revision FILE corresponds to
        --strict                FILE must stay an exact copy
        --force                 relink an already linked file

    unlink PATH...              remove links (the files are kept)
    mv OLD NEW                  move a linked file (git mv), keeping its link

    map [URL [DIR]]             use the local checkout DIR instead of fetching
                                URL; its branch is used, unpushed commits
                                included; without DIR: list mappings
        --global                global git config (default: this repository)
        --unset                 remove the mapping for URL

    install-hooks               install pre-push/post-merge reminder hooks
    uninstall-hooks             remove them again

    Common options:
        --no-fetch              use the cached state, don't fetch (status,
                                pull, diff, difftool, add)
        --remote                ignore local checkout mappings (same commands)
        --color[=WHEN], --no-color  always, never or auto (default)

Exit codes: 0 ok, 1 unfinished (conflicts, not committed, --exit-code),
2 error.

Files stored in Git LFS (in the master, the slave, both or neither) are
handled transparently, as are differing line-ending conventions. Output is
colored like git's (color.filesync / color.ui, --color, NO_COLOR).

Requires Python >= 3.7 and Git >= 2.26 (git-lfs for LFS files).
Works on Linux, macOS and Windows.
Manual: https://github.com/stsichler/git-filesync/blob/main/MANUAL.md
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

__version__ = "0.1.0"
REGISTRY = ".git-filesync"
EXIT_OK, EXIT_PENDING, EXIT_ERROR = 0, 1, 2
HOOK_MARKER = "git-filesync"
HOOKS = {
    "pre-push": "git filesync status --hook",
    "post-merge": "git filesync status --hook --no-fetch",
}
REGISTRY_HEADER = ("# git-filesync: files of this repository that are kept in sync with\n"
                   "# files in other repositories. Maintained by 'git filesync'; [file]\n"
                   "# commit/blob record the master version each file is based on.\n")


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

    Hooks may run with GIT_DIR & co. set for the slave repository; commands
    that operate on a master repository must not inherit them.
    """
    global _clean_env
    if _clean_env is None:
        p = subprocess.run(["git", "rev-parse", "--local-env-vars"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        names = set(p.stdout.decode().split()) if p.returncode == 0 else set()
        names |= {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                  "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"}
        _clean_env = {k: v for k, v in os.environ.items() if k not in names}
    return _clean_env


def git(args, cwd=None, data=None, check=True, env=None):
    p = subprocess.run(["git"] + [str(a) for a in args], cwd=cwd, input=data,
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise FsError(f"git {args[0]} failed: {err}")
    return p


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
# master side
# --------------------------------------------------------------------------

class Source:
    """A Git repository providing the master versions of synced files."""

    def __init__(self, repo, ref, label, local=False, note=None):
        self.repo, self.ref, self.label = Path(repo), ref, label
        self.local = local   # mapped local checkout: ref is its local branch
        self.note = note     # remark about the ref choice, shown by status

    def git(self, args, **kw):
        kw.setdefault("env", clean_env())
        return git(["-C", self.repo] + list(args), **kw)

    def head_ref(self):
        """Full ref name checked out in a local checkout, None if detached."""
        p = self.git(["symbolic-ref", "-q", "HEAD"], check=False)
        return out(p) if p.returncode == 0 else None

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
        if not out(self.git(["for-each-ref", "--count=1", "refs/remotes/"])):
            return True
        return bool(out(self.git(["for-each-ref", "--count=1", "--contains", commit,
                                  "refs/remotes/"])))

    def has_uncommitted(self, path):
        return self.git(["diff", "--quiet", "HEAD", "--", lit(path)],
                        check=False).returncode == 1

    def resolve(self, rev=None):
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

    def blob_at(self, commit, path):
        """Blob id of the file at path, None if there is none (or a directory).
        ls-tree needs no blobs, so nothing is fetched in the blobless cache."""
        p = self.git(["ls-tree", "-z", "--full-tree", commit, "--", lit(path)], check=False)
        for entry in p.stdout.decode("utf-8", "replace").split("\0"):
            info, _, name = entry.partition("\t")
            if name == path and info.split(" ")[1:2] == ["blob"]:
                return info.split(" ")[2]
        return None

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
        return self.git(["merge-base", "--is-ancestor", a, b],
                        check=False).returncode == 0

    def last_change(self, rev, path):
        """Newest commit up to rev that changed path: the commit the file's
        version at rev comes from (same blob, by git's history simplification).
        Recorded as a link's commit, so one file version always gives the same
        entry, whatever else happened on the branch."""
        return out(self.git(["rev-list", "-1", rev, "--", lit(path)])) or rev

    def count(self, old, new, path):
        return int(out(self.git(["rev-list", "--count", f"{old}..{new}", "--", lit(path)])))

    def log(self, rng, path):
        return out(self.git(["log", "--reverse", "--format=- %s (%h)", rng, "--", lit(path)]))

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
    """Creates and caches Sources; fetches each master repository at most once."""

    def __init__(self, args, slave=None):
        self.slave_top = slave.top if slave else None
        self.fetch = not getattr(args, "no_fetch", False)
        self.force_remote = getattr(args, "remote", False)
        self._sources = {}
        self._ready = set()
        self._mappings = None

    def source(self, url, branch):
        key = (norm_url(url), branch)
        if key not in self._sources:
            self._sources[key] = self._make(url, branch)
        return self._sources[key]

    def local_path(self, url):
        """Mapped local checkout for url (validated), or None."""
        if self.force_remote:
            return None
        if self._mappings is None:
            # repo-local mapping overrides a global one (later entries win)
            self._mappings = {norm_url(u): d for _, _, u, d in
                              local_mappings(cwd=self.slave_top)}
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
        """Default branch of the master: from a mapped checkout or the cache
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
            p = git(["ls-remote", "--symref", "--", url, "HEAD"], env=clean_env(), check=False)
            m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out(p), re.M)
            if m:
                return m.group(1)
        d = self.cache_dir(url)
        if d.exists():   # HEAD of the bare clone names the remote's default branch
            p = git(["-C", d, "symbolic-ref", "--short", "HEAD"], env=clean_env(), check=False)
            if p.returncode == 0:
                return out(p)
        raise FsError(f"cannot determine default branch of {url}; use --branch")

    def _make(self, url, branch):
        local = self.local_path(url)
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
                      repo_label(url))

    @staticmethod
    def cache_dir(url):
        return cache_root() / (hashlib.sha1(norm_url(url).encode()).hexdigest()[:16] + ".git")

    def _cache(self, url):
        d = self.cache_dir(url)
        if d in self._ready:
            return d
        env = clean_env()
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(f"{d.name}.tmp{os.getpid()}")
            print(paint(f"Cloning {url} (blobless) ...", "dim", "err"), file=sys.stderr)
            try:
                git(["clone", "--bare", "--quiet", "--filter=blob:none", "--", url, tmp], env=env)
                git(["-C", tmp, "config", "remote.origin.fetch",
                     "+refs/heads/*:refs/remotes/origin/*"], env=env)
                git(["-C", tmp, "fetch", "--quiet", "origin"], env=env)
                self._drop_heads(tmp)
                tmp.rename(d)
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
        elif self.fetch:
            p = git(["-C", d, "fetch", "--quiet", "--prune", "origin"], env=env, check=False)
            if p.returncode:
                warn(f"fetching {url} failed, using cached state")
            self._drop_heads(d)
        self._ready.add(d)
        return d

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
# slave side
# --------------------------------------------------------------------------

class Slave:
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

    def git(self, args, **kw):
        return git(args, cwd=self.top, **kw)

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
    """The slave's .git-filesync: [source] and [file] sections."""

    def __init__(self, slave):
        self.slave = slave
        self.path = slave.top / REGISTRY
        self.sources, self.files = {}, {}
        if self.path.exists():
            p = git(["config", "-f", self.path, "--list", "-z"], check=False)
            if p.returncode:
                raise FsError(f"{REGISTRY}: cannot parse: "
                              + p.stderr.decode("utf-8", "replace").strip())
            self.sources, self.files = parse_registry(p.stdout)

    def links(self):
        return [Link(self, rel) for rel in sorted(self.files)]

    def _cfg(self, *args):
        if not self.path.exists():
            self.path.write_bytes(REGISTRY_HEADER.encode())
        git(["config", "-f", self.path] + list(args))

    def set_file(self, rel, name, value):
        self._cfg(f"file.{rel}.{name}", value)
        self.files.setdefault(rel, {})[name] = value

    def find_source(self, url, branch):
        for name, s in self.sources.items():
            if norm_url(s.get("url", "")) == norm_url(url) and s.get("branch") == branch:
                return name
        return None

    def add_source(self, url, branch):
        """Name of the [source] for url+branch, created if necessary."""
        name = self.find_source(url, branch)
        if name:
            return name
        base = repo_label(url).split("/")[-1] or "master"
        name = base if base not in self.sources else f"{base}-{branch}"
        n = 2
        while name in self.sources:
            name, n = f"{base}-{branch}-{n}", n + 1
        self._cfg(f"source.{name}.url", url)
        self._cfg(f"source.{name}.branch", branch)
        self.sources[name] = {"url": url, "branch": branch}
        return name

    def remove_file(self, rel):
        src = self.files.pop(rel, {}).get("source")
        self._cfg("--remove-section", f"file.{rel}")
        if src and src in self.sources and \
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
                self.slave.fix_eol(self.path)
        self.slave.git(["add", "-A", "--", REGISTRY])

    def uncommitted(self):
        """[file] entries that differ from the committed .git-filesync."""
        p = self.slave.git(["config", "--blob", f"HEAD:{REGISTRY}", "--list", "-z"], check=False)
        head = parse_registry(p.stdout)[1] if p.returncode == 0 else {}
        return {rel for rel in set(head) | set(self.files)
                if head.get(rel) != self.files.get(rel)}


class Link:
    """One [file] entry: a slave file linked to a file in a master repository."""

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
        return self.reg.slave.top / self.rel

    @property
    def source(self):
        return self.reg.sources.get(self.v.get("source", ""), {})

    url = property(lambda self: self.source.get("url", ""))
    branch = property(lambda self: self.source.get("branch", ""))
    path = property(lambda self: self.v.get("path", ""))
    commit = property(lambda self: self.v.get("commit", ""))
    blob = property(lambda self: self.v.get("blob", ""))

    @property
    def strict(self):
        """The file must stay an exact copy of the master version."""
        return self.v.get("strict", "").lower() in ("true", "yes", "on", "1")

    def set(self, name, value):
        self.reg.set_file(self.rel, name, value)


def select_links(slave, reg, paths):
    """Links for the given files/directories (all links if none given)."""
    if not paths:
        return reg.links()
    result = []
    for s in paths:
        rel = slave.rel(slave.user_path(s))
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

def local_equiv(slave, src, blob, rel, path):
    """Master blob as this repo would store it; None if unavailable."""
    if not blob:
        return None
    try:
        return slave.as_local(src.read_content(blob, path), rel)
    except FsError:
        return None


class BaseUnavailable(FsError):
    pass


def matches_base(slave, src, link, oid, read):
    """Does a slave blob (id oid; read() returns its raw bytes) equal the
    synced master version, i.e. the base recorded in .git-filesync?
    Raises BaseUnavailable if that version can't be read."""
    if oid == link.blob:
        return True
    if not link.blob:
        return False
    try:
        ptr = lfs_pointer(src.read_blob(link.blob))
        if ptr:   # master stores it in LFS: compare against the pointer's hash first
            data = read()
            if (hashlib.sha256(data).hexdigest(), len(data)) == ptr or lfs_pointer(data) == ptr:
                return True
        return oid == slave.as_local(src.read_content(link.blob, link.path), link.rel)
    except BaseUnavailable:
        raise
    except FsError as e:
        raise BaseUnavailable(f"synced version {link.blob[:12]} not available in "
                              f"{src.label}, file counts as modified ({e})")


def evaluate(ctx, slave, link):
    """State of a linked file in three independent respects:
    upstream  - synced master version vs. current master (changed/behind/...)
    committed - committed slave version vs. synced master version
                ('unmodified' | 'adapted' | None if not committed)
    worktree  - working file vs. committed version
                ('clean' | 'modified' | 'deleted' | 'added' | 'missing')
    local     - working file vs. synced master version ('clean' | 'modified'
                | 'missing'); what a pull has to merge"""
    st = SimpleNamespace(link=link, rel=link.rel, error=None, warnings=[],
                         src=None, old=link.commit, old_blob=link.blob, new=None, new_blob=None,
                         count=0, behind=0, has_old=False, diverged=False, local="clean",
                         committed=None, worktree="clean", head_blob=None,
                         changed=False, pending=False, strict=link.strict, violation=False)
    url, branch, path = link.url, link.branch, link.path
    problem = path_problem(link.rel)
    if problem:
        st.error = (f"{problem} - entry ignored; remove it with "
                    f"'git config -f {REGISTRY} --remove-section \"file.{link.rel}\"'")
        return st
    if not (url and branch and path):
        st.error = f"incomplete entry in {REGISTRY} (needs source with url and branch, and path)"
        return st
    try:
        src = st.src = ctx.source(url, branch)
    except FsError as e:
        st.error = str(e)
        return st

    def base_matches(oid, read):
        try:
            return matches_base(slave, src, link, oid, read)
        except BaseUnavailable as e:
            if str(e) not in st.warnings:
                st.warnings.append(str(e))
            return False
    try:
        cur = slave.worktree_blob(link.target)
        p = slave.git(["rev-parse", "--verify", "-q", f"HEAD:{link.rel}"], check=False)
        head = st.head_blob = out(p) if p.returncode == 0 else None
        if head:
            st.committed = "unmodified" if base_matches(
                head, lambda: slave.read_blob(head)) else "adapted"
        if cur is None:
            st.worktree = "deleted" if head else "missing"
        elif not head:
            st.worktree = "added"
        elif slave.git(["diff", "--quiet", "HEAD", "--", lit(link.rel)],
                       check=False).returncode == 1:
            st.worktree = "modified"
        if cur is None:
            st.local = "missing"
        elif st.worktree == "clean":
            st.local = "clean" if st.committed == "unmodified" else "modified"
        elif base_matches(cur, link.target.read_bytes):
            st.local = "clean"
        else:
            st.local = "modified"
    except FsError as e:
        st.error = str(e)
        return st
    st.violation = st.strict and (st.committed == "adapted" or st.local == "modified")
    where = f"branch '{branch}'"
    tip = src.resolve()
    if not tip:
        st.error = f"{where} not found in {src.label}"
        return st
    st.new_blob = src.blob_at(tip, path)
    if not st.new_blob:
        st.error = (f"'{path}' does not exist in {where} of {src.label} "
                    f"(renamed upstream? fix the path in {REGISTRY})")
        return st
    st.new = src.last_change(tip, path)    # not the tip: what a pull records
    st.has_old = bool(st.old) and src.resolve(st.old) == st.old
    if st.has_old:
        if st.new != st.old and src.is_ancestor(st.new, st.old):
            st.behind = src.count(st.new, st.old, path)   # branch older than last sync
        else:
            st.count = src.count(st.old, st.new, path)
            st.diverged = not src.is_ancestor(st.old, st.new)
    else:
        st.warnings.append(f"last synced commit {st.old[:12] or '-'} not found in "
                           f"{src.label} (unpushed?)")
    st.changed = st.new_blob != st.old_blob
    # a file deleted in the working tree is an uncommitted change, not a sync
    st.pending = st.changed or st.worktree == "missing"
    if src.local:
        if src.note:
            st.warnings.append(src.note)
        if not src.is_published(st.new):   # other unpushed commits don't matter
            st.warnings.append(f"'{path}' in {src.label} comes from commit "
                               f"{src.short(st.new)}, which is not pushed")
        if src.head_ref() != src.ref:
            if src.blob_at("HEAD", path) != st.new_blob:
                st.warnings.append(f"{src.label} has {src.head_desc()} checked out; "
                                   f"'{path}' there differs from branch '{branch}', "
                                   "which is what gets synced")
        elif src.has_uncommitted(path):
            st.warnings.append(f"uncommitted changes to '{path}' in {src.label} "
                               "are not synced (commit them first)")
    return st


def upstream_state(st):
    """(label, note) of a pending upstream change, None if there is none."""
    def commits(n):
        return f"{n} commit{'' if n == 1 else 's'}"
    if st.changed:
        if st.behind:
            return "older", f"master branch is {commits(st.behind)} older than last sync"
        if st.has_old and not st.diverged:
            return "pending", commits(st.count)
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


def render(parts, stream="out"):
    return ", ".join(paint(t, s, stream) for t, s in parts)


def short_code(st):
    """Three columns like `git status -s`: upstream, committed, working tree."""
    if st.error:
        return "E  "
    up = upstream_state(st)
    x = {"pending": "P", "older": "O", "changed": "D", "new": "N"}[up[0]] if up else " "
    y = "A" if st.committed == "adapted" else " "
    z = {"modified": "M", "deleted": "D", "added": "?"}.get(st.worktree, " ")
    return x + y + z


def shown(slave, rel):
    """Path relative to the current directory, like git status shows it."""
    return Path(os.path.relpath(slave.top / rel, slave.base)).as_posix()


def print_short(slave, sts):
    for st in sts:
        code = short_code(st)
        if code.strip() or st.violation:
            line = paint(code[0], "yellow") + paint(code[1], "cyan") + paint(code[2], "red")
            if code[0] == "E":
                line = paint(code, "boldred")
            print(f"{line} {shown(slave, st.rel)}" + (paint("  (strict!)", "boldred") if st.violation else ""))


def print_long(slave, sts, verbose):
    """Sections like `git status`."""
    hints = out(slave.git(["config", "--type=bool", "advice.statusHints"], check=False)) != "false"

    def section(title, hint_lines, rows, style):
        if not rows:
            return
        print(title)
        if hints:
            for h in hint_lines:
                print(f"  ({h})")
        for label, rel, note, nstyle in rows:
            line = paint(f"{label + ':':<12}{shown(slave, rel)}", style)
            print(f"\t{line}" + (f"  {paint('(' + note + ')', nstyle)}" if note else ""))
        print()

    ok = [st for st in sts if not st.error]
    if verbose:
        rows = []
        for st in ok:
            via = f" via {st.src.label}" if st.src and st.src.local else ""
            strict = ", strict" if st.strict else ""
            rows.append((st.committed or "uncommitted", st.rel,
                         f"from {repo_label(st.link.url)}:{st.link.path} "
                         f"({st.link.branch}{strict}){via}", "dim"))
        section("Linked files:", [], rows, None)

    up_rows = []
    for st in ok:
        up = upstream_state(st)
        if up:
            up_rows.append((up[0], st.rel, up[1], "dim"))
    section("Upstream changes to sync:", ['use "git filesync pull <file>..." to sync'],
            up_rows, "yellow")

    strict_note = ("NOT ALLOWED: strict", "boldred")
    adapted = [st for st in ok if st.committed == "adapted"]
    section("Locally adapted files:",
            ['use "git filesync diff --committed <file>..." to see the adaptations']
            + (['use "git filesync pull --overwrite <file>..." to discard them']
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
            print(f"\t{paint('warning:', 'yellow')} {shown(slave, rel)}: {w}")
        print()

    if not up_rows and len(ok) == len(sts):
        n = len(sts)
        files = f"{n} linked file{'s' if n != 1 else ''}"
        print("nothing to sync" + ("" if adapted or dirty else
                                   f", {'all ' if n > 1 else ''}{files} unmodified"))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(ctx, slave, args):
    """Like `git status`: exit code 0 unless --exit-code (1 = something to
    sync or a strict violation) or an error (2)."""
    reg = Registry(slave)
    links = select_links(slave, reg, args.paths)
    if not links:
        if not (args.hook or args.short):
            print(f"no linked files ({REGISTRY} not found or empty)")
        return EXIT_OK
    sts = [evaluate(ctx, slave, link) for link in links]
    attention = [st for st in sts if st.error or st.pending or st.violation]
    rc = EXIT_ERROR if any(st.error for st in sts) else \
        EXIT_PENDING if args.exit_code and attention else EXIT_OK
    if args.hook:
        for st in attention:
            print(f"filesync: {paint(st.rel, 'yellow', 'err')}: {render(describe(st), 'err')}",
                  file=sys.stderr)
        if any(st.pending for st in attention):
            print("filesync: run 'git filesync pull <file>' to sync", file=sys.stderr)
        if any(st.violation for st in attention):
            print("filesync: see 'git filesync status' and 'git filesync diff <file>' "
                  "for strict violations", file=sys.stderr)
        return rc
    for st in sts:
        if st.error:
            error(f"{st.rel}: {st.error}")
    if args.short:
        print_short(slave, sts)
    else:
        print_long(slave, sts, args.verbose)
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


def build_message(st, src, new, new_blob, merged, conflicts, discarded=False):
    link = st.link
    url, branch, path = link.url, link.branch, link.path
    # content goes back to the synced master version -> restore, not a sync
    verb = "Restore" if new_blob == st.old_blob and discarded else "Sync"
    lines = [f"{verb} {st.rel} from {repo_label(url)}@{src.short(new)}", "",
             f"Upstream: {url} ({branch}:{path})"]
    if new == st.old:
        pass
    elif st.has_old:
        old = st.old
        if src.is_ancestor(new, old) and new != old:
            log = src.log(f"{new}..{old}", path)
            if log:
                lines += ["", f"Reverts upstream changes after {src.short(new)}:", log]
        else:
            if not src.is_ancestor(old, new):
                lines += ["", f"Note: {src.short(new)} is not a descendant of the "
                          f"previous sync point {src.short(old)}."]
            log = src.log(f"{old}..{new}", path)
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


def pull_one(slave, reg, st, args):
    link, src = st.link, st.src
    path = link.path
    new, new_blob = st.new, st.new_blob
    if args.commit:
        new = src.resolve(args.commit)
        if not new:
            raise FsError(f"unknown revision '{args.commit}' in {src.label}")
        new_blob = src.blob_at(new, path)
        if not new_blob:
            raise FsError(f"'{path}' does not exist at {args.commit}")
        new = src.last_change(new, path)
    # like `git pull`: uncommitted changes are never merged into a sync
    # commit; --autostash sets them aside and re-applies them afterwards
    dirty = st.worktree in ("modified", "deleted", "added")
    stash = None
    if dirty and args.autostash:
        if st.worktree != "modified":
            raise FsError(f"{st.rel}: --autostash can't set aside a {st.worktree} file")
        stash = slave.read_content(slave.worktree_blob(link.target, write=True), st.rel)
    local_mod = st.committed == "adapted" if stash is not None else st.local == "modified"
    discard = args.overwrite and local_mod
    if st.strict and local_mod and not discard:
        raise FsError(f"{st.rel}: {violation_text(st)} - inspect with "
                      f"'git filesync diff {st.rel}'; discard adaptations with "
                      f"'git filesync pull --overwrite {st.rel}', uncommitted changes with "
                      f"'git restore {cmd_arg(st.rel)}'; or allow them with "
                      f"'git config -f {REGISTRY} file.{st.rel}.strict false'")
    if new_blob == st.old_blob and st.worktree != "missing" and not discard:
        print(f"{st.rel}: {paint('up to date', 'green')}"
              + (" (adaptations kept)" if st.committed == "adapted" else ""))
        return EXIT_OK
    if dirty and stash is None:
        raise FsError(f"your local changes to '{st.rel}' would be overwritten by pull - "
                      "commit or stash them first, or use --autostash "
                      f"('git restore {cmd_arg(st.rel)}' discards them)")
    if not args.no_commit:
        # one commit = this file + its entry; other uncommitted entries would
        # end up in it without their files
        others = reg.uncommitted() - {st.rel}
        if others:
            raise FsError(f"{REGISTRY} has uncommitted changes for {', '.join(sorted(others))}"
                          " - commit them first, or use --no-commit to stage everything "
                          "and commit together")
    for w in st.warnings:
        warn(f"{st.rel}: {w}")

    theirs = src.read_content(new_blob, path)
    merged, conflicts = False, 0
    if local_mod and not discard:
        # merge all three versions in this repo's normalized form, so that
        # differing eol conventions (and LFS) of master and slave don't matter
        base = local_equiv(slave, src, st.old_blob, st.rel, path)
        if not base:
            raise FsError(f"{st.rel}: base version {st.old_blob[:12]} unavailable; "
                          "cannot merge local modifications")
        base = slave.read_content(base, st.rel)
        theirs = slave.read_content(slave.as_local(theirs, st.rel), st.rel)
        ours = slave.read_content(st.head_blob if stash is not None else
                                  slave.worktree_blob(link.target, write=True), st.rel)
        old_label = src.short(st.old) if st.has_old else st.old_blob[:8]
        conflicts, content = merge3(ours, base, theirs,
                                    [f"{st.rel} (local)", f"upstream {old_label}",
                                     f"upstream {src.short(new)}"])
        merged = True
    else:
        content = slave.read_content(slave.as_local(theirs, st.rel), st.rel)

    link.target.parent.mkdir(parents=True, exist_ok=True)
    link.target.write_bytes(slave.to_worktree(content, st.rel))
    link.set("commit", new)
    link.set("blob", new_blob)
    reg.finish()

    msgfile = slave.gitdir / ("FILESYNC_MSG_" + re.sub(r"[^A-Za-z0-9._-]", "_", st.rel))
    msgfile.write_bytes(build_message(st, src, new, new_blob, merged, conflicts, discard)
                        .encode("utf-8"))
    commit_cmd = f'git commit -e -F "{msgfile}" -- {cmd_arg(st.rel)} {REGISTRY}'

    if conflicts:
        if stash is not None:
            stashfile = slave.gitdir / ("FILESYNC_STASH_" + re.sub(r"[^A-Za-z0-9._-]", "_", st.rel))
            stashfile.write_bytes(slave.to_worktree(stash, st.rel))
            print(f"{st.rel}: autostash kept in {stashfile} (not re-applied because of the conflicts)")
        print(f"{st.rel}: {paint(f'{conflicts} merge conflict(s)', 'boldred')}. "
              f"Resolve them, then run:\n    git add {cmd_arg(st.rel)}\n    {commit_cmd}")
        return EXIT_PENDING
    slave.git(["add", "--", lit(st.rel)])
    rc = EXIT_OK
    if args.no_commit:
        print(f"{st.rel}: {paint('synced and staged', 'green')}. Commit with:\n    {commit_cmd}")
    else:
        cmd = ["git", "commit", "-F", str(msgfile)] + ([] if args.no_edit else ["-e"]) + \
            ["--", lit(st.rel), REGISTRY]
        if subprocess.run(cmd, cwd=slave.top).returncode:
            print(f"{st.rel}: {paint('commit not done', 'yellow')}; changes stay staged. "
                  f"Commit later with:\n    {commit_cmd}")
            rc = EXIT_PENDING
        else:
            msgfile.unlink()
    if stash is not None:
        # re-apply the stashed uncommitted changes on top of the synced version
        head = slave.read_content(st.head_blob, st.rel)
        c2, data = merge3(content, head, stash, [f"{st.rel} (synced)", f"{st.rel} (HEAD)",
                                                 f"{st.rel} (autostash)"])
        link.target.write_bytes(slave.to_worktree(data, st.rel))
        if c2:
            print(f"{st.rel}: {paint(f'applying autostash resulted in {c2} conflict(s)', 'boldred')}"
                  " - resolve them in the working tree")
            rc = EXIT_PENDING
        else:
            print(f"{st.rel}: {paint('applied autostash', 'green')} (uncommitted changes restored)")
    return rc


def cmd_pull(ctx, slave, args):
    reg = Registry(slave)
    if args.all:
        links = reg.links()
    elif args.files:
        links = select_links(slave, reg, args.files)
    else:
        raise FsError("specify file(s) or --all")
    if args.commit and len(links) != 1:
        raise FsError("--commit requires exactly one file")
    rc, done = EXIT_OK, 0
    for link in links:
        st = evaluate(ctx, slave, link)
        if st.error:
            print(f"{paint(st.rel, 'red', 'err')}: {render(describe(st), 'err')}", file=sys.stderr)
            rc = EXIT_ERROR
            continue
        if args.all and not st.pending:
            continue
        done += 1
        try:
            rc = max(rc, pull_one(slave, reg, st, args))
        except FsError as e:   # report and carry on with the other files
            error(str(e))
            rc = EXIT_ERROR
    if args.all and not done and rc == EXIT_OK:
        print(paint("everything up to date", "green"))
    return rc


def diff_pairs(ctx, slave, args):
    """(st, name, base, other) blob ids for every linked file with a difference.
    base = last synced master version; other = local file (None if missing),
    or with --upstream the current master version. All as actual content in
    this repo's normalized form (LFS resolved), so eol conventions and LFS
    pointers don't show up."""
    rc = EXIT_OK
    pairs = []
    reg = Registry(slave)
    for link in select_links(slave, reg, args.files):
        st = evaluate(ctx, slave, link)
        if st.error:
            print(f"{paint(st.rel, 'red', 'err')}: {render(describe(st), 'err')}", file=sys.stderr)
            rc = EXIT_ERROR
            continue
        if args.upstream:
            if not st.changed:
                continue
        elif args.committed:
            if st.committed != "adapted":
                continue
        elif st.local == "clean":
            continue
        try:
            base = local_equiv(slave, st.src, st.old_blob, st.rel, link.path)
            if not base:
                raise FsError(f"synced version {st.old_blob[:12]} unavailable")
            base = slave.content_id(base, st.rel)
            if args.upstream:
                other = slave.as_local(st.src.read_content(st.new_blob, link.path), st.rel)
                other = slave.content_id(other, st.rel)
            elif args.committed:
                other = slave.content_id(st.head_blob, st.rel)
            elif st.local == "missing":
                other = None
            else:
                other = slave.content_id(slave.worktree_blob(link.target, write=True), st.rel)
        except FsError as e:
            error(f"{st.rel}: {e}")
            rc = EXIT_ERROR
            continue
        name = link.path if args.master_paths else st.rel
        pairs.append((st, name, base, other))
    return rc, pairs


def make_tree(slave, entries):
    """Tree object with the given (path, blob id) entries, via a temp index."""
    with tempfile.TemporaryDirectory(prefix="filesync-") as td:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(td) / "index"))
        if entries:
            data = "".join(f"100644 {oid}\t{path}\n" for path, oid in entries)
            slave.git(["update-index", "--add", "--index-info"], data=data.encode(), env=env)
        return out(slave.git(["write-tree"], env=env))


def cmd_diff(ctx, slave, args):
    """One `git diff <tree> <tree>` in the slave repo over all differing files:
    real paths, the repo's diff settings and pager, options after `--`."""
    rc, pairs = diff_pairs(ctx, slave, args)
    if not pairs:
        return rc
    left = make_tree(slave, [(n, b) for _, n, b, _ in pairs])
    right = make_tree(slave, [(n, o) for _, n, _, o in pairs if o])
    if args.master_paths:
        prefixes = []                  # standard a/ b/: `git apply` in the master
    else:
        prefixes = ["--src-prefix=synced/", "--dst-prefix=" + (
            "upstream/" if args.upstream else "committed/" if args.committed else "local/")]
    color = {"always": ["--color=always"], "never": ["--no-color"]}.get(args.color, [])
    p = subprocess.run(["git", "diff"] + color + prefixes + args.extra + [left, right],
                       cwd=slave.top)
    if p.returncode > 1:
        rc = EXIT_ERROR
    elif p.returncode == 1 and ("--exit-code" in args.extra or "--quiet" in args.extra):
        rc = max(rc, EXIT_PENDING)      # like `git diff --exit-code`: 1 = differences
    return rc


def difftool_prompting(slave, args):
    """Ask before each file like `git difftool`: by default only when no files
    were given; -y/--no-prompt and difftool.prompt=false turn it off,
    --prompt turns it on."""
    if args.prompt:
        return True
    if args.no_prompt or args.files:
        return False
    cfg = out(slave.git(["config", "--type=bool", "difftool.prompt"], check=False))
    return cfg != "false"


def difftool_name(slave, extra):
    for i, a in enumerate(extra):              # -t TOOL / --tool=TOOL passed after --
        if a.startswith("--tool="):
            return a.split("=", 1)[1]
        if a in ("-t", "--tool") and i + 1 < len(extra):
            return extra[i + 1]
    for key in ("diff.tool", "merge.tool"):
        name = out(slave.git(["config", key], check=False))
        if name:
            return name
    return "difftool"


def cmd_difftool(ctx, slave, args):
    """Open each differing file in the configured difftool. Without --upstream
    the real working file is passed, so edits made in the tool are kept."""
    rc, pairs = diff_pairs(ctx, slave, args)
    if not (args.upstream or args.committed):
        for st, _, _, other in pairs:
            if other is None:
                print(f"{st.rel}: file missing, nothing to compare", file=sys.stderr)
        pairs = [p for p in pairs if p[3] is not None]
    prompt = difftool_prompting(slave, args)
    tool = difftool_name(slave, args.extra)
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
                f.write_bytes(slave.to_worktree(slave.read_blob(oid), st.rel))
                return str(f)
            left = tmpfile(f"synced-{src.short(st.old) if st.has_old else st.old_blob[:8]}", base)
            if args.upstream:
                right = tmpfile(f"upstream-{src.short(st.new)}", other)
            elif args.committed:
                right = tmpfile("committed-HEAD", other)
            else:
                right = str(st.link.target)
            subprocess.run(["git", "difftool", "--no-index", "-y"] + args.extra + [left, right],
                           cwd=slave.top)
    return rc


def find_matching_commit(slave, src, cur, rel, path, target, max_equiv=100):
    """Newest master commit that introduced the content of the local file.
    Exact blob match first; then the most recent versions compared by content
    (different eol normalization, LFS in only one of the repos)."""
    hist = src.path_history(path, 5000)
    for rev, oid in hist:
        if oid == cur:
            return rev
    data = target.read_bytes()
    local_hash = (hashlib.sha256(data).hexdigest(), len(data))
    seen = {}
    for rev, oid in hist[:max_equiv]:
        if oid not in seen:
            ptr = lfs_pointer(src.read_blob(oid))
            if ptr:        # LFS in the master: compare hashes, no download needed
                seen[oid] = ptr in (local_hash, lfs_pointer(data))
            else:
                seen[oid] = local_equiv(slave, src, oid, rel, path) == cur
        if seen[oid]:
            return rev
    return None


def cmd_add(ctx, slave, args):
    reg = Registry(slave)
    target = slave.user_path(args.file)
    rel = slave.rel(target)
    if target.is_dir():
        raise FsError(f"cannot link '{rel}': is a directory")
    problem = path_problem(rel)
    if problem:
        raise FsError(f"cannot link '{rel}': {problem}")
    relink = rel in reg.files
    if relink and not args.force:
        raise FsError(f"'{rel}' is already linked (use --force to relink)")
    if args.source in reg.sources:            # name of an existing [source]
        url = reg.sources[args.source].get("url", "")
        branch = args.branch or reg.sources[args.source].get("branch", "")
    else:
        url = args.source
        branch = args.branch or ctx.default_branch(url)
    path = (args.path or rel).strip("/")
    src = ctx.source(url, branch)
    head = src.resolve()
    if not head:
        raise FsError(f"branch '{branch}' not found in {src.label}")
    cur = slave.worktree_blob(target)
    if args.commit:
        commit = src.resolve(args.commit)
        if not commit:
            raise FsError(f"unknown revision '{args.commit}' in {src.label}")
    elif cur:
        commit = find_matching_commit(slave, src, cur, rel, path, target)
        if commit:
            print(f"{rel} matches upstream {src.short(commit)}")
        else:
            commit = head
            warn(f"{rel} matches no upstream version of '{path}'; differences to "
                 f"upstream {src.short(head)} count as local modifications "
                 "(use --commit to choose a better base)")
    else:
        commit = head
    blob = src.blob_at(commit, path)
    if not blob:
        raise FsError(f"no file '{path}' in {src.label} at {src.short(commit)}")
    commit = src.last_change(commit, path)
    content = src.read_content(blob, path) if cur is None else None

    if relink:
        reg.remove_file(rel)
    name = reg.add_source(url, branch)
    link = Link(reg, rel)
    for k, v in (("source", name), ("path", path), ("commit", commit), ("blob", blob)):
        link.set(k, v)
    if args.strict:
        link.set("strict", "true")
    if content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        stored = slave.read_content(slave.as_local(content, rel), rel)
        target.write_bytes(slave.to_worktree(stored, rel))
        slave.git(["add", "--", lit(rel)])
    reg.finish()
    staged = f"{REGISTRY}, {rel}" if content is not None else REGISTRY
    print(f"{paint('linked', 'green')} {rel} -> {repo_label(url)}:{path} ({branch}, "
          f"source '{name}'); staged {staged} - commit when ready")
    return EXIT_OK


def cmd_unlink(ctx, slave, args):
    reg = Registry(slave)
    links = select_links(slave, reg, args.files)
    for link in links:
        reg.remove_file(link.rel)
        print(f"{paint('unlinked', 'green')} {link.rel} (file kept)")
    reg.finish()
    return EXIT_OK


def cmd_mv(ctx, slave, args):
    reg = Registry(slave)
    old = slave.rel(slave.user_path(args.src))
    if old not in reg.files:
        raise FsError(f"'{old}' is not linked")
    dst = slave.user_path(args.dst)
    if dst.is_dir():
        dst = dst / Path(old).name
    new = slave.rel(dst)
    problem = path_problem(new)
    if problem:
        raise FsError(f"cannot move to '{new}': {problem}")
    if new in reg.files or dst.exists():
        raise FsError(f"'{new}' already exists")
    if slave.git(["ls-files", "--error-unmatch", "--", lit(old)], check=False).returncode == 0:
        dst.parent.mkdir(parents=True, exist_ok=True)
        slave.git(["mv", "--", old, new])
    elif (slave.top / old).exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        (slave.top / old).rename(dst)
    reg.rename_file(old, new)
    reg.finish()
    print(f"{paint('moved', 'green')} {old} -> {new} (link kept)")
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


def cmd_map(args, slave):
    """Map a master URL to a local checkout. Default scope is the current
    (slave) repository's config, so different slaves can use different
    checkouts of the same master; --global applies to all repositories."""
    top = slave.top if slave else None
    if not args.dir and not args.unset:      # listing: all scopes visible here
        print_mappings(local_mappings(cwd=top), args.url)
        return EXIT_OK
    if not args.url:
        raise FsError("--unset needs the URL of the mapping to remove")
    if args.glob:
        scope = "--global"
    elif slave:
        scope = "--local"
    else:
        raise FsError("not inside a Git repository; use --global for a global mapping")
    name = scope[2:]
    matching = [k for _, k, u, _ in local_mappings(scope, cwd=top)
                if norm_url(u) == norm_url(args.url)]
    if args.unset:
        if not matching:
            print(f"no {name} mapping for {args.url}")
            return EXIT_OK
        for k in matching:
            git(["config", scope, "--unset-all", k], cwd=top)
        print(f"removed {name} mapping for {args.url}")
        rest = [m for m in local_mappings(cwd=top) if norm_url(m[2]) == norm_url(args.url)]
        if rest:
            print(f"now using [{rest[-1][0]}] {rest[-1][3]}")
        return EXIT_OK
    base = slave.base if slave else Path.cwd()
    d = (base / os.path.expanduser(args.dir)).resolve()
    if git(["-C", d, "rev-parse", "--git-dir"], env=clean_env(), check=False).returncode:
        raise FsError(f"{d} is not a Git repository")
    for k in matching:
        git(["config", scope, "--unset-all", k], cwd=top)
    git(["config", scope, f"filesync.{args.url}.localpath", str(d)], cwd=top)
    print(f"{paint(f'[{name}]', 'cyan')} {args.url} -> {d}")
    if scope == "--global" and slave:
        own = [m for m in local_mappings("--local", cwd=top) if norm_url(m[2]) == norm_url(args.url)]
        if own:
            warn(f"this repository has its own mapping ({own[-1][3]}), which takes precedence")
    return EXIT_OK


def hook_dir(slave, action):
    hp = out(slave.git(["config", "core.hooksPath"], check=False))
    if hp:
        hookdir = Path(os.path.expanduser(hp))
        if not hookdir.is_absolute():
            hookdir = slave.top / hookdir
        warn(f"core.hooksPath is set; {action} {hookdir} "
             "(may affect other repositories using it)")
    else:
        hookdir = Path(out(slave.git(["rev-parse", "--git-path", "hooks"])))
        if not hookdir.is_absolute():
            hookdir = slave.top / hookdir
    return hookdir


def hook_snippet(cmd):
    return (f"# {HOOK_MARKER}: remind about pending file syncs (never blocks)\n"
            f"{cmd} </dev/null || true\n")


def is_our_hook_line(line):
    s = line.strip()
    return s.startswith(f"# {HOOK_MARKER}:") or s.startswith("git filesync status --hook")


def cmd_install_hooks(slave, args):
    hookdir = hook_dir(slave, "installing into")
    hookdir.mkdir(parents=True, exist_ok=True)
    for name, cmd in HOOKS.items():
        f = hookdir / name
        snippet = hook_snippet(cmd)
        if f.exists():
            if HOOK_MARKER in f.read_text(encoding="utf-8", errors="replace"):
                print(f"{name}: already installed")
            else:
                print(f"{name}: {paint('hook exists', 'yellow')}, add these lines to {f}:\n{snippet}")
            continue
        f.write_bytes(("#!/bin/sh\n" + snippet + "exit 0\n").encode())
        f.chmod(0o755)
        print(f"{name}: {paint('installed', 'green')}")
    return EXIT_OK


def cmd_uninstall_hooks(slave, args):
    """Remove our hooks. A hook file that only contains our snippet is deleted;
    in other hook files only our lines are removed, the rest stays untouched."""
    hookdir = hook_dir(slave, "removing from")
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

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass

    colorp = argparse.ArgumentParser(add_help=False)
    colorp.add_argument("--color", nargs="?", const="always", default="auto",
                        choices=["always", "never", "auto"], help="colored output (default: auto)")
    colorp.add_argument("--no-color", dest="color", action="store_const", const="never",
                        help="same as --color=never")
    common = argparse.ArgumentParser(add_help=False, parents=[colorp])
    common.add_argument("--no-fetch", action="store_true",
                        help="do not fetch master repositories, use cached state")
    common.add_argument("--remote", action="store_true",
                        help="ignore local checkout mappings, use the remote URL")

    ap = argparse.ArgumentParser(prog="git filesync",
                                 description="Keep single files in sync between Git repositories.",
                                 epilog="Without a command: status. "
                                        "'git filesync <command> -h' lists the options of a command.")
    ap.add_argument("--version", action="version", version=f"git-filesync {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("status", parents=[common], help="show sync state of linked files")
    p.add_argument("paths", nargs="*", help="files or directories (default: all)")
    p.add_argument("-s", "--short", action="store_true",
                   help="short format: upstream / committed / working tree columns")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also list all linked files with their sources")
    p.add_argument("--exit-code", action="store_true",
                   help="exit with 1 if something is to sync or a strict file is modified")
    p.add_argument("--hook", action="store_true", help="terse output for git hooks")

    p = sub.add_parser("pull", parents=[common], help="sync file(s) from master")
    p.add_argument("files", nargs="*", help="files or directories")
    p.add_argument("--all", action="store_true", help="sync all files with something to sync")
    p.add_argument("--commit", metavar="REV", help="sync to this master revision (exactly one file)")
    p.add_argument("--no-edit", action="store_true", help="commit without opening the editor")
    p.add_argument("--no-commit", action="store_true", help="only stage; print commit command")
    p.add_argument("--overwrite", action="store_true",
                   help="discard local adaptations instead of merging them")
    p.add_argument("--autostash", action="store_true",
                   help="set uncommitted changes aside and re-apply them after the sync")

    for name, hlp in (("diff", "show local modifications against the synced master version"),
                      ("difftool", "same in the configured difftool")):
        p = sub.add_parser(name, parents=[common], help=hlp,
                           epilog="Options after '--' are passed to git " + name + ".")
        p.add_argument("files", nargs="*", help="files or directories (default: all)")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--upstream", action="store_true",
                       help="show what 'pull' would bring instead (synced -> current master)")
        g.add_argument("--committed", action="store_true",
                       help="only the committed adaptations (synced -> HEAD)")
        if name == "diff":
            p.add_argument("--master-paths", action="store_true",
                           help="name files by their master path, for 'git apply' in the master")
        else:
            p.add_argument("-y", "--no-prompt", action="store_true",
                           help="don't ask before launching the tool for each file")
            p.add_argument("--prompt", action="store_true",
                           help="ask before each file even if files are given")

    p = sub.add_parser("add", parents=[common], help="link a file to a file in a master repository")
    p.add_argument("file", help="file in this repository (fetched from master if missing)")
    p.add_argument("source", metavar="URL|SOURCE", help="master URL or name of a [source] in "
                   + REGISTRY)
    p.add_argument("-b", "--branch", help="master branch (default: remote HEAD, or the branch of SOURCE)")
    p.add_argument("-p", "--path", help="path in master repo (default: same as here)")
    p.add_argument("--commit", metavar="REV", help="master revision the local file corresponds to")
    p.add_argument("--force", action="store_true", help="relink an already linked file")
    p.add_argument("--strict", action="store_true",
                   help="file must stay an exact copy (no local modifications)")

    p = sub.add_parser("unlink", parents=[colorp], help="remove links (the files are kept)")
    p.add_argument("files", nargs="+", help="files or directories")

    p = sub.add_parser("mv", parents=[colorp], help="move a linked file, keeping its link")
    p.add_argument("src", metavar="OLD", help="linked file")
    p.add_argument("dst", metavar="NEW", help="new path or existing directory")

    p = sub.add_parser("map", parents=[colorp], help="use a local checkout for a master URL "
                                                     "(this repo's config; --global for all repos)")
    p.add_argument("url", nargs="?", help="master URL (without DIR: list its mappings)")
    p.add_argument("dir", nargs="?", help="local checkout of the master")
    p.add_argument("--unset", action="store_true", help="remove the mapping for URL")
    p.add_argument("--global", dest="glob", action="store_true",
                   help="use the global git config instead of this repository's")

    sub.add_parser("install-hooks", parents=[colorp], help="install pre-push/post-merge reminder hooks")
    sub.add_parser("uninstall-hooks", parents=[colorp], help="remove the reminder hooks again")

    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if argv and argv[0] in ("diff", "difftool") and "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["status"])
    args.extra = extra
    args.master_paths = getattr(args, "master_paths", False)
    try:
        try:
            slave = Slave()
        except FsError:
            slave = None
        setup_colors(args.color, slave.top if slave else None)
        if args.cmd == "map":
            return cmd_map(args, slave)
        if slave is None:
            raise FsError("not inside a Git working tree")
        if args.cmd == "install-hooks":
            return cmd_install_hooks(slave, args)
        if args.cmd == "uninstall-hooks":
            return cmd_uninstall_hooks(slave, args)
        ctx = Context(args, slave)
        return {"status": cmd_status, "pull": cmd_pull, "add": cmd_add,
                "unlink": cmd_unlink, "mv": cmd_mv,
                "diff": cmd_diff, "difftool": cmd_difftool}[args.cmd](ctx, slave, args)
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
