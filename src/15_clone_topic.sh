#!/usr/bin/env bash
# Clone every repo in data/raw/github_topic/topic_repos_included.tsv
# (GitHub topic search, data/bio_keywords.txt, after data/topic_exclusion_rules.md) for agent-trace mining.
# Bare, partial (--filter=blob:none: commits and trees, no file contents) and shallow since 2023-01-01,
# one year before the 2024-01-01 window so window commits have their parents (see deepen_clones.sh).
# Only the default branch. Clones go to data/clones_topic/<owner>__<name>.git, apart from data/clones,
# so the community scripts (03-07) never see them.
# Safe to rerun: finished clones are skipped; temp dir first. Failures: data/raw/github_topic/clone_failures.txt
# Arguments: optional owner/name repos (default: all included repos).
set -u
cd "$(dirname "$0")/.."

LIST=data/raw/github_topic/topic_repos_included.tsv
DEST=data/clones_topic
FAIL=data/raw/github_topic/clone_failures.txt
JOBS=${JOBS:-6}
mkdir -p "$DEST"
: > "$FAIL"

clone_one() {
    r=$1
    d="$DEST/${r/\//__}.git"
    [ -d "$d" ] && return 0
    for try in 1 2 3; do
        rm -rf "$DEST/.tmp_${r/\//__}.git"
        if GIT_TERMINAL_PROMPT=0 git clone -q --bare --single-branch --filter=blob:none --shallow-since=2023-01-01 \
               "https://github.com/$r.git" "$DEST/.tmp_${r/\//__}.git" 2>/dev/null; then
            mv "$DEST/.tmp_${r/\//__}.git" "$d"
            echo "ok   $r"
            return 0
        fi
        sleep $((try * 10))
    done
    rm -rf "$DEST/.tmp_${r/\//__}.git"
    echo "$r" >> "$FAIL"
    echo "FAIL $r"
}
export -f clone_one
export DEST FAIL

if [ $# -gt 0 ]; then printf '%s\n' "$@"; else tail -n +2 "$LIST" | cut -f1; fi |
    xargs -P "$JOBS" -I{} bash -c 'clone_one "$@"' _ {}

echo "cloned: $(find "$DEST" -maxdepth 1 -name '*.git' ! -name '.tmp_*' | wc -l) / $(($(wc -l < "$LIST") - 1));" \
     "failed this run: $(wc -l < "$FAIL") (see $FAIL)"
