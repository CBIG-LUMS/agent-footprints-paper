#!/usr/bin/env bash
# Clone the nf-core pipelines from GitHub: every repository of the nf-core organisation that is neither
# archived nor a fork, from data/raw/nfcore_org_repos.json (the list used in the paper; fetched with gh only
# if the file is missing). One kept repository, basic_training, has no commits since 2024-01-01, so its
# shallow clone fails: 177 listed, 176 cloned.
# 1. Bare, shallow clone (commits since 2024-01-01) of the default branch.
# 2. Add the dev branch. nf-core merges day-to-day work into dev and only merges dev into the default branch
#    at a release, so the default branch alone misses unreleased commits. dev is fetched into the same clone
#    as refs/heads/dev; 06/07 read the default branch and dev together.
# 3. Deepen to 2023-01-01 (deepen_clones.sh), so every commit since 2024 has its parent.
# Safe to rerun. 
cd "$(dirname "$0")/.."

LIST=data/raw/nfcore_org_repos.json
DEST=data/clones/nf-core
FAIL=data/raw/nfcore_clone_failures.txt
JOBS=${JOBS:-4}
mkdir -p "$DEST" data/raw
[ -f "$LIST" ] || gh repo list nf-core --limit 1000 --json name,isArchived,isFork,pushedAt,primaryLanguage > "$LIST"
: > "$FAIL"

clone_one() {  # repository name
    g="$DEST/$1.git"
    [ -d "$g" ] && return 0
    for try in 1 2 3; do
        rm -rf "$g.tmp"
        if git clone -q --bare --shallow-since=2024-01-01 "https://github.com/nf-core/$1" "$g.tmp" 2>/dev/null; then
            mv "$g.tmp" "$g"; echo "ok   $1"; return 0
        fi
        sleep $((try * 5))
    done
    rm -rf "$g.tmp"; echo "clone $1" >> "$FAIL"; echo "FAIL $1"
}

add_dev() {  # clone dir
    g=$1; r=$(basename "$g" .git)
    [ "$(git -C "$g" symbolic-ref --short HEAD)" = dev ] && return 0
    git -C "$g" rev-parse -q --verify refs/heads/dev >/dev/null && return 0
    git -C "$g" ls-remote --exit-code --heads origin dev >/dev/null 2>&1 || { echo "skip $r (no dev)"; return 0; }
    for try in 1 2 3; do
        if git -C "$g" fetch -q --shallow-since=2024-01-01 origin dev:dev 2>/dev/null; then
            echo "dev  $r $(git -C "$g" rev-list --count --no-merges HEAD..dev) commits on dev only"
            return 0
        fi
        sleep $((try * 10))
    done
    echo "dev $r" >> "$FAIL"; echo "FAIL dev $r"
}
export -f clone_one add_dev
export DEST FAIL

python -c "
import json
for r in json.load(open('$LIST')):
    if not r['isArchived'] and not r['isFork']:
        print(r['name'])" | xargs -P "$JOBS" -I{} bash -c 'clone_one "$@"' _ {}
echo "cloned: $(find "$DEST" -maxdepth 1 -name '*.git' | wc -l) (paper: 176; basic_training is expected to fail)"

echo "adding dev branches ..."
find "$DEST" -maxdepth 1 -name '*.git' -print0 | xargs -0 -P "$JOBS" -I{} bash -c 'add_dev "$@"' _ {}

echo "deepening to 2023-01-01 ..."
mapfile -t CLONES < <(find "$DEST" -maxdepth 1 -name '*.git' ! -name '.tmp_*')
bash src/deepen_clones.sh "${CLONES[@]}"
echo "failures: $(wc -l < "$FAIL") (see $FAIL)"
