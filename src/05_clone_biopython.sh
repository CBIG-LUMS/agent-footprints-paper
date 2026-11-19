#!/usr/bin/env bash
# Clone biopython/biopython from GitHub and list its pull requests.
# 1. Bare, shallow clone (commits since 2024-01-01) of the default branch.
# 2. Deepen to 2023-01-01 (deepen_clones.sh), so every commit since 2024 has its parent.
# 3. Pull requests opened since 2024-01-01 -> data/raw/biopython_prs.json (573 in the paper), read by
#    12_summary.py. Fetched with gh only if the file is missing, so the paper's list is kept.
# Safe to rerun. A few minutes.
set -u
cd "$(dirname "$0")/.."

G=data/clones/biopython/biopython.git
PRS=data/raw/biopython_prs.json
mkdir -p data/clones/biopython data/raw

if [ ! -d "$G" ]; then
    for try in 1 2 3; do
        rm -rf "$G.tmp"
        if git clone -q --bare --shallow-since=2024-01-01 https://github.com/biopython/biopython.git "$G.tmp"; then
            mv "$G.tmp" "$G"; echo "ok   biopython"; break
        fi
        sleep $((try * 5))
    done
fi
[ -d "$G" ] || { echo "FAIL biopython clone"; exit 1; }

echo "deepening to 2023-01-01 ..."
bash src/deepen_clones.sh "$G"

if [ ! -f "$PRS" ]; then
    gh pr list -R biopython/biopython --state all --limit 5000 --search "created:>=2024-01-01" \
        --json number,author,body,createdAt,headRefName,labels,mergedAt > "$PRS"
fi
echo "pull requests in $PRS: $(python -c "import json; print(len(json.load(open('$PRS'))))")"
