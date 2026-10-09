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
# report). Three columns: upstream (P pending, O older ...), committed
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
git commit -qm link
check "add + status clean" "$(st)" ""

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
git checkout -q src/lib.c 2>/dev/null
git reset -q --hard

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
  git commit -qm link
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
git commit -qm l
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
  (new_slave $s && quiet git filesync add x.c "$URL3" && git commit -qm l)
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
  && quiet git filesync add -b rel x.c "$URL3" \
  && git commit -qm l)
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
git commit -qm link

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
git commit -qm link

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
check "add by source name" "$(rc git filesync add include/new.h "$SRC" -p lib/new.h)" "0"
check "add by source name: same source" "$(git config -f .git-filesync file.include/new.h.source)" "$SRC"

# pull commits .git-filesync, so it refuses while another entry is uncommitted
check "pull refused while other entry uncommitted" "$(rc git filesync pull --no-edit src/foo.c)" "2"
check "refusal names the entry" \
  "$(git filesync pull --no-edit src/foo.c 2>&1 | grep -c 'uncommitted changes for include/new.h')" "1"
git commit -qm "link new.h"
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
mkdir d
check "add directory refused" "$(git filesync add d file:///nowhere/m6.git -p a.txt 2>&1 | grep -c 'is a directory')" "1"
check "master path is a directory" "$(git filesync add x.txt file:///nowhere/m6.git -p sub 2>&1 | grep -c "no file 'sub'")" "1"
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
git commit -qm link
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
        git commit -qm link
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
