#!/usr/bin/env bash
# Helper used by 03/04/05_clone_*.sh (not a step on its own).
# Move the shallow cut of every clone back from 2024-01-01 to 2023-01-01.
# Why: in a shallow clone the oldest kept commit has no parent, so git shows it as adding every
# file in the repo (HiCcompare 8471ef2: 95 files / 5,944 lines instead of 2 files / +32 -6), and a
# merge at the cut looks like a single-parent commit. With one more year of history every commit in
# the study window (2024-01-01 on) has its parents, so commit sizes and --no-merges are right.
# The window itself does not change: 06/07 still read commits since 2024-01-01.
# Before fetching, cut points the server listed but never sent (no object in the clone) are dropped
# from the shallow file; git refuses to fetch otherwise. Only FETCH_HEAD is updated, never
# refs/heads, so branch tips stay where they were when the commits were mined.
# A window commit whose parent is older than the new cut (a long-dormant package, e.g. methylumi
# dc9915e with a 2021 parent) is still at the cut; such a clone gets its full history (--unshallow;
# deepening one generation at a time was unreliable on git.bioconductor.org). Each clone then reports
# how many window commits are still at the cut (should be 0) and whether it was unshallowed.
# Safe to rerun. Arguments: clone dirs (default: all of data/clones/*/*.git). Failures are listed in
# data/raw/deepen_failures.txt.
set -u
cd "$(dirname "$0")/.."

CUT=2023-01-01
SINCE=2024-01-01
FAIL=data/raw/deepen_failures.txt
JOBS=${JOBS:-4}
: > "$FAIL"

clean_shallow() {
    g=$1
    [ -f "$g/shallow" ] || return 0
    while read -r s; do git -C "$g" cat-file -e "$s" 2>/dev/null && echo "$s"; done < "$g/shallow" > "$g/shallow.tmp"
    mv "$g/shallow.tmp" "$g/shallow"
}

at_cut() {  # window commits that are still shallow cut points
    g=$1; shift
    [ -f "$g/shallow" ] || { echo 0; return; }
    git -C "$g" log --no-merges --since=$SINCE --format=%H "$@" | grep -cxFf "$g/shallow"
}

deepen_one() {
    g=$1
    revs=HEAD
    [ "$(git -C "$g" symbolic-ref --short HEAD)" != dev ] && git -C "$g" rev-parse -q --verify refs/heads/dev >/dev/null && revs="HEAD dev"
    clean_shallow "$g"
    ok=0
    for try in 1 2 3; do
        # shellcheck disable=SC2086
        if git -C "$g" fetch -q --shallow-since=$CUT origin $revs 2>/dev/null; then ok=1; break; fi
        sleep $((try * 10))
    done
    clean_shallow "$g"
    if [ $ok = 0 ]; then echo "$g" >> "$FAIL"; echo "FAIL $g"; return 0; fi
    full=""
    # shellcheck disable=SC2086
    left=$(at_cut "$g" $revs)
    if [ "$left" != 0 ]; then
        # shellcheck disable=SC2086
        git -C "$g" fetch -q --unshallow origin $revs 2>/dev/null && full=" (full history)"
        # shellcheck disable=SC2086
        left=$(at_cut "$g" $revs)
    fi
    echo "ok   $(basename "$g" .git) cut-points-in-window=$left$full"
}
export -f clean_shallow at_cut deepen_one
export CUT SINCE FAIL

if [ $# -gt 0 ]; then printf '%s\n' "$@"; else find data/clones -mindepth 2 -maxdepth 2 -name '*.git' ! -name '.tmp_*'; fi |
    xargs -P "$JOBS" -I{} bash -c 'deepen_one "$@"' _ {}
echo "done; failures: $(wc -l < "$FAIL") (see $FAIL)"
