#!/bin/bash
# =============================================================================
# Regression test for git-filesync (Linux, macOS, Git Bash on Windows)
# =============================================================================
#
# Usage:  test/regress.sh [path/to/git-filesync.py] </dev/null
#         (PYTHON=python test/regress.sh … to use another interpreter, e.g.
#         in Git Bash on Windows)
#
# The script builds throwaway "upstream" and "downstream" repositories in a temp
# directory ($T, removed on exit) and runs git-filesync against them. Each
# check prints "ok   <name>" or "FAIL <name>: got [...] expected [...]";
# the exit code is 1 if any check failed. The Git LFS section is skipped
# when git-lfs is not installed.
#
# With the oldest supported Python and Git (see test/minver.Containerfile):
#   podman build -t filesync-minver -f test/minver.Containerfile test
#   podman run --rm -v "$PWD":/src:ro,Z -w /src filesync-minver test/regress.sh </dev/null
#
# Naming in the scenarios:
#   upstream, m, m3 ...  upstream repositories (where "upstream" commits are made)
#   *.git                bare copies of them, standing in for the server
#   co*                  local checkouts of an upstream (for 'git filesync source map')
#   downstream, s, sA .. repositories that link files from an upstream
#   file:///nowhere/...  URL of a server that does not exist; such sources
#                        only work through a mapping to a local checkout
#
# Sections:
#    1. Basic workflow: add, status, pull, merge, conflict, hooks
#    2. Line endings: CRLF upstream, repositories with different normalization
#    3. Branch name as --commit
#    4. source map: mappings to local checkouts of an upstream
#    5. Offline operation
#    6. diff / difftool / strict files
#    7. .git-filesync registry: sources, rm, unlink, mv, commit consistency
#    8. Colors
#    9. status like 'git status', pull like 'git pull'
#   10. Robustness: unsafe registry paths, special file names, odd entries
#   11. Recorded commit: the one that produced the synced version
#   12. Git LFS: upstream / downstream / both / neither, via mapping and via cache
#   13. Tags: files pinned to a tag
#   14. source: list, rename and change sources
#   15. Files renamed or deleted upstream
#   16. Dry runs: pull --dry-run, add / unlink / mv -n
#   17. add DIR: all files of an upstream directory, --include / --exclude
#   18. pull -b / --tag: another branch or tag, once; newer tags
#   19. set: change source, tag, upstream path or strict of linked files
#   20. cache: show, list and clean up the cache of upstream clones
#   21. Performance: git processes don't grow with the number of files
#   22. Closed output pipe; discarded content kept
#   23. A cache that lacks a branch; symlinks in this repository; parallel clones
#
# Adding a test: put it into the section it belongs to, or add a new
# section at the end that starts with 'section' and 'cd "$T"'.

# --- setup -------------------------------------------------------------------

# The script under test (absolute path): the argument, or the one in the
# directory above this test.
S=${1:-$(dirname "$0")/../git-filesync.py}
S=$(cd "$(dirname "$S")" && pwd)/$(basename "$S")
command -v cygpath >/dev/null && S=$(cygpath -m "$S")    # Git Bash: C:/... for Python

# Scratch directory for all repositories; removed on exit. In Git Bash on
# Windows as a Windows path (C:/...), which native git and Python understand.
T=$(cd "$(mktemp -d)" && pwd -P)       # physical path (macOS: /var -> /private/var)
trap 'rm -rf "$T"' EXIT
command -v cygpath >/dev/null && T=$(cygpath -m "$T")
cd "$T" || exit 2

# TURL - file:// URL of $T (file:///C:/... on Windows)
case $T in ?:*) TURL=file:///$T ;; *) TURL=file://$T ;; esac

PYTHON=${PYTHON:-python3}

# Isolate from the user's setup: own HOME (global git config) and own
# cache directory (git-filesync keeps its clones of upstream repos there).
export HOME=$T/home FILESYNC_CACHE=$T/cache
mkdir -p "$HOME"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@x GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@x
export GIT_EDITOR=true                 # accept commit messages unchanged
export GIT_PAGER=cat                   # never start a pager
git config --global init.defaultBranch main
git config --global core.autocrlf false    # Git for Windows: true by default

# Upstream repositories are read-only for git-filesync: every run goes
# through guard.sh, which logs any path written outside the repository it
# runs in, its cache and $HOME (a mapped checkout, a server copy, another
# repository ...) to $T/foreign-writes; the summary fails if there are any.
# Not counted: files directly in $T (output the tests redirect there) and
# $T itself.
# Checking timestamps instead of making the upstreams read-only also catches
# writes git only does if it may (index refresh) and works as root and on
# Windows.
mkdir -p "$T/stamps"
REAL_GIT=$(command -v git)
cat > "$T/guard.sh" <<EOF
stamp=\$(mktemp "$T/stamps/XXXXXX")
"$PYTHON" "$S" "\$@"
rc=\$?
top=\$("$REAL_GIT" rev-parse --show-toplevel 2>/dev/null)
gd=\$("$REAL_GIT" rev-parse --absolute-git-dir 2>/dev/null)
find "$T" \\( -path "$T/stamps" -o -path "$T/cache*" -o -path "$T/home" \\
    \${top:+-o -path "\$top"} \${gd:+-o -path "\$gd"} \\
    -o -type f -path "$T/*" ! -path "$T/*/*" \\) -prune -o \\
    -newer "\$stamp" ! -path "$T" -print > "\$stamp.new"
while read -r f; do echo "filesync \$*: \$f"; done < "\$stamp.new" >> "$T/foreign-writes"
rm -f "\$stamp" "\$stamp.new"
exit \$rc
EOF
git config --global alias.filesync "!bash $T/guard.sh"

# --- helpers -----------------------------------------------------------------

TAB=$(printf '\t')     # for grep -E patterns (portable, unlike Perl regexes)

PASSED=0 FAILED=0

# check NAME ACTUAL EXPECTED - compare two strings and report the result
check() {
  if [ "$2" = "$3" ]; then
    echo "ok   $1"; PASSED=$((PASSED + 1))
  else
    echo "FAIL $1: got [$2] expected [$3]"; FAILED=$((FAILED + 1))
  fi
}

# section TITLE - print a heading between the check results
section() { printf '\n=== %s\n' "$1"; }

# st [ARGS...] - 'status -s' code of the first file listed ("" = nothing to
# report). Three columns: upstream (P pending, O older, R renamed ...), committed
# (A adapted), worktree (M modified, D deleted ...); trailing blanks removed.
st() { git filesync status -s "$@" 2>/dev/null | head -1 | cut -c1-3 | sed 's/ *$//'; }

# quiet CMD... - run a command with all output discarded
quiet() { "$@" >/dev/null 2>&1; }

# rc CMD... - run a command quietly and print its exit code
rc() { "$@" >/dev/null 2>&1; echo $?; }

# addc ARGS... - 'git filesync add' (which only stages, like git add), then
# commit with the proposed message, as 'git commit --no-edit' offers it
addc() { git filesync add "$@" >/dev/null 2>&1 && git commit -q --no-edit >/dev/null 2>&1; }

# pullc ARGS... - 'git filesync pull' (which only stages, like git merge
# --squash), then commit what it staged with the proposed message; the exit
# code and output are pull's
pullc() { git filesync pull "$@"; local rc=$?; [ $rc = 0 ] && git commit -q --no-edit >/dev/null 2>&1; return $rc; }

# fsd ARGS... - git-filesync run directly, not through the git alias. On
# Windows git runs aliases through its MSYS shell, which expands wildcard
# characters in arguments if a file matches ('f[1].txt' -> f1.txt) and
# turns arguments starting with '/' into Windows paths ('/x.md' ->
# 'C:/Program Files/Git/x.md'); the latter is avoided here with
# MSYS_NO_PATHCONV (which can't be set for the alias: it breaks how git
# passes the arguments to it). No effect elsewhere.
fsd() { MSYS_NO_PATHCONV=1 bash "$T/guard.sh" "$@"; }

# sedi SCRIPT FILE... - edit each FILE in place with sed; works with GNU and
# BSD sed and keeps CRLF (GNU sed in Git Bash only does with -b)
SED_B=; sed --version >/dev/null 2>&1 && SED_B=-b
sedi() {
  local script=$1 f; shift
  for f; do sed $SED_B "$script" "$f" > "$f.sedi" && cat "$f.sedi" > "$f" && rm -f "$f.sedi" || return; done
}

# lines - number of lines on stdin, without the blanks BSD wc puts in front
lines() { wc -l | tr -d ' '; }

# oneline - join the lines of stdin with blanks ("a\nb\n" -> "a b ")
oneline() { tr '\n' ' '; }

# changes - only the changed lines of a diff on stdin, joined ("-b +B ")
changes() { grep -E '^[-+][^-+]' | oneline; }

# new_repo DIR - create a repository with an empty initial commit, cd into it
new_repo() { git init -q "$1" && cd "$1" && git commit -q --allow-empty -m init; }


# =============================================================================
section "1. Basic workflow: add, status, pull, merge, conflict, hooks"
# =============================================================================

# upstream: lib.c with lines a..g; upstream.git: the "server"
git init -q upstream
(cd upstream && printf 'a\nb\nc\nd\ne\nf\ng\n' > lib.c && git add . && git commit -qm "initial lib")
git clone -q --bare upstream upstream.git
git -C upstream.git config uploadpack.allowFilter true    # allow blobless clones
git -C upstream remote add origin "$T/upstream.git"
git -C upstream fetch -q
URL=$TURL/upstream.git

# up SED-EXPR MESSAGE - change lib.c upstream, commit and push
up() { (cd "$T/upstream" && sedi "$1" lib.c && git commit -qam "$2" && git push -q origin main); }

# downstream: links upstream's lib.c as src/lib.c
new_repo downstream
# like cp: the directory of FILE must exist (pull and restore create it)
check "add: a missing directory is refused" \
  "$(git filesync add "$URL" src/lib.c -p lib.c 2>&1 | grep -c "^error: directory 'src' does not exist$")" "1"
mkdir src
OUT=$(git filesync add "$URL" src/lib.c -p lib.c 2>&1)
check "--help: basic and advanced commands" \
  "$(git filesync -h | grep -E '^(basic commands|advanced commands):$|^  (status|mv|set|hooks?) ' | cut -c1-8 | oneline)" \
  "basic co   status   mv     advanced   set      hooks  "
check "command help repeats the summary" "$(git filesync add -h | grep -c '^Link a file (or all files of a directory) to the upstream repository\.$')" "1"
check "add stages, like git add" "$(git status --porcelain | oneline)" "A  .git-filesync A  src/lib.c "
check "add: says how to commit" "$(echo "$OUT" | grep -cxE '    git commit|\(it offers the proposed commit message; a copy stays in \.git/FILESYNC_MSG\)')" "2"
check "add: copy of the proposed message" "$(cat .git/FILESYNC_MSG)" "$(cat .git/SQUASH_MSG)"
git commit -q --no-edit
check "add + commit: status clean" "$(st)" ""
check "add + commit: file and entry" "$(git show --name-only --format= HEAD | sort | oneline)" ".git-filesync src/lib.c "
check "add: proposed commit message" "$(git log -1 --format=%B | sed '/^$/d' | sed 's/@[0-9a-f]*$/@X/' | oneline)" \
  "[filesync] Add src/lib.c from $(basename "$T")/upstream@X Upstream: $URL (main:lib.c) "

# the blobless cache fetches missing file contents lazily, which needs
# protocol v2 - git-filesync asks for it even if v0 is configured
git config --global protocol.version 0
check "protocol.version=0 configured: add works" \
  "$( (new_repo "$T/sv0" && FILESYNC_CACHE=$T/cache-v0 git filesync add "$URL" x.c -p lib.c >/dev/null 2>&1; echo $?) )" "0"
git config --global --unset protocol.version

# two upstream commits -> pending; pull lists them in the commit message
up 's/^b$/B/' "Change B"
up 's/^c$/C/' "Change C"
check "pending count, relative path (from subdir)" \
  "$(cd src && git filesync status | grep -cE "^${TAB}pending:[[:space:]]+lib\.c  \(2 commits\)")" "1"
pullc src/lib.c >/dev/null
check "commit msg lists commits" "$(git log -1 --format=%B | grep -c '^- Change')" "2"
check "after pull" "$(st)" ""

# a committed local adaptation is kept by the next pull (3-way merge)
sedi 's/^g$/G-local/' src/lib.c
git commit -qam tweak
up 's/^a$/A/' "Change A"
check "pending + adapted" "$(st)" "PM"
pullc src/lib.c >/dev/null
check "clean merge result" "$(oneline < src/lib.c)" "A B C d e f G-local "

# local and upstream change of the same line -> conflict
sedi 's/^e$/E-local/' src/lib.c
git commit -qam "local e"
up 's/^e$/E-up/' "Change E"
check "conflict rc" "$(rc git filesync pull src/lib.c)" "1"
check "conflict markers" "$(grep -c '^<<<<<<<' src/lib.c)" "1"
check "conflict: message prepared for git commit" \
  "$(head -1 "$(git rev-parse --git-dir)/SQUASH_MSG" | grep -c '^\[filesync\] Sync src/lib.c from')" "1"
git checkout -q src/lib.c 2>/dev/null
git reset -q --hard
check "git reset drops the prepared message" "$(ls "$(git rev-parse --git-dir)/SQUASH_MSG" 2>/dev/null)" ""
check "... but the copy stays" "$(head -1 .git/FILESYNC_MSG | cut -d' ' -f1-3)" "[filesync] Sync src/lib.c"

# mapped to the local checkout, unpushed upstream commits are seen and warned
git filesync source map "$URL" "$T/upstream" >/dev/null
(cd "$T/upstream" && sedi 's/^f$/F/' lib.c && git commit -qam "unpushed F")
check "local checkout warns unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "1"
git filesync source map "$URL" --unset >/dev/null
check "--remote / unmapped ignores unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "0"
(cd "$T/upstream" && git push -q origin main)

# --commit with an older upstream commit syncs backwards (revert)
OLD=$(git -C "$T/upstream" rev-parse HEAD~3)
git reset -q --hard
quiet pullc --commit "$OLD" src/lib.c
check "revert message" "$(git log -1 --format=%B | grep -c 'Reverts upstream')" "1"

# a deleted linked file is an uncommitted change; pull --all leaves it alone
quiet pullc src/lib.c
rm src/lib.c
check "deleted file is an uncommitted change" "$(st)" " MD"
quiet pullc --all
check "pull --all leaves locally deleted file alone" \
  "$([ -e src/lib.c ] && echo restored || echo deleted)" "deleted"
git restore src/lib.c

# hooks: install and remove our own hook files; 'hooks' shows their state
check "hooks: none yet" "$(git filesync hooks | cut -d' ' -f1-3 | oneline)" "pre-push: not installed post-merge: not installed "
git filesync hooks install >/dev/null
check "hooks installed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | lines)" "2"
check "hooks: installed" "$(git filesync hooks | oneline)" "pre-push: installed post-merge: installed "
git filesync hooks uninstall >/dev/null
check "own hooks removed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | lines)" "0"
check "install-hooks is 'hooks install' now" "$(rc git filesync install-hooks)" "2"

# foreign hooks: hooks install leaves them alone and prints the lines to add.
# pre-push gets these lines added by hand, post-merge stays without them;
# hooks uninstall must remove only our lines.
printf '#!/bin/sh\necho mine\n' > .git/hooks/pre-push
chmod +x .git/hooks/pre-push
check "hooks: a foreign hook" "$(git filesync hooks | grep -c "^pre-push: hook of another tool, without our lines (add them with 'git filesync hooks install --force')$")" "1"
OUT=$(git filesync hooks install 2>/dev/null)
check "foreign pre-push: put our lines before git lfs" \
  "$(echo "$OUT" | grep -c '^pre-push: hook exists, add these lines to .*, before commands that read the pushed refs from stdin (e.g. git lfs pre-push):$')" "1"
echo "$OUT" | sed -n '/^# git-filesync/,/^git_filesync_refs_end$/p' >> .git/hooks/pre-push
printf '#!/bin/sh\necho other\n' > .git/hooks/post-merge
git filesync hooks uninstall >/dev/null
check "foreign hook: own lines removed" "$(cat .git/hooks/pre-push)" "$(printf '#!/bin/sh\necho mine')"
check "foreign hook: still executable" "$([ -x .git/hooks/pre-push ] && echo yes)" "yes"
check "foreign hook without snippet untouched" "$(cat .git/hooks/post-merge)" "$(printf '#!/bin/sh\necho other')"
rm -f .git/hooks/pre-push .git/hooks/post-merge

# hooks install --force adds our lines to a foreign hook, right after the #!
# line (before git lfs pre-push, which reads the refs from stdin)
printf '#!/bin/sh\ngit lfs pre-push "$@"\n' > .git/hooks/pre-push
chmod +x .git/hooks/pre-push
check "foreign hook: --force suggested" \
  "$(git filesync hooks install 2>/dev/null | grep -c "^(or run 'git filesync hooks install --force' to add them)$")" "1"
OUT=$(git filesync hooks install --force 2>/dev/null)
check "hooks install --force: lines added" "$(echo "$OUT" | grep -c '^pre-push: lines added to the existing hook$')" "1"
check "hooks install --force: our block first, the rest kept" \
  "$(head -2 .git/hooks/pre-push | cut -c1-14 | oneline)| $(tail -1 .git/hooks/pre-push)" "#!/bin/sh # git-filesync | git lfs pre-push \"\$@\""
check "hooks install --force again: nothing to do" "$(git filesync hooks install --force 2>/dev/null | grep -c 'already installed')" "2"
git filesync hooks uninstall >/dev/null
check "uninstall after --force: foreign lines kept" "$(cat .git/hooks/pre-push)" "$(printf '#!/bin/sh\ngit lfs pre-push "$@"')"
rm -f .git/hooks/pre-push

# hooks of an older version are updated in place, other lines kept
printf '#!/bin/sh\necho mine\n# git-filesync: old\ngit filesync hook post-merge </dev/null || true\nexit 0\n' \
  > .git/hooks/post-merge
check "hooks: an old hook of ours is outdated" "$(git filesync hooks | grep -c '^post-merge: outdated')" "1"
check "hooks install: old hook updated" "$(git filesync hooks install 2>/dev/null | grep -c '^post-merge: updated')" "1"
check "updated hook: new command, rest kept" "$(sed -n '2p;4,5p' .git/hooks/post-merge | oneline)" \
  "echo mine git filesync hook post-merge \"\$@\" </dev/null || true exit 0 "
check "hooks install again: nothing to do" "$(git filesync hooks install 2>/dev/null | grep -c 'already installed')" "2"
git filesync hooks uninstall >/dev/null

# a hook file we wrote (before 0.9.1: ending in exit 0) is rewritten without
# exit 0, so lines appended later (git lfs install's) run
printf '#!/bin/sh\n# git-filesync: old\ngit filesync hook pre-push "$@" || [ $? -ne 3 ] || exit 1\nexit 0\n' \
  > .git/hooks/pre-push
quiet git filesync hooks install
check "own old hook: exit 0 dropped" "$(head -1 .git/hooks/pre-push) $(grep -c '^exit 0' .git/hooks/pre-push)" "#!/bin/sh 0"
check "own old hook: refs block" "$(grep -c git_filesync_refs .git/hooks/pre-push)" "5"
git filesync hooks uninstall >/dev/null

# pre-push: a pushed file synced to an upstream commit that isn't on the
# server (pulled from an unpushed commit of the mapped checkout)
git filesync source map "$URL" "$T/upstream" >/dev/null
(cd "$T/upstream" && echo unpushed >> lib.c && git commit -qam "unpushed line")
check "pull from an unpushed upstream commit" "$(rc pullc --overwrite src/lib.c)" "0"
UNPUSHED=$(git -C "$T/upstream" rev-parse --short=12 HEAD)
PUSH="refs/heads/main $(git rev-parse HEAD) refs/heads/main 0000000000000000000000000000000000000000"
check "pre-push: unpushed upstream commit reported" "$(echo "$PUSH" | git filesync hook pre-push origin x 2>&1 \
  | grep -c "^filesync: src/lib.c: synced from upstream commit $UNPUSHED, which is not on the server")" "1"
check "pre-push: only a warning by default" "$(echo "$PUSH" | rc git filesync hook pre-push origin x)" "0"
check "pre-push: nothing pushed, nothing checked" \
  "$(git filesync hook pre-push origin x </dev/null 2>&1 | grep -c 'not on the server')" "0"
check "pre-push by hand (no arguments): checks HEAD" \
  "$(git filesync hook pre-push </dev/null 2>&1 | grep -c 'not on the server')" "1"
git config filesync.pushCheck off
check "pushCheck=off: no check" "$(echo "$PUSH" | git filesync hook pre-push origin x 2>&1 | grep -c 'not on the server')" "0"
git config filesync.pushCheck error
check "pushCheck=error: refused" "$(echo "$PUSH" | rc git filesync hook pre-push origin x)" "3"

# entries the remote already has are not checked again: those in the
# commit the push replaces ...
KNOWN=$(git rev-parse HEAD)
git commit -q --allow-empty -m "on top"
check "pre-push: entries of the replaced commit skipped" \
  "$(echo "refs/heads/main $(git rev-parse HEAD) refs/heads/main $KNOWN" | rc git filesync hook pre-push origin x)" "0"

# the installed hook: refuses with pushCheck=error, otherwise never blocks
git init -q --bare "$T/downstream-remote.git"
git remote add origin "$T/downstream-remote.git"
git filesync hooks install >/dev/null
check "new hook: no exit 0" "$(grep -c '^exit 0' .git/hooks/pre-push)" "0"
check "installed hook refuses the push" "$(rc git push -q origin HEAD:main)" "1"
check "push --no-verify skips the hook" "$(rc git push -q --no-verify origin HEAD:main)" "0"
# ... and those on the remote's remote-tracking branches (origin/main now)
check "pre-push: entries on the remote's branches skipped" "$(echo "$PUSH" | rc git filesync hook pre-push origin x)" "0"
check "pre-push: ... but checked for another remote" "$(echo "$PUSH" | rc git filesync hook pre-push other x)" "3"
git commit -q --allow-empty -m "after no-verify"
check "failing git-filesync doesn't block a push" "$(rc git -c alias.filesync='!exit 1' push -q origin HEAD:main)" "0"
git commit -q --allow-empty -m "once more"
(cd "$T/upstream" && git push -q origin main)
check "upstream pushed: not reported" "$(echo "$PUSH" | git filesync hook pre-push other x 2>&1 | grep -c 'not on the server')" "0"
check "upstream pushed: push goes through" "$(rc git push -q origin HEAD:main)" "0"
git config --unset filesync.pushCheck
# commands after our block (e.g. git lfs pre-push) still get the pushed refs;
# with nothing on stdin, they get nothing (not a blank line)
printf 'cat > "%s/after-refs"\n' "$T" >> .git/hooks/pre-push
git commit -q --allow-empty -m "for the stdin test"
quiet git push -q origin HEAD:main
check "pre-push: commands after our block get the refs" \
  "$(lines < "$T/after-refs") $(cut -d' ' -f2-3 "$T/after-refs")" "1 $(git rev-parse HEAD) refs/heads/main"
quiet .git/hooks/pre-push origin x </dev/null
check "pre-push: nothing in, nothing restored" "$(wc -c < "$T/after-refs" | tr -d ' ')" "0"
git filesync hooks uninstall >/dev/null
git remote remove origin
git filesync source map "$URL" --unset >/dev/null

# output into a pipe that is closed early
check "broken pipe no traceback" "$(git filesync status 2>&1 | head -1 | grep -c Traceback)" "0"


# =============================================================================
section "2. Line endings: CRLF upstream, repositories with different normalization"
# =============================================================================
cd "$T"

# upstream m has w.c committed with CRLF line endings
git init -q m
(cd m && printf 'a\r\nb\r\nc\r\nd\r\n' > w.c && git add . && git commit -qm init)
git clone -q --bare m m.git
git -C m remote add origin "$T/m.git"
git -C m fetch -q
URL2=$TURL/m.git

# The same scenario for a repository with core.autocrlf=true, one with
# '* text=auto' and one without any normalization: neither add nor pull
# nor a merge may produce eol warnings or spurious changes.
for mode in autocrlf textauto plain; do
  rm -rf s; git init -q s; cd s
  case $mode in
    autocrlf) git config core.autocrlf true ;;
    textauto) echo '* text=auto' > .gitattributes; git add .gitattributes ;;
  esac
  git commit -q --allow-empty -m i
  addc "$URL2" w.c
  check "$mode: clean after add" "$(st)" ""

  # upstream change; git's "CRLF will be replaced by LF" must not appear
  (cd ../m && printf 'a\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam B && git push -q origin main)
  W=$(pullc w.c 2>&1 >/dev/null | grep -c 'will be replaced')
  check "$mode: no eol warnings" "$W" "0"
  check "$mode: clean after pull" "$(st)" ""

  # local adaptation + upstream change -> merge
  sedi 's/^d/D-local/' w.c
  git commit -qam loc
  (cd ../m && printf 'A\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam A && git push -q origin main)
  check "$mode: merge rc" "$(rc pullc w.c)" "0"
  check "$mode: merged content" "$(git show HEAD:w.c | tr -d '\r' | oneline)" "A B c D-local "
  check "$mode: worktree clean" "$(git status --porcelain)" ""

  # status, diff and the hooks only read: they leave .git/objects alone, also
  # where they compare in this repository's form - checked in a fresh clone,
  # which lacks that form of the synced version (merged above)
  git clone -q --no-local . ../s2 && cd ../s2
  OBJ=$(git count-objects | cut -d' ' -f1)
  quiet git filesync status; quiet git filesync diff; quiet git filesync hook post-merge 0
  check "$mode: status, diff, hook write no objects" "$(git count-objects | cut -d' ' -f1)" "$OBJ"
  cd ../s; rm -rf ../s2

  # reset the upstream for the next mode
  cd ..
  git -C m reset -q --hard HEAD~2
  git -C m push -qf origin main
done


# =============================================================================
section "3. Branch name as --commit"
# =============================================================================
# --commit <branch> must use the branch's current head, not a stale ref
# remembered in the cache clone.

(cd m && git checkout -q -b develop && printf 'x\r\n' > w.c && git commit -qam d1 && git push -q origin develop)
rm -rf s
new_repo s
addc "$URL2" w.c
(cd ../m && printf 'y\r\n' > w.c && git commit -qam d2 && git push -q origin develop && git checkout -q main)
quiet pullc --commit develop w.c
check "--commit <branch> gets current head" "$(tr -d '\r' < w.c)" "y"


# =============================================================================
section "4. source map: mappings to local checkouts of an upstream"
# =============================================================================
cd "$T"
check "map is 'source map' now" "$(rc git filesync map)" "2"

# upstream m3 with x.c = v1; checkout coA has an unpushed v2, coB is at v1
git init -q m3
(cd m3 && echo v1 > x.c && git add . && git commit -qm v1)
git clone -q --bare m3 m3.git
URL3=$TURL/m3.git
git clone -q m3.git coA
(cd coA && echo v2 > x.c && git commit -qam v2)
git clone -q m3.git coB

# three repositories linking x.c
for s in sA sB sC; do
  (new_repo $s && addc "$URL3" x.c)
done

# sA -> coA (given as relative path from a subdirectory), sB -> coB
(cd sA && mkdir -p sub && cd sub && git filesync source map "$URL3" ../../coA >/dev/null)
(cd sB && git filesync source map "$URL3" "$T/coB" >/dev/null)
check "map default scope is repo-local" "$(git -C sA config --local --get-regexp '^filesync\.' | lines)" "1"
check "nothing written globally" "$(git config --global --get-regexp '^filesync\.' | lines)" "0"
check "repo A uses checkout A" "$(cd sA && st)" "P"
check "repo B uses checkout B" "$(cd sB && st)" ""
(cd sA && quiet pullc x.c)
check "repo A synced from checkout A" "$(cat sA/x.c)" "v2"

# global mapping (set from sC) -> coA; local mappings take precedence
(cd sC && git filesync source map --global "$URL3" "$T/coA" >/dev/null)
check "global mapping used without local one" \
  "$(cd sC && git filesync status -v | grep -c "via local checkout .*coA)")" "1"
check "local mapping overrides global" "$(cd sB && st)" ""
check "list marks overridden global" \
  "$(cd sB && git filesync source map | grep '^\[global\]' | grep -c overridden)" "1"
(cd sB && git filesync source map "$URL3" --unset >/dev/null)
check "after local unset, global applies" "$(cd sB && st)" "P"
check "local map outside repo fails" "$(rc git filesync source map "$URL3" "$T/coA")" "2"

# the name of a [source] instead of the URL: the mapping belongs to the URL
SRC3=$(git -C sB config -f .git-filesync file.x.c.source)
(cd sB && git filesync source map "$SRC3" "$T/coB" >/dev/null)
check "map SOURCE: mapping for its URL" \
  "$(cd sB && git filesync source map "$URL3" | grep -c "^\[local\] $URL3 -> .*coB$")" "1"
check "map SOURCE: listing by name" "$(cd sB && git filesync source map "$SRC3" | grep -c '^\[local\]')" "1"
(cd sB && git filesync source map "$SRC3" --unset >/dev/null)
check "map SOURCE --unset" "$(git -C sB config --local --get-regexp '^filesync\.' | lines)" "0"
check "map: mistyped source name refused" "$(cd sB && rc git filesync source map no-such-source "$T/coB")" "2"
check "map: nothing written for it" "$(git -C sB config --local --get-regexp '^filesync\.' | lines)" "0"

# A mapped repository follows the link's branch in the checkout (refs/heads/main),
# not whatever is checked out there.
(cd sB && git filesync source map "$URL3" "$T/coB" >/dev/null)
(cd coB && git tag v1 && echo v1b > x.c && git commit -qam v1b)         # local, unpushed
check "mapped: local branch commit pending" "$(cd sB && st)" "P"
(cd sB && quiet pullc x.c)
check "mapped: pulled local branch state" "$(cat sB/x.c)" "v1b"

(cd coB && git checkout -q -b feature && echo feat > x.c && git commit -qam feat)
check "mapped: other checked-out branch ignored" "$(cd sB && st)" ""
check "mapped: other checked-out branch warned" \
  "$(cd sB && git filesync status | grep -c "has feature checked out")" "1"
(cd sB && quiet pullc x.c)
check "mapped: pull does not take other branch" "$(cat sB/x.c)" "v1b"

(cd coB && git checkout -q main && git reset -q --hard v1)              # branch moved back
check "mapped: older branch state detected" "$(cd sB && st)" "O"
(cd sB && quiet pullc x.c)
check "mapped: synced back to older state" "$(cat sB/x.c)" "v1"
check "mapped: revert listed in message" "$(git -C sB log -1 --format=%B | grep -c '^- v1b')" "1"

# uncommitted changes in the checkout are warned about, never synced
echo dirty > coB/x.c
check "mapped: uncommitted upstream change warned" \
  "$(cd sB && git filesync status | grep -c 'uncommitted changes')" "1"
check "mapped: uncommitted change not synced" "$(cd sB && st)" ""
(cd coB && git checkout -q -- x.c)

# the checkout is only read: a file whose timestamp changed doesn't make
# git-filesync refresh (rewrite) the checkout's index, as `git diff` would
(cd coB && git update-index -q --refresh; touch -t 202001010000 x.c)
IDX=$(cksum < coB/.git/index)
check "mapped: timestamp change is no uncommitted change" \
  "$(cd sB && git filesync status | grep -c 'uncommitted changes')" "0"
check "mapped: checkout's index not rewritten" "$(cksum < coB/.git/index)" "$IDX"

# branch 'rel' only known as origin/rel in the checkout -> fallback
(cd coA && git push -q origin HEAD:rel)
(cd coB && git fetch -q)
git init -q sD
(cd sD && git commit -q --allow-empty -m i \
  && git filesync source map "$URL3" "$T/coB" >/dev/null \
  && addc -b rel "$URL3" x.c)
check "mapped: falls back to origin/<branch>" "$(cat sD/x.c)" "v2"
check "mapped: fallback noted" "$(cd sD && git filesync status | grep -c 'using origin/rel')" "1"
git filesync source map --global "$URL3" --unset >/dev/null


# =============================================================================
section "5. Offline operation"
# =============================================================================
cd "$T"

# add via a mapping to a server that cannot be reached; without -b the
# branch is taken from the checkout's origin/HEAD
OFF=https://unreachable.invalid/owner/m3.git
(cd coA && git remote set-head origin main >/dev/null 2>&1)
new_repo sOff
git filesync source map "$OFF" "$T/coA" >/dev/null
check "offline add via mapping (no -b)" "$(rc git filesync add "$OFF" x.c)" "0"
check "offline add: branch from checkout" \
  "$(git config -f .git-filesync --get-regexp "^source\..*\.branch" | cut -d" " -f2)" "main"
check "offline add: content from checkout" "$(cat x.c)" "v2"
git commit -q --no-edit

# All commands, including the pre-push hook, with network access forbidden
# (GIT_ALLOW_PROTOCOL=file: any http/https/ssh access fails loudly). Allowed
# on stderr are only the 'not pushed' warning and the hook's 'filesync: ...'
# lines - the push check asks the upstream server, which fails here and is
# reported ("Cloning" its cache first).
(cd "$T/coA" && echo v3 > x.c && git commit -qam v3)
git init -q --bare "$T/sOff-remote.git"
git remote add origin "$T/sOff-remote.git"
git filesync hooks install >/dev/null
ERR=$(
  export GIT_ALLOW_PROTOCOL=file
  {
    git filesync status
    git filesync status --no-fetch
    pullc x.c
    git filesync status
    pullc --all
    git commit -q --allow-empty -m p
    git push -q origin HEAD:main
    git filesync source map
  } 2>&1 >/dev/null | grep -vE 'not pushed|^filesync: |^Cloning '
)
check "offline: no errors/warnings in any command" "$ERR" ""
check "offline: pull got v3 from checkout" "$(cat x.c)" "v3"

# known URL, server gone, but a cache clone exists: add still works
cd "$T"
mv m3.git m3-away.git
new_repo sOff2
check "offline add via cache (no -b)" "$(rc git filesync add "$URL3" x.c)" "0"
check "offline add via cache: content" "$(cat x.c)" "v1"
cd "$T"
mv m3-away.git m3.git


# =============================================================================
section "6. diff / difftool / strict files"
# =============================================================================
cd "$T"

# Fake difftool: prints "TOOL <dir of LOCAL> <REMOTE>", so the checks see
# which files would be compared (LOCAL lives in a temp dir named after the
# synced version, REMOTE is the working file or a temp copy).
git config --global difftool.fake.cmd 'echo "TOOL $(basename "$(dirname "$LOCAL")") $REMOTE"'
git config --global diff.tool fake

# upstream m4 (only reachable via mapping) with lib/foo.c and lib/bar.h;
# s4 links them as src/foo.c and src/bar.h (strict)
git init -q m4
(cd m4 && mkdir lib && printf 'a\nb\nc\nd\ne\n' > lib/foo.c && printf 'x\n' > lib/bar.h \
  && git add . && git commit -qm init)
new_repo s4
git filesync source map file:///nowhere/m4.git "$T/m4" >/dev/null
mkdir src
addc file:///nowhere/m4.git src/foo.c -p lib/foo.c
addc file:///nowhere/m4.git src/bar.h -p lib/bar.h --strict

# diff: synced version <-> local file
check "diff: nothing when clean" "$(git filesync diff)" ""
sedi 's/^b$/B-local/' src/foo.c
git commit -qm 'adapt foo' src/foo.c
check "diff: shows local change" "$(git filesync diff | changes)" "-b +B-local "
check "diff: labels" "$(git filesync diff | grep -E '^(---|\+\+\+)' | oneline)" "--- synced/src/foo.c +++ local/src/foo.c "
check "diff: options after --" "$(git filesync diff -- --stat | head -1 | tr -s ' ')" " src/foo.c | 2 +-"

# --for-upstream: a patch that applies upstream, also after it moved on
git filesync diff --for-upstream > ../p4.patch
check "diff --for-upstream applies upstream" "$(cd ../m4 && git apply --check ../p4.patch && echo ok)" "ok"
check "diff --for-upstream: upstream paths, a/ b/" \
  "$(git filesync diff --committed --for-upstream | grep -E '^(---|\+\+\+)' | oneline)" "--- a/lib/foo.c +++ b/lib/foo.c "
check "diff --for-upstream not with --upstream" "$(rc git filesync diff --upstream --for-upstream)" "2"
(cd ../m4 && sedi 's/^e$/E-up/' lib/foo.c && git commit -qam "Change E")
check "diff --upstream" "$(git filesync diff --upstream | changes)" "-e +E-up "
check "apply -3 after upstream moved" \
  "$(cd ../m4 && git apply -3 ../p4.patch >/dev/null 2>&1 && sed -n 2p lib/foo.c; git reset -q --hard)" "B-local"

# difftool: the working file itself is passed, --upstream uses temp copies
check "difftool: real working file" "$(git filesync difftool -y src/foo.c | tr '\\' / \
  | grep -cE "^TOOL synced-$(git -C ../m4 rev-parse --short HEAD~1) .*/s4/src/foo\.c$")" "1"
check "difftool --upstream: temp copy" "$(git filesync difftool -y --upstream | grep -c "upstream-")" "1"

# difftool asks per file like 'git difftool' (bar.h comes before foo.c)
echo z >> src/bar.h
OUT=$(printf 'y\nn\n' | git filesync difftool)
check "difftool prompt: y then n" "$(echo "$OUT" | grep -c 'TOOL ') $(echo "$OUT" | grep -c 'TOOL.*bar.h')" "1 1"
check "difftool prompt text" "$(echo "$OUT" | grep -c "Viewing (2/2): 'src/foo.c'")" "1"
check "difftool prompt: Enter = yes" "$(printf '\n\n' | git filesync difftool | grep -c 'TOOL ')" "2"
check "difftool prompt: q quits" "$(printf 'q\n' | git filesync difftool | grep -c 'TOOL ')" "0"
check "difftool prompt: EOF quits" "$(git filesync difftool </dev/null | grep -c 'TOOL ')" "0"
check "difftool -y: no prompt" "$(git filesync difftool -y </dev/null | grep -c 'TOOL ')" "2"
check "difftool with file: asks too, like git difftool" "$(printf 'n\n' | git filesync difftool src/foo.c | grep -c 'TOOL ')" "0"
check "difftool -y --prompt: the last counts" "$(printf 'n\n' | git filesync difftool -y --prompt src/foo.c | grep -c 'TOOL ')" "0"
git config difftool.prompt false
check "difftool.prompt=false respected" "$(git filesync difftool </dev/null | grep -c 'TOOL ')" "2"
check "difftool --prompt beats difftool.prompt=false" "$(printf 'n\n' | git filesync difftool --prompt src/foo.c | grep -c 'TOOL ')" "0"
git config --unset difftool.prompt
check "difftool prompt names tool" "$(printf 'q\n' | git filesync difftool | grep -c "Launch 'fake'")" "1"
git checkout -q -- src/bar.h

# strict: any change of src/bar.h is a violation
check "strict file clean: no violation" "$(st src/bar.h)" ""
echo y >> src/bar.h
check "strict violation reported (uncommitted)" "$(git filesync status -s src/bar.h)" "  M src/bar.h  (strict!)"
check "strict violation in long format" \
  "$(git filesync status src/bar.h | grep -cE "^${TAB}modified:[[:space:]]+src/bar\.h  \(NOT ALLOWED: strict\)")" "1"
check "strict violation exit code" "$(rc git filesync status --exit-code src/bar.h)" "1"
check "strict violation in hook output" "$(git filesync hook pre-push origin x </dev/null 2>&1 | grep -c 'NOT ALLOWED')" "1"
check "pull refuses strict merge" "$(rc pullc src/bar.h)" "2"
check "strict refusal: how to go on" \
  "$(pullc src/bar.h 2>&1 | grep -c "discard them with 'git filesync restore -SW src/bar.h', or sync anyway with 'git filesync pull --overwrite src/bar.h'")" "1"
check "pull --all continues after strict error" "$(pullc --all 2>&1 | grep -c '^error:')" "0"
check "non-strict file merged by --all" "$(sed -n 2p src/foo.c; sed -n 5p src/foo.c)" "$(printf 'B-local\nE-up')"
git commit -qm "adapt bar" src/bar.h
check "strict violation (committed)" "$(git filesync status -s src/bar.h)" " M  src/bar.h  (strict!)"
check "status: restore hint for a strict file" \
  "$(git filesync status src/bar.h | grep -c 'use "git filesync restore -SW <file>..." to discard them')" "1"

# restore: back to the synced upstream version, like git restore (default:
# working tree; -S: the index; -S -W: both); nothing committed
OUT=$(git filesync restore src/bar.h)
check "restore: said so" "$(echo "$OUT" | grep -c '^src/bar.h: restored (nowhere/m4@')" "1"
check "restore: working tree is the base" "$(git filesync diff src/bar.h)" ""
check "restore: index untouched" "$(git status --porcelain src/bar.h)" " M src/bar.h"
check "restore again: nothing to do" "$(git filesync restore src/bar.h)" "src/bar.h: nothing to restore"
git checkout -q -- src/bar.h
quiet git filesync restore -S src/bar.h
check "restore -S: only the index" "$(git status --porcelain src/bar.h)" "MM src/bar.h"
check "restore -S: staged is the base" "$(git diff --cached HEAD~1 -- src/bar.h)" ""
git reset -q --hard
quiet git filesync restore -SW src/bar.h
check "restore -SW: both" "$(git status --porcelain src/bar.h)" "M  src/bar.h"
check "restore -SW again: nothing to do" "$(git filesync restore -SW src/bar.h)" "src/bar.h: nothing to restore"
git reset -q --hard
rm src/bar.h
quiet git filesync restore src
check "restore DIR: deleted file back" "$(git filesync diff src/bar.h) $(ls src/bar.h)" " src/bar.h"
git reset -q --hard
check "restore: not linked" "$(rc git filesync restore README)" "2"

# pull --overwrite restores the upstream version, in strict and other files
quiet pullc --overwrite src/bar.h
check "pull --overwrite restores" "$(cat src/bar.h)" "x"
check "overwrite commit message" "$(git log -1 --format=%s)" \
  "[filesync] Restore src/bar.h from nowhere/m4@$(git -C ../m4 log -1 --format=%h -- lib/bar.h)"
check "after overwrite clean" "$(st src/bar.h)" ""
sedi 's/^a$/A-local/' src/foo.c
git commit -qm 'adapt a' src/foo.c
quiet pullc --overwrite src/foo.c
check "--overwrite discards in non-strict file" "$(git filesync diff)" ""


# =============================================================================
section "7. .git-filesync registry: sources, rm, unlink, mv, commit consistency"
# =============================================================================
# (continues in s4)

# files from one upstream share one [source]; add accepts the source name
check "one [source] for files of one upstream" \
  "$(git config -f .git-filesync --get-regexp '^source\..*\.url' | lines)" "1"
SRC=$(git config -f .git-filesync --get-regexp '^source\..*\.url' | sed 's/^source\.\(.*\)\.url .*/\1/')
(cd ../m4 && printf 'n\n' > lib/new.h && sedi 's/^d$/D-up/' lib/foo.c && git add . && git commit -qm "add new.h")
# add only stages; the proposed message is prepared for a plain git commit
mkdir include
OUT=$(git filesync add "$SRC" include/new.h -p lib/new.h 2>&1)
check "add by source name" "$?" "0"
check "add by source name: same source" "$(git config -f .git-filesync file.include/new.h.source)" "$SRC"
check "add: staged, not committed" "$(git status --porcelain | oneline)" "M  .git-filesync A  include/new.h "
check "add: message prepared for git commit" \
  "$(head -1 "$(git rev-parse --git-dir)/SQUASH_MSG" | grep -c "^\[filesync\] Add include/new.h from $SRC@")" "1"

git commit -q
check "add: plain git commit takes the message" "$(git log -1 --format=%s | grep -c '^\[filesync\] Add include/new.h from')" "1"
check "commit drops the prepared message" "$(ls "$(git rev-parse --git-dir)/SQUASH_MSG" 2>/dev/null)" ""
check "registry committed with link" "$(git show --name-only --format= HEAD | sort | oneline)" ".git-filesync include/new.h "

# mv: moves file and entry
check "mv rc" "$(rc git filesync mv include/new.h include/renamed.h)" "0"
check "mv: file moved" "$(ls include)" "renamed.h"
check "mv: link moved (staged, not yet committed)" "$(git filesync status -s include/renamed.h)" "  ? include/renamed.h"
check "mv: old entry gone" "$(git config -f .git-filesync --get-regexp '^file\.include/new\.h\.' | lines)" "0"
git commit -qm mv

# directories: add and mv put files into existing ones only, like cp and
# git mv; add DIR may create DIR itself; pull and restore recreate them
check "mv: a missing directory is refused, like git mv" \
  "$(git filesync mv include/renamed.h nope/r.h 2>&1)-$(git status --porcelain)" \
  "error: destination directory does not exist, source=include/renamed.h, destination=nope/r.h-"
printf '*.gen\n' > .git/info/exclude
echo own > own.gen
check "add: an ignored file is linked and staged like any other" \
  "$(rc git filesync add "$SRC" own.gen -p lib/foo.c) $(git status --porcelain own.gen)" "0 A  own.gen"
git reset -q --hard && rm -f own.gen .git/info/exclude
check "add: a file where the directory should be" \
  "$(git filesync add -n "$SRC" include/renamed.h/x.h -p lib/foo.c 2>&1 | grep -c "^error: cannot add 'include/renamed.h/x.h': 'include/renamed.h' is not a directory$")" "1"
check "add DIR: a missing parent directory is refused" \
  "$(git filesync add -n "$SRC" nope/lib -p lib 2>&1 | grep -c "^error: directory 'nope' does not exist$")" "1"
check "add DIR: DIR itself may be new" "$(git filesync add -n "$SRC" newdir -p lib | grep -c '^would link newdir/')" "3"
rm -r include
check "restore: recreates a missing directory" "$(rc git filesync restore include/renamed.h) $(cat include/renamed.h)" "0 n"
git rm -q -r include && git commit -qm "include gone, its entry kept"
check "pull: recreates a missing directory" "$(rc git filesync pull include/renamed.h) $(cat include/renamed.h)" "0 n"
git reset -q --hard HEAD~1

# unlink: removes the entry, keeps the file; the last unlink removes the registry
{ printf '# my own note\n\n'; cat .git-filesync; } > "$T/reg" && cp "$T/reg" .git-filesync
git commit -qam "own comment"
check "unlink rc" "$(rc git filesync unlink include/renamed.h)" "0"
check "unlink: own comment and layout kept" "$(head -2 .git-filesync | oneline)" "# my own note  "
check "unlink: file kept" "$(cat include/renamed.h)" "n"
check "unlink: entry removed" "$(git filesync status include/renamed.h 2>&1 | grep -c 'not linked')" "1"
check "unlink: source kept while used" "$(git config -f .git-filesync --get-regexp '^source\.' | lines)" "2"
git commit -qm unlink
git filesync unlink src/foo.c src/bar.h >/dev/null
check "unlink all: registry removed" "$([ -e .git-filesync ] && echo exists || echo gone)" "gone"
check "unlink all: removal staged" "$(git status --porcelain .git-filesync)" "D  .git-filesync"
git reset -q --hard

# rm: removes file and entry, both staged, like git rm; refused (for all
# files) with uncommitted changes unless -f
echo more >> src/foo.c
check "rm: refused with uncommitted changes" "$(git filesync rm src 2>&1)" \
  "error: src/foo.c: has uncommitted changes - use -f to remove it anyway"
check "rm: refused, nothing removed" "$(ls src | oneline) $(git status --porcelain | oneline)" "bar.h foo.c   M src/foo.c "
check "rm -n" "$(git filesync rm -n -f src | sort | oneline)" "would remove src/bar.h would remove src/foo.c "
quiet git filesync rm -f src/foo.c
check "rm -f: file and entry removed, staged" "$(git status --porcelain | oneline)" "M  .git-filesync D  src/foo.c "
check "rm: entry gone" "$(git config -f .git-filesync --get-regexp '^file\.src/foo\.c\.' | lines)" "0"
rm src/bar.h
check "rm: file gone already" "$(git filesync rm src/bar.h)" "removed src/bar.h"
check "rm: last one removes the registry" "$(git status --porcelain | oneline)" "D  .git-filesync D  src/bar.h D  src/foo.c "
git reset -q --hard

# a new [source] is keyed 'owner/repo' after its URL; another URL with the
# same key gets a number appended instead of reusing the existing source
check "source key from URL" "$SRC" "nowhere/m4"
git filesync source map file:///other/nowhere/m4.git "$T/m4" >/dev/null
check "add: output shows the new key" \
  "$(git filesync add file:///other/nowhere/m4.git include/other.h -p lib/bar.h 2>&1 | grep -c '^linked include/other.h -> nowhere/m4-2:lib/bar.h (main)')" "1"
check "same key, other URL: own source" \
  "$(git config -f .git-filesync source.nowhere/m4-2.url)" "file:///other/nowhere/m4.git"
check "same key, other URL: existing source unchanged" \
  "$(git config -f .git-filesync source.nowhere/m4.url)" "file:///nowhere/m4.git"
check "same key, other URL: file uses the new source" \
  "$(git config -f .git-filesync file.include/other.h.source)" "nowhere/m4-2"
git reset -q --hard

# the source is found by URL, whatever its key; status and pull show the key
BASE=$(git rev-parse HEAD)
git config -f .git-filesync --rename-section source.nowhere/m4 source.mylib
git config -f .git-filesync file.src/foo.c.source mylib
git config -f .git-filesync file.src/bar.h.source mylib
git commit -qam "rename source"
check "status -v: source key as label" \
  "$(git filesync status -v | grep -c 'src/foo.c *(from mylib:lib/foo.c (main)')" "1"
quiet pullc src/foo.c
check "pull: source key in commit message" \
  "$(git log -1 --format=%s)" "[filesync] Sync src/foo.c from mylib@$(git -C ../m4 log -1 --format=%h -- lib/foo.c)"
addc file:///nowhere/m4.git include/x.h -p lib/bar.h
check "add finds the source by URL, not by key" \
  "$(git config -f .git-filesync file.include/x.h.source)" "mylib"
check "add by URL: no new source" "$(git config -f .git-filesync --get-regexp '^source\..*\.url' | lines)" "1"

# add over an existing, different file: message notes modifications and strict
echo mine > include/y.h
addc --strict mylib include/y.h -p lib/bar.h
check "add existing file: subject" "$(git log -1 --format=%s | sed 's/@[0-9a-f]*$//')" "[filesync] Link include/y.h to mylib"
check "add existing file: notes" \
  "$(git log -1 --format=%B | grep -cE '^(Contains local modifications|Strict:)')" "2"
check "add existing file: committed as is" "$(git show HEAD:include/y.h)" "mine"
check "add existing file: warned" \
  "$(git filesync add -n --force mylib include/y.h -p lib/bar.h 2>&1 | grep -c '^warning: include/y.h differs from upstream .*--overwrite')" "1"
# --overwrite replaces it with the upstream version; --force: it is linked already
check "add --overwrite of a linked file needs --force" "$(rc git filesync add --overwrite mylib include/y.h -p lib/bar.h)" "2"
quiet git filesync add --force --overwrite mylib include/y.h -p lib/bar.h
git commit -q --no-edit
check "add --overwrite: upstream content" "$(cat include/y.h)" "$(git -C ../m4 show main:lib/bar.h)"
check "add --overwrite: unmodified" "$(st include/y.h)" ""
check "add --overwrite: message" \
  "$(git log -1 --format=%B | sed 's/@[0-9a-f]*$//' | grep -cE '^(\[filesync\] Relink include/y.h to mylib|The existing file was replaced by the upstream version\.)$')" "2"

# pull never commits, so never starts an editor
(cd ../m4 && sedi 's/^D-up$/D-up2/' lib/foo.c && git commit -qam "foo up2")
check "pull: no editor, exit 0" "$(GIT_EDITOR=false rc git filesync pull src/foo.c)" "0"
check "pull: staged" "$(git status --porcelain | oneline)" "M  .git-filesync M  src/foo.c "
git reset -q --hard "$BASE"


# =============================================================================
section "8. Colors"
# =============================================================================
# (continues in s4)

ESC=$(printf '\033')
check "no color when piped" "$(git filesync status | grep -c "$ESC")" "0"
check "--color=always" "$(git filesync status --color=always | grep -q "$ESC" && echo yes)" "yes"
check "--color alone: always, like git" "$(git filesync status --color | grep -q "$ESC" && echo yes)" "yes"
check "--color takes no path as its value" "$(rc git filesync status --color src/foo.c)" "0"
check "color.ui=always via git -c" "$(git -c color.ui=always filesync status | grep -q "$ESC" && echo yes)" "yes"
check "color.filesync=never beats color.ui" \
  "$(git -c color.ui=always -c color.filesync=never filesync status | grep -c "$ESC")" "0"
check "NO_COLOR" "$(NO_COLOR=1 git -c color.ui=always filesync status | grep -c "$ESC")" "0"
check "colored error on stderr" "$(git filesync pull nothere --color=always 2>&1 | grep -c "${ESC}\[1;31merror:")" "1"


# =============================================================================
section "9. status like 'git status', pull like 'git pull'"
# =============================================================================
cd "$T"

# upstream m5 with a.c .. e.c (lines 1..5), all linked in s5; e.c is strict
git init -q m5
(cd m5 && for f in a b c d e; do printf '1\n2\n3\n4\n5\n' > $f.c; done && git add . && git commit -qm i)
new_repo s5
git filesync source map file:///nowhere/m5.git "$T/m5" >/dev/null
for f in a b c d e; do
  quiet git filesync add file:///nowhere/m5.git $f.c
done
git config -f .git-filesync file.e.c.strict true
git add .git-filesync
git commit -qm link
check "status: clean summary" "$(git filesync status)" "nothing to sync, all 5 linked files unmodified"
check "status -s: nothing when clean" "$(git filesync status -s)" ""

# one file per combination of the three status columns:
#   a.c  pending                 d.c  pending + uncommitted change
#   b.c  pending + adapted       e.c  adapted (strict -> violation)
#   c.c  adapted + uncommitted change
(cd ../m5 && sedi 's/^5$/5-up/' a.c b.c d.c && git commit -qam up)
sedi 's/^1$/1-adapt/' b.c c.c e.c; git commit -qam adapt          # committed adaptations
sedi 's/^3$/3-wip/' c.c d.c                                          # uncommitted changes
check "status -s: three columns" "$(git filesync status -s | tr '\n' '|')" \
  "P   a.c|PM  b.c| MM c.c|P M d.c| M  e.c  (strict!)|"

# long format: sections like git status
OUT=$(git filesync status)
check "status: upstream section" "$(echo "$OUT" | grep -A5 '^Upstream changes to sync:' | grep -cE "^${TAB}pending:")" "3"
check "status: upstream hints, diff first" "$(echo "$OUT" | grep -A2 '^Upstream changes to sync:' | sed 1d | oneline)" \
  '  (use "git filesync diff --upstream <file>..." to see what pull would bring)   (use "git filesync pull <file>..." to sync) '
check "status: commit count" "$(echo "$OUT" | grep -cE "^${TAB}pending:[[:space:]]+b\.c  \(1 commit\)")" "1"
check "status: adapted section" "$(echo "$OUT" | grep -A6 '^Locally adapted files:' | grep -cE "^${TAB}adapted:")" "3"
check "status: strict note on adapted" "$(echo "$OUT" | grep -cE "^${TAB}adapted:[[:space:]]+e\.c  \(NOT ALLOWED: strict\)")" "1"
check "status: uncommitted section" "$(echo "$OUT" | grep -A5 '^Uncommitted changes:' | grep -cE "^${TAB}modified:")" "2"
check "status: no 'nothing to sync' when pending" "$(echo "$OUT" | grep -c 'nothing to sync')" "0"
check "status: exit code 0 like git" "$(rc git filesync status)" "0"
check "status --exit-code" "$(rc git filesync status --exit-code)" "1"
check "status: advice.statusHints=false" "$(git -c advice.statusHints=false filesync status | grep -c '(use ')" "0"
check "status -v: all files listed" \
  "$(git filesync status -v | grep -A6 '^Linked files:' | grep -cE "^${TAB}(unmodified|adapted):")" "5"
check "hook: adapted alone is quiet" "$(git filesync hook pre-push origin x </dev/null 2>&1 | grep -c 'c\.c')" "0"

# pull refuses to overwrite uncommitted changes (like git pull)
check "pull refuses uncommitted changes" "$(rc pullc d.c)" "2"
check "pull refusal message" "$(pullc d.c 2>&1 | grep -c "would be overwritten by pull - commit or stash them first ('git stash'")" "1"
check "refused pull leaves file alone" "$(oneline < d.c)" "1 2 3-wip 4 5 "
check "--autostash is gone" "$(rc pullc --autostash d.c)" "2"
check "--remote is gone" "$(rc git filesync status --remote)" "2"
quiet pullc b.c
check "pull merges committed adaptation" "$(oneline < b.c)" "1-adapt 2 3 4 5-up "

# pull only stages, like git merge --squash; a plain git commit takes the
# proposed message
OUT=$(git filesync pull a.c)
check "pull: staged, not committed" "$(git status --porcelain a.c .git-filesync | oneline)" "M  .git-filesync M  a.c "
check "pull: says how to commit" "$(echo "$OUT" | grep -cx '    git commit')" "1"
check "--no-commit and --no-edit are gone" "$(rc git filesync pull --no-commit a.c)|$(rc git filesync pull --no-edit a.c)" "2|2"
git commit -q
check "pull: plain git commit takes the message" \
  "$(git log -1 --format=%B | grep -cE '^(\[filesync\] Sync a\.c from |- up \()')" "2"

# diff --committed: without uncommitted changes; diff exit code passed on
check "diff --committed: adaptations only" \
  "$(git filesync diff --committed -- --stat | tail -1 | grep -o '[0-9]* files changed')" "3 files changed"
check "diff --committed: no wip" "$(git filesync diff --committed c.c | grep -c 3-wip)" "0"
check "diff: includes wip" "$(git filesync diff c.c | grep -c 3-wip)" "1"
check "diff -- --exit-code: no difference" "$(rc git filesync diff a.c -- --exit-code)" "0"
check "diff -- --exit-code: difference" "$(rc git filesync diff c.c -- --exit-code)" "1"

# one pull, one commit: the files share it, each with a section of its own
(cd ../m5 && sedi 's/^4$/4-up/' a.c b.c && git commit -qam up4)
N=$(git rev-list --count HEAD)
quiet pullc a.c b.c
check "pull of two files: one commit" "$(( $(git rev-list --count HEAD) - N ))" "1"
check "pull of two files: subject" "$(git log -1 --format=%s | sed 's/ from .*//')" "[filesync] Sync 2 files"
check "pull of two files: a section each" "$(git log -1 --format=%B | grep -cE '^Sync (a|b)\.c from ')" "2"
check "pull of two files: both in the commit" "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" ".git-filesync a.c b.c "
# a merge conflict in one of them: nothing committed, the others stay staged
(cd ../m5 && sedi 's/^1$/1-up/' a.c b.c && git commit -qam up3)
N=$(git rev-list --count HEAD)
OUT=$(pullc a.c b.c); RC=$?
check "conflict: nothing committed, exit 1" "$(( $(git rev-list --count HEAD) - N ))-$RC" "0-1"
check "conflict: the others staged" "$(git status --porcelain a.c b.c .git-filesync | oneline)" "M  .git-filesync M  a.c  M b.c "
check "conflict: how to go on" "$(echo "$OUT" | grep -cE '^    (git add b\.c|git commit)$')" "2"
printf '1-both\n2\n3\n4-up\n5-up\n' > b.c
git add b.c && git commit -q --no-edit
check "conflict resolved: one commit for both" "$(git log -1 --format=%B | grep -cE '^Sync (a|b)\.c from ')" "2"


# =============================================================================
section "10. Robustness: unsafe registry paths, special file names, odd entries"
# =============================================================================
cd "$T"

# upstream m6: a.txt, sub/s.txt and a file name with glob characters
git init -q m6
(cd m6 && mkdir sub && echo a > a.txt && echo s > sub/s.txt && echo f > 'f[1].txt' \
  && git add . && git commit -qm i)
M6=$(git -C m6 rev-parse HEAD)
B6=$(git -C m6 rev-parse HEAD:a.txt)
new_repo s6
git filesync source map file:///nowhere/m6.git "$T/m6" >/dev/null

# hand-written registry with entries pointing outside the work tree or into .git
printf '[source "m6"]\n\turl = file:///nowhere/m6.git\n\tbranch = main\n' > .git-filesync
for f in ../outside.txt "$T/abs.txt" .git/hooks/post-commit; do
  printf '[file "%s"]\n\tsource = m6\n\tpath = a.txt\n\tcommit = %s\n\tblob = %s\n' "$f" "$M6" "$B6" >> .git-filesync
done
git add .git-filesync
git commit -qm "unsafe entries"
check "unsafe paths: pull fails" "$(rc pullc --all)" "2"
check "unsafe paths: nothing written" "$(ls ../outside.txt "$T/abs.txt" .git/hooks/post-commit 2>/dev/null | lines)" "0"
check "unsafe paths: status errors" "$(git filesync status -s 2>/dev/null | grep -c '^E')" "3"
check "unsafe paths: removal hint" "$(git filesync status 2>&1 | grep -c 'remove-section')" "3"
git rm -q .git-filesync
git commit -qm "drop unsafe entries"

# the same paths given on the command line
check "add into .git refused" "$(rc git filesync add file:///nowhere/m6.git .git/x -p a.txt)" "2"
check "add outside refused" "$(rc git filesync add file:///nowhere/m6.git ../x -p a.txt)" "2"
# an upstream file added to an existing directory goes into it, like cp
mkdir d
quiet git filesync add file:///nowhere/m6.git d -p a.txt
check "add FILE into existing directory" "$(git config -f .git-filesync file.d/a.txt.path)" "a.txt"
git reset -q --hard
# an upstream directory links the files below it
check "upstream path is a directory" "$(git filesync add -n file:///nowhere/m6.git x.txt -p sub | cut -d' ' -f1-5)" \
  "would link x.txt/s.txt -> nowhere/m6:sub/s.txt"
check "upstream path with backslashes (copied on Windows)" \
  "$(git filesync add -n file:///nowhere/m6.git x.txt -p '.\sub\s.txt' | cut -d' ' -f1-5)" \
  "would link x.txt -> nowhere/m6:sub/s.txt"
addc file:///nowhere/m6.git a.txt
check "mv outside refused" "$(rc git filesync mv a.txt ../moved.txt)" "2"
check "mv outside: file stays" "$(ls a.txt ../moved.txt 2>/dev/null)" "a.txt"
check "map --unset without URL" "$(rc git filesync source map --unset)" "2"

# wildcard characters in a file name are taken literally: 'f[1].txt' must
# not match the unrelated file f1.txt
echo other > f1.txt
git add f1.txt
quiet fsd add file:///nowhere/m6.git 'f[1].txt'
git commit -qm link
echo changed > f1.txt
check "glob chars: other file's change not attributed" "$(fsd status -s 'f[1].txt' | cut -c1-3)" ""
(cd ../m6 && echo f2 > 'f[1].txt' && git commit -qam f2)
quiet fsd pull 'f[1].txt'; quiet git commit --no-edit
check "glob chars: pull commits only the file" \
  "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" ".git-filesync f[1].txt "
check "glob chars: other file stays uncommitted" "$(git status --porcelain f1.txt)" " M f1.txt"
git checkout -q -- f1.txt

# 'strict' without a value is true, as everywhere in git config
echo local >> a.txt
git commit -qam adapt
sedi '/^\[file "a.txt"\]/a\
strict' .git-filesync
check "bare 'strict' means true" "$(git filesync status -s a.txt)" " M  a.txt  (strict!)"
git checkout -q -- .git-filesync

# synced version not readable -> warning, not a silent 'adapted'; --overwrite recovers
git config -f .git-filesync 'file.f[1].txt.blob' 0123456789abcdef0123456789abcdef01234567
check "base unavailable: warned" \
  "$(git filesync status 2>&1 | grep -c 'synced version 0123456789ab not available')" "1"
quiet fsd pull --overwrite 'f[1].txt'; quiet git commit --no-edit
check "base unavailable: --overwrite recovers" "$(fsd status -s 'f[1].txt' | cut -c1-3)" ""

# mapped checkout with a remote but no origin/HEAD: the default branch is a
# guess (the checked-out branch), and add says so
cd "$T"
git clone -q m6 co6
(cd co6 && git remote set-head origin -d && git checkout -q -b feature)
new_repo s7
git filesync source map file:///nowhere/m6.git "$T/co6" >/dev/null
check "default branch guessed: warned" \
  "$(git filesync add file:///nowhere/m6.git a.txt 2>&1 | grep -c "using its checked-out branch 'feature'")" "1"


# =============================================================================
section "11. Recorded commit: the one that produced the synced version"
# =============================================================================
# The registry records the upstream commit that last changed the file, not
# the branch tip; commits not touching the file are ignored everywhere.
cd "$T"

# m7.git (bare) and checkout co7: "f v1" changes f.txt, "other 1" only o.txt
git init -q --bare m7.git
git -C m7.git config uploadpack.allowFilter true
git clone -q m7.git co7 2>/dev/null
(cd co7 && echo v1 > f.txt && echo o1 > o.txt && git add . && git commit -qm "f v1" \
  && echo o2 > o.txt && git commit -qam "other 1" && git push -q origin main)
URL7=$TURL/m7.git

# rec - the commit recorded for f.txt
rec() { git config -f .git-filesync file.f.txt.commit; }

new_repo s8
addc "$URL7" f.txt
check "add (new file): commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"
quiet git filesync add --force "$URL7" f.txt
check "relink unchanged file: registry unchanged" "$(git status --porcelain)" ""
quiet git filesync add --force --commit "$(git -C ../co7 rev-parse HEAD)" "$URL7" f.txt
check "add --commit tip: commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"

# "f v2" changes f.txt, "other 2" does not
(cd ../co7 && echo v2 > f.txt && git commit -qam "f v2" && echo o3 > o.txt && git commit -qam "other 2" \
  && git push -q origin main)
check "status counts only commits changing the file" "$(git filesync status | grep -c '(1 commit)')" "1"
quiet pullc f.txt
check "pull: commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"
check "pull message: names that commit" \
  "$(git log -1 --format=%s | grep -c "@$(git -C ../co7 rev-parse --short HEAD~1)$")" "1"
check "pull message: only commits changing the file" \
  "$(git log -1 --format=%B | grep '^- ' | tr '\n' '|')" "- f v2 ($(git -C ../co7 rev-parse --short HEAD~1))|"

# mapped: unpushed commits matter only if they change the file
git filesync source map "$URL7" "$T/co7" >/dev/null
(cd ../co7 && echo o4 > o.txt && git commit -qam "other unpushed")
check "unpushed commit not touching the file: no warning" "$(git filesync status 2>&1 | grep -c 'not pushed')" "0"
check "unpushed other commit: still up to date" "$(st)" ""
(cd ../co7 && echo v3 > f.txt && git commit -qam "f unpushed")
check "unpushed change of the file: warned" "$(git filesync status 2>&1 | grep -c 'not pushed')" "1"
git filesync source map "$URL7" --unset >/dev/null


# =============================================================================
section "12. Git LFS: upstream / downstream / both / neither, via mapping and via cache"
# =============================================================================
cd "$T"

if git lfs version >/dev/null 2>&1; then
  git lfs install --skip-repo >/dev/null

  # Every combination of: d.txt in LFS upstream (ulfs), in LFS downstream
  # (dlfs), upstream accessed via mapping or via cache clone (via).
  # Content must always be the real file, storage must follow the repository's
  # .gitattributes, diff and merge must work on the resolved content.
  for ulfs in yes no; do
    # upstream ml (checkout) / ml.git (bare): d.txt with lines l1..l5
    rm -rf ml ml.git
    git init -q --bare ml.git
    git clone -q ml.git ml 2>/dev/null
    (cd ml && { [ $ulfs = yes ] && git lfs track d.txt >/dev/null; true; } \
       && printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt && git add . && git commit -qm v1 && git push -q origin main 2>/dev/null)

    for dlfs in yes no; do
      for via in map cache; do
        tag="lfs upstream=$ulfs downstream=$dlfs via=$via"
        lfs_count=$([ $dlfs = yes ] && echo 1 || echo 0)   # expected LFS pointers downstream

        # fresh repository (and fresh cache) linking d.txt
        rm -rf sl "$T/cache"; git init -q sl; cd sl
        [ $dlfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        git commit -q --allow-empty -m i
        [ $via = map ] && git filesync source map "$TURL/ml.git" "$T/ml" >/dev/null
        addc "$TURL/ml.git" d.txt
        check "$tag: content after add" "$(head -1 d.txt)" "l1"
        check "$tag: downstream storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$lfs_count"
        check "$tag: clean" "$(st)" ""

        # upstream change of l5, local change of l1 -> diff and merge
        (cd "$T/ml" && sedi 's/^l5$/L5-up/' d.txt && git commit -qam l5 && git push -q origin main 2>/dev/null)
        sedi 's/^l1$/L1-local/' d.txt
        git commit -qam loc
        check "$tag: diff" "$(git filesync diff | changes)" "-l1 +L1-local "
        check "$tag: diff --upstream" "$(git filesync diff --upstream | changes)" "-l5 +L5-up "
        quiet pullc d.txt
        check "$tag: merged" "$(oneline < d.txt)" "L1-local l2 l3 l4 L5-up "
        check "$tag: committed storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$lfs_count"
        check "$tag: after merge (adapted, clean worktree)" "$(st) $(git status --porcelain)" " M "

        # add over an existing file: an older upstream version differs from
        # the base (the head), the same content doesn't (LFS or not);
        # --overwrite takes the upstream version, stored as configured here
        cd ..; rm -rf sl2; git init -q sl2; cd sl2
        [ $dlfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt
        git add .
        git commit -qm i
        [ $via = map ] && git filesync source map "$TURL/ml.git" "$T/ml" >/dev/null
        check "$tag: add over an older version: differs from the head" \
          "$(git filesync add "$TURL/ml.git" d.txt 2>&1 | grep -c 'd.txt differs from upstream')" "1"
        git reset -q --hard
        quiet git filesync add --overwrite "$TURL/ml.git" d.txt
        git commit -q --no-edit
        check "$tag: add --overwrite: upstream content" "$(oneline < d.txt)" "l1 l2 l3 l4 L5-up "
        check "$tag: add --overwrite: storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$lfs_count"
        check "$tag: add --overwrite: clean" "$(st)" ""
        quiet git filesync unlink d.txt; git commit -qam unlink
        check "$tag: add over the same content: no warning" \
          "$(git filesync add "$TURL/ml.git" d.txt 2>&1 | grep -c 'differs')" "0"
        cd ..

        # reset the upstream for the next combination
        (cd ml && git reset -q --hard HEAD~1 && git push -qf origin main 2>/dev/null)
      done
    done
  done

  # LFS content unavailable -> clear error instead of a pointer file
  rm -rf sl "$T/cache"
  new_repo sl
  (cd ../ml && git lfs track d.txt >/dev/null && git add . && git commit -qm lfs && git push -q origin main 2>/dev/null)
  ERR=$(GIT_LFS_SKIP_SMUDGE=1 git filesync add "$TURL/ml.git" d.txt 2>&1)
  check "lfs unavailable: add fails" "$(echo "$ERR" | grep -c 'stored in Git LFS')" "1"
  check "lfs unavailable: no pointer file written" "$([ -e d.txt ] && echo written || echo none)" "none"

  # a mapped checkout without the LFS object: fetched into a temporary
  # store, nothing written into the checkout's .git/lfs
  git clone -q "$TURL/ml.git" "$T/mlfull" 2>/dev/null
  GIT_LFS_SKIP_SMUDGE=1 git clone -q "$TURL/ml.git" "$T/mlnolfs" 2>/dev/null
  rm -rf "$T/mlnolfs/.git/lfs"
  cd "$T" && new_repo slmap
  git filesync source map "$TURL/ml.git" "$T/mlnolfs" >/dev/null
  addc "$TURL/ml.git" d.txt
  check "lfs via mapping, object missing there: content" "$(cat d.txt)" "$(cat "$T/mlfull/d.txt")"
  check "lfs via mapping, object missing there: checkout untouched" \
    "$([ -e "$T/mlnolfs/.git/lfs" ] && echo written || echo none)" "none"
  cd "$T/sl"

  # pre-push hook shared with git lfs: our block first (as hooks install
  # says) - LFS must still get the pushed refs and upload its objects
  cd "$T"
  git init -q --bare lfsremote.git
  new_repo slh
  git lfs install --local >/dev/null 2>&1
  git lfs track '*.bin' >/dev/null
  head -c 2000 /dev/urandom > a.bin
  git add . && git commit -qm lfs
  git remote add origin "$T/lfsremote.git"
  { echo '#!/bin/sh'
    git filesync hooks install 2>/dev/null | sed -n '/^# git-filesync/,/^git_filesync_refs_end$/p'
    tail -n +2 .git/hooks/pre-push; } > hook.new
  mv hook.new .git/hooks/pre-push && chmod +x .git/hooks/pre-push
  quiet git push origin main
  N=$(find "$T/lfsremote.git/lfs/objects" -type f 2>/dev/null | lines)
  if [ "$N" = 0 ] && ! grep -q 'git lfs pre-push' .git/hooks/pre-push; then
    echo "skip: git lfs install wrote no pre-push hook"
  else
    check "hook with git lfs: our block first, LFS objects uploaded" "$N" "1"
  fi
else
  echo "skip Git LFS tests (git-lfs not installed)"
fi


# =============================================================================
section "13. Tags: files pinned to a tag"
# =============================================================================
cd "$T"

# m9.git (bare, the server) and checkout co9: t.c with lines 1..3, tag v1
git init -q --bare m9.git
git -C m9.git config uploadpack.allowFilter true
git clone -q m9.git co9 2>/dev/null
(cd co9 && printf '1\n2\n3\n' > t.c && git add . && git commit -qm v1 && git tag v1 \
  && git push -q origin main v1)
URL9=$TURL/m9.git

new_repo s9
addc --tag v1 "$URL9" t.c
SRC9=$(git config -f .git-filesync --get-regexp '^source\..*\.url' | sed 's/^source\.\(.*\)\.url .*/\1/')
check "add --tag: the source has the branch, the file the tag" \
  "$(git config -f .git-filesync --get-regexp '^source\.' | cut -d' ' -f1 | sed 's/.*\.//' | sort | oneline)$(git config -f .git-filesync file.t.c.tag)" "branch url v1"
check "add --tag: message names the tag" "$(git log -1 --format=%B | grep -c "^Upstream: $URL9 (v1:t.c)$")" "1"
check "status -v shows the tag" "$(git filesync status -v | grep -c '(tag v1 on main)')" "1"

# a newer commit on the branch doesn't concern the pinned file
(cd ../co9 && sedi 's/^3$/3b/' t.c && git commit -qam "on main" && git push -q origin main)
check "tag: branch commits ignored" "$(st)" ""

# the tag is in the cache: nothing is fetched, works without the server
mv ../m9.git ../m9-away.git
check "tag: no fetch needed (server gone)" "$(git filesync status 2>&1)" "nothing to sync, 1 linked file unmodified"
mv ../m9-away.git ../m9.git

# new tag v2: set --tag stages the change, the missing tag is fetched
(cd ../co9 && git tag v2 && git push -q origin v2)
git filesync set t.c --tag v2 >/dev/null
check "set --tag: tag replaced" "$(git config -f .git-filesync file.t.c.tag)" "v2"
check "set --tag: registry staged" "$(git status --porcelain .git-filesync)" "M  .git-filesync"
git commit -qm "pin v2"
check "new tag: pending" "$(st)" "P"
quiet pullc t.c
check "pull to the new tag" "$(oneline < t.c)" "1 2 3b "

# with a mapped checkout the tag is taken from there, its branch ignored
git filesync source map "$URL9" "$T/co9" >/dev/null
(cd ../co9 && sedi 's/^1$/1c/' t.c && git commit -qam "after v2")
check "mapped: branch ignored" "$(st)" ""
check "mapped: no checked-out warning for a tag" "$(git filesync status 2>&1 | grep -c 'checked out')" "0"
(cd ../co9 && git tag v3)
git filesync set t.c --tag v3 >/dev/null
check "mapped: tag from the checkout" "$(st)" "P"
git filesync source map "$URL9" --unset >/dev/null
check "tag unknown on the server: error" "$(st)" "E"

# back to following the branch: set --no-tag; a tag not upstream is refused
check "set --tag: a missing tag is refused" "$(rc git filesync set t.c --tag v9)" "2"
check "set: --tag and --no-tag exclude each other" "$(rc git filesync set t.c --tag v2 --no-tag)" "2"
git filesync set t.c --no-tag >/dev/null
check "set --no-tag: follows the branch again" "$(git config -f .git-filesync file.t.c.tag)|$(st)" "|"
check "source set-branch needs the branch" "$(rc git filesync source set-branch "$SRC9")" "2"
check "source set-tag is gone" "$(rc git filesync source set-tag "$SRC9" v2)" "2"
git commit -qm "follow main"

# a tag in a [source] (before 0.14) is an error, with a hint
git config -f .git-filesync "source.$SRC9.tag" v1
check "tag in a source: error" "$(st)|$(git filesync status 2>&1 | grep -c "tag in \[source \"$SRC9\"\] is no longer supported")" "E|1"
git checkout -q .git-filesync


# =============================================================================
section "14. source: list, rename and change sources"
# =============================================================================
# (continues in s9)

check "source: lists the keys" "$(git filesync source)" "$SRC9"
check "source -v" "$(git filesync source -v)" "$(printf '%s\t%s (main, 1 file)' "$SRC9" "$URL9")"
check "source: unknown name" "$(rc git filesync source set-url nope file:///x)" "2"

git filesync source rename "$SRC9" lib9 >/dev/null
check "rename: section renamed" "$(git config -f .git-filesync source.lib9.url)" "$URL9"
check "rename: files follow" "$(git config -f .git-filesync file.t.c.source)" "lib9"
check "rename: old section gone" "$(git config -f .git-filesync --get-regexp "^source\.$SRC9\." | lines)" "0"
check "rename: status works" "$(st)" ""
git commit -qm "rename source"

git filesync source set-url lib9 "$URL9/" >/dev/null
check "set-url" "$(git config -f .git-filesync source.lib9.url)" "$URL9/"
check "set-url: status works" "$(st)" ""

# set -b: another branch of the same upstream for some files - they move to
# the source for URL and branch (created); a source left without files is
# removed; one that would duplicate another is refused
(cd ../co9 && git push -q origin main:dev)
quiet git filesync add lib9 u.c -p t.c
git commit -qm "u.c"
quiet git filesync set u.c -b dev
SRCD=$(git config -f .git-filesync file.u.c.source)
check "set -b: a new source for the branch" \
  "$(git config -f .git-filesync source.$SRCD.branch) $(git config -f .git-filesync source.$SRCD.url) $(git config -f .git-filesync file.t.c.source)" "dev $URL9/ lib9"
check "set -b: a missing branch is refused" "$(rc git filesync set u.c -b nope)" "2"
check "set-branch: duplicate refused" "$(rc git filesync source set-branch "$SRCD" main)" "2"
check "rename: existing name refused" "$(rc git filesync source rename "$SRCD" lib9)" "2"
check "set -b back: joins the source again, the empty one goes" \
  "$(git filesync set u.c -b main -n)" "would: u.c: source $SRCD -> lib9"
git commit -qm "u.c on dev"

# add by name: exactly that source; -b may only repeat its branch. A tag
# pins the file, the source stays as it is.
quiet git filesync add "$SRCD" w.c -p t.c
check "add by name: that source" "$(git config -f .git-filesync file.w.c.source)" "$SRCD"
check "add by name, other branch: refused" "$(rc git filesync add -b main "$SRCD" x.c -p t.c)" "2"
check "add by name, same branch repeated" "$(rc git filesync add -b dev "$SRCD" y.c -p t.c)" "0"
quiet git filesync add --tag v1 lib9 v1.c -p t.c
check "add by name with a tag: the file pinned" \
  "$(git config -f .git-filesync file.v1.c.source) $(git config -f .git-filesync file.v1.c.tag)" "lib9 v1"
check "add by name with a tag: content at the tag" "$(oneline < v1.c)" "1 2 3 "
quiet git filesync add --force --tag v2 lib9 v1.c -p t.c
check "relink with another tag" "$(git config -f .git-filesync file.v1.c.tag)" "v2"
printf '[source "dup"]\n\turl = %s\n\tbranch = main\n' "$URL9" >> .git-filesync
quiet git filesync add dup v.c -p t.c
check "add by name: that source, not an equal one" "$(git config -f .git-filesync file.v.c.source)" "dup"

# add by URL: the source with that URL and branch (default: remote HEAD)
quiet git filesync add "$URL9" a.c -p t.c
check "add by URL, default branch: source reused" "$(git config -f .git-filesync file.a.c.source)" "lib9"
quiet git filesync add "$URL9" b.c -p t.c --tag v1
check "add by URL + tag: the branch's source, the file pinned" \
  "$(git config -f .git-filesync file.b.c.source) $(git config -f .git-filesync file.b.c.tag)" "lib9 v1"
check "two adds: both messages prepared" \
  "$(grep -cE '^\[filesync\] Add (a|b)\.c from' "$(git rev-parse --git-dir)/SQUASH_MSG")" "2"
quiet git filesync add "$URL9/" c.c -p t.c -b dev
check "add by URL + branch: that source" "$(git config -f .git-filesync file.c.c.source)" "$SRCD"
check "add -b: a missing branch is an error" "$(rc git filesync add "$URL9" e.c -p t.c -b nope)" "2"
git reset -q --hard

# a SQUASH_MSG of git's own (e.g. merge --squash) gets the proposal too;
# the copy in .git/FILESYNC_MSG is rewritten each time, the path shown
# relative to the current directory
echo "squashed" > "$(git rev-parse --git-dir)/SQUASH_MSG"
quiet git filesync add "$URL9" f.c -p t.c
check "foreign SQUASH_MSG: proposal added" \
  "$(head -1 .git/SQUASH_MSG) $(grep -c '^\[filesync\] Add f\.c from' .git/SQUASH_MSG)" "squashed 1"
mkdir sub
check "subdirectory: copy shown relative to it" \
  "$(cd sub && git filesync add "$URL9" g.c -p t.c | grep -c 'a copy stays in \.\./\.git/FILESYNC_MSG)$')" "1"
git commit -q
check "commit takes all proposals" "$(git log -1 --format=%B | grep -cE '^squashed$|^\[filesync\] Add (f|sub/g)\.c ')" "3"
check "the copy stays, rewritten" "$(head -1 .git/FILESYNC_MSG) $(ls .git/FILESYNC_* | oneline)" "squashed .git/FILESYNC_MSG "
git reset -q --hard HEAD~1

# adds and a pull go into one commit, with all their proposals
cd "$T"
new_repo s9c
addc "$URL9" t.c --commit v1
check "linked at v1: pending" "$(st)" "P"
quiet git filesync add "$URL9" u.c -p t.c
check "pull despite another uncommitted entry" "$(rc git filesync pull t.c)" "0"
git commit -q
check "one commit: files of add and pull" "$(git show --name-only --format= HEAD | sort | oneline)" ".git-filesync t.c u.c "
check "one commit: both proposals" "$(git log -1 --format=%B | grep -cE '^\[filesync\] (Add u\.c|Sync t\.c) from')" "2"


# =============================================================================
section "15. Files renamed or deleted upstream"
# =============================================================================
cd "$T"

# m10.git (bare, via the blobless cache) and checkout co10:
# lib/r.c (lines a..i) and lib/gone.c
git init -q --bare m10.git
git -C m10.git config uploadpack.allowFilter true
git clone -q m10.git co10 2>/dev/null
(cd co10 && mkdir lib && printf 'a\nb\nc\nd\ne\nf\ng\nh\ni\n' > lib/r.c && echo x > lib/gone.c \
  && git add . && git commit -qm init && git push -q origin main)
URL10=$TURL/m10.git

new_repo s10
addc "$URL10" r.c -p lib/r.c
addc "$URL10" gone.c -p lib/gone.c
SRC10=$(git config -f .git-filesync file.r.c.source)

# r.c: renamed with a change, then changed again; gone.c: deleted
(cd ../co10 && git mv lib/r.c lib/renamed.c && sedi 's/^b$/B/' lib/renamed.c \
  && git commit -qm "rename r" && sedi 's/^i$/I/' lib/renamed.c && git commit -qam "change I" \
  && git rm -q lib/gone.c && git commit -qm "drop gone" && git push -q origin main)
check "renamed upstream: short code" "$(st r.c)" "R"
check "renamed upstream: long format" \
  "$(git filesync status r.c | grep -cE "^${TAB}renamed:[[:space:]]+r\.c  \(lib/r\.c -> lib/renamed\.c, 2 commits\)")" "1"
check "deleted upstream: short code" "$(st gone.c)" "X"
check "deleted upstream: unlink hint" "$(git filesync status | grep -c 'git filesync unlink <file>')" "1"
# a patch for upstream applies to its current path, also after a rename there
sedi 's/^e$/E-local/' r.c
git filesync diff --for-upstream r.c > "$T/r.patch"
check "diff --for-upstream: the upstream path after a rename" \
  "$(grep -c '^+++ b/lib/renamed.c$' "$T/r.patch") $(cd ../co10 && git apply -3 "$T/r.patch" >/dev/null 2>&1 && grep -c E-local lib/renamed.c)" "1 1"
(cd ../co10 && git reset -q --hard)
git checkout -q r.c
check "deleted upstream: status rc 0" "$(rc git filesync status)" "0"
check "deleted upstream: --exit-code" "$(rc git filesync status --exit-code gone.c)" "1"
check "deleted upstream: hook" "$(git filesync hook pre-push origin x </dev/null 2>&1 | grep -c 'gone.c: upstream deleted')" "1"

# pull follows the rename; a committed adaptation is merged across it
sedi 's/^e$/e-local/' r.c
git commit -qam adapt
quiet pullc r.c
check "pull follows rename: path updated" "$(git config -f .git-filesync file.r.c.path)" "lib/renamed.c"
check "pull follows rename: merged" "$(oneline < r.c)" "a B c d e-local f g h I "
check "pull follows rename: message" \
  "$(git log -1 --format=%B | grep -cE '^(Upstream: .*\(main:lib/renamed.c\)|Renamed upstream: lib/r.c -> lib/renamed.c|- rename r .*|- change I .*)$')" "4"
check "after rename: only adapted" "$(st r.c)" " M"

# pull refuses a deleted file and says how to proceed
check "pull refuses deleted file" "$(rc pullc gone.c)" "2"
check "deleted: hint" "$(git filesync pull gone.c 2>&1 | grep -c "keep the file with 'git filesync unlink gone.c'")" "1"
check "deleted: file untouched" "$(cat gone.c)" "x"
check "deleted: --commit with an older revision" \
  "$(rc pullc --commit "$(git -C ../co10 rev-parse HEAD~1)" gone.c)" "0"

# renamed twice; a pure rename commits only the registry
(cd ../co10 && git mv lib/renamed.c lib/again.c && git commit -qm "rename again" \
  && git mv lib/again.c lib/final.c && git commit -qm "and again" && git push -q origin main)
check "chained rename" "$(git filesync status r.c | grep -c 'lib/renamed.c -> lib/final.c, 2 commits')" "1"
quiet pullc r.c
check "pure rename: path updated" "$(git config -f .git-filesync file.r.c.path)" "lib/final.c"
check "pure rename: commit has only the registry" "$(git show --name-only --format= HEAD)" ".git-filesync"
check "pure rename: then clean" "$(st r.c)" " M"


# =============================================================================
section "16. Dry runs: pull --dry-run, add / unlink / mv -n"
# =============================================================================
# (continues in s10)

(cd ../co10 && sedi 's/^g$/G-up/' lib/final.c && git commit -qam "change G" && git push -q origin main)
BEFORE=$(git rev-parse HEAD)
check "pull --dry-run: reports" "$(git filesync pull --dry-run r.c)" \
  "r.c: would sync to $SRC10@$(git -C ../co10 rev-parse --short HEAD) (adaptations merged cleanly)"
check "pull --dry-run: nothing changed" "$(git rev-parse HEAD) $(git status --porcelain)" "$BEFORE "
sedi 's/^g$/g-local/' r.c
git commit -qam "local g"
check "pull --dry-run: conflict reported" "$(git filesync pull --dry-run r.c | grep -c '1 merge conflict(s)')" "1"
check "pull --dry-run: rc" "$(rc git filesync pull --dry-run r.c)" "0"
check "pull --dry-run: file untouched" "$(grep -c '^<<<<<<<' r.c)" "0"
git reset -q --hard HEAD~1

check "add -n" "$(git filesync add -n "$URL10" new.c -p lib/final.c)" \
  "would link new.c -> $SRC10:lib/final.c (main), fetched, based on $(git -C ../co10 rev-parse --short HEAD)"
check "add -n: nothing written" "$(ls new.c 2>/dev/null; git status --porcelain)" ""
check "unlink -n" "$(git filesync unlink -n r.c)" "would unlink r.c"
check "mv -n" "$(git filesync mv -n r.c moved.c)" "would move r.c -> moved.c"
check "-n: nothing changed" "$(ls r.c) $(git status --porcelain)" "r.c "


# =============================================================================
section "17. add DIR: all files of an upstream directory, --include / --exclude"
# =============================================================================
cd "$T"

# m11 (only via mapping): api/ with .proto files, tests and a README; docs/
git init -q m11
(cd m11 && mkdir -p api/v1 api/test docs \
  && for f in api/a.proto api/v1/b.proto api/v1/b_test.proto api/test/t.proto api/README.md docs/x.md; do
       echo "$f" > $f; done && git add . && git commit -qm init)
new_repo s11
git filesync source map file:///nowhere/m11.git "$T/m11" >/dev/null

# PROTO - the options linking the .proto files of api/ as proto/
PROTO=(-p api --include '*.proto' --exclude '*_test.proto' --exclude test/)
addc file:///nowhere/m11.git proto "${PROTO[@]}"
check "add DIR: files linked" \
  "$(git config -f .git-filesync --get-regexp '^file\..*\.path' | LC_ALL=C sort | oneline)" \
  "file.proto/a.proto.path api/a.proto file.proto/v1/b.proto.path api/v1/b.proto "
check "add DIR: content" "$(cat proto/v1/b.proto)" "api/v1/b.proto"
check "add DIR: one commit" "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" \
  ".git-filesync proto/a.proto proto/v1/b.proto "
check "add DIR: message" "$(git log -1 --format=%B | sed '/^$/d; s/@[0-9a-f]*$/@X/' | oneline)" \
  "[filesync] Add 2 files from nowhere/m11@X Upstream: file:///nowhere/m11.git (main:api/) - proto/a.proto - proto/v1/b.proto "
check "add DIR: status clean" "$(st)" ""

# a new upstream file: the same add links only that one
(cd ../m11 && echo c > api/c.proto && git add . && git commit -qm c)
OUT=$(git filesync add nowhere/m11 proto "${PROTO[@]}" 2>&1)
git commit -q --no-edit
check "add DIR again: linked ones skipped" "$(echo "$OUT" | grep -c '^2 files already linked, skipped')" "1"
check "add DIR again: new file committed" "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" \
  ".git-filesync proto/c.proto "
check "add DIR again: subject" "$(git log -1 --format=%s | sed 's/@.*//')" "[filesync] Add proto/c.proto from nowhere/m11"
check "add DIR: nothing new" "$(git filesync add nowhere/m11 proto "${PROTO[@]}" 2>&1)" \
  "3 files already linked, skipped (use --force to relink)"

# an existing file is linked as it is; '/x.md' is anchored at the directory
mkdir docs && echo mine > docs/x.md
quiet fsd add nowhere/m11 docs --include /x.md && git commit -q --no-edit
check "add DIR: existing file kept" "$(cat docs/x.md)" "mine"
check "add DIR: existing file adapted" "$(st docs)" " M"
check "add DIR: subject for an existing file" "$(git log -1 --format=%s | sed 's/@.*//')" "[filesync] Link docs/x.md to nowhere/m11"
check "add DIR --overwrite: existing file replaced" \
  "$(fsd add -n --force --overwrite nowhere/m11 docs --include /x.md | grep -c 'replacing the existing file')" "1"

# pattern forms
check "pattern '**/v1/*'" "$(git filesync add -n nowhere/m11 all -p api --include '**/v1/*' | lines)" "2"
check "pattern 'test/' (directory)" "$(git filesync add -n nowhere/m11 all -p api --include 'test/' | cut -d' ' -f3)" "all/test/t.proto"
check "pattern 'v?/b*.proto'" "$(git filesync add -n nowhere/m11 all -p api --include 'v?/b[_.]*' | lines)" "2"
check "patterns need an upstream directory" "$(rc git filesync add nowhere/m11 x -p api/a.proto --include '*')" "2"
check "whole upstream repository (docs/x.md already linked)" \
  "$(fsd add -n nowhere/m11 . -p / --exclude '*.proto' | grep '^would' | cut -d' ' -f3 | oneline)" "api/README.md "

# the script itself, synced into the repository and run via a repo alias
mkdir tools && cp "$S" tools/git-filesync.py
git config alias.fs "!$PYTHON tools/git-filesync.py"
check "repo alias to a copy of the script, from a subdirectory" "$(cd proto && git fs status -s v1/b.proto; echo $?)" "0"


# =============================================================================
section "18. pull -b / --tag: another branch or tag, once; newer tags"
# =============================================================================
cd "$T"

# m12.git (bare, via the cache) and checkout co12: a.c b.c c.c (lines 1..5).
# v1.0; v1.1 changes line 5 of a.c and b.c; v2.0-rc1 changes a.c
git init -q --bare m12.git
git -C m12.git config uploadpack.allowFilter true
git clone -q m12.git co12 2>/dev/null
(cd co12 && printf '1\n2\n3\n4\n5\n' > a.c && cp a.c b.c && cp a.c c.c && git add . \
  && git commit -qm v1 && git tag v1.0 \
  && sedi 's/^5$/5-v11/' a.c b.c && git commit -qam "v1.1 change" && git tag v1.1 \
  && sedi 's/^5-v11$/5-rc/' a.c && git commit -qam "rc change" && git tag v2.0-rc1 \
  && git push -q origin main --tags)
URL12=$TURL/m12.git

new_repo s12
for f in a b c; do addc --tag v1.0 "$URL12" $f.c; done
SRC12=$(git config -f .git-filesync file.a.c.source)

# newer tags by their place in the commit graph, on the source's branch -
# names are opaque, so a pre-release counts like any tag: status -v, pull
check "status -v: newest tag" "$(git filesync status -v | grep -c '(tag v1.0 on main, newest v2.0-rc1)')" "3"
check "plain status: no hint" "$(git filesync status | grep -c newest)" "0"
check "source -v: the branch" "$(git filesync source -v)" "$(printf '%s\t%s (main, 3 files)' "$SRC12" "$URL12")"
check "pull: hint" "$(git filesync pull --all 2>&1 | grep -c "^hint: 3 files pinned to tag v1.0; \
the newest tag on branch main is v2.0-rc1 (use 'git filesync set --tag v2.0-rc1 <file>...' and pull to switch)$")" "1"

# a maintenance branch from v1.0 with v1.0.1; a feature branch from v1.1
# with tag f1, merged into main; rel-2 on the same commit as v2.0-rc1; v1.2
# on the v1.1 commit (older than v2.0-rc1 on main, whatever its name)
(cd ../co12 && git checkout -qb maint v1.0 && echo m > m.txt && git add m.txt \
  && git commit -qm maint && git tag -a -m 1.0.1 v1.0.1 \
  && git checkout -qb feature v1.1 && echo f > f.txt && git add f.txt && git commit -qm f \
  && git tag f1 && git checkout -q main && git merge -q --no-ff -m "merge feature" feature \
  && git tag rel-2 HEAD^1 && git tag v1.2 v1.1 && git push -q origin main maint feature --tags)
check "branch: only its line, merged side branch ignored" \
  "$(git filesync status -v | grep -c '(tag v1.0 on main, newest rel-2 = v2.0-rc1)')" "3"
check "pull: hint, tags on one commit" "$(git filesync pull --all 2>&1 | grep -c "^hint: 3 files pinned \
to tag v1.0; the newest tag on branch main is rel-2 = v2.0-rc1 (use 'git filesync set --tag rel-2 ")" "1"
git filesync source set-branch "$SRC12" maint >/dev/null
check "branch maint" "$(git filesync status -v | grep -c '(tag v1.0 on maint, newest v1.0.1)')" "3"
git filesync set a.c --tag v1.0.1 >/dev/null
check "newest tag pinned: no newer" "$(git filesync status -v a.c | grep -c newest)" "0"
git filesync source set-branch "$SRC12" main >/dev/null
check "tag not on the branch: warning, naming its branch" \
  "$(git filesync status -v 2>&1 | grep -c "tag v1.0.1 is not on branch 'main' .* (it is on maint; -b selects another branch)")" "1"
check "tag not on the branch: no error" "$(rc git filesync status)" "0"
check "source set-branch: a missing branch refused" \
  "$(git filesync source set-branch "$SRC12" nope 2>&1 | grep -c "^error: branch 'nope' not found")-$(rc git filesync source set-branch "$SRC12" nope)" "1-2"
git config -f .git-filesync "source.$SRC12.branch" nope     # as if edited by hand
check "a missing branch of pinned files: an error" \
  "$(git filesync status 2>&1 | grep -c "^error: .*branch 'nope' not found")-$(rc git filesync status)" "3-2"
git config -f .git-filesync "source.$SRC12.branch" main
git filesync set a.c --tag v1.0 >/dev/null
git commit -qm "pinned to v1.0 on main"

# with a mapped checkout: its branches and tags, unpushed ones included
(cd ../co12 && git tag local-3)
git filesync source map "$URL12" "$T/co12" >/dev/null
check "mapped: newest tag from the checkout" \
  "$(git filesync status -v | grep -c '(tag v1.0 on main, newest local-3)')" "3"
git filesync source map "$URL12" --unset >/dev/null
(cd ../co12 && git tag -d local-3 >/dev/null)

# pull -b / --tag sync to another branch or tag once; the links keep their
# own (switching them: set -b/--tag, source set-branch/set-tag)
sedi 's/^1$/1-local/' a.c
git commit -qam adapt
OUT=$(pullc --tag v1.1 a.c 2>&1)
check "pull --tag: merged" "$(oneline < a.c)" "1-local 2 3 4 5-v11 "
check "pull --tag: registry keeps the tag" \
  "$(git config -f .git-filesync file.a.c.tag) $(git config -f .git-filesync file.a.c.source)" "v1.0 $SRC12"
check "pull --tag: message without a note on it" \
  "$(git log -1 --format=%B | grep -cE '^\[filesync\] Sync a.c from |once|follows')" "1"
check "pull --tag: hint how to stay" \
  "$(echo "$OUT" | grep -c "^hint: .*to stay on tag v1.1, use 'git filesync set <file>... --tag v1.1'$")" "1"
check "pull --tag: all committed" "$(git status --porcelain)" ""
check "after pull --tag: the link's tag is older" "$(st a.c)" "OM"
quiet pullc a.c
check "plain pull: back to the link's tag" "$(oneline < a.c)" "1-local 2 3 4 5 "

# --all with --tag / -b: every file, also those up to date with their own tag
quiet pullc --all --tag v1.1
check "pull --all --tag: all files" "$(cat a.c b.c c.c | oneline)" "1-local 2 3 4 5-v11 1 2 3 4 5-v11 1 2 3 4 5 "
check "pull --all --tag: registry unchanged" "$(git config -f .git-filesync file.a.c.tag)" "v1.0"
quiet pullc --all -b main
check "-b: synced to the branch" "$(oneline < a.c)" "1-local 2 3 4 5-rc "
check "-b: registry unchanged" \
  "$(git config -f .git-filesync source.$SRC12.branch) $(git config -f .git-filesync file.a.c.tag)" "main v1.0"

# refusals and dry runs change nothing
check "pull -v: where from, synced so far" "$(git filesync pull -v -n a.c | head -1)" \
  "a.c: from $SRC12:a.c (tag v1.0 on main, newest rel-2 = v2.0-rc1), synced at $(git -C ../co12 log -1 --format=%h main -- a.c)"
check "pull -v: syncs too" \
  "$(git filesync pull -v a.c >/dev/null 2>&1; echo $?) $(git diff --cached --name-only | oneline)" \
  "0 .git-filesync a.c "
git reset -q --hard
check "pull --tag: missing tag" "$(rc pullc --tag v9 a.c)" "2"
check "missing tag: nothing changed" "$(git status --porcelain)" ""
check "--commit and --tag exclude each other" "$(rc git filesync pull --commit v1.0 --tag v1.0 a.c)" "2"
check "-b and --tag exclude each other" "$(rc git filesync pull -b main --tag v1.0 a.c)" "2"
check "pull --dry-run --tag" "$(git filesync pull --dry-run --tag v1.0 a.c | grep -c '^a.c: would sync to .*(tag v1.0 once')" "1"
check "pull --dry-run --tag: nothing changed" "$(git status --porcelain)" ""

# diff/difftool --upstream with --commit / -b / --tag: what that pull would
# bring (synced: main = 5-rc); nothing is switched
check "diff --upstream --tag" "$(git filesync diff --upstream --tag v1.0 a.c | changes)" "-5-rc +5 "
check "diff --upstream --tag: only differing files" \
  "$(git filesync diff --upstream --tag v1.1 -- --name-only)" "a.c"
check "diff --upstream -b" "$(git filesync diff --upstream -b maint a.c | changes)" "-5-rc +5 "
check "diff --upstream --commit" "$(git filesync diff --upstream --commit v1.1 a.c | changes)" "-5-rc +5-v11 "
check "difftool --upstream --tag: temp copy of the tag's version" \
  "$(git filesync difftool -y --upstream --tag v1.0 a.c | grep -c "upstream-$(git -C ../co12 rev-parse --short v1.0)")" "1"
check "diff --upstream --tag: nothing changed" "$(git status --porcelain)" ""
check "diff --tag without --upstream" "$(rc git filesync diff --tag v1.0 a.c)" "2"
check "diff --upstream --commit: one file only" "$(rc git filesync diff --upstream --commit v1.0)" "2"
check "diff --upstream: missing tag" "$(rc git filesync diff --upstream --tag v9 a.c)" "2"

# pull --dry-run with a conflict points to both diffs, with the same options
sedi 's/^5-rc$/5-local/' a.c
git commit -qam "adapt 5"
check "pull --dry-run: conflict hint" "$(git filesync pull --dry-run --tag v1.1 a.c | grep -c \
  "^hint: compare the adaptations ('git filesync diff a.c') with the upstream changes \
('git filesync diff --upstream --tag v1.1 a.c')$")" "1"
git reset -q --hard HEAD^

# an uncommitted source rename doesn't block pull; it goes into the sync commit
git filesync source rename "$SRC12" lib12 >/dev/null
(cd ../co12 && sedi 's/^3$/3-up/' a.c && git commit -qam "change 3" && git push -q origin main)
check "pull after uncommitted source rename" "$(rc pullc a.c)" "0"
check "rename went into the sync commit" "$(git status --porcelain) $(git show HEAD:.git-filesync | grep -c 'source = lib12')" " 3"

# a tag pattern: the newest matching tag on the source's branch, by the
# commit graph; the branch is filled in; tags that don't match are ignored
# (main: v1.0 - v1.1 = v1.2 - v2.0-rc1 = rel-2 - merge f1 - change 3)
cd "$T"
new_repo s12p
check "add --tag with a tag not on the branch: warning" \
  "$(git filesync add -n "$URL12" x.c -p a.c --tag v1.0.1 -b main 2>&1 | grep -c "^warning: tag v1.0.1 is not on branch 'main'")" "1"
addc --tag 'v1.*' "$URL12" a.c
SRCP=$(git config -f .git-filesync file.a.c.source)
check "pattern: on the source's (default) branch" \
  "$(git config -f .git-filesync file.a.c.tag) $(git config -f .git-filesync source.$SRCP.branch)" "v1.* main"
check "pattern: newest matching tag on main" "$(oneline < a.c)" "1 2 3 4 5-v11 "
check "pattern: status -v shows the matching tags" "$(git filesync status -v | grep -c '(tag v1\.\* = v1\.1 = v1\.2 on main)')" "1"
check "pattern: no hint at other tags" "$(git filesync pull --all 2>&1 | grep -c hint)" "0"
(cd ../co12 && git tag v1.3 main && git push -q origin v1.3)
check "pattern: a new matching tag is pending" "$(st)" "P"
quiet pullc a.c
check "pattern: pull follows it" "$(oneline < a.c)" "1 2 3-up 4 5-rc "
check "pattern: message names the tag" "$(git log -1 --format=%B | grep -c "^Upstream: $URL12 (v1.3:a.c)$")" "1"
check "pattern: registry unchanged" "$(git status --porcelain) $(git config -f .git-filesync file.a.c.tag)" " v1.*"
check "pull --tag with a pattern, once" \
  "$(git filesync pull --dry-run --tag 'v1.0*' a.c | grep -c "would sync to $SRCP@$(git -C ../co12 rev-parse --short v1.0) (tag v1.0\* once")" "1"
# with a mapped checkout: its tags, unpushed ones included
(cd ../co12 && git tag v1.4 main)
git filesync source map "$URL12" "$T/co12" >/dev/null
check "pattern, mapped: local tags" "$(git filesync status -v | grep -c '= v1\.3 = v1\.4 on main')" "1"
git filesync source map "$URL12" --unset >/dev/null
(cd ../co12 && git tag -d v1.4 >/dev/null)
# no match: an error; a pattern keeps its branch
check "set --tag: a pattern without a match is refused" "$(rc git filesync set a.c --tag 'x*')" "2"
check "a pattern matching on another branch: named" \
  "$(git filesync set a.c --tag 'v1.0.1*' 2>&1 | grep -c "no tag matching 'v1.0.1\*' on branch 'main' .* (matching tags on maint; -b selects another branch)")" "1"
check "set -b with --tag: the pattern on that branch (the only file: its source changes)" \
  "$(git filesync set a.c -b maint --tag 'v1.0.1*' -n | oneline)" "would: source $SRCP: branch main -> maint would: a.c: tag v1.0.1* "
git config -f .git-filesync file.a.c.tag 'x*'
check "pattern without a match: error" \
  "$(git filesync status 2>&1 | grep -c "no tag matching 'x\*' on branch 'main'")-$(rc git filesync status)" "1-2"
git checkout -q .git-filesync


# =============================================================================
section "19. set: change source, tag, upstream path or strict of linked files"
# =============================================================================
cd "$T"

# m13.git (bare, the server) with a.c and b.c, tag v1; m13fork.git: a clone
# with one more commit (c.txt only); m13copy.git: the same a.c and b.c with
# a history of its own
git init -q m13
(cd m13 && printf '1\n2\n3\n' > a.c && printf 'x\ny\n' > b.c && git add . && git commit -qm i \
  && git tag v1)
git clone -q --bare m13 m13.git
git clone -q --bare m13 m13fork.git
(git clone -q m13fork.git cofork && cd cofork && echo c > c.txt && git add . && git commit -qm c \
  && git push -q origin main) 2>/dev/null
git init -q m13copy
(cd m13copy && cp ../m13/a.c ../m13/b.c . && git add . && git commit -qm "own history")
git clone -q --bare m13copy m13copy.git
URL13=$TURL/m13.git
for r in m13 m13fork m13copy; do git -C $r.git config uploadpack.allowFilter true; done

new_repo s13
addc "$URL13" a.c
addc "$URL13" b.c
SRC13=$(git config -f .git-filesync file.a.c.source)
COMMIT13=$(git config -f .git-filesync file.a.c.commit)

check "set: nothing to change" "$(rc git filesync set a.c)" "2"
check "set --strict" "$(git filesync set a.c --strict | head -1)" "a.c: strict"
check "set --strict: entry" "$(git config -f .git-filesync file.a.c.strict)" "true"
check "set: only staged" "$(git status --porcelain | oneline) $(git log -1 --format=%s | cut -c1-16)" "M  .git-filesync  [filesync] Add b"
check "set --strict again: nothing" "$(git filesync set a.c --strict)" "nothing to change"
check "set --no-strict" "$(git filesync set a.c --no-strict | head -1) $(git config -f .git-filesync file.a.c.strict)" "a.c: not strict "
quiet git filesync set a.c --strict
echo z >> a.c
git commit -qam "adapt strict file"
check "strict refusal names set --no-strict" \
  "$(pullc a.c 2>&1 | grep -c "'git filesync set --no-strict a.c'")" "1"
git reset -q --hard HEAD~1

# another upstream path: the synced version is looked up as for add
check "set -p: one file only" "$(rc git filesync set a.c b.c -p a.c)" "2"
check "set -p" "$(git filesync set b.c -p a.c 2>/dev/null | grep -c '^b.c: path b.c -> a.c, based on .*, with local modifications$')" "1"
check "set -p: entry" "$(git config -f .git-filesync file.b.c.path)" "a.c"
check "set -p: content differs from the new base" "$(st b.c)" " M"
quiet git filesync set b.c -p b.c
check "set -p back: matching version found" "$(st b.c) $(git config -f .git-filesync file.b.c.path)" " b.c"
check "set -p back: entry as committed" "$(git status --porcelain)" ""

# source set-url looks up the synced versions there, as set --source does
quiet git filesync source set-url "$SRC13" "$TURL/m13copy.git"
check "source set-url: commit of the copy" "$(git config -f .git-filesync file.a.c.commit)" \
  "$(git -C ../m13copy rev-parse HEAD)"
git reset -q --hard

# a fork with the same history: all files of the source move, so the source
# itself gets the new URL; the recorded commit is kept
check "set --source fork" "$(git filesync set a.c b.c --source "$TURL/m13fork.git" 2>/dev/null | head -1)" \
  "source $SRC13: url $URL13 -> $TURL/m13fork.git"
check "set --source fork: URL changed in place" \
  "$(git config -f .git-filesync source.$SRC13.url) $(git config -f .git-filesync file.a.c.source)" "$TURL/m13fork.git $SRC13"
check "set --source fork: commit kept" "$(git config -f .git-filesync file.a.c.commit)" "$COMMIT13"
check "set --source fork: up to date" "$(git filesync status -s)" ""
git commit -qm fork

# a copy with a history of its own: a.c alone moves to a new source; its
# commit is the copy's commit with the same version of a.c
quiet git filesync set a.c --source "$TURL/m13copy.git"
check "set --source copy: new source" \
  "$(git config -f .git-filesync file.a.c.source | grep -c m13copy) $(git config -f .git-filesync file.b.c.source)" "1 $SRC13"
check "set --source copy: commit of the copy" "$(git config -f .git-filesync file.a.c.commit)" "$(git -C ../m13copy rev-parse HEAD)"
check "set --source copy: up to date" "$(git filesync status -s)" ""
git commit -qm copy

# --tag pins the file, without syncing; the branch stays the source's
quiet git filesync set b.c --tag v1
check "set --tag: pinned, branch kept" \
  "$(git config -f .git-filesync file.b.c.tag) $(git config -f .git-filesync source.$SRC13.branch)" "v1 main"
check "set --tag: file unchanged" "$(oneline < b.c)$(git status --porcelain b.c)" "x y "
check "set -b: an unknown branch is refused" "$(rc git filesync set b.c -b other)" "2"

# dry run changes nothing
git commit -qm tag
check "set -n" "$(git filesync set a.c --strict -n)" "would: a.c: strict"
check "set -n: nothing changed" "$(git status --porcelain)" ""

# edit: .git-filesync in the editor (here: scripts as GIT_EDITOR), then
# checked and staged
check "edit without changes" "$(git filesync edit)" ".git-filesync: no changes"
check "edit: failing editor" "$(GIT_EDITOR=false git filesync edit 2>&1)" "error: the editor failed; nothing staged"
printf 'git config -f "$1" file.a.c.strict true\n' > "$T/ed-strict.sh"
OUT=$(GIT_EDITOR="sh $T/ed-strict.sh" git filesync edit 2>&1)
check "edit: change staged" "$(git diff --cached --name-only) $(git config -f .git-filesync file.a.c.strict)" \
  ".git-filesync true"
check "edit: says so" "$(echo "$OUT" | grep -c '^.git-filesync staged')" "1"
git commit -qm "strict by edit"
printf 'git config -f "$1" --unset source.%s.url\n' "$SRC13" > "$T/ed-nourl.sh"
check "edit: gaps are warned about" \
  "$(GIT_EDITOR="sh $T/ed-nourl.sh" git filesync edit 2>&1 | grep -c "warning: .git-filesync: \[source \"$SRC13\"\] has no url")" "1"
git reset -q --hard
printf 'echo "[file" >> "$1"\n' > "$T/ed-broken.sh"
check "edit: unreadable result fails" "$(GIT_EDITOR="sh $T/ed-broken.sh" rc git filesync edit)" "2"
check "edit: ... and stages nothing" "$(git diff --cached --name-only)" ""
git checkout -q .git-filesync
check "edit without .git-filesync" "$( (new_repo "$T/s13e" && rc git filesync edit) )" "2"


# =============================================================================
section "20. cache: show, list and clean up the cache of upstream clones"
# =============================================================================
cd "$T"

# make every clone look unused for a long time (a marker in each clone)
age_clones() { for d in "$T"/cache/*.git; do touch -t 202001010000 "$d/filesync-last-used"; done; }
nclones() { ls -d "$T"/cache/*.git 2>/dev/null | lines; }
N=$(nclones)
check "cache: clones there" "$([ "$N" -gt 2 ] && echo yes)" "yes"
check "cache dir" "$(basename "$(git filesync cache dir)")" "cache"
check "cache: summary" "$(git filesync cache | sed -n 2p)" \
  "cleaned up automatically: clones unused for 90 days (filesync.cacheMaxAge, filesync.cacheMaxSize)"
check "cache list: one line per clone" "$(git filesync cache list | lines)" "$N"
check "cache list: the URL" "$(git filesync cache list | grep -c " $URL12$")" "1"
check "cache prune: recently used ones kept" "$(git filesync cache prune --max-size 1 | tail -1)" \
  "removed 0 clones (0 bytes) from the cache - clones used in the last minutes are kept"
age_clones
check "cache prune -n" "$(git filesync cache prune -n | grep -c '^would remove .* 2020-01-01 ')" "$N"
check "cache prune -n: nothing removed" "$(nclones)" "$N"
check "cache prune --max-size: least recently used" \
  "$(git filesync cache prune --older-than 100000 --max-size 1 -n | grep -c '^would remove .* 2020-01-01 ')" "$N"
check "cache prune: 0 is no limit, as configured" \
  "$(git filesync cache prune --older-than 0 -n | grep -c '^would remove .* 2020-01-01 ')-$(git filesync cache prune --older-than 100000 --max-size 0 -n | grep -c '^would remove .* 2020-01-01 ')" "0-0"

# automatic clean-up after a fetch, at most once a day: here everything
# but the clone just used is old
git config --global filesync.cacheMaxAge 1
rm -f "$T/cache/last-prune"
new_repo s20
addc "$URL12" a.c
check "automatic clean-up keeps the clone in use" "$(nclones)" "1"
age_clones
quiet git filesync status
check "... at most once a day" "$(nclones)" "1"
git config --global filesync.cacheMaxAge off
check "cacheMaxAge off: no limits" "$(git filesync cache prune)" \
  "no limits set (filesync.cacheMaxAge, filesync.cacheMaxSize, --older-than, --max-size) - nothing to do"
git config --global --unset filesync.cacheMaxAge
check "cache clear -n" "$(git filesync cache clear -n | tail -1 | cut -d' ' -f1-4)" "would remove 1 clone"
quiet git filesync cache clear
check "cache clear" "$(nclones) $(git filesync cache list)" "0 the cache is empty ($(git filesync cache dir))"
check "status after clear: cloned again" "$(rc git filesync status)" "0"


# =============================================================================
section "21. Performance: git processes don't grow with the number of files"
# =============================================================================
cd "$T"

# Starting a process is slow on Windows: status asks git per repository and
# per source, not per file. A wrapper named git (first on PATH) counts the
# calls; not on Windows, where Python would still find git.exe first.
# a failing git command is named in the error, not the "-c" option before it
check "error names the git command" \
  "$( (new_repo "$T/s21e" && git filesync add file:///nowhere/none.git x.c -b main 2>&1) | grep -c 'git clone failed')" "1"

if command -v cygpath >/dev/null; then
  echo "skipped on Windows"
else
  REALGIT=$(command -v git)
  mkdir -p "$T/countbin"
  printf '#!/bin/sh\necho x >> "$GITCALLS"\nexec "%s" "$@"\n' "$REALGIT" > "$T/countbin/git"
  chmod +x "$T/countbin/git"
  # calls of 'git filesync ARGS' (run directly, not through the alias)
  calls() { : > "$T/calls"; GITCALLS=$T/calls PATH=$T/countbin:$PATH fsd "$@" >/dev/null 2>&1; lines < "$T/calls"; }
  git init -q m21 && (cd m21 && mkdir lib && for i in $(seq 1 60); do echo "v$i" > lib/f$i.c; done \
    && git add . && git commit -qm init)
  new_repo s21
  git filesync source map file:///nowhere/m21.git "$T/m21" >/dev/null
  addc file:///nowhere/m21.git src -p lib --include 'f[1-3]?.c'      # 30 files
  C30=$(calls status)
  addc file:///nowhere/m21.git src -p lib                             # all 60
  C60=$(calls status)
  check "status: git calls independent of the number of files ($C30 / $C60)" \
    "$([ "$C60" -le "$((C30 + 2))" ] && [ "$C60" -lt 30 ] && echo yes)" "yes"
  # adapted files are compared without a git call each
  for i in 1 2 3 4 5 6 7 8 9; do echo local >> src/f$i.c; done
  git commit -qam "adapt 9"
  check "status: adapted files cost no git calls each" "$([ "$(calls status)" -le "$((C60 + 3))" ] && echo yes)" "yes"
  check "status: adapted files reported" "$(git filesync status -s | grep -c '^ M ')" "9"
  # diff, restore and pull compare, convert and write all files at once:
  # 9 files cost (almost) no more git calls than one
  D1=$(calls diff src/f1.c); D9=$(calls diff src)
  check "diff: no git calls per file ($D1 / $D9)" "$([ "$D9" -le "$((D1 + 2))" ] && echo yes)" "yes"
  R1=$(calls restore -SW src/f1.c); git reset -q --hard
  R9=$(calls restore -SW src); git reset -q --hard
  check "restore: no git calls per file ($R1 / $R9)" "$([ "$R9" -le "$((R1 + 2))" ] && echo yes)" "yes"
  # pull: per file only what its upstream history needs (last change, log)
  git reset -q --hard HEAD~1
  (cd ../m21 && for i in $(seq 1 60); do echo "w$i" >> lib/f$i.c; done && git commit -qam w)
  CP=$(calls pull --all); quiet git commit --no-edit
  check "pull: few git calls per file ($CP for 60)" "$([ "$CP" -le $((60 * 3 + 30)) ] && echo yes)" "yes"
  check "pull: all in one commit" "$(git log -1 --format=%s)" "[filesync] Sync 60 files from nowhere/m21"
  # unlink and rm remove all entries (and files) at once
  U1=$(calls unlink src/f1.c); git reset -q --hard
  U60=$(calls unlink src); git reset -q --hard
  check "unlink: no git calls per file ($U1 / $U60)" "$([ "$U60" -le "$((U1 + 2))" ] && echo yes)" "yes"
  M1=$(calls rm src/f1.c); git reset -q --hard
  M60=$(calls rm src); git reset -q --hard
  check "rm: no git calls per file ($M1 / $M60)" "$([ "$M60" -le "$((M1 + 2))" ] && echo yes)" "yes"
fi


# =============================================================================
section "22. Closed output pipe; discarded content kept"
# =============================================================================
cd "$T"

git init -q m22 && (cd m22 && for i in 1 2 3; do echo "v$i" > f$i; done && git add . && git commit -qm init)
new_repo s22
git filesync source map file:///nowhere/m22.git "$T/m22" >/dev/null
fsd add file:///nowhere/m22.git d -p / >/dev/null 2>&1 && git commit -q --no-edit   # fsd: '/' (Windows)
check "closed pipe: files linked" "$(ls d | oneline)" "f1 f2 f3 "
(cd ../m22 && for i in 1 2 3; do echo "w$i" >> f$i; done && git commit -qam w)

# output into a pipe whose reader is gone (`| head`, a pager quit early):
# a reading command stops, a changing one carries on - never halfway -
# both exit with 141 like git (unbuffered: the first line already fails)
PYTHONUNBUFFERED=1 fsd status | true
check "closed pipe: status exits with 141" "${PIPESTATUS[0]}" "141"
PYTHONUNBUFFERED=1 fsd pull --all | true
check "closed pipe: pull exits with 141" "${PIPESTATUS[0]}" "141"
check "closed pipe: pull staged all" "$(git status --porcelain | oneline)" "M  .git-filesync M  d/f1 M  d/f2 M  d/f3 "
git commit -q --no-edit
check "closed pipe: the proposed message complete" "$(git log -1 --format=%s)" "[filesync] Sync 3 files from nowhere/m22"
check "closed pipe: nothing left to sync" "$(st)" ""
check "closed pipe: an error keeps its exit code" "$(fsd pull nothere 2>/dev/null | true; echo "${PIPESTATUS[0]}")" "2"

# content with uncommitted changes that restore, add --overwrite or rm -f
# discard is kept as a blob, with a hint how to get it back
echo mine >> d/f1
OUT=$(git filesync restore d/f1)
check "restore: discarded content reported" "$(echo "$OUT" | grep -c '^discarded: d/f1 (git show [0-9a-f]\{12\} to get it back)$')" "1"
ID=$(echo "$OUT" | sed -n 's/.*git show \([0-9a-f]*\).*/\1/p')
check "restore: discarded content can be got back" "$(git show "$ID" | tail -1)" "mine"
check "restore: file restored" "$(cat d/f1)" "$(git show HEAD:d/f1)"
echo staged >> d/f2 && git add d/f2
check "restore: staged content (index stays) not reported" "$(git filesync restore d/f2 | grep -c discarded)" "0"
git reset -q --hard
echo adapted >> d/f2 && git commit -qam adapt
check "restore: committed adaptation not reported" "$(git filesync restore d/f2 | grep -c discarded)" "0"
git reset -q --hard
echo mine2 >> d/f2
check "restore -SW: discarded content reported" "$(git filesync restore -SW d/f2 | grep -c '^discarded: d/f2 ')" "1"
git reset -q --hard
echo mine3 >> d/f3
OUT=$(git filesync rm -f d/f3)
check "rm -f: discarded content reported" "$(echo "$OUT" | grep -c '^discarded: d/f3 ')" "1"
check "rm -f: discarded content can be got back" \
  "$(git show "$(echo "$OUT" | sed -n 's/.*git show \([0-9a-f]*\).*/\1/p')" | tail -1)" "mine3"
git reset -q --hard
check "rm: unchanged file not reported" "$(git filesync rm d/f3 | grep -c discarded)" "0"
git reset -q --hard
echo own > x
check "add --overwrite: replaced untracked file reported" \
  "$(git filesync add --overwrite file:///nowhere/m22.git x -p f1 | grep -c '^discarded: x ')" "1"
git reset -q --hard


# =============================================================================
section "23. A cache that lacks a branch; symlinks in this repository; parallel clones"
# =============================================================================
cd "$T"

git init -q m23 && (cd m23 && echo a > a.c && git add . && git commit -qm init)
git clone -q --bare m23 m23.git && git -C m23.git config uploadpack.allowFilter true
new_repo s23
addc "$TURL/m23.git" a.c
# diff of local changes doesn't fetch - unless the cache lacks the branch
# (here: b.c linked to a branch made after our cache was)
(cd ../m23 && git checkout -qb dev && echo b > b.c && git add b.c && git commit -qm b \
  && git push -q ../m23.git dev)
(FILESYNC_CACHE=$T/cache-23 addc -b dev "$TURL/m23.git" b.c)
echo local >> b.c
check "diff: a branch the cache lacks is fetched" "$(git filesync diff b.c 2>&1 | grep -c '^+local$')" "1"
git reset -q --hard

# own comments in .git-filesync: a removed entry takes the comments between
# its keys along, not those after them (one may introduce the next entry)
new_repo "$T/s23c"
for f in x y z; do addc "$TURL/m23.git" $f.c -p a.c; done
awk '/^\[file "y.c"\]/ { print "# group Y" } { print } /^\[file "x.c"\]/ { print "\t# about x" }' \
  .git-filesync > "$T/reg23" && cp "$T/reg23" .git-filesync && echo "# trailing note" >> .git-filesync
git commit -qam comments
quiet git filesync unlink x.c z.c
check "unlink: comments between the keys go along" "$(grep -c '# about x' .git-filesync)" "0"
check "unlink: comments after the keys stay" "$(grep -cE '^# (group Y|trailing note)$' .git-filesync)" "2"
check "unlink: only y.c left" "$(git config -f .git-filesync --get-regexp '^file\.' | cut -d. -f2 | sort -u | oneline)" "y "
# a changed value keeps the spacing and the comment of its line; a renamed
# section keeps the comment of its header
sedi 's/^[[:space:]]*commit = \(.*\)$/    commit   =  \1   ; mine/' .git-filesync
sedi 's/^\(\[source "[^"]*"\]\)$/\1   # our upstream/' .git-filesync
git commit -qam layout
(cd ../m23 && git checkout -q main && echo c >> a.c && git commit -qam c && git push -q ../m23.git main)
quiet git filesync pull y.c
check "pull: a changed value keeps spacing and comment" \
  "$(grep -c '^    commit   =  [0-9a-f]*   ; mine$' .git-filesync) $(git config -f .git-filesync file.y.c.commit)" \
  "1 $(git -C ../m23 rev-parse HEAD)"
git commit -q --no-edit
quiet git filesync source rename "$(git config -f .git-filesync file.y.c.source)" mine23
check "source rename: the header keeps its comment" "$(grep -c '^\[source "mine23"\]   # our upstream$' .git-filesync)" "1"
check "source rename: the entries follow" "$(git config -f .git-filesync file.y.c.source) $(st y.c)" "mine23 "
# ... also when a key is removed in the same run (set -b ... --no-tag)
git commit -qam rename
(cd ../m23 && git tag t23 && git push -q ../m23.git t23)
quiet git filesync set y.c --tag t23
sedi 's/^[[:space:]]*branch = main$/    branch   =  main   ; our line/' .git-filesync
git commit -qam "pinned, own layout"
quiet git filesync set y.c -b dev --no-tag
check "set -b --no-tag: the changed line keeps its layout" \
  "$(grep -c '^    branch   =  dev   ; our line$' .git-filesync) $(git config -f .git-filesync file.y.c.tag)" "1 "
git reset -q --hard
# nocr FILE - its lines without CRLF (counted with tr: awk and grep in Git
# Bash drop the CR when they read)
nocr() { echo $(( $(lines < "$1") - $(tr -cd '\r' < "$1" | wc -c) )); }
# .git-filesync is written with the line ends of a checkout: CRLF by a git
# attribute stays CRLF (only the changed line differs), and with
# core.autocrlf an LF one becomes CRLF, so that git doesn't warn about it
git commit -qam rename
printf '.git-filesync eol=crlf\n' > .gitattributes && git add .gitattributes
awk '{ sub(/\r$/, ""); printf "%s\r\n", $0 }' .git-filesync > "$T/reg23" && cp "$T/reg23" .git-filesync
git commit -qam crlf
quiet git filesync set y.c --strict
check "eol=crlf: .git-filesync stays CRLF, only the changed line" \
  "$(nocr .git-filesync) $(git diff --cached --numstat .git-filesync | cut -f1,2 | tr '\t' ' ')" "0 1 0"
git reset -q --hard
new_repo "$T/s23a"
git config core.autocrlf true
addc "$TURL/m23.git" a.c
tr -d '\r' < .git-filesync > "$T/reg23" && cp "$T/reg23" .git-filesync
quiet git filesync set a.c --strict
git add .git-filesync 2> "$T/warn23"
check "autocrlf: an LF .git-filesync becomes CRLF, git doesn't warn" \
  "$(nocr .git-filesync) $(grep -c 'will be replaced' "$T/warn23")" "0 0"
cd "$T/s23c"
cd "$T/s23"

if ln -s x "$T/lncheck" 2>/dev/null && [ -L "$T/lncheck" ]; then
  # .git-filesync comes from commits of others: as a symlink it is refused,
  # never written through
  new_repo "$T/s23l"
  printf '[x]\n\ty = 1\n' > "$T/outside23.cfg"
  ln -s "$T/outside23.cfg" .git-filesync && git add .git-filesync && git commit -qm "symlink"
  check "symlinked .git-filesync: refused" "$(rc git filesync add "$TURL/m23.git" c.c -p a.c)" "2"
  check "symlinked .git-filesync: its target untouched" "$(lines < "$T/outside23.cfg")" "2"
  # a linked file that is a symlink: named by its own path (not its
  # target's), and synced as a file - its target stays as it is
  cd "$T/s23"
  rm a.c && echo x > there && ln -s there a.c && git add a.c there && git commit -qm "a.c a symlink"
  (cd ../m23 && git checkout -q main && echo more >> a.c && git commit -qam more && git push -q ../m23.git main)
  check "symlink: named by its own path" "$(st a.c)" "PM"
  quiet git filesync pull --overwrite a.c
  check "symlink: synced as a file" "$(git ls-files -s a.c | cut -c1-6) $([ -L a.c ] && echo link || echo file)" \
    "100644 file"
  check "symlink: its target untouched" "$(cat there)" "x"
else
  echo "skipped: no symlinks here"
fi

# runs in parallel that clone the same URL into an empty cache (e.g. CI
# jobs sharing it): one clone wins, the others use it (run directly: the
# guard would take the others' writes for its own)
cd "$T"
for i in 1 2 3 4; do new_repo "$T/s23p$i" >/dev/null; cd "$T"; done
for i in 1 2 3 4; do
  (cd "$T/s23p$i" && FILESYNC_CACHE=$T/cache-23p "$PYTHON" "$S" add "$TURL/m23.git" a.c >/dev/null 2>&1; \
   echo $? > "$T/s23p$i.rc") &
done
wait
check "parallel first clones: all succeed" "$(cat "$T"/s23p?.rc | oneline)" "0 0 0 0 "


# =============================================================================
# summary
# =============================================================================
section "Upstream repositories untouched"
check "no writes outside the repository git-filesync runs in" \
  "$(cat "$T/foreign-writes" 2>/dev/null)" ""
echo
if [ $FAILED = 0 ]; then
  echo "ALL PASSED ($PASSED checks)"
  exit 0
else
  echo "SOME FAILED ($FAILED of $((PASSED + FAILED)) checks)"
  exit 1
fi
