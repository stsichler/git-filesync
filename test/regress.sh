#!/bin/bash
# =============================================================================
# Regression test for git-filesync (Linux/macOS/Git Bash)
# =============================================================================
#
# Usage:  test/regress.sh [path/to/git-filesync.py] </dev/null
#
# The script builds throwaway "master" and "slave" repositories in a temp
# directory ($T, removed on exit) and runs git-filesync against them. Each
# check prints "ok   <name>" or "FAIL <name>: got [...] expected [...]";
# the exit code is 1 if any check failed. The Git LFS section is skipped
# when git-lfs is not installed.
#
# Naming in the scenarios:
#   master, m, m3 ...    upstream repositories (where "upstream" commits are made)
#   *.git                bare copies of them, standing in for the server
#   co*                  local checkouts of a master (for 'git filesync map')
#   slave, s, sA ...     repositories that link files from a master
#   file:///nowhere/...  URL of a server that does not exist; such sources
#                        only work through a mapping to a local checkout
#
# Sections:
#    1. Basic workflow: add, status, pull, merge, conflict, hooks
#    2. Line endings: CRLF in master, slaves with different normalization
#    3. Branch name as --commit
#    4. map: mappings to local checkouts of a master
#    5. Offline operation
#    6. diff / difftool / strict files
#    7. .git-filesync registry: sources, unlink, mv, commit consistency
#    8. Colors
#    9. status like 'git status', pull like 'git pull'
#   10. Robustness: unsafe registry paths, special file names, odd entries
#   11. Recorded commit: the one that produced the synced version
#   12. Git LFS: master / slave / both / neither, via mapping and via cache
#   13. Tags: sources pinned to a tag
#   14. source: list, rename and change sources
#   15. Files renamed or deleted in the master
#   16. Dry runs: pull --dry-run, add / unlink / mv -n
#   17. add DIR: all files of a master directory, --include / --exclude
#   18. pull -b / --tag: switching branch or tag; newer tags
#
# Adding a test: put it into the section it belongs to, or add a new
# section at the end that starts with 'section' and 'cd "$T"'.

# --- setup -------------------------------------------------------------------

# The script under test (absolute path): the argument, or the one in the
# directory above this test.
S=${1:-$(dirname "$0")/../git-filesync.py}
S=$(cd "$(dirname "$S")" && pwd)/$(basename "$S")

# Scratch directory for all repositories; removed on exit.
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cd "$T" || exit 2

# Isolate from the user's setup: own HOME (global git config) and own
# cache directory (git-filesync keeps its clones of master repos there).
export HOME=$T/home XDG_CACHE_HOME=$T/cache
mkdir -p "$HOME"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@x GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@x
export GIT_EDITOR=true                 # accept commit messages unchanged
export GIT_PAGER=cat                   # never start a pager
git config --global init.defaultBranch main
git config --global alias.filesync "!python3 $S"

# --- helpers -----------------------------------------------------------------

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

# oneline - join the lines of stdin with blanks ("a\nb\n" -> "a b ")
oneline() { tr '\n' ' '; }

# changes - only the changed lines of a diff on stdin, joined ("-b +B ")
changes() { grep -E '^[-+][^-+]' | oneline; }

# new_slave DIR - create a repository with an empty initial commit, cd into it
new_slave() { git init -q "$1" && cd "$1" && git commit -q --allow-empty -m init; }


# =============================================================================
section "1. Basic workflow: add, status, pull, merge, conflict, hooks"
# =============================================================================

# master: lib.c with lines a..g; master.git: the "server"
git init -q master
(cd master && printf 'a\nb\nc\nd\ne\nf\ng\n' > lib.c && git add . && git commit -qm "initial lib")
git clone -q --bare master master.git
git -C master.git config uploadpack.allowFilter true    # allow blobless clones
git -C master remote add origin "$T/master.git"
git -C master fetch -q
URL=file://$T/master.git

# up SED-EXPR MESSAGE - change lib.c in master, commit and push
up() { (cd "$T/master" && sed -i "$1" lib.c && git commit -qam "$2" && git push -q origin main); }

# slave: links master's lib.c as src/lib.c
new_slave slave
quiet git filesync add src/lib.c "$URL" -p lib.c
check "add + status clean" "$(st)" ""
check "add commits file and entry" "$(git show --name-only --format= HEAD | sort | oneline)" ".git-filesync src/lib.c "
check "add: proposed commit message" "$(git log -1 --format=%B | sed '/^$/d' | sed 's/@[0-9a-f]*$/@X/' | oneline)" \
  "Add src/lib.c from $(basename "$T")/master@X Upstream: $URL (main:lib.c) "

# two upstream commits -> pending; pull lists them in the commit message
up 's/^b$/B/' "Change B"
up 's/^c$/C/' "Change C"
check "pending count, relative path (from subdir)" \
  "$(cd src && git filesync status | grep -cP '^\tpending:\s+lib\.c  \(2 commits\)')" "1"
git filesync pull --no-edit src/lib.c >/dev/null
check "commit msg lists commits" "$(git log -1 --format=%B | grep -c '^- Change')" "2"
check "after pull" "$(st)" ""

# a committed local adaptation is kept by the next pull (3-way merge)
sed -i 's/^g$/G-local/' src/lib.c
git commit -qam tweak
up 's/^a$/A/' "Change A"
check "pending + adapted" "$(st)" "PA"
git filesync pull --no-edit src/lib.c >/dev/null
check "clean merge result" "$(oneline < src/lib.c)" "A B C d e f G-local "

# local and upstream change of the same line -> conflict
sed -i 's/^e$/E-local/' src/lib.c
git commit -qam "local e"
up 's/^e$/E-up/' "Change E"
check "conflict rc" "$(rc git filesync pull src/lib.c)" "1"
check "conflict markers" "$(grep -c '^<<<<<<<' src/lib.c)" "1"
check "conflict: message prepared for git commit" \
  "$(head -1 "$(git rev-parse --git-dir)/SQUASH_MSG" | grep -c '^Sync src/lib.c from')" "1"
git checkout -q src/lib.c 2>/dev/null
git reset -q --hard
check "git reset drops the prepared message" "$(ls "$(git rev-parse --git-dir)/SQUASH_MSG" 2>/dev/null)" ""

# mapped to the local checkout, unpushed master commits are seen and warned
git filesync map "$URL" "$T/master" >/dev/null
(cd "$T/master" && sed -i 's/^f$/F/' lib.c && git commit -qam "unpushed F")
check "local checkout warns unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "1"
git filesync map "$URL" --unset >/dev/null
check "--remote / unmapped ignores unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "0"
(cd "$T/master" && git push -q origin main)

# --commit with an older master commit syncs backwards (revert)
OLD=$(git -C "$T/master" rev-parse HEAD~3)
git reset -q --hard
quiet git filesync pull --no-edit --commit "$OLD" src/lib.c
check "revert message" "$(git log -1 --format=%B | grep -c 'Reverts upstream')" "1"

# a deleted linked file is an uncommitted change; pull --all leaves it alone
quiet git filesync pull --no-edit src/lib.c
rm src/lib.c
check "deleted file is an uncommitted change" "$(st)" " AD"
quiet git filesync pull --all --no-edit
check "pull --all leaves locally deleted file alone" \
  "$([ -e src/lib.c ] && echo restored || echo deleted)" "deleted"
git restore src/lib.c

# hooks: install and remove our own hook files
git filesync install-hooks >/dev/null
check "hooks installed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | wc -l)" "2"
git filesync uninstall-hooks >/dev/null
check "own hooks removed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | wc -l)" "0"

# foreign hooks: install-hooks leaves them alone and prints the lines to add.
# pre-push gets these lines added by hand, post-merge stays without them;
# uninstall-hooks must remove only our lines.
printf '#!/bin/sh\necho mine\n' > .git/hooks/pre-push
chmod +x .git/hooks/pre-push
git filesync install-hooks 2>/dev/null | sed -n '/^# git-filesync/,/|| true$/p' >> .git/hooks/pre-push
printf '#!/bin/sh\necho other\n' > .git/hooks/post-merge
git filesync uninstall-hooks >/dev/null
check "foreign hook: own lines removed" "$(cat .git/hooks/pre-push)" "$(printf '#!/bin/sh\necho mine')"
check "foreign hook: still executable" "$([ -x .git/hooks/pre-push ] && echo yes)" "yes"
check "foreign hook without snippet untouched" "$(cat .git/hooks/post-merge)" "$(printf '#!/bin/sh\necho other')"
rm -f .git/hooks/pre-push .git/hooks/post-merge

# output into a pipe that is closed early
check "broken pipe no traceback" "$(git filesync status 2>&1 | head -1 | grep -c Traceback)" "0"


# =============================================================================
section "2. Line endings: CRLF in master, slaves with different normalization"
# =============================================================================
cd "$T"

# master m has w.c committed with CRLF line endings
git init -q m
(cd m && printf 'a\r\nb\r\nc\r\nd\r\n' > w.c && git add . && git commit -qm init)
git clone -q --bare m m.git
git -C m remote add origin "$T/m.git"
git -C m fetch -q
URL2=file://$T/m.git

# The same scenario for a slave with core.autocrlf=true, one with
# '* text=auto' and one without any normalization: neither add nor pull
# nor a merge may produce eol warnings or spurious changes.
for mode in autocrlf textauto plain; do
  rm -rf s; git init -q s; cd s
  case $mode in
    autocrlf) git config core.autocrlf true ;;
    textauto) echo '* text=auto' > .gitattributes; git add .gitattributes ;;
  esac
  git commit -q --allow-empty -m i
  quiet git filesync add w.c "$URL2"
  check "$mode: clean after add" "$(st)" ""

  # upstream change; git's "CRLF will be replaced by LF" must not appear
  (cd ../m && printf 'a\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam B && git push -q origin main)
  W=$(git filesync pull --no-edit w.c 2>&1 >/dev/null | grep -c 'will be replaced')
  check "$mode: no eol warnings" "$W" "0"
  check "$mode: clean after pull" "$(st)" ""

  # local adaptation + upstream change -> merge
  sed -i 's/^d/D-local/' w.c
  git commit -qam loc
  (cd ../m && printf 'A\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam A && git push -q origin main)
  check "$mode: merge rc" "$(rc git filesync pull --no-edit w.c)" "0"
  check "$mode: merged content" "$(git show HEAD:w.c | tr -d '\r' | oneline)" "A B c D-local "
  check "$mode: worktree clean" "$(git status --porcelain)" ""

  # reset the master for the next mode
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
new_slave s
quiet git filesync add w.c "$URL2"
(cd ../m && printf 'y\r\n' > w.c && git commit -qam d2 && git push -q origin develop && git checkout -q main)
quiet git filesync pull --no-edit --commit develop w.c
check "--commit <branch> gets current head" "$(tr -d '\r' < w.c)" "y"


# =============================================================================
section "4. map: mappings to local checkouts of a master"
# =============================================================================
cd "$T"

# master m3 with x.c = v1; checkout coA has an unpushed v2, coB is at v1
git init -q m3
(cd m3 && echo v1 > x.c && git add . && git commit -qm v1)
git clone -q --bare m3 m3.git
URL3=file://$T/m3.git
git clone -q m3.git coA
(cd coA && echo v2 > x.c && git commit -qam v2)
git clone -q m3.git coB

# three slaves linking x.c
for s in sA sB sC; do
  (new_slave $s && quiet git filesync add x.c "$URL3")
done

# sA -> coA (given as relative path from a subdirectory), sB -> coB
(cd sA && mkdir -p sub && cd sub && git filesync map "$URL3" ../../coA >/dev/null)
(cd sB && git filesync map "$URL3" "$T/coB" >/dev/null)
check "map default scope is repo-local" "$(git -C sA config --local --get-regexp '^filesync\.' | wc -l)" "1"
check "nothing written globally" "$(git config --global --get-regexp '^filesync\.' | wc -l)" "0"
check "slave A uses checkout A" "$(cd sA && st)" "P"
check "slave B uses checkout B" "$(cd sB && st)" ""
(cd sA && quiet git filesync pull --no-edit x.c)
check "slave A synced from checkout A" "$(cat sA/x.c)" "v2"

# global mapping (set from sC) -> coA; local mappings take precedence
(cd sC && git filesync map --global "$URL3" "$T/coA" >/dev/null)
check "global mapping used without local one" \
  "$(cd sC && git filesync status -v | grep -c "via local checkout $T/coA")" "1"
check "local mapping overrides global" "$(cd sB && st)" ""
check "list marks overridden global" \
  "$(cd sB && git filesync map | grep '^\[global\]' | grep -c overridden)" "1"
(cd sB && git filesync map "$URL3" --unset >/dev/null)
check "after local unset, global applies" "$(cd sB && st)" "P"
check "local map outside repo fails" "$(rc git filesync map "$URL3" "$T/coA")" "2"

# A mapped slave follows the link's branch in the checkout (refs/heads/main),
# not whatever is checked out there.
(cd sB && git filesync map "$URL3" "$T/coB" >/dev/null)
(cd coB && git tag v1 && echo v1b > x.c && git commit -qam v1b)         # local, unpushed
check "mapped: local branch commit pending" "$(cd sB && st)" "P"
(cd sB && quiet git filesync pull --no-edit x.c)
check "mapped: pulled local branch state" "$(cat sB/x.c)" "v1b"

(cd coB && git checkout -q -b feature && echo feat > x.c && git commit -qam feat)
check "mapped: other checked-out branch ignored" "$(cd sB && st)" ""
check "mapped: other checked-out branch warned" \
  "$(cd sB && git filesync status | grep -c "has feature checked out")" "1"
(cd sB && quiet git filesync pull --no-edit x.c)
check "mapped: pull does not take other branch" "$(cat sB/x.c)" "v1b"

(cd coB && git checkout -q main && git reset -q --hard v1)              # branch moved back
check "mapped: older branch state detected" "$(cd sB && st)" "O"
(cd sB && quiet git filesync pull --no-edit x.c)
check "mapped: synced back to older state" "$(cat sB/x.c)" "v1"
check "mapped: revert listed in message" "$(git -C sB log -1 --format=%B | grep -c '^- v1b')" "1"

# uncommitted changes in the checkout are warned about, never synced
echo dirty > coB/x.c
check "mapped: uncommitted master change warned" \
  "$(cd sB && git filesync status | grep -c 'uncommitted changes')" "1"
check "mapped: uncommitted change not synced" "$(cd sB && st)" ""
(cd coB && git checkout -q -- x.c)

# branch 'rel' only known as origin/rel in the checkout -> fallback
(cd coA && git push -q origin HEAD:rel)
(cd coB && git fetch -q)
git init -q sD
(cd sD && git commit -q --allow-empty -m i \
  && git filesync map "$URL3" "$T/coB" >/dev/null \
  && quiet git filesync add -b rel x.c "$URL3")
check "mapped: falls back to origin/<branch>" "$(cat sD/x.c)" "v2"
check "mapped: fallback noted" "$(cd sD && git filesync status | grep -c 'using origin/rel')" "1"
git filesync map --global "$URL3" --unset >/dev/null


# =============================================================================
section "5. Offline operation"
# =============================================================================
cd "$T"

# add via a mapping to a server that cannot be reached; without -b the
# branch is taken from the checkout's origin/HEAD
OFF=https://unreachable.invalid/owner/m3.git
(cd coA && git remote set-head origin main >/dev/null 2>&1)
new_slave sOff
git filesync map "$OFF" "$T/coA" >/dev/null
check "offline add via mapping (no -b)" "$(rc git filesync add x.c "$OFF")" "0"
check "offline add: branch from checkout" \
  "$(git config -f .git-filesync --get-regexp "^source\..*\.branch" | cut -d" " -f2)" "main"
check "offline add: content from checkout" "$(cat x.c)" "v2"

# All commands, including the pre-push hook, with network access forbidden
# (GIT_ALLOW_PROTOCOL=file: any http/https/ssh access fails loudly). Allowed
# on stderr are only the 'not pushed' warning and the hook's 'filesync: ...'
# lines.
(cd "$T/coA" && echo v3 > x.c && git commit -qam v3)
git init -q --bare "$T/sOff-remote.git"
git remote add origin "$T/sOff-remote.git"
git filesync install-hooks >/dev/null
ERR=$(
  export GIT_ALLOW_PROTOCOL=file
  {
    git filesync status
    git filesync status --no-fetch
    git filesync pull --no-edit x.c
    git filesync status
    git filesync pull --all --no-edit
    git commit -q --allow-empty -m p
    git push -q origin HEAD:main
    git filesync map
  } 2>&1 >/dev/null | grep -vE 'not pushed|^filesync: '
)
check "offline: no errors/warnings in any command" "$ERR" ""
check "offline: pull got v3 from checkout" "$(cat x.c)" "v3"

# known URL, server gone, but a cache clone exists: add still works
cd "$T"
mv m3.git m3-away.git
new_slave sOff2
check "offline add via cache (no -b)" "$(rc git filesync add x.c "$URL3")" "0"
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

# master m4 (only reachable via mapping) with lib/foo.c and lib/bar.h;
# slave s4 links them as src/foo.c and src/bar.h (strict)
git init -q m4
(cd m4 && mkdir lib && printf 'a\nb\nc\nd\ne\n' > lib/foo.c && printf 'x\n' > lib/bar.h \
  && git add . && git commit -qm init)
new_slave s4
git filesync map file:///nowhere/m4.git "$T/m4" >/dev/null
quiet git filesync add src/foo.c file:///nowhere/m4.git -p lib/foo.c
quiet git filesync add src/bar.h file:///nowhere/m4.git -p lib/bar.h --strict

# diff: synced version <-> local file
check "diff: nothing when clean" "$(git filesync diff)" ""
sed -i 's/^b$/B-local/' src/foo.c
git commit -qm 'adapt foo' src/foo.c
check "diff: shows local change" "$(git filesync diff | changes)" "-b +B-local "
check "diff: labels" "$(git filesync diff | grep -E '^(---|\+\+\+)' | oneline)" "--- synced/src/foo.c +++ local/src/foo.c "
check "diff: options after --" "$(git filesync diff -- --stat | head -1 | tr -s ' ')" " src/foo.c | 2 +-"

# --master-paths: a patch that applies in the master, also after it moved on
git filesync diff --master-paths > ../p4.patch
check "diff --master-paths applies in master" "$(cd ../m4 && git apply --check ../p4.patch && echo ok)" "ok"
(cd ../m4 && sed -i 's/^e$/E-up/' lib/foo.c && git commit -qam "Change E")
check "diff --upstream" "$(git filesync diff --upstream | changes)" "-e +E-up "
check "apply -3 after master moved" \
  "$(cd ../m4 && git apply -3 ../p4.patch >/dev/null 2>&1 && sed -n 2p lib/foo.c; git reset -q --hard)" "B-local"

# difftool: the working file itself is passed, --upstream uses temp copies
check "difftool: real working file" "$(git filesync difftool src/foo.c)" \
  "TOOL synced-$(git -C ../m4 rev-parse --short HEAD~1) $T/s4/src/foo.c"
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
check "difftool with file: no prompt" "$(git filesync difftool src/foo.c </dev/null | grep -c 'TOOL ')" "1"
check "difftool --prompt with file" "$(printf 'n\n' | git filesync difftool --prompt src/foo.c | grep -c 'TOOL ')" "0"
git config difftool.prompt false
check "difftool.prompt=false respected" "$(git filesync difftool </dev/null | grep -c 'TOOL ')" "2"
git config --unset difftool.prompt
check "difftool prompt names tool" "$(printf 'q\n' | git filesync difftool | grep -c "Launch 'fake'")" "1"
git checkout -q -- src/bar.h

# strict: any change of src/bar.h is a violation
check "strict file clean: no violation" "$(st src/bar.h)" ""
echo y >> src/bar.h
check "strict violation reported (uncommitted)" "$(git filesync status -s src/bar.h)" "  M src/bar.h  (strict!)"
check "strict violation in long format" \
  "$(git filesync status src/bar.h | grep -cP '^\tmodified:\s+src/bar\.h  \(NOT ALLOWED: strict\)')" "1"
check "strict violation exit code" "$(rc git filesync status --exit-code src/bar.h)" "1"
check "strict violation in hook output" "$(git filesync status --hook 2>&1 | grep -c 'NOT ALLOWED')" "1"
check "pull refuses strict merge" "$(rc git filesync pull --no-edit src/bar.h)" "2"
check "pull --all continues after strict error" "$(git filesync pull --all --no-edit 2>&1 | grep -c '^error:')" "0"
check "non-strict file merged by --all" "$(sed -n 2p src/foo.c; sed -n 5p src/foo.c)" "$(printf 'B-local\nE-up')"
git commit -qm "adapt bar" src/bar.h
check "strict violation (committed)" "$(git filesync status -s src/bar.h)" " A  src/bar.h  (strict!)"

# pull --overwrite restores the master version, in strict and other files
quiet git filesync pull --no-edit --overwrite src/bar.h
check "pull --overwrite restores" "$(cat src/bar.h)" "x"
check "overwrite commit message" "$(git log -1 --format=%s)" \
  "Restore src/bar.h from nowhere/m4@$(git -C ../m4 log -1 --format=%h -- lib/bar.h)"
check "after overwrite clean" "$(st src/bar.h)" ""
sed -i 's/^a$/A-local/' src/foo.c
git commit -qm 'adapt a' src/foo.c
quiet git filesync pull --no-edit --overwrite src/foo.c
check "--overwrite discards in non-strict file" "$(git filesync diff)" ""


# =============================================================================
section "7. .git-filesync registry: sources, unlink, mv, commit consistency"
# =============================================================================
# (continues in s4)

# files from one master share one [source]; add accepts the source name
check "one [source] for files of one master" \
  "$(git config -f .git-filesync --get-regexp '^source\..*\.url' | wc -l)" "1"
SRC=$(git config -f .git-filesync --get-regexp '^source\..*\.url' | sed 's/^source\.\(.*\)\.url .*/\1/')
(cd ../m4 && printf 'n\n' > lib/new.h && sed -i 's/^d$/D-up/' lib/foo.c && git add . && git commit -qm "add new.h")
# --no-commit: only staged; the proposed message is printed for copying
OUT=$(git filesync add --no-commit include/new.h "$SRC" -p lib/new.h 2>&1)
check "add by source name" "$?" "0"
check "add by source name: same source" "$(git config -f .git-filesync file.include/new.h.source)" "$SRC"
check "add --no-commit: staged, not committed" "$(git status --porcelain | oneline)" "M  .git-filesync A  include/new.h "
check "add --no-commit: prints the message" "$(echo "$OUT" | grep -c "^Add include/new.h from $SRC@")" "1"
check "add --no-commit: prints the commit command" \
  "$(echo "$OUT" | grep -c 'git commit -e -F ".*FILESYNC_MSG_include_new.h" -- include/new.h .git-filesync')" "1"
check "add --no-commit: message prepared for git commit" \
  "$(head -1 "$(git rev-parse --git-dir)/SQUASH_MSG" | grep -c "^Add include/new.h from $SRC@")" "1"
check "add --no-commit: says so" "$(echo "$OUT" | grep -c "also prepared for a plain 'git commit'")" "1"

# pull commits .git-filesync, so it refuses while another entry is uncommitted
check "pull refused while other entry uncommitted" "$(rc git filesync pull --no-edit src/foo.c)" "2"
check "refusal names the entry" \
  "$(git filesync pull --no-edit src/foo.c 2>&1 | grep -c 'uncommitted changes for include/new.h')" "1"
check "add refused while other entry uncommitted" "$(rc git filesync add include/new2.h "$SRC" -p lib/new.h)" "2"
git commit -q -F "$(git rev-parse --git-dir)/FILESYNC_MSG_include_new.h"
check "add --no-commit: message file usable" "$(git log -1 --format=%s | grep -c '^Add include/new.h from')" "1"
check "commit drops the prepared message" "$(ls "$(git rev-parse --git-dir)/SQUASH_MSG" 2>/dev/null)" ""
check "registry committed with link" "$(git show --name-only --format= HEAD | sort | oneline)" ".git-filesync include/new.h "

# mv: moves file and entry
check "mv rc" "$(rc git filesync mv include/new.h include/renamed.h)" "0"
check "mv: file moved" "$(ls include)" "renamed.h"
check "mv: link moved (staged, not yet committed)" "$(git filesync status -s include/renamed.h)" "  ? include/renamed.h"
check "mv: old entry gone" "$(git config -f .git-filesync --get-regexp '^file\.include/new\.h\.' | wc -l)" "0"
git commit -qm mv

# unlink: removes the entry, keeps the file; the last unlink removes the registry
check "unlink rc" "$(rc git filesync unlink include/renamed.h)" "0"
check "unlink: file kept" "$(cat include/renamed.h)" "n"
check "unlink: entry removed" "$(git filesync status include/renamed.h 2>&1 | grep -c 'not linked')" "1"
check "unlink: source kept while used" "$(git config -f .git-filesync --get-regexp '^source\.' | wc -l)" "2"
git commit -qm unlink
git filesync unlink src/foo.c src/bar.h >/dev/null
check "unlink all: registry removed" "$([ -e .git-filesync ] && echo exists || echo gone)" "gone"
check "unlink all: removal staged" "$(git status --porcelain .git-filesync)" "D  .git-filesync"
git reset -q --hard

# a new [source] is keyed 'owner/repo' after its URL; another URL with the
# same key gets a number appended instead of reusing the existing source
check "source key from URL" "$SRC" "nowhere/m4"
git filesync map file:///other/nowhere/m4.git "$T/m4" >/dev/null
check "add: output shows the new key" \
  "$(git filesync add --no-commit include/other.h file:///other/nowhere/m4.git -p lib/bar.h 2>&1 | grep -c '^linked include/other.h -> nowhere/m4-2:lib/bar.h (main)')" "1"
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
quiet git filesync pull --no-edit src/foo.c
check "pull: source key in commit message" \
  "$(git log -1 --format=%s)" "Sync src/foo.c from mylib@$(git -C ../m4 log -1 --format=%h -- lib/foo.c)"
quiet git filesync add include/x.h file:///nowhere/m4.git -p lib/bar.h
check "add finds the source by URL, not by key" \
  "$(git config -f .git-filesync file.include/x.h.source)" "mylib"
check "add by URL: no new source" "$(git config -f .git-filesync --get-regexp '^source\..*\.url' | wc -l)" "1"

# add over an existing, different file: message notes modifications and strict
echo mine > include/y.h
quiet git filesync add --strict include/y.h mylib -p lib/bar.h
check "add existing file: subject" "$(git log -1 --format=%s | sed 's/@[0-9a-f]*$//')" "Link include/y.h to mylib"
check "add existing file: notes" \
  "$(git log -1 --format=%B | grep -cE '^(Contains local modifications|Strict:)')" "2"
check "add existing file: committed as is" "$(git show HEAD:include/y.h)" "mine"

# commit aborted in the editor: changes stay staged, rc 1
check "add: commit aborted" "$(GIT_EDITOR=false rc git filesync add include/z.h mylib -p lib/bar.h)" "1"
check "add: aborted commit leaves it staged" "$(git status --porcelain | oneline)" "M  .git-filesync A  include/z.h "
git reset -q --hard "$BASE"


# =============================================================================
section "8. Colors"
# =============================================================================
# (continues in s4)

ESC=$(printf '\033')
check "no color when piped" "$(git filesync status | grep -c "$ESC")" "0"
check "--color=always" "$(git filesync status --color=always | grep -q "$ESC" && echo yes)" "yes"
check "color.ui=always via git -c" "$(git -c color.ui=always filesync status | grep -q "$ESC" && echo yes)" "yes"
check "color.filesync=never beats color.ui" \
  "$(git -c color.ui=always -c color.filesync=never filesync status | grep -c "$ESC")" "0"
check "NO_COLOR" "$(NO_COLOR=1 git -c color.ui=always filesync status | grep -c "$ESC")" "0"
check "colored error on stderr" "$(git filesync pull nothere --color=always 2>&1 | grep -c "${ESC}\[1;31merror:")" "1"


# =============================================================================
section "9. status like 'git status', pull like 'git pull'"
# =============================================================================
cd "$T"

# master m5 with a.c .. e.c (lines 1..5), all linked in s5; e.c is strict
git init -q m5
(cd m5 && for f in a b c d e; do printf '1\n2\n3\n4\n5\n' > $f.c; done && git add . && git commit -qm i)
new_slave s5
git filesync map file:///nowhere/m5.git "$T/m5" >/dev/null
for f in a b c d e; do
  quiet git filesync add $f.c file:///nowhere/m5.git
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
(cd ../m5 && sed -i 's/^5$/5-up/' a.c b.c d.c && git commit -qam up)
sed -i 's/^1$/1-adapt/' b.c c.c e.c; git commit -qam adapt          # committed adaptations
sed -i 's/^3$/3-wip/' c.c d.c                                          # uncommitted changes
check "status -s: three columns" "$(git filesync status -s | tr '\n' '|')" \
  "P   a.c|PA  b.c| AM c.c|P M d.c| A  e.c  (strict!)|"

# long format: sections like git status
OUT=$(git filesync status)
check "status: upstream section" "$(echo "$OUT" | grep -A4 '^Upstream changes to sync:' | grep -cP '^\tpending:')" "3"
check "status: commit count" "$(echo "$OUT" | grep -cP '^\tpending:\s+b\.c  \(1 commit\)')" "1"
check "status: adapted section" "$(echo "$OUT" | grep -A6 '^Locally adapted files:' | grep -cP '^\tadapted:')" "3"
check "status: strict note on adapted" "$(echo "$OUT" | grep -cP '^\tadapted:\s+e\.c  \(NOT ALLOWED: strict\)')" "1"
check "status: uncommitted section" "$(echo "$OUT" | grep -A5 '^Uncommitted changes:' | grep -cP '^\tmodified:')" "2"
check "status: no 'nothing to sync' when pending" "$(echo "$OUT" | grep -c 'nothing to sync')" "0"
check "status: exit code 0 like git" "$(rc git filesync status)" "0"
check "status --exit-code" "$(rc git filesync status --exit-code)" "1"
check "status: advice.statusHints=false" "$(git -c advice.statusHints=false filesync status | grep -c '(use ')" "0"
check "status -v: all files listed" \
  "$(git filesync status -v | grep -A6 '^Linked files:' | grep -cP '^\t(unmodified|adapted):')" "5"
check "status --hook: adapted alone is quiet" "$(git filesync status --hook 2>&1 | grep -c 'c\.c')" "0"

# pull refuses to overwrite uncommitted changes, unless --autostash
check "pull refuses uncommitted changes" "$(rc git filesync pull --no-edit d.c)" "2"
check "pull refusal message" "$(git filesync pull --no-edit d.c 2>&1 | grep -c 'would be overwritten by pull')" "1"
check "refused pull leaves file alone" "$(oneline < d.c)" "1 2 3-wip 4 5 "
check "pull --autostash" "$(rc git filesync pull --no-edit --autostash d.c)" "0"
check "autostash: commit has synced version only" "$(git show HEAD:d.c | oneline)" "1 2 3 4 5-up "
check "autostash: uncommitted change re-applied" "$(oneline < d.c)" "1 2 3-wip 4 5-up "
quiet git filesync pull --no-edit b.c
check "pull merges committed adaptation" "$(oneline < b.c)" "1-adapt 2 3 4 5-up "

# --no-commit: only staged; the proposed message is printed for copying
OUT=$(git filesync pull --no-commit a.c)
check "pull --no-commit: staged, not committed" "$(git status --porcelain a.c .git-filesync | oneline)" "M  .git-filesync M  a.c "
check "pull --no-commit: prints the message" "$(echo "$OUT" | grep -cE '^(Sync a\.c from |- up \()')" "2"
git commit -q
check "pull --no-commit: plain git commit takes the message" \
  "$(git log -1 --format=%B | grep -cE '^(Sync a\.c from |- up \()')" "2"

# diff --committed: without uncommitted changes; diff exit code passed on
check "diff --committed: adaptations only" \
  "$(git filesync diff --committed -- --stat | tail -1 | grep -o '[0-9]* files changed')" "3 files changed"
check "diff --committed: no wip" "$(git filesync diff --committed c.c | grep -c 3-wip)" "0"
check "diff: includes wip" "$(git filesync diff c.c | grep -c 3-wip)" "1"
check "diff -- --exit-code: no difference" "$(rc git filesync diff a.c -- --exit-code)" "0"
check "diff -- --exit-code: difference" "$(rc git filesync diff c.c -- --exit-code)" "1"


# =============================================================================
section "10. Robustness: unsafe registry paths, special file names, odd entries"
# =============================================================================
cd "$T"

# master m6: a.txt, sub/s.txt and a file name with glob characters
git init -q m6
(cd m6 && mkdir sub && echo a > a.txt && echo s > sub/s.txt && echo f > 'f[1].txt' \
  && git add . && git commit -qm i)
M6=$(git -C m6 rev-parse HEAD)
B6=$(git -C m6 rev-parse HEAD:a.txt)
new_slave s6
git filesync map file:///nowhere/m6.git "$T/m6" >/dev/null

# hand-written registry with entries pointing outside the work tree or into .git
printf '[source "m6"]\n\turl = file:///nowhere/m6.git\n\tbranch = main\n' > .git-filesync
for f in ../outside.txt "$T/abs.txt" .git/hooks/post-commit; do
  printf '[file "%s"]\n\tsource = m6\n\tpath = a.txt\n\tcommit = %s\n\tblob = %s\n' "$f" "$M6" "$B6" >> .git-filesync
done
git add .git-filesync
git commit -qm "unsafe entries"
check "unsafe paths: pull fails" "$(rc git filesync pull --all --no-edit)" "2"
check "unsafe paths: nothing written" "$(ls ../outside.txt "$T/abs.txt" .git/hooks/post-commit 2>/dev/null | wc -l)" "0"
check "unsafe paths: status errors" "$(git filesync status -s 2>/dev/null | grep -c '^E')" "3"
check "unsafe paths: removal hint" "$(git filesync status 2>&1 | grep -c 'remove-section')" "3"
git rm -q .git-filesync
git commit -qm "drop unsafe entries"

# the same paths given on the command line
check "add into .git refused" "$(rc git filesync add .git/x file:///nowhere/m6.git -p a.txt)" "2"
check "add outside refused" "$(rc git filesync add ../x file:///nowhere/m6.git -p a.txt)" "2"
# a master file added to an existing directory goes into it, like cp
mkdir d
quiet git filesync add --no-commit d file:///nowhere/m6.git -p a.txt
check "add FILE into existing directory" "$(git config -f .git-filesync file.d/a.txt.path)" "a.txt"
git reset -q --hard
# a master directory links the files below it
check "master path is a directory" "$(git filesync add -n x.txt file:///nowhere/m6.git -p sub | cut -d' ' -f1-5)" \
  "would link x.txt/s.txt -> nowhere/m6:sub/s.txt"
quiet git filesync add a.txt file:///nowhere/m6.git
check "mv outside refused" "$(rc git filesync mv a.txt ../moved.txt)" "2"
check "mv outside: file stays" "$(ls a.txt ../moved.txt 2>/dev/null)" "a.txt"
check "map --unset without URL" "$(rc git filesync map --unset)" "2"

# wildcard characters in a file name are taken literally: 'f[1].txt' must
# not match the unrelated file f1.txt
echo other > f1.txt
git add f1.txt
quiet git filesync add 'f[1].txt' file:///nowhere/m6.git
git commit -qm link
echo changed > f1.txt
check "glob chars: other file's change not attributed" "$(st 'f[1].txt')" ""
(cd ../m6 && echo f2 > 'f[1].txt' && git commit -qam f2)
quiet git filesync pull --no-edit 'f[1].txt'
check "glob chars: pull commits only the file" \
  "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" ".git-filesync f[1].txt "
check "glob chars: other file stays uncommitted" "$(git status --porcelain f1.txt)" " M f1.txt"
git checkout -q -- f1.txt

# 'strict' without a value is true, as everywhere in git config
echo local >> a.txt
git commit -qam adapt
sed -i '/^\[file "a.txt"\]/a\	strict' .git-filesync
check "bare 'strict' means true" "$(git filesync status -s a.txt)" " A  a.txt  (strict!)"
git checkout -q -- .git-filesync

# synced version not readable -> warning, not a silent 'adapted'; --overwrite recovers
git config -f .git-filesync 'file.f[1].txt.blob' 0123456789abcdef0123456789abcdef01234567
check "base unavailable: warned" \
  "$(git filesync status 2>&1 | grep -c 'synced version 0123456789ab not available')" "1"
quiet git filesync pull --no-edit --overwrite 'f[1].txt'
check "base unavailable: --overwrite recovers" "$(st 'f[1].txt')" ""

# mapped checkout with a remote but no origin/HEAD: the default branch is a
# guess (the checked-out branch), and add says so
cd "$T"
git clone -q m6 co6
(cd co6 && git remote set-head origin -d && git checkout -q -b feature)
new_slave s7
git filesync map file:///nowhere/m6.git "$T/co6" >/dev/null
check "default branch guessed: warned" \
  "$(git filesync add a.txt file:///nowhere/m6.git 2>&1 | grep -c "using its checked-out branch 'feature'")" "1"


# =============================================================================
section "11. Recorded commit: the one that produced the synced version"
# =============================================================================
# The registry records the master commit that last changed the file, not
# the branch tip; commits not touching the file are ignored everywhere.
cd "$T"

# m7.git (bare) and checkout co7: "f v1" changes f.txt, "other 1" only o.txt
git init -q --bare m7.git
git -C m7.git config uploadpack.allowFilter true
git clone -q m7.git co7 2>/dev/null
(cd co7 && echo v1 > f.txt && echo o1 > o.txt && git add . && git commit -qm "f v1" \
  && echo o2 > o.txt && git commit -qam "other 1" && git push -q origin main)
URL7=file://$T/m7.git

# rec - the commit recorded for f.txt
rec() { git config -f .git-filesync file.f.txt.commit; }

new_slave s8
quiet git filesync add f.txt "$URL7"
check "add (new file): commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"
quiet git filesync add --force f.txt "$URL7"
check "relink unchanged file: registry unchanged" "$(git status --porcelain)" ""
quiet git filesync add --force --commit "$(git -C ../co7 rev-parse HEAD)" f.txt "$URL7"
check "add --commit tip: commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"

# "f v2" changes f.txt, "other 2" does not
(cd ../co7 && echo v2 > f.txt && git commit -qam "f v2" && echo o3 > o.txt && git commit -qam "other 2" \
  && git push -q origin main)
check "status counts only commits changing the file" "$(git filesync status | grep -c '(1 commit)')" "1"
quiet git filesync pull --no-edit f.txt
check "pull: commit that changed the file" "$(rec)" "$(git -C ../co7 rev-parse HEAD~1)"
check "pull message: names that commit" \
  "$(git log -1 --format=%s | grep -c "@$(git -C ../co7 rev-parse --short HEAD~1)$")" "1"
check "pull message: only commits changing the file" \
  "$(git log -1 --format=%B | grep '^- ' | tr '\n' '|')" "- f v2 ($(git -C ../co7 rev-parse --short HEAD~1))|"

# mapped: unpushed commits matter only if they change the file
git filesync map "$URL7" "$T/co7" >/dev/null
(cd ../co7 && echo o4 > o.txt && git commit -qam "other unpushed")
check "unpushed commit not touching the file: no warning" "$(git filesync status 2>&1 | grep -c 'not pushed')" "0"
check "unpushed other commit: still up to date" "$(st)" ""
(cd ../co7 && echo v3 > f.txt && git commit -qam "f unpushed")
check "unpushed change of the file: warned" "$(git filesync status 2>&1 | grep -c 'not pushed')" "1"
git filesync map "$URL7" --unset >/dev/null


# =============================================================================
section "12. Git LFS: master / slave / both / neither, via mapping and via cache"
# =============================================================================
cd "$T"

if git lfs version >/dev/null 2>&1; then
  git lfs install --skip-repo >/dev/null

  # Every combination of: d.txt in LFS in the master (mlfs), in LFS in the
  # slave (slfs), master accessed via mapping or via cache clone (via).
  # Content must always be the real file, storage must follow the slave's
  # .gitattributes, diff and merge must work on the resolved content.
  for mlfs in yes no; do
    # master ml (checkout) / ml.git (bare): d.txt with lines l1..l5
    rm -rf ml ml.git
    git init -q --bare ml.git
    git clone -q ml.git ml 2>/dev/null
    (cd ml && { [ $mlfs = yes ] && git lfs track d.txt >/dev/null; true; } \
       && printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt && git add . && git commit -qm v1 && git push -q origin main 2>/dev/null)

    for slfs in yes no; do
      for via in map cache; do
        tag="lfs master=$mlfs slave=$slfs via=$via"
        lfs_count=$([ $slfs = yes ] && echo 1 || echo 0)   # expected LFS pointers in slave

        # fresh slave (and fresh cache) linking d.txt
        rm -rf sl "$T/cache"; git init -q sl; cd sl
        [ $slfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        git commit -q --allow-empty -m i
        [ $via = map ] && git filesync map "file://$T/ml.git" "$T/ml" >/dev/null
        quiet git filesync add d.txt "file://$T/ml.git"
        check "$tag: content after add" "$(head -1 d.txt)" "l1"
        check "$tag: slave storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$lfs_count"
        check "$tag: clean" "$(st)" ""

        # upstream change of l5, local change of l1 -> diff and merge
        (cd "$T/ml" && sed -i 's/^l5$/L5-up/' d.txt && git commit -qam l5 && git push -q origin main 2>/dev/null)
        sed -i 's/^l1$/L1-local/' d.txt
        git commit -qam loc
        check "$tag: diff" "$(git filesync diff | changes)" "-l1 +L1-local "
        check "$tag: diff --upstream" "$(git filesync diff --upstream | changes)" "-l5 +L5-up "
        quiet git filesync pull --no-edit d.txt
        check "$tag: merged" "$(oneline < d.txt)" "L1-local l2 l3 l4 L5-up "
        check "$tag: committed storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$lfs_count"
        check "$tag: after merge (adapted, clean worktree)" "$(st) $(git status --porcelain)" " A "

        # add over an existing file that equals an older master version
        cd ..; rm -rf sl2; git init -q sl2; cd sl2
        [ $slfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt
        git add .
        git commit -qm i
        [ $via = map ] && git filesync map "file://$T/ml.git" "$T/ml" >/dev/null
        check "$tag: add detects older version" \
          "$(git filesync add d.txt "file://$T/ml.git" 2>&1 | grep -c 'matches upstream')" "1"
        cd ..

        # reset the master for the next combination
        (cd ml && git reset -q --hard HEAD~1 && git push -qf origin main 2>/dev/null)
      done
    done
  done

  # LFS content unavailable -> clear error instead of a pointer file
  rm -rf sl "$T/cache"
  new_slave sl
  (cd ../ml && git lfs track d.txt >/dev/null && git add . && git commit -qm lfs && git push -q origin main 2>/dev/null)
  ERR=$(GIT_LFS_SKIP_SMUDGE=1 git filesync add d.txt "file://$T/ml.git" 2>&1)
  check "lfs unavailable: add fails" "$(echo "$ERR" | grep -c 'stored in Git LFS')" "1"
  check "lfs unavailable: no pointer file written" "$([ -e d.txt ] && echo written || echo none)" "none"
else
  echo "skip Git LFS tests (git-lfs not installed)"
fi


# =============================================================================
section "13. Tags: sources pinned to a tag"
# =============================================================================
cd "$T"

# m9.git (bare, the server) and checkout co9: t.c with lines 1..3, tag v1
git init -q --bare m9.git
git -C m9.git config uploadpack.allowFilter true
git clone -q m9.git co9 2>/dev/null
(cd co9 && printf '1\n2\n3\n' > t.c && git add . && git commit -qm v1 && git tag v1 \
  && git push -q origin main v1)
URL9=file://$T/m9.git

new_slave s9
quiet git filesync add --tag v1 t.c "$URL9"
SRC9=$(git config -f .git-filesync --get-regexp '^source\..*\.url' | sed 's/^source\.\(.*\)\.url .*/\1/')
check "add --tag: source with tag, no branch" \
  "$(git config -f .git-filesync --get-regexp '^source\.' | cut -d' ' -f1 | sed 's/.*\.//' | sort | oneline)" "tag url "
check "add --tag: message names the tag" "$(git log -1 --format=%B | grep -c "^Upstream: $URL9 (v1:t.c)$")" "1"
check "status -v shows the tag" "$(git filesync status -v | grep -c '(tag v1)')" "1"

# a newer commit on the branch doesn't concern the pinned file
(cd ../co9 && sed -i 's/^3$/3b/' t.c && git commit -qam "on main" && git push -q origin main)
check "tag: branch commits ignored" "$(st)" ""

# the tag is in the cache: nothing is fetched, works without the server
mv ../m9.git ../m9-away.git
check "tag: no fetch needed (server gone)" "$(git filesync status 2>&1)" "nothing to sync, 1 linked file unmodified"
mv ../m9-away.git ../m9.git

# new tag v2: set-tag stages the change, the missing tag is fetched
(cd ../co9 && git tag v2 && git push -q origin v2)
git filesync source set-tag "$SRC9" v2 >/dev/null
check "set-tag: tag replaced" "$(git config -f .git-filesync source.$SRC9.tag)" "v2"
check "set-tag: registry staged" "$(git status --porcelain .git-filesync)" "M  .git-filesync"
git commit -qm "pin v2"
check "new tag: pending" "$(st)" "P"
quiet git filesync pull --no-edit t.c
check "pull to the new tag" "$(oneline < t.c)" "1 2 3b "

# with a mapped checkout the tag is taken from there, its branch ignored
git filesync map "$URL9" "$T/co9" >/dev/null
(cd ../co9 && sed -i 's/^1$/1c/' t.c && git commit -qam "after v2")
check "mapped: branch ignored" "$(st)" ""
check "mapped: no checked-out warning for a tag" "$(git filesync status 2>&1 | grep -c 'checked out')" "0"
(cd ../co9 && git tag v3)
git filesync source set-tag "$SRC9" v3 >/dev/null
check "mapped: tag from the checkout" "$(st)" "P"
git filesync map "$URL9" --unset >/dev/null
check "tag unknown on the server: error" "$(st)" "E"

# back to following the branch: set-branch only sets the branch (the one to
# look for newer tags on), set-tag --unset removes the pin
check "set-tag: TAG or --unset" "$(rc git filesync source set-tag "$SRC9")" "2"
check "set-tag --unset without a branch: refused" "$(rc git filesync source set-tag "$SRC9" --unset)" "2"
git filesync source set-branch "$SRC9" main >/dev/null
check "set-branch on a pinned source: tag kept" \
  "$(git config -f .git-filesync source.$SRC9.branch) $(git config -f .git-filesync source.$SRC9.tag)" "main v3"
check "set-branch on a pinned source: still pinned" "$(st)" "E"
git filesync source set-tag "$SRC9" --unset >/dev/null
check "set-tag --unset: branch kept, tag removed" \
  "$(git config -f .git-filesync source.$SRC9.branch) $(git config -f .git-filesync source.$SRC9.tag)" "main "
check "set-tag --unset: up to date with main" "$(st)" ""
check "set-branch --unset on a following source: refused" \
  "$(rc git filesync source set-branch "$SRC9" --unset)" "2"
git commit -qm "follow main"


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
check "rename: old section gone" "$(git config -f .git-filesync --get-regexp "^source\.$SRC9\." | wc -l)" "0"
check "rename: status works" "$(st)" ""
git commit -qm "rename source"

git filesync source set-url lib9 "$URL9/" >/dev/null
check "set-url" "$(git config -f .git-filesync source.lib9.url)" "$URL9/"
check "set-url: status works" "$(st)" ""

# a second source for the same URL, pinned to v1; making it follow main too
# would duplicate lib9
quiet git filesync add --tag v1 u.c "$URL9" -p t.c
SRC9B=$(git config -f .git-filesync file.u.c.source)
check "same URL, other ref: own source" "$([ "$SRC9B" != lib9 ] && echo own)" "own"
quiet git filesync source set-branch "$SRC9B" main
check "set-tag --unset: duplicate refused" "$(rc git filesync source set-tag "$SRC9B" --unset)" "2"
quiet git filesync source set-branch "$SRC9B" --unset
check "set-branch --unset: pinned, no branch" \
  "$(git config -f .git-filesync --get-regexp "^source\.$SRC9B\." | cut -d' ' -f1 | sed 's/.*\.//' | sort | oneline)" "tag url "
check "rename: existing name refused" "$(rc git filesync source rename "$SRC9B" lib9)" "2"

# add by name: exactly that source, whatever its branch or tag; -b/--tag may
# only repeat it. Relinking its only file keeps the source.
quiet git filesync add --force u.c "$SRC9B" -p t.c
check "relink only file by name: source kept" "$(git config -f .git-filesync source.$SRC9B.tag)" "v1"
quiet git filesync add --no-commit w.c "$SRC9B" -p t.c
check "add by name: pinned source joined" "$(git config -f .git-filesync file.w.c.source)" "$SRC9B"
check "add by name: content at the tag" "$(oneline < w.c)" "1 2 3 "
check "add by name, other ref: refused" "$(rc git filesync add --no-commit -b main x.c "$SRC9B" -p t.c)" "2"
check "add by name, same ref repeated" "$(rc git filesync add --no-commit --tag v1 y.c "$SRC9B" -p t.c)" "0"
check "add by name, other branch for the tag: refused" \
  "$(rc git filesync add --no-commit --tag v1 -b main y2.c "$SRC9B" -p t.c)" "2"
printf '[source "dup"]\n\turl = %s\n\ttag = v1\n' "$URL9" >> .git-filesync
quiet git filesync add --no-commit v.c dup -p t.c
check "add by name: that source, not an equal one" "$(git config -f .git-filesync file.v.c.source)" "dup"

# add by URL: a source is reused only if URL and branch/tag both match;
# with --tag but no -b, one pinned to the tag whatever its branch
quiet git filesync add --no-commit a.c "$URL9" -p t.c
check "add by URL, default branch: branch source reused" "$(git config -f .git-filesync file.a.c.source)" "lib9"
quiet git filesync add --no-commit b.c "$URL9" -p t.c --tag v1
check "add by URL + tag: first source with that tag" "$(git config -f .git-filesync file.b.c.source)" "$SRC9B"
check "--no-commit twice: both messages prepared" \
  "$(grep -cE '^Add (a|b)\.c from' "$(git rev-parse --git-dir)/SQUASH_MSG")" "2"
quiet git filesync add --no-commit c.c "$URL9" -p t.c --tag v2 -b main
SRC9C=$(git config -f .git-filesync file.c.c.source)
check "add by URL, other tag: new source" "$(echo "$SRC9C" | grep -cvE "^(lib9|$SRC9B|dup)$")" "1"
check "add --tag -b: both recorded" \
  "$(git config -f .git-filesync source.$SRC9C.tag) $(git config -f .git-filesync source.$SRC9C.branch)" "v2 main"
quiet git filesync add --no-commit d.c "$URL9" -p t.c --tag v2
check "add by URL + tag, no -b: source with a branch reused" "$(git config -f .git-filesync file.d.c.source)" "$SRC9C"
check "add --tag -b: tag not on the branch" \
  "$(git filesync add --no-commit e.c "$URL9" -p t.c --tag v2 -b nope 2>&1 | grep -c "branch 'nope' not found")" "1"
git reset -q --hard

# a SQUASH_MSG of git's own (e.g. merge --squash) is left alone
echo "squashed" > "$(git rev-parse --git-dir)/SQUASH_MSG"
check "foreign SQUASH_MSG: said so" \
  "$(git filesync add --no-commit f.c "$URL9" -p t.c | grep -c "SQUASH_MSG is in use")" "1"
check "foreign SQUASH_MSG: kept" "$(cat "$(git rev-parse --git-dir)/SQUASH_MSG")" "squashed"
git reset -q --hard


# =============================================================================
section "15. Files renamed or deleted in the master"
# =============================================================================
cd "$T"

# m10.git (bare, via the blobless cache) and checkout co10:
# lib/r.c (lines a..i) and lib/gone.c
git init -q --bare m10.git
git -C m10.git config uploadpack.allowFilter true
git clone -q m10.git co10 2>/dev/null
(cd co10 && mkdir lib && printf 'a\nb\nc\nd\ne\nf\ng\nh\ni\n' > lib/r.c && echo x > lib/gone.c \
  && git add . && git commit -qm init && git push -q origin main)
URL10=file://$T/m10.git

new_slave s10
quiet git filesync add r.c "$URL10" -p lib/r.c
quiet git filesync add gone.c "$URL10" -p lib/gone.c
SRC10=$(git config -f .git-filesync file.r.c.source)

# r.c: renamed with a change, then changed again; gone.c: deleted
(cd ../co10 && git mv lib/r.c lib/renamed.c && sed -i 's/^b$/B/' lib/renamed.c \
  && git commit -qm "rename r" && sed -i 's/^i$/I/' lib/renamed.c && git commit -qam "change I" \
  && git rm -q lib/gone.c && git commit -qm "drop gone" && git push -q origin main)
check "renamed upstream: short code" "$(st r.c)" "R"
check "renamed upstream: long format" \
  "$(git filesync status r.c | grep -cP '^\trenamed:\s+r\.c  \(lib/r\.c -> lib/renamed\.c, 2 commits\)')" "1"
check "deleted upstream: short code" "$(st gone.c)" "X"
check "deleted upstream: unlink hint" "$(git filesync status | grep -c 'git filesync unlink <file>')" "1"
check "deleted upstream: status rc 0" "$(rc git filesync status)" "0"
check "deleted upstream: --exit-code" "$(rc git filesync status --exit-code gone.c)" "1"
check "deleted upstream: hook" "$(git filesync status --hook 2>&1 | grep -c 'gone.c: upstream deleted')" "1"

# pull follows the rename; a committed adaptation is merged across it
sed -i 's/^e$/e-local/' r.c
git commit -qam adapt
quiet git filesync pull --no-edit r.c
check "pull follows rename: path updated" "$(git config -f .git-filesync file.r.c.path)" "lib/renamed.c"
check "pull follows rename: merged" "$(oneline < r.c)" "a B c d e-local f g h I "
check "pull follows rename: message" \
  "$(git log -1 --format=%B | grep -cE '^(Upstream: .*\(main:lib/renamed.c\)|Renamed upstream: lib/r.c -> lib/renamed.c|- rename r .*|- change I .*)$')" "4"
check "after rename: only adapted" "$(st r.c)" " A"

# pull refuses a deleted file and says how to proceed
check "pull refuses deleted file" "$(rc git filesync pull --no-edit gone.c)" "2"
check "deleted: hint" "$(git filesync pull gone.c 2>&1 | grep -c "keep the file with 'git filesync unlink gone.c'")" "1"
check "deleted: file untouched" "$(cat gone.c)" "x"
check "deleted: --commit with an older revision" \
  "$(rc git filesync pull --no-edit --commit "$(git -C ../co10 rev-parse HEAD~1)" gone.c)" "0"

# renamed twice; a pure rename commits only the registry
(cd ../co10 && git mv lib/renamed.c lib/again.c && git commit -qm "rename again" \
  && git mv lib/again.c lib/final.c && git commit -qm "and again" && git push -q origin main)
check "chained rename" "$(git filesync status r.c | grep -c 'lib/renamed.c -> lib/final.c, 2 commits')" "1"
quiet git filesync pull --no-edit r.c
check "pure rename: path updated" "$(git config -f .git-filesync file.r.c.path)" "lib/final.c"
check "pure rename: commit has only the registry" "$(git show --name-only --format= HEAD)" ".git-filesync"
check "pure rename: then clean" "$(st r.c)" " A"


# =============================================================================
section "16. Dry runs: pull --dry-run, add / unlink / mv -n"
# =============================================================================
# (continues in s10)

(cd ../co10 && sed -i 's/^g$/G-up/' lib/final.c && git commit -qam "change G" && git push -q origin main)
BEFORE=$(git rev-parse HEAD)
check "pull --dry-run: reports" "$(git filesync pull --dry-run r.c)" \
  "r.c: would sync to $SRC10@$(git -C ../co10 rev-parse --short HEAD) (adaptations merged cleanly)"
check "pull --dry-run: nothing changed" "$(git rev-parse HEAD) $(git status --porcelain)" "$BEFORE "
sed -i 's/^g$/g-local/' r.c
git commit -qam "local g"
check "pull --dry-run: conflict reported" "$(git filesync pull --dry-run r.c | grep -c '1 merge conflict(s)')" "1"
check "pull --dry-run: rc" "$(rc git filesync pull --dry-run r.c)" "0"
check "pull --dry-run: file untouched" "$(grep -c '^<<<<<<<' r.c)" "0"
git reset -q --hard HEAD~1

check "add -n" "$(git filesync add -n new.c "$URL10" -p lib/final.c)" \
  "would link new.c -> $SRC10:lib/final.c (main), fetched, based on $(git -C ../co10 rev-parse --short HEAD)"
check "add -n: nothing written" "$(ls new.c 2>/dev/null; git status --porcelain)" ""
check "unlink -n" "$(git filesync unlink -n r.c)" "would unlink r.c"
check "mv -n" "$(git filesync mv -n r.c moved.c)" "would move r.c -> moved.c"
check "-n: nothing changed" "$(ls r.c) $(git status --porcelain)" "r.c "


# =============================================================================
section "17. add DIR: all files of a master directory, --include / --exclude"
# =============================================================================
cd "$T"

# m11 (only via mapping): api/ with .proto files, tests and a README; docs/
git init -q m11
(cd m11 && mkdir -p api/v1 api/test docs \
  && for f in api/a.proto api/v1/b.proto api/v1/b_test.proto api/test/t.proto api/README.md docs/x.md; do
       echo "$f" > $f; done && git add . && git commit -qm init)
new_slave s11
git filesync map file:///nowhere/m11.git "$T/m11" >/dev/null

# PROTO - the options linking the .proto files of api/ as proto/
PROTO=(-p api --include '*.proto' --exclude '*_test.proto' --exclude test/)
quiet git filesync add proto file:///nowhere/m11.git "${PROTO[@]}"
check "add DIR: files linked" \
  "$(git config -f .git-filesync --get-regexp '^file\..*\.path' | LC_ALL=C sort | oneline)" \
  "file.proto/a.proto.path api/a.proto file.proto/v1/b.proto.path api/v1/b.proto "
check "add DIR: content" "$(cat proto/v1/b.proto)" "api/v1/b.proto"
check "add DIR: one commit" "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" \
  ".git-filesync proto/a.proto proto/v1/b.proto "
check "add DIR: message" "$(git log -1 --format=%B | sed '/^$/d; s/@[0-9a-f]*$/@X/' | oneline)" \
  "Add 2 files from nowhere/m11@X Upstream: file:///nowhere/m11.git (main:api/) - proto/a.proto - proto/v1/b.proto "
check "add DIR: status clean" "$(st)" ""

# a new master file: the same add links only that one
(cd ../m11 && echo c > api/c.proto && git add . && git commit -qm c)
OUT=$(git filesync add proto nowhere/m11 "${PROTO[@]}" 2>&1)
check "add DIR again: linked ones skipped" "$(echo "$OUT" | grep -c '^2 files already linked, skipped')" "1"
check "add DIR again: new file committed" "$(git show --name-only --format= HEAD | LC_ALL=C sort | oneline)" \
  ".git-filesync proto/c.proto "
check "add DIR again: subject" "$(git log -1 --format=%s | sed 's/@.*//')" "Add proto/c.proto from nowhere/m11"
check "add DIR: nothing new" "$(git filesync add proto nowhere/m11 "${PROTO[@]}" 2>&1)" \
  "3 files already linked, skipped (use --force to relink)"

# an existing file is linked as it is; '/x.md' is anchored at the directory
mkdir docs && echo mine > docs/x.md
quiet git filesync add docs nowhere/m11 --include /x.md
check "add DIR: existing file kept" "$(cat docs/x.md)" "mine"
check "add DIR: existing file adapted" "$(st docs)" " A"
check "add DIR: subject for an existing file" "$(git log -1 --format=%s | sed 's/@.*//')" "Link docs/x.md to nowhere/m11"

# pattern forms
check "pattern '**/v1/*'" "$(git filesync add -n all nowhere/m11 -p api --include '**/v1/*' | wc -l)" "2"
check "pattern 'test/' (directory)" "$(git filesync add -n all nowhere/m11 -p api --include 'test/' | cut -d' ' -f3)" "all/test/t.proto"
check "pattern 'v?/b*.proto'" "$(git filesync add -n all nowhere/m11 -p api --include 'v?/b[_.]*' | wc -l)" "2"
check "patterns need a master directory" "$(rc git filesync add x nowhere/m11 -p api/a.proto --include '*')" "2"
check "whole master repository (docs/x.md already linked)" \
  "$(git filesync add -n . nowhere/m11 -p / --exclude '*.proto' | grep '^would' | cut -d' ' -f3 | oneline)" "api/README.md "

# the script itself, synced into the repository and run via a repo alias
mkdir tools && cp "$S" tools/git-filesync.py
git config alias.fs '!python3 tools/git-filesync.py'
check "repo alias to a copy of the script, from a subdirectory" "$(cd proto && git fs status -s v1/b.proto; echo $?)" "0"


# =============================================================================
section "18. pull -b / --tag: switching branch or tag; newer tags"
# =============================================================================
cd "$T"

# m12.git (bare, via the cache) and checkout co12: a.c b.c c.c (lines 1..5).
# v1.0; v1.1 changes line 5 of a.c and b.c; v2.0-rc1 changes a.c
git init -q --bare m12.git
git -C m12.git config uploadpack.allowFilter true
git clone -q m12.git co12 2>/dev/null
(cd co12 && printf '1\n2\n3\n4\n5\n' > a.c && cp a.c b.c && cp a.c c.c && git add . \
  && git commit -qm v1 && git tag v1.0 \
  && sed -i 's/^5$/5-v11/' a.c b.c && git commit -qam "v1.1 change" && git tag v1.1 \
  && sed -i 's/^5-v11$/5-rc/' a.c && git commit -qam "rc change" && git tag v2.0-rc1 \
  && git push -q origin main --tags)
URL12=file://$T/m12.git

new_slave s12
for f in a b c; do quiet git filesync add --tag v1.0 $f.c "$URL12"; done
SRC12=$(git config -f .git-filesync file.a.c.source)

# newer tags by their place in the commit graph - names are opaque, so a
# pre-release counts like any tag: status -v, source -v, pull
check "status -v: newest tag" "$(git filesync status -v | grep -c '(tag v1.0, newest v2.0-rc1 on main)')" "3"
check "plain status: no hint" "$(git filesync status | grep -c newest)" "0"
check "source -v: newest tag" "$(git filesync source -v)" \
  "$(printf '%s\t%s (tag v1.0, newest v2.0-rc1 on main, 3 files)' "$SRC12" "$URL12")"
check "pull: hint" "$(git filesync pull --all 2>&1 | grep -c "^hint: $SRC12 is pinned to tag v1.0; \
the newest tag is v2.0-rc1 on main (use 'git filesync pull --tag v2.0-rc1 <file>...' to switch)$")" "1"

# a maintenance branch from v1.0 with v1.0.1; a feature branch from v1.1
# with tag f1, merged into main; rel-2 on the same commit as v2.0-rc1; v1.2
# on the v1.1 commit (older than v2.0-rc1 on main, whatever its name)
(cd ../co12 && git checkout -qb maint v1.0 && echo m > m.txt && git add m.txt \
  && git commit -qm maint && git tag -a -m 1.0.1 v1.0.1 \
  && git checkout -qb feature v1.1 && echo f > f.txt && git add f.txt && git commit -qm f \
  && git tag f1 && git checkout -q main && git merge -q --no-ff -m "merge feature" feature \
  && git tag rel-2 HEAD^1 && git tag v1.2 v1.1 && git push -q origin main maint feature --tags)
check "all branches: newest per branch" "$(git filesync source -v | grep -c \
  'newest f1 on feature; rel-2 = v2.0-rc1 on main; v1.0.1 on maint, 3 files)')" "1"
check "pull: hint with several" "$(git filesync pull --all 2>&1 | grep -c "^hint: $SRC12 is pinned \
to tag v1.0; newer tags: f1 on feature; rel-2 = v2.0-rc1 on main; v1.0.1 on maint (use .*set-branch")" "1"
git filesync source set-branch "$SRC12" main >/dev/null
check "branch: only its line, merged side branch ignored" \
  "$(git filesync source -v | grep -c '(tag v1.0 on main, newest rel-2 = v2.0-rc1, 3 files)')" "1"
check "pull: hint for the branch" "$(git filesync pull --all 2>&1 | grep -c "^hint: $SRC12 is pinned \
to tag v1.0; the newest tag on branch main is rel-2 = v2.0-rc1 (use 'git filesync pull --tag rel-2 ")" "1"
git filesync source set-branch "$SRC12" maint >/dev/null
check "branch maint" "$(git filesync source -v | grep -c '(tag v1.0 on maint, newest v1.0.1, 3 files)')" "1"
git filesync source set-tag "$SRC12" v1.0.1 >/dev/null
check "newest tag pinned: no newer" "$(git filesync source -v | grep -c newest)" "0"
git filesync source set-branch "$SRC12" main >/dev/null
check "tag not on the branch: warning (per file)" "$(git filesync status -v 2>&1 | grep -c "tag v1.0.1 is not on branch 'main'")" "3"
git filesync source set-tag "$SRC12" v1.0 >/dev/null
git commit -qm "pinned to v1.0 on main"

# with a mapped checkout: its branches and tags, unpushed ones included
(cd ../co12 && git tag local-3)
git filesync map "$URL12" "$T/co12" >/dev/null
check "mapped: newest tag from the checkout" \
  "$(git filesync source -v | grep -c '(tag v1.0 on main, newest local-3, 3 files)')" "1"
git filesync map "$URL12" --unset >/dev/null
(cd ../co12 && git tag -d local-3 >/dev/null)

# switching only some files of a source splits it; the adaptation is merged
sed -i 's/^1$/1-local/' a.c
git commit -qam adapt
quiet git filesync pull --no-edit --tag v1.1 a.c
check "partial switch: file moved to a new source" "$(git config -f .git-filesync file.a.c.source)" "$SRC12-2"
check "partial switch: new source pinned, branch kept" \
  "$(git config -f .git-filesync source.$SRC12-2.tag) $(git config -f .git-filesync source.$SRC12-2.branch)" "v1.1 main"
check "partial switch: old source unchanged" \
  "$(git config -f .git-filesync source.$SRC12.tag) $(git config -f .git-filesync file.b.c.source)" "v1.0 $SRC12"
check "partial switch: merged" "$(oneline < a.c)" "1-local 2 3 4 5-v11 "
check "partial switch: message" \
  "$(git log -1 --format=%B | grep -cE '^(Sync a.c from |Switched from tag v1.0 on main to tag v1.1 on main.$)')" "2"
check "partial switch: all committed" "$(git status --porcelain)" ""

# the remaining files join the source that already has v1.1; the emptied
# source is removed; c.c is unchanged, so its switch goes into b.c's commit
quiet git filesync pull --no-edit --tag v1.1 b.c c.c
check "switch rest: files joined the existing source" \
  "$(git config -f .git-filesync file.b.c.source) $(git config -f .git-filesync file.c.c.source)" "$SRC12-2 $SRC12-2"
check "switch rest: emptied source removed" "$(git config -f .git-filesync --get-regexp "^source\.$SRC12\." | wc -l)" "0"
check "switch rest: all committed" "$(git status --porcelain)" ""

# all files of a source: the source itself is changed; nothing to sync -> own commit
quiet git filesync pull --no-edit --all --tag v1.2
check "whole source switched in place" "$(git config -f .git-filesync source.$SRC12-2.tag)" "v1.2"
check "switch without sync: own commit" "$(git log -1 --format=%s)" "Switch $SRC12-2 from tag v1.1 on main to tag v1.2 on main"
check "switch without sync: committed" "$(git status --porcelain)" ""

# back to the branch
quiet git filesync pull --no-edit --all -b main
check "-b: branch set, tag removed" \
  "$(git config -f .git-filesync source.$SRC12-2.branch) $(git config -f .git-filesync source.$SRC12-2.tag)" "main "
check "-b: synced to the branch" "$(oneline < a.c)" "1-local 2 3 4 5-rc "

# refusals and dry runs change nothing
check "switch to a missing tag" "$(rc git filesync pull --no-edit --tag v9 a.c)" "2"
check "missing tag: registry unchanged" "$(git status --porcelain) $(git config -f .git-filesync source.$SRC12-2.branch)" " main"
check "--commit and --tag exclude each other" "$(rc git filesync pull --commit v1.0 --tag v1.0 a.c)" "2"
check "pull --dry-run --tag" "$(git filesync pull --dry-run --tag v1.0 a.c | grep -cE '^(would: Move a.c from|a.c: would sync to .*from branch main)')" "2"
check "pull --dry-run --tag -b" \
  "$(git filesync pull --dry-run --tag v1.0 -b maint a.c | grep -c '^would: Move a.c from .* (tag v1.0 on maint)')" "1"
check "pull --dry-run --tag: nothing changed" "$(git status --porcelain)" ""

# an uncommitted source rename doesn't block pull; it goes into the sync commit
git filesync source rename "$SRC12-2" lib12 >/dev/null
(cd ../co12 && sed -i 's/^3$/3-up/' a.c && git commit -qam "change 3" && git push -q origin main)
check "pull after uncommitted source rename" "$(rc git filesync pull --no-edit a.c)" "0"
check "rename went into the sync commit" "$(git status --porcelain) $(git show HEAD:.git-filesync | grep -c 'source = lib12')" " 3"


# =============================================================================
# summary
# =============================================================================
echo
if [ $FAILED = 0 ]; then
  echo "ALL PASSED ($PASSED checks)"
  exit 0
else
  echo "SOME FAILED ($FAILED of $((PASSED + FAILED)) checks)"
  exit 1
fi
