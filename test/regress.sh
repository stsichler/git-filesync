#!/bin/bash
# Regression test for git-filesync (Linux/macOS/Git Bash).
# Usage: test/regress.sh [path/to/git-filesync.py]   - runs in a temp dir
S=$(cd "$(dirname "$0")/.." && pwd)/git-filesync.py; S=${1:-$S}; S=$(cd "$(dirname "$S")" && pwd)/$(basename "$S")
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; cd "$T" || exit 2
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@x GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@x GIT_EDITOR=true
export HOME=$T/home XDG_CACHE_HOME=$T/cache; mkdir -p "$HOME"
git config --global init.defaultBranch main
git config --global alias.filesync "!python3 $S"
FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got [$2] expected [$3]"; FAIL=1; fi; }
st() { git filesync status -s "$@" 2>/dev/null | head -1 | cut -c1-3 | sed 's/ *$//'; }   # short code

# --- LF master ---------------------------------------------------------------
git init -q master && (cd master && printf 'a\nb\nc\nd\ne\nf\ng\n' > lib.c && git add . && git commit -qm "initial lib")
git clone -q --bare master master.git && git -C master.git config uploadpack.allowFilter true
git -C master remote add origin "$T/master.git" && git -C master fetch -q
URL=file://$T/master.git
up() { (cd "$T/master" && sed -i "$1" lib.c && git commit -qam "$2" && git push -q origin main); }

git init -q slave && cd slave && git commit -q --allow-empty -m init
git filesync add src/lib.c "$URL" -p lib.c >/dev/null 2>&1; git commit -qm link
check "add + status clean" "$(st)" ""
up 's/^b$/B/' "Change B"; up 's/^c$/C/' "Change C"
check "pending count, relative path (from subdir)" "$(cd src && git filesync status | grep -cP '^\tpending:\s+lib\.c  \(2 commits\)')" "1"
git filesync pull --no-edit src/lib.c >/dev/null
check "commit msg lists commits" "$(git log -1 --format=%B | grep -c '^- Change')" "2"
check "after pull" "$(st)" ""
sed -i 's/^g$/G-local/' src/lib.c; git commit -qam tweak
up 's/^a$/A/' "Change A"
check "pending + adapted" "$(st)" "PA"
git filesync pull --no-edit src/lib.c >/dev/null
check "clean merge result" "$(tr '\n' ' ' < src/lib.c)" "A B C d e f G-local "
sed -i 's/^e$/E-local/' src/lib.c; git commit -qam "local e"
up 's/^e$/E-up/' "Change E"
git filesync pull src/lib.c >/dev/null; check "conflict rc" "$?" "1"
check "conflict markers" "$(grep -c '^<<<<<<<' src/lib.c)" "1"
git checkout -q src/lib.c 2>/dev/null; git reset -q --hard
# local checkout mapping
git filesync map "$URL" "$T/master" >/dev/null
(cd "$T/master" && sed -i 's/^f$/F/' lib.c && git commit -qam "unpushed F")
check "local checkout warns unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "1"
git filesync map "$URL" --unset >/dev/null
check "--remote / unmapped ignores unpushed" "$(git filesync status 2>/dev/null | grep -c 'not pushed')" "0"
(cd "$T/master" && git push -q origin main)
# --commit backwards (revert)
OLD=$(git -C "$T/master" rev-parse HEAD~3)
git reset -q --hard; git filesync pull --no-edit --commit "$OLD" src/lib.c >/dev/null 2>&1
check "revert message" "$(git log -1 --format=%B | grep -c 'Reverts upstream')" "1"
# missing file + --all
git filesync pull --no-edit src/lib.c >/dev/null 2>&1
rm src/lib.c
check "deleted file is an uncommitted change" "$(st)" " AD"
git filesync pull --all --no-edit >/dev/null 2>&1
check "pull --all leaves locally deleted file alone" "$([ -e src/lib.c ] && echo restored || echo deleted)" "deleted"
git restore src/lib.c
git filesync install-hooks >/dev/null
check "hooks installed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | wc -l)" "2"
git filesync uninstall-hooks >/dev/null
check "own hooks removed" "$(ls .git/hooks/pre-push .git/hooks/post-merge 2>/dev/null | wc -l)" "0"
# foreign pre-push hook with our snippet added by hand, foreign post-merge without it
printf '#!/bin/sh\necho mine\n' > .git/hooks/pre-push; chmod +x .git/hooks/pre-push
git filesync install-hooks 2>/dev/null | sed -n '/^# git-filesync/,/|| true$/p' >> .git/hooks/pre-push
printf '#!/bin/sh\necho other\n' > .git/hooks/post-merge
git filesync uninstall-hooks >/dev/null
check "foreign hook: own lines removed" "$(cat .git/hooks/pre-push)" "$(printf '#!/bin/sh\necho mine')"
check "foreign hook: still executable" "$([ -x .git/hooks/pre-push ] && echo yes)" "yes"
check "foreign hook without snippet untouched" "$(cat .git/hooks/post-merge)" "$(printf '#!/bin/sh\necho other')"
rm -f .git/hooks/pre-push .git/hooks/post-merge
check "broken pipe no traceback" "$(git filesync status 2>&1 | head -1 | grep -c Traceback)" "0"
cd "$T"

# --- CRLF committed in master, slaves with different normalization -----------
git init -q m && (cd m && printf 'a\r\nb\r\nc\r\nd\r\n' > w.c && git add . && git commit -qm init)
git clone -q --bare m m.git; git -C m remote add origin "$T/m.git"; git -C m fetch -q; URL2=file://$T/m.git
for mode in autocrlf textauto plain; do
  rm -rf s; git init -q s; cd s
  case $mode in autocrlf) git config core.autocrlf true;; textauto) echo '* text=auto' > .gitattributes; git add .gitattributes;; esac
  git commit -q --allow-empty -m i
  git filesync add w.c "$URL2" >/dev/null 2>&1; git commit -qm link
  check "$mode: clean after add" "$(st)" ""
  (cd ../m && printf 'a\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam B && git push -q origin main)
  W=$(git filesync pull --no-edit w.c 2>&1 >/dev/null | grep -c 'will be replaced')
  check "$mode: no eol warnings" "$W" "0"
  check "$mode: clean after pull" "$(st)" ""
  sed -i 's/^d/D-local/' w.c; git commit -qam loc
  (cd ../m && printf 'A\r\nB\r\nc\r\nd\r\n' > w.c && git commit -qam A && git push -q origin main)
  git filesync pull --no-edit w.c >/dev/null 2>&1; check "$mode: merge rc" "$?" "0"
  check "$mode: merged content" "$(git show HEAD:w.c | tr -d '\r' | tr '\n' ' ')" "A B c D-local "
  check "$mode: worktree clean" "$(git status --porcelain)" ""
  cd ..; git -C m reset -q --hard HEAD~2; git -C m push -qf origin main
done

# --- branch name with --commit (stale refs in cache) -------------------------
(cd m && git checkout -q -b develop && printf 'x\r\n' > w.c && git commit -qam d1 && git push -q origin develop)
rm -rf s; git init -q s; cd s; git commit -q --allow-empty -m i
git filesync add w.c "$URL2" >/dev/null 2>&1; git commit -qm l
(cd ../m && printf 'y\r\n' > w.c && git commit -qam d2 && git push -q origin develop && git checkout -q main)
git filesync pull --no-edit --commit develop w.c >/dev/null 2>&1
check "--commit <branch> gets current head" "$(tr -d '\r' < w.c)" "y"
cd "$T"

# --- map: per-repo mappings to different checkouts of one master -------------
git init -q m3 && (cd m3 && echo v1 > x.c && git add . && git commit -qm v1)
git clone -q --bare m3 m3.git; URL3=file://$T/m3.git
git clone -q m3.git coA && (cd coA && echo v2 > x.c && git commit -qam v2)   # checkout A: newer
git clone -q m3.git coB                                                      # checkout B: v1
for s in sA sB sC; do
  git init -q $s; (cd $s && git commit -q --allow-empty -m i && git filesync add x.c "$URL3" >/dev/null 2>&1 && git commit -qm l)
done
(cd sA && mkdir -p sub && cd sub && git filesync map "$URL3" ../../coA >/dev/null)   # relative path from subdir
(cd sB && git filesync map "$URL3" "$T/coB" >/dev/null)
check "map default scope is repo-local" "$(git -C sA config --local --get-regexp '^filesync\.' | wc -l)" "1"
check "nothing written globally" "$(git config --global --get-regexp '^filesync\.' | wc -l)" "0"
check "slave A uses checkout A" "$(cd sA && st)" "P"
check "slave B uses checkout B" "$(cd sB && st)" ""
(cd sA && git filesync pull --no-edit x.c >/dev/null 2>&1)
check "slave A synced from checkout A" "$(cat sA/x.c)" "v2"
(cd sC && git filesync map --global "$URL3" "$T/coA" >/dev/null)
check "global mapping used without local one" "$(cd sC && git filesync status -v | grep -c "via local checkout $T/coA")" "1"
check "local mapping overrides global" "$(cd sB && st)" ""
check "list marks overridden global" "$(cd sB && git filesync map | grep '^\[global\]' | grep -c overridden)" "1"
(cd sB && git filesync map "$URL3" --unset >/dev/null)
check "after local unset, global applies" "$(cd sB && st)" "P"
git filesync map "$URL3" "$T/coA" >/dev/null 2>&1
check "local map outside repo fails" "$?" "2"
# mapped: slave follows the link's branch in the checkout, not what is checked out
(cd sB && git filesync map "$URL3" "$T/coB" >/dev/null)
(cd coB && git tag v1 && echo v1b > x.c && git commit -qam v1b)              # local, unpushed
check "mapped: local branch commit pending" "$(cd sB && st)" "P"
(cd sB && git filesync pull --no-edit x.c >/dev/null 2>&1)
check "mapped: pulled local branch state" "$(cat sB/x.c)" "v1b"
(cd coB && git checkout -q -b feature && echo feat > x.c && git commit -qam feat)
check "mapped: other checked-out branch ignored" "$(cd sB && st)" ""
check "mapped: other checked-out branch warned" "$(cd sB && git filesync status | grep -c "has feature checked out")" "1"
(cd sB && git filesync pull --no-edit x.c >/dev/null 2>&1)
check "mapped: pull does not take other branch" "$(cat sB/x.c)" "v1b"
(cd coB && git checkout -q main && git reset -q --hard v1)                   # branch moved back
check "mapped: older branch state detected" "$(cd sB && st)" "O"
(cd sB && git filesync pull --no-edit x.c >/dev/null 2>&1)
check "mapped: synced back to older state" "$(cat sB/x.c)" "v1"
check "mapped: revert listed in message" "$(git -C sB log -1 --format=%B | grep -c '^- v1b')" "1"
echo dirty > coB/x.c
check "mapped: uncommitted master change warned" "$(cd sB && git filesync status | grep -c 'uncommitted changes')" "1"
check "mapped: uncommitted change not synced" "$(cd sB && st)" ""
(cd coB && git checkout -q -- x.c)
# branch only known as origin/<branch> in the checkout
(cd coA && git push -q origin HEAD:rel) && (cd coB && git fetch -q)
git init -q sD && (cd sD && git commit -q --allow-empty -m i && git filesync map "$URL3" "$T/coB" >/dev/null \
  && git filesync add -b rel x.c "$URL3" >/dev/null 2>&1 && git commit -qm l)
check "mapped: falls back to origin/<branch>" "$(cat sD/x.c)" "v2"
check "mapped: fallback noted" "$(cd sD && git filesync status | grep -c 'using origin/rel')" "1"
git filesync map --global "$URL3" --unset >/dev/null

# --- offline add -------------------------------------------------------------
OFF=https://unreachable.invalid/owner/m3.git          # server not reachable
(cd coA && git remote set-head origin main >/dev/null 2>&1)
git init -q sOff && cd sOff && git commit -q --allow-empty -m i
git filesync map "$OFF" "$T/coA" >/dev/null
git filesync add x.c "$OFF" >/dev/null 2>&1; check "offline add via mapping (no -b)" "$?" "0"
check "offline add: branch from checkout" "$(git config -f .git-filesync --get-regexp "^source\..*\.branch" | cut -d" " -f2)" "main"
check "offline add: content from checkout" "$(cat x.c)" "v2"
git commit -qm link
# all commands with network forbidden (any http/https/ssh access fails loudly)
(cd "$T/coA" && echo v3 > x.c && git commit -qam v3)
git init -q --bare "$T/sOff-remote.git"; git remote add origin "$T/sOff-remote.git"
git filesync install-hooks >/dev/null
ERR=$(
  export GIT_ALLOW_PROTOCOL=file
  { git filesync status; git filesync status --no-fetch; git filesync pull --no-edit x.c
    git filesync status; git filesync pull --all --no-edit
    git commit -q --allow-empty -m p; git push -q origin HEAD:main; git filesync map; } 2>&1 >/dev/null \
  | grep -vE 'not pushed|^filesync: '
)
check "offline: no errors/warnings in any command" "$ERR" ""
check "offline: pull got v3 from checkout" "$(cat x.c)" "v3"
cd "$T"
mv m3.git m3-away.git                                 # known URL, server gone, cache exists
git init -q sOff2 && cd sOff2 && git commit -q --allow-empty -m i
git filesync add x.c "$URL3" >/dev/null 2>&1; check "offline add via cache (no -b)" "$?" "0"
check "offline add via cache: content" "$(cat x.c)" "v1"
cd "$T"; mv m3-away.git m3.git

# --- diff / difftool / strict ------------------------------------------------
export GIT_PAGER=cat
git config --global difftool.fake.cmd 'echo "TOOL $(basename "$(dirname "$LOCAL")") $REMOTE"'
git config --global diff.tool fake
git init -q m4 && (cd m4 && mkdir lib && printf 'a\nb\nc\nd\ne\n' > lib/foo.c && printf 'x\n' > lib/bar.h \
  && git add . && git commit -qm init)
git init -q s4 && cd s4 && git commit -q --allow-empty -m i
git filesync map file:///nowhere/m4.git "$T/m4" >/dev/null
git filesync add src/foo.c file:///nowhere/m4.git -p lib/foo.c >/dev/null 2>&1
git filesync add src/bar.h file:///nowhere/m4.git -p lib/bar.h --strict >/dev/null 2>&1; git commit -qm link
check "diff: nothing when clean" "$(git filesync diff)" ""
sed -i 's/^b$/B-local/' src/foo.c; git commit -qm 'adapt foo' src/foo.c
check "diff: shows local change" "$(git filesync diff | grep -E '^[-+][^-+]' | tr '\n' ' ')" "-b +B-local "
check "diff: labels" "$(git filesync diff | grep -E '^(---|\+\+\+)' | tr '\n' ' ')" "--- synced/src/foo.c +++ local/src/foo.c "
check "diff: options after --" "$(git filesync diff -- --stat | head -1 | tr -s ' ')" " src/foo.c | 2 +-"
git filesync diff --master-paths > ../p4.patch
check "diff --master-paths applies in master" "$(cd ../m4 && git apply --check ../p4.patch && echo ok)" "ok"
(cd ../m4 && sed -i 's/^e$/E-up/' lib/foo.c && git commit -qam "Change E")
check "diff --upstream" "$(git filesync diff --upstream | grep -E '^[-+][^-+]' | tr '\n' ' ')" "-e +E-up "
check "apply -3 after master moved" "$(cd ../m4 && git apply -3 ../p4.patch >/dev/null 2>&1 && sed -n 2p lib/foo.c; git reset -q --hard)" "B-local"
check "difftool: real working file" "$(git filesync difftool src/foo.c)" "TOOL synced-$(git -C ../m4 rev-parse --short HEAD~1) $T/s4/src/foo.c"
check "difftool --upstream: temp copy" "$(git filesync difftool -y --upstream | grep -c "upstream-")" "1"
# per-file prompt like git difftool (bar.h before foo.c)
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
# strict
check "strict file clean: no violation" "$(st src/bar.h)" ""
echo y >> src/bar.h
check "strict violation reported (uncommitted)" "$(git filesync status -s src/bar.h)" "  M src/bar.h  (strict!)"
check "strict violation in long format" "$(git filesync status src/bar.h | grep -cP '^\tmodified:\s+src/bar\.h  \(NOT ALLOWED: strict\)')" "1"
git filesync status --exit-code src/bar.h >/dev/null; check "strict violation exit code" "$?" "1"
check "strict violation in hook output" "$(git filesync status --hook 2>&1 | grep -c 'NOT ALLOWED')" "1"
git filesync pull --no-edit src/bar.h >/dev/null 2>&1; check "pull refuses strict merge" "$?" "2"
check "pull --all continues after strict error" "$(git filesync pull --all --no-edit 2>&1 | grep -c '^error:')" "0"
check "non-strict file merged by --all" "$(sed -n 2p src/foo.c; sed -n 5p src/foo.c)" "$(printf 'B-local\nE-up')"
git commit -qm "adapt bar" src/bar.h
check "strict violation (committed)" "$(git filesync status -s src/bar.h)" " A  src/bar.h  (strict!)"
git filesync pull --no-edit --overwrite src/bar.h >/dev/null 2>&1
check "pull --overwrite restores" "$(cat src/bar.h)" "x"
check "overwrite commit message" "$(git log -1 --format=%s)" "Restore src/bar.h from nowhere/m4@$(git -C ../m4 rev-parse --short HEAD)"
check "after overwrite clean" "$(st src/bar.h)" ""
sed -i 's/^a$/A-local/' src/foo.c; git commit -qm 'adapt a' src/foo.c
git filesync pull --no-edit --overwrite src/foo.c >/dev/null 2>&1
check "--overwrite discards in non-strict file" "$(git filesync diff)" ""

# --- .git-filesync registry: sources, unlink, mv, commit consistency ---------
check "one [source] for files of one master" "$(git config -f .git-filesync --get-regexp '^source\..*\.url' | wc -l)" "1"
SRC=$(git config -f .git-filesync --get-regexp '^source\..*\.url' | sed 's/^source\.\(.*\)\.url .*/\1/')
(cd ../m4 && printf 'n\n' > lib/new.h && sed -i 's/^d$/D-up/' lib/foo.c && git add . && git commit -qm "add new.h")
git filesync add include/new.h "$SRC" -p lib/new.h >/dev/null 2>&1; check "add by source name" "$?" "0"
check "add by source name: same source" "$(git config -f .git-filesync file.include/new.h.source)" "$SRC"
git filesync pull --no-edit src/foo.c >/dev/null 2>&1
check "pull refused while other entry uncommitted" "$?" "2"
check "refusal names the entry" "$(git filesync pull --no-edit src/foo.c 2>&1 | grep -c 'uncommitted changes for include/new.h')" "1"
git commit -qm "link new.h"
check "registry committed with link" "$(git show --name-only --format= HEAD | sort | tr '\n' ' ')" ".git-filesync include/new.h "
git filesync mv include/new.h include/renamed.h >/dev/null; check "mv rc" "$?" "0"
check "mv: file moved" "$(ls include)" "renamed.h"
check "mv: link moved (staged, not yet committed)" "$(git filesync status -s include/renamed.h)" "  ? include/renamed.h"
check "mv: old entry gone" "$(git config -f .git-filesync --get-regexp '^file\.include/new\.h\.' | wc -l)" "0"
git commit -qm mv
git filesync unlink include/renamed.h >/dev/null; check "unlink rc" "$?" "0"
check "unlink: file kept" "$(cat include/renamed.h)" "n"
check "unlink: entry removed" "$(git filesync status include/renamed.h 2>&1 | grep -c 'not linked')" "1"
check "unlink: source kept while used" "$(git config -f .git-filesync --get-regexp '^source\.' | wc -l)" "2"
git commit -qm unlink
git filesync unlink src/foo.c src/bar.h >/dev/null
check "unlink all: registry removed" "$([ -e .git-filesync ] && echo exists || echo gone)" "gone"
check "unlink all: removal staged" "$(git status --porcelain .git-filesync)" "D  .git-filesync"
git reset -q --hard

# --- colors ------------------------------------------------------------------
ESC=$(printf '\033')
check "no color when piped" "$(git filesync status | grep -c "$ESC")" "0"
check "--color=always" "$(git filesync status --color=always | grep -q "$ESC" && echo yes)" "yes"
check "color.ui=always via git -c" "$(git -c color.ui=always filesync status | grep -q "$ESC" && echo yes)" "yes"
check "color.filesync=never beats color.ui" "$(git -c color.ui=always -c color.filesync=never filesync status | grep -c "$ESC")" "0"
check "NO_COLOR" "$(NO_COLOR=1 git -c color.ui=always filesync status | grep -c "$ESC")" "0"
check "colored error on stderr" "$(git filesync pull nothere --color=always 2>&1 | grep -c "${ESC}\[1;31merror:")" "1"
unset GIT_PAGER
cd "$T"

# --- status like git status, pull like git pull -------------------------------
export GIT_PAGER=cat
git init -q m5 && (cd m5 && for f in a b c d e; do printf '1\n2\n3\n4\n5\n' > $f.c; done && git add . && git commit -qm i)
git init -q s5 && cd s5 && git commit -q --allow-empty -m i && git filesync map file:///nowhere/m5.git "$T/m5" >/dev/null
for f in a b c d e; do git filesync add $f.c file:///nowhere/m5.git >/dev/null 2>&1; done
git config -f .git-filesync file.e.c.strict true; git add .git-filesync; git commit -qm link
check "status: clean summary" "$(git filesync status)" "nothing to sync, all 5 linked files unmodified"
check "status -s: nothing when clean" "$(git filesync status -s)" ""
(cd ../m5 && sed -i 's/^5$/5-up/' a.c b.c d.c && git commit -qam up)
sed -i 's/^1$/1-adapt/' b.c c.c e.c; git commit -qam adapt          # committed adaptations
sed -i 's/^3$/3-wip/' c.c d.c                                          # uncommitted changes
check "status -s: three columns" "$(git filesync status -s | tr '\n' '|')" "P   a.c|PA  b.c| AM c.c|P M d.c| A  e.c  (strict!)|"
OUT=$(git filesync status)
check "status: upstream section" "$(echo "$OUT" | grep -A4 '^Upstream changes to sync:' | grep -cP '^\tpending:')" "3"
check "status: commit count" "$(echo "$OUT" | grep -cP '^\tpending:\s+b\.c  \(1 commit\)')" "1"
check "status: adapted section" "$(echo "$OUT" | grep -A6 '^Locally adapted files:' | grep -cP '^\tadapted:')" "3"
check "status: strict note on adapted" "$(echo "$OUT" | grep -cP '^\tadapted:\s+e\.c  \(NOT ALLOWED: strict\)')" "1"
check "status: uncommitted section" "$(echo "$OUT" | grep -A5 '^Uncommitted changes:' | grep -cP '^\tmodified:')" "2"
check "status: no 'nothing to sync' when pending" "$(echo "$OUT" | grep -c 'nothing to sync')" "0"
check "status: exit code 0 like git" "$(git filesync status >/dev/null; echo $?)" "0"
check "status --exit-code" "$(git filesync status --exit-code >/dev/null; echo $?)" "1"
check "status: advice.statusHints=false" "$(git -c advice.statusHints=false filesync status | grep -c '(use ')" "0"
check "status -v: all files listed" "$(git filesync status -v | grep -A6 '^Linked files:' | grep -cP '^\t(unmodified|adapted):')" "5"
check "status --hook: adapted alone is quiet" "$(git filesync status --hook 2>&1 | grep -c 'c\.c')" "0"
git filesync pull --no-edit d.c >/dev/null 2>&1; check "pull refuses uncommitted changes" "$?" "2"
check "pull refusal message" "$(git filesync pull --no-edit d.c 2>&1 | grep -c 'would be overwritten by pull')" "1"
check "refused pull leaves file alone" "$(tr '\n' ' ' < d.c)" "1 2 3-wip 4 5 "
git filesync pull --no-edit --autostash d.c >/dev/null 2>&1; check "pull --autostash" "$?" "0"
check "autostash: commit has synced version only" "$(git show HEAD:d.c | tr '\n' ' ')" "1 2 3 4 5-up "
check "autostash: uncommitted change re-applied" "$(tr '\n' ' ' < d.c)" "1 2 3-wip 4 5-up "
git filesync pull --no-edit b.c >/dev/null 2>&1
check "pull merges committed adaptation" "$(tr '\n' ' ' < b.c)" "1-adapt 2 3 4 5-up "
check "diff --committed: adaptations only" "$(git filesync diff --committed -- --stat | tail -1 | grep -o '[0-9]* files changed')" "3 files changed"
check "diff --committed: no wip" "$(git filesync diff --committed c.c | grep -c 3-wip)" "0"
check "diff: includes wip" "$(git filesync diff c.c | grep -c 3-wip)" "1"
check "diff -- --exit-code: no difference" "$(git filesync diff a.c -- --exit-code >/dev/null; echo $?)" "0"
check "diff -- --exit-code: difference" "$(git filesync diff c.c -- --exit-code >/dev/null; echo $?)" "1"
unset GIT_PAGER
cd "$T"

# --- robustness: unsafe registry paths, special file names, odd entries ------
git init -q m6 && (cd m6 && mkdir sub && echo a > a.txt && echo s > sub/s.txt && echo f > 'f[1].txt' \
  && git add . && git commit -qm i)
M6=$(git -C m6 rev-parse HEAD); B6=$(git -C m6 rev-parse HEAD:a.txt)
git init -q s6 && cd s6 && git commit -q --allow-empty -m i && git filesync map file:///nowhere/m6.git "$T/m6" >/dev/null
printf '[source "m6"]\n\turl = file:///nowhere/m6.git\n\tbranch = main\n' > .git-filesync
for f in ../outside.txt "$T/abs.txt" .git/hooks/post-commit; do
  printf '[file "%s"]\n\tsource = m6\n\tpath = a.txt\n\tcommit = %s\n\tblob = %s\n' "$f" "$M6" "$B6" >> .git-filesync
done
git add .git-filesync && git commit -qm "unsafe entries"
git filesync pull --all --no-edit >/dev/null 2>&1; check "unsafe paths: pull fails" "$?" "2"
check "unsafe paths: nothing written" "$(ls ../outside.txt "$T/abs.txt" .git/hooks/post-commit 2>/dev/null | wc -l)" "0"
check "unsafe paths: status errors" "$(git filesync status -s 2>/dev/null | grep -c '^E')" "3"
check "unsafe paths: removal hint" "$(git filesync status 2>&1 | grep -c 'remove-section')" "3"
git rm -q .git-filesync && git commit -qm "drop unsafe entries"
git filesync add .git/x file:///nowhere/m6.git -p a.txt >/dev/null 2>&1; check "add into .git refused" "$?" "2"
git filesync add ../x file:///nowhere/m6.git -p a.txt >/dev/null 2>&1; check "add outside refused" "$?" "2"
mkdir d; check "add directory refused" "$(git filesync add d file:///nowhere/m6.git -p a.txt 2>&1 | grep -c 'is a directory')" "1"
check "master path is a directory" "$(git filesync add x.txt file:///nowhere/m6.git -p sub 2>&1 | grep -c "no file 'sub'")" "1"
git filesync add a.txt file:///nowhere/m6.git >/dev/null 2>&1
git filesync mv a.txt ../moved.txt >/dev/null 2>&1; check "mv outside refused" "$?" "2"
check "mv outside: file stays" "$(ls a.txt ../moved.txt 2>/dev/null)" "a.txt"
git filesync map --unset >/dev/null 2>&1; check "map --unset without URL" "$?" "2"
# wildcard characters in a file name are taken literally
echo other > f1.txt; git add f1.txt; git filesync add 'f[1].txt' file:///nowhere/m6.git >/dev/null 2>&1; git commit -qm link
echo changed > f1.txt
check "glob chars: other file's change not attributed" "$(st 'f[1].txt')" ""
(cd ../m6 && echo f2 > 'f[1].txt' && git commit -qam f2)
git filesync pull --no-edit 'f[1].txt' >/dev/null 2>&1
check "glob chars: pull commits only the file" "$(git show --name-only --format= HEAD | LC_ALL=C sort | tr '\n' ' ')" ".git-filesync f[1].txt "
check "glob chars: other file stays uncommitted" "$(git status --porcelain f1.txt)" " M f1.txt"
git checkout -q -- f1.txt
# 'strict' without a value is true, as everywhere in git config
echo local >> a.txt; git commit -qam adapt
sed -i '/^\[file "a.txt"\]/a\	strict' .git-filesync
check "bare 'strict' means true" "$(git filesync status -s a.txt)" " A  a.txt  (strict!)"
git checkout -q -- .git-filesync
# synced version not readable -> warning, not a silent 'adapted'; --overwrite recovers
git config -f .git-filesync 'file.f[1].txt.blob' 0123456789abcdef0123456789abcdef01234567
check "base unavailable: warned" "$(git filesync status 2>&1 | grep -c 'synced version 0123456789ab not available')" "1"
git filesync pull --no-edit --overwrite 'f[1].txt' >/dev/null 2>&1
check "base unavailable: --overwrite recovers" "$(st 'f[1].txt')" ""
cd "$T"
# mapped checkout with a remote but no origin/HEAD: default branch is a guess
git clone -q m6 co6 && (cd co6 && git remote set-head origin -d && git checkout -q -b feature)
git init -q s7 && cd s7 && git commit -q --allow-empty -m i && git filesync map file:///nowhere/m6.git "$T/co6" >/dev/null
check "default branch guessed: warned" "$(git filesync add a.txt file:///nowhere/m6.git 2>&1 | grep -c "using its checked-out branch 'feature'")" "1"
cd "$T"

# --- Git LFS: master / slave / both / neither, via mapping and via cache ------
if git lfs version >/dev/null 2>&1; then
  git lfs install --skip-repo >/dev/null
  export GIT_PAGER=cat
  for mlfs in yes no; do
    rm -rf ml ml.git; git init -q --bare ml.git; git clone -q ml.git ml 2>/dev/null
    (cd ml && { [ $mlfs = yes ] && git lfs track d.txt >/dev/null; true; } \
       && printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt && git add . && git commit -qm v1 && git push -q origin main 2>/dev/null)
    for slfs in yes no; do
      for via in map cache; do
        tag="lfs master=$mlfs slave=$slfs via=$via"
        rm -rf sl "$T/cache"; git init -q sl; cd sl
        [ $slfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        git commit -q --allow-empty -m i
        [ $via = map ] && git filesync map "file://$T/ml.git" "$T/ml" >/dev/null
        git filesync add d.txt "file://$T/ml.git" >/dev/null 2>&1; git commit -qm link
        check "$tag: content after add" "$(head -1 d.txt)" "l1"
        check "$tag: slave storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$([ $slfs = yes ] && echo 1 || echo 0)"
        check "$tag: clean" "$(st)" ""
        (cd "$T/ml" && sed -i 's/^l5$/L5-up/' d.txt && git commit -qam l5 && git push -q origin main 2>/dev/null)
        sed -i 's/^l1$/L1-local/' d.txt; git commit -qam loc
        check "$tag: diff" "$(git filesync diff | grep -E '^[-+][^-+]' | tr '\n' ' ')" "-l1 +L1-local "
        check "$tag: diff --upstream" "$(git filesync diff --upstream | grep -E '^[-+][^-+]' | tr '\n' ' ')" "-l5 +L5-up "
        git filesync pull --no-edit d.txt >/dev/null 2>&1
        check "$tag: merged" "$(tr '\n' ' ' < d.txt)" "L1-local l2 l3 l4 L5-up "
        check "$tag: committed storage" "$(git cat-file -p HEAD:d.txt | head -1 | grep -c git-lfs)" "$([ $slfs = yes ] && echo 1 || echo 0)"
        check "$tag: after merge (adapted, clean worktree)" "$(st) $(git status --porcelain)" " A "
        cd ..; rm -rf sl2; git init -q sl2; cd sl2
        [ $slfs = yes ] && git lfs track d.txt >/dev/null && git add .gitattributes
        printf 'l1\nl2\nl3\nl4\nl5\n' > d.txt; git add .; git commit -qm i
        [ $via = map ] && git filesync map "file://$T/ml.git" "$T/ml" >/dev/null
        check "$tag: add detects older version" "$(git filesync add d.txt "file://$T/ml.git" 2>&1 | grep -c 'matches upstream')" "1"
        cd ..
        (cd ml && git reset -q --hard HEAD~1 && git push -qf origin main 2>/dev/null)
      done
    done
  done
  # LFS content unavailable -> clear error instead of a pointer file
  rm -rf sl "$T/cache"; git init -q sl; cd sl; git commit -q --allow-empty -m i
  (cd ../ml && git lfs track d.txt >/dev/null && git add . && git commit -qm lfs && git push -q origin main 2>/dev/null)
  ERR=$(GIT_LFS_SKIP_SMUDGE=1 git filesync add d.txt "file://$T/ml.git" 2>&1)
  check "lfs unavailable: add fails" "$(echo "$ERR" | grep -c 'stored in Git LFS')" "1"
  check "lfs unavailable: no pointer file written" "$([ -e d.txt ] && echo written || echo none)" "none"
  unset GIT_PAGER
  cd "$T"
else
  echo "skip Git LFS tests (git-lfs not installed)"
fi

[ $FAIL = 0 ] && echo "ALL PASSED" || echo "SOME FAILED"
exit $FAIL
