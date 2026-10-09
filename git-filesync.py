#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git-filesync - keep individual files in sync between Git repositories.

The "slave" repository stores, next to each synchronized file FILE, a sidecar
FILE.sync (git-config format) that links it to a file in a "master" repository:

    [upstream]
        url = https://github.com/owner/repo.git
        branch = main
        path = lib/foo.c
    [state]
        commit = <master commit of the last sync>
        blob = <blob id of the master's file content at that commit>

Commands (run inside the slave repository):
    status [PATH...]           show which synced files need attention
    pull   [FILE...|--all]     sync files from master, propose commit message
    add    FILE URL [...]      link a file to a file in a master repository
    map    [URL [DIR]]         use a local checkout instead of fetching URL
    install-hooks              install pre-push/post-merge reminder hooks

Requires Python >= 3.7 and Git >= 2.20. Works on Linux, macOS and Windows.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

SUFFIX = ".sync"
EXIT_OK, EXIT_PENDING, EXIT_ERROR = 0, 1, 2
HOOK_MARKER = "git-filesync"
HOOKS = {
    "pre-push": "git filesync status --hook",
    "post-merge": "git filesync status --hook --no-fetch",
}


class FsError(Exception):
    pass


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


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


def local_mappings(scope=None):
    """List of (config key, url, dir) from filesync.<url>.localpath entries."""
    args = ["config"] + ([scope] if scope else []) + \
        ["--get-regexp", r"^filesync\..+\.localpath$"]
    result = []
    for line in out(git(args, check=False)).splitlines():
        key, _, val = line.partition(" ")
        url = key[len("filesync."):-len(".localpath")]
        result.append((key, url, val))
    return result


def default_branch(url):
    p = git(["ls-remote", "--symref", url, "HEAD"], env=clean_env(), check=False)
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out(p), re.M)
    if not m:
        raise FsError(f"cannot determine default branch of {url}; use --branch")
    return m.group(1)


# --------------------------------------------------------------------------
# master side
# --------------------------------------------------------------------------

class Source:
    """A Git repository providing the master versions of synced files."""

    def __init__(self, repo, ref, label, pushed_ref=None):
        self.repo, self.ref, self.label = Path(repo), ref, label
        self.pushed_ref = pushed_ref   # set for local checkouts

    def git(self, args, **kw):
        kw.setdefault("env", clean_env())
        return git(["-C", self.repo] + list(args), **kw)

    def resolve(self, rev=None):
        p = self.git(["rev-parse", "--verify", "--quiet",
                      (rev or self.ref) + "^{commit}"], check=False)
        return out(p) if p.returncode == 0 else None

    def blob_at(self, commit, path):
        p = self.git(["rev-parse", "--verify", "--quiet", f"{commit}:{path}"],
                     check=False)
        return out(p) if p.returncode == 0 else None

    def read_blob(self, oid):
        return self.git(["cat-file", "blob", oid]).stdout

    def short(self, oid):
        return out(self.git(["rev-parse", "--short", oid]))

    def is_ancestor(self, a, b):
        return self.git(["merge-base", "--is-ancestor", a, b],
                        check=False).returncode == 0

    def count(self, old, new, path):
        return int(out(self.git(["rev-list", "--count", f"{old}..{new}", "--", path])))

    def log(self, rng, path):
        return out(self.git(["log", "--reverse", "--format=- %s (%h)", rng, "--", path]))

    def find_commit_with_blob(self, blob, path, max_count=5000):
        """Newest commit on the branch that introduced content `blob` at path."""
        revs = out(self.git(["rev-list", f"--max-count={max_count}",
                             self.ref, "--", path])).split()
        if not revs:
            return None
        data = "".join(f"{r}:{path}\n" for r in revs).encode()
        ids = out(self.git(["cat-file", "--batch-check=%(objectname)"],
                           data=data)).splitlines()
        for rev, oid in zip(revs, ids):
            if oid == blob:
                return rev
        return None


class Context:
    """Creates and caches Sources; fetches each master repository at most once."""

    def __init__(self, args):
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

    def _make(self, url, branch):
        if not self.force_remote:
            if self._mappings is None:
                self._mappings = {norm_url(u): d for _, u, d in local_mappings()}
            local = self._mappings.get(norm_url(url))
            if local:
                path = Path(os.path.expanduser(local))
                if git(["-C", path, "rev-parse", "--git-dir"], env=clean_env(),
                       check=False).returncode == 0:
                    return Source(path, f"refs/heads/{branch}",
                                  f"local checkout {path}",
                                  pushed_ref=f"refs/remotes/origin/{branch}")
                warn(f"mapped local checkout {path} is not a Git repository; "
                     f"using {url}")
        return Source(self._cache(url), f"refs/remotes/origin/{branch}",
                      repo_label(url))

    def _cache(self, url):
        d = cache_root() / (hashlib.sha1(norm_url(url).encode()).hexdigest()[:16] + ".git")
        if d in self._ready:
            return d
        env = clean_env()
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(f"{d.name}.tmp{os.getpid()}")
            print(f"Cloning {url} (blobless) ...", file=sys.stderr)
            try:
                git(["clone", "--bare", "--quiet", "--filter=blob:none", url, tmp], env=env)
                git(["-C", tmp, "config", "remote.origin.fetch",
                     "+refs/heads/*:refs/remotes/origin/*"], env=env)
                git(["-C", tmp, "fetch", "--quiet", "origin"], env=env)
                tmp.rename(d)
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
        elif self.fetch:
            p = git(["-C", d, "fetch", "--quiet", "--prune", "origin"], env=env, check=False)
            if p.returncode:
                warn(f"fetching {url} failed, using cached state")
        self._ready.add(d)
        return d


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
        """Blob id of the (clean-filtered) working tree file, None if missing."""
        if not path.is_file():
            return None
        args = ["hash-object"] + (["-w"] if write else []) + \
            [f"--path={self.rel(path)}", str(path)]
        return out(self.git(args))

    def read_blob(self, oid):
        return self.git(["cat-file", "blob", oid]).stdout

    def to_worktree(self, content, rel):
        """Convert normalized blob content to this repo's working tree form
        (eol conversion, smudge filters per .gitattributes / core.autocrlf)."""
        oid = out(self.git(["hash-object", "-w", "--stdin", "--no-filters"], data=content))
        return self.git(["cat-file", "--filters", f"--path={rel}", oid]).stdout


class Sidecar:
    def __init__(self, path):
        self.path = Path(path)
        self.target = self.path.with_name(self.path.name[:-len(SUFFIX)])
        self.values = {}
        if self.path.exists():
            p = git(["config", "-f", self.path, "--list"], check=False)
            if p.returncode:
                raise FsError(f"{self.path}: cannot parse sidecar")
            for line in out(p).splitlines():
                k, _, v = line.partition("=")
                self.values[k] = v

    def get(self, key):
        return self.values.get(key, "")

    def set(self, key, value):
        git(["config", "-f", self.path, key, value])
        self.values[key] = value

    def valid(self):
        return bool(self.get("upstream.url"))


def find_sidecars(slave, paths):
    explicit = bool(paths)
    cands = []
    if not paths:
        paths = ["."]
    for s in paths:
        p = slave.user_path(s)
        if p.is_dir():
            rel = slave.rel(p)
            spec = f"*{SUFFIX}" if rel == "." else f"{rel}/*{SUFFIX}"
            res = slave.git(["ls-files", "-z", "-co", "--exclude-standard", "--", spec])
            found = [slave.top / x for x in res.stdout.decode("utf-8", "replace").split("\0") if x]
            cands += [(c, False) for c in found]
        elif p.name.endswith(SUFFIX):
            cands.append((p, explicit))
        else:
            cands.append((p.with_name(p.name + SUFFIX), explicit))
    result, seen = [], set()
    for c, must in cands:
        if c in seen:
            continue
        seen.add(c)
        if not c.is_file():
            if must:
                raise FsError(f"no sidecar {slave.rel(c)} (use 'add' to link the file)")
            continue
        sc = Sidecar(c)
        if sc.valid():
            result.append(sc)
        elif must:
            raise FsError(f"{slave.rel(c)} is not a git-filesync sidecar")
    return sorted(result, key=lambda sc: str(sc.path))


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

def evaluate(ctx, slave, sc):
    st = SimpleNamespace(sc=sc, rel=slave.rel(sc.target), error=None, warnings=[],
                         src=None, old=sc.get("state.commit"),
                         old_blob=sc.get("state.blob"), new=None, new_blob=None,
                         count=0, has_old=False, diverged=False, local="clean",
                         changed=False, pending=False)
    url, branch, path = (sc.get(k) for k in ("upstream.url", "upstream.branch", "upstream.path"))
    if not (url and branch and path):
        st.error = "incomplete sidecar (needs upstream.url, .branch, .path)"
        return st
    cur = slave.worktree_blob(sc.target)
    st.local = "missing" if cur is None else ("clean" if cur == st.old_blob else "modified")
    try:
        src = st.src = ctx.source(url, branch)
    except FsError as e:
        st.error = str(e)
        return st
    st.new = src.resolve()
    if not st.new:
        st.error = f"branch '{branch}' not found in {src.label}"
        return st
    st.new_blob = src.blob_at(st.new, path)
    if not st.new_blob:
        st.error = (f"'{path}' does not exist on {branch} in {src.label} "
                    f"(renamed upstream? fix upstream.path in {slave.rel(sc.path)})")
        return st
    st.has_old = bool(st.old) and src.resolve(st.old) == st.old
    if st.has_old:
        st.count = src.count(st.old, st.new, path)
        st.diverged = not src.is_ancestor(st.old, st.new)
    else:
        st.warnings.append(f"last synced commit {st.old[:12] or '-'} not found in "
                           f"{src.label} (unpushed?)")
    st.changed = st.new_blob != st.old_blob
    st.pending = st.changed or st.local == "missing"
    if src.pushed_ref:
        pushed = src.resolve(src.pushed_ref)
        if not pushed or not src.is_ancestor(st.new, pushed):
            st.warnings.append(f"'{branch}' in {src.label} has commits not pushed to origin")
    return st


def describe(st):
    if st.error:
        return f"ERROR: {st.error}"
    parts = []
    if st.changed:
        if st.has_old and not st.diverged:
            parts.append(f"{st.count} upstream commit(s) pending")
        else:
            parts.append("upstream changed (history diverged)" if st.has_old else "upstream changed")
    else:
        parts.append("up to date")
    if st.local == "modified":
        parts.append("local modifications" + (" (merge needed)" if st.changed else ""))
    elif st.local == "missing":
        parts.append("file missing")
    return ", ".join(parts)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(ctx, slave, args):
    sidecars = find_sidecars(slave, args.paths)
    if not sidecars:
        if not args.hook:
            print("no synced files found")
        return EXIT_OK
    rc, pending = EXIT_OK, []
    for sc in sidecars:
        st = evaluate(ctx, slave, sc)
        if st.error:
            rc = EXIT_ERROR
        elif st.pending:
            rc = max(rc, EXIT_PENDING)
        if args.hook:
            if st.error or st.pending:
                pending.append(st.rel)
                print(f"filesync: {st.rel}: {describe(st)}", file=sys.stderr)
            continue
        print(f"{st.rel}: {describe(st)}")
        via = f" via {st.src.label}" if st.src and st.src.pushed_ref else ""
        print(f"    from {repo_label(sc.get('upstream.url'))}:{sc.get('upstream.path')}"
              f" ({sc.get('upstream.branch')}){via}")
        for w in st.warnings:
            print(f"    warning: {w}")
    if args.hook and pending:
        print("filesync: run 'git filesync pull <file>' to sync", file=sys.stderr)
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


def build_message(st, src, new, merged, conflicts):
    sc = st.sc
    url, branch, path = (sc.get(k) for k in ("upstream.url", "upstream.branch", "upstream.path"))
    lines = [f"Sync {st.rel} from {repo_label(url)}@{src.short(new)}", "",
             f"Upstream: {url} ({branch}:{path})"]
    if st.has_old:
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
    return "\n".join(lines) + "\n"


def pull_one(slave, st, args):
    sc, src = st.sc, st.src
    path = sc.get("upstream.path")
    new, new_blob = st.new, st.new_blob
    if args.commit:
        new = src.resolve(args.commit)
        if not new:
            raise FsError(f"unknown revision '{args.commit}' in {src.label}")
        new_blob = src.blob_at(new, path)
        if not new_blob:
            raise FsError(f"'{path}' does not exist at {args.commit}")
    if new_blob == st.old_blob and st.local != "missing":
        print(f"{st.rel}: up to date" + (" (local modifications kept)" if st.local == "modified" else ""))
        return EXIT_OK
    for w in st.warnings:
        warn(f"{st.rel}: {w}")

    theirs = src.read_blob(new_blob)
    merged, conflicts = False, 0
    if st.local == "modified":
        try:
            base = src.read_blob(st.old_blob)
        except FsError:
            raise FsError(f"{st.rel}: base version {st.old_blob[:12]} unavailable; "
                          "cannot merge local modifications")
        ours = slave.read_blob(slave.worktree_blob(sc.target, write=True))
        old_label = src.short(st.old) if st.has_old else st.old_blob[:8]
        conflicts, content = merge3(ours, base, theirs,
                                    [f"{st.rel} (local)", f"upstream {old_label}",
                                     f"upstream {src.short(new)}"])
        merged = True
    else:
        content = theirs

    sc.target.parent.mkdir(parents=True, exist_ok=True)
    sc.target.write_bytes(slave.to_worktree(content, st.rel))
    sc.set("state.commit", new)
    sc.set("state.blob", new_blob)

    msgfile = slave.gitdir / ("FILESYNC_MSG_" + re.sub(r"[^A-Za-z0-9._-]", "_", st.rel))
    msgfile.write_bytes(build_message(st, src, new, merged, conflicts).encode("utf-8"))
    side_rel = slave.rel(sc.path)
    commit_cmd = f'git commit -e -F "{msgfile}" -- {st.rel} {side_rel}'

    if conflicts:
        slave.git(["add", "--", side_rel])
        print(f"{st.rel}: {conflicts} merge conflict(s). Resolve them, then run:\n"
              f"    git add {st.rel}\n    {commit_cmd}")
        return EXIT_PENDING
    slave.git(["add", "--", st.rel, side_rel])
    if args.no_commit:
        print(f"{st.rel}: synced and staged. Commit with:\n    {commit_cmd}")
        return EXIT_OK
    cmd = ["git", "commit", "-F", str(msgfile)] + ([] if args.no_edit else ["-e"]) + \
        ["--", st.rel, side_rel]
    if subprocess.run(cmd, cwd=slave.top).returncode:
        print(f"{st.rel}: commit not done; changes stay staged. Commit later with:\n"
              f"    {commit_cmd}")
        return EXIT_PENDING
    msgfile.unlink()
    return EXIT_OK


def cmd_pull(ctx, slave, args):
    if args.all:
        sidecars = find_sidecars(slave, [])
    elif args.files:
        sidecars = find_sidecars(slave, args.files)
    else:
        raise FsError("specify file(s) or --all")
    if args.commit and len(sidecars) != 1:
        raise FsError("--commit requires exactly one file")
    rc, done = EXIT_OK, 0
    for sc in sidecars:
        st = evaluate(ctx, slave, sc)
        if st.error:
            print(f"{st.rel}: ERROR: {st.error}", file=sys.stderr)
            rc = EXIT_ERROR
            continue
        if args.all and not st.pending:
            continue
        done += 1
        rc = max(rc, pull_one(slave, st, args))
    if args.all and not done and rc == EXIT_OK:
        print("everything up to date")
    return rc


def cmd_add(ctx, slave, args):
    target = slave.user_path(args.file)
    side = target.with_name(target.name + SUFFIX)
    rel = slave.rel(target)
    if side.exists() and not args.force:
        raise FsError(f"{slave.rel(side)} already exists (use --force to relink)")
    branch = args.branch or default_branch(args.url)
    path = (args.path or rel).strip("/")
    src = ctx.source(args.url, branch)
    head = src.resolve()
    if not head:
        raise FsError(f"branch '{branch}' not found in {src.label}")
    cur = slave.worktree_blob(target)
    if args.commit:
        commit = src.resolve(args.commit)
        if not commit:
            raise FsError(f"unknown revision '{args.commit}' in {src.label}")
    elif cur:
        commit = src.find_commit_with_blob(cur, path)
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
        raise FsError(f"'{path}' not found in {src.label} at {src.short(commit)}")

    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_bytes(f"# git-filesync: links {target.name} to a file in another "
                     "repository. Do not edit [state].\n".encode())
    sc = Sidecar(side)
    for k, v in (("upstream.url", args.url), ("upstream.branch", branch),
                 ("upstream.path", path), ("state.commit", commit), ("state.blob", blob)):
        sc.set(k, v)
    stage = [slave.rel(side)]
    if cur is None:
        target.write_bytes(slave.to_worktree(src.read_blob(blob), rel))
        stage.append(rel)
    slave.git(["add", "--"] + stage)
    print(f"linked {rel} -> {repo_label(args.url)}:{path} ({branch}); "
          f"staged {', '.join(stage)} - commit when ready")
    return EXIT_OK


def cmd_map(args):
    maps = local_mappings("--global")
    if not args.url:
        for _, url, d in maps:
            print(f"{url} -> {d}")
        return EXIT_OK
    matching = [k for k, u, _ in maps if norm_url(u) == norm_url(args.url)]
    if args.unset:
        for k in matching:
            git(["config", "--global", "--unset-all", k])
        return EXIT_OK
    if not args.dir:
        for k, u, d in maps:
            if norm_url(u) == norm_url(args.url):
                print(f"{u} -> {d}")
        return EXIT_OK
    d = Path(os.path.expanduser(args.dir)).resolve()
    if git(["-C", d, "rev-parse", "--git-dir"], env=clean_env(), check=False).returncode:
        raise FsError(f"{d} is not a Git repository")
    for k in matching:
        git(["config", "--global", "--unset-all", k])
    git(["config", "--global", f"filesync.{args.url}.localpath", str(d)])
    print(f"{args.url} -> {d}")
    return EXIT_OK


def cmd_install_hooks(slave, args):
    hp = out(slave.git(["config", "core.hooksPath"], check=False))
    if hp:
        hookdir = Path(os.path.expanduser(hp))
        if not hookdir.is_absolute():
            hookdir = slave.top / hookdir
        warn(f"core.hooksPath is set; installing into {hookdir}")
    else:
        hookdir = Path(out(slave.git(["rev-parse", "--git-path", "hooks"])))
        if not hookdir.is_absolute():
            hookdir = slave.top / hookdir
    hookdir.mkdir(parents=True, exist_ok=True)
    for name, cmd in HOOKS.items():
        f = hookdir / name
        snippet = (f"# {HOOK_MARKER}: remind about pending file syncs (never blocks)\n"
                   f"{cmd} </dev/null || true\n")
        if f.exists():
            if HOOK_MARKER in f.read_text(encoding="utf-8", errors="replace"):
                print(f"{name}: already installed")
            else:
                print(f"{name}: hook exists, add these lines to {f}:\n{snippet}")
            continue
        f.write_bytes(("#!/bin/sh\n" + snippet + "exit 0\n").encode())
        f.chmod(0o755)
        print(f"{name}: installed")
    return EXIT_OK


# --------------------------------------------------------------------------

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-fetch", action="store_true",
                        help="do not fetch master repositories, use cached state")
    common.add_argument("--remote", action="store_true",
                        help="ignore local checkout mappings, use the remote URL")

    ap = argparse.ArgumentParser(prog="git filesync",
                                 description="Keep single files in sync between Git repositories.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("status", parents=[common], help="show sync state of linked files")
    p.add_argument("paths", nargs="*", help="files or directories (default: whole repo)")
    p.add_argument("--hook", action="store_true", help="terse output for git hooks")

    p = sub.add_parser("pull", parents=[common], help="sync file(s) from master")
    p.add_argument("files", nargs="*")
    p.add_argument("--all", action="store_true", help="sync all files with pending changes")
    p.add_argument("--commit", metavar="REV", help="sync to this master revision instead of the branch head")
    p.add_argument("--no-edit", action="store_true", help="commit without opening the editor")
    p.add_argument("--no-commit", action="store_true", help="only stage; print commit command")

    p = sub.add_parser("add", parents=[common], help="link a file to a master repository")
    p.add_argument("file")
    p.add_argument("url")
    p.add_argument("-b", "--branch", help="master branch (default: remote HEAD)")
    p.add_argument("-p", "--path", help="path in master repo (default: same as here)")
    p.add_argument("--commit", metavar="REV", help="master revision the local file corresponds to")
    p.add_argument("--force", action="store_true", help="overwrite an existing sidecar")

    p = sub.add_parser("map", help="use a local checkout for a master URL (global git config)")
    p.add_argument("url", nargs="?")
    p.add_argument("dir", nargs="?")
    p.add_argument("--unset", action="store_true")

    sub.add_parser("install-hooks", help="install pre-push/post-merge reminder hooks")

    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["status"])
    try:
        if args.cmd == "map":
            return cmd_map(args)
        slave = Slave()
        if args.cmd == "install-hooks":
            return cmd_install_hooks(slave, args)
        ctx = Context(args)
        return {"status": cmd_status, "pull": cmd_pull, "add": cmd_add}[args.cmd](ctx, slave, args)
    except FsError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
