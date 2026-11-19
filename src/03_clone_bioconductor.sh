#!/usr/bin/env bash
# Clone every Bioconductor package in data/raw/bioc_packages.tsv (2,418) from git.bioconductor.org.
# 1. Bare, shallow clone (commits since 2024-01-01) of the default devel branch.
# 2. Deepen to 2023-01-01 (deepen_clones.sh), so every commit since 2024 has its parent.
# Safe to rerun: finished clones are skipped, and each clone goes to a temp dir first so a half-finished
# clone is never mistaken for done. Packages that still fail after 3 tries are listed in
# data/raw/bioc_clone_failures.txt. About 1-2 hours.
set -u
cd "$(dirname "$0")/.."

LIST=data/raw/bioc_packages.tsv
DEST=data/clones/bioconductor
FAIL=data/raw/bioc_clone_failures.txt
JOBS=${JOBS:-4}   # parallel clones; keep small to be polite to the server
mkdir -p "$DEST"
: > "$FAIL"

clone_one() {
    p=$1
    [ -d "$DEST/$p.git" ] && return 0
    for try in 1 2 3; do
        rm -rf "$DEST/.tmp_$p.git"
        if git clone -q --bare --shallow-since=2024-01-01 \
               "https://git.bioconductor.org/packages/$p" "$DEST/.tmp_$p.git" 2>/dev/null; then
            mv "$DEST/.tmp_$p.git" "$DEST/$p.git"
            echo "ok   $p"
            return 0
        fi
        sleep $((try * 10))
    done
    rm -rf "$DEST/.tmp_$p.git"
    echo "$p" >> "$FAIL"
    echo "FAIL $p"
}
export -f clone_one
export DEST FAIL

tail -n +2 "$LIST" | cut -f1 | xargs -P "$JOBS" -I{} bash -c 'clone_one "$@"' _ {}
done_n=$(find "$DEST" -maxdepth 1 -name '*.git' ! -name '.tmp_*' | wc -l)
echo "cloned: $done_n / $(($(wc -l < "$LIST") - 1)); failed: $(wc -l < "$FAIL") (see $FAIL)"

echo "deepening to 2023-01-01 ..."
mapfile -t CLONES < <(find "$DEST" -maxdepth 1 -name '*.git' ! -name '.tmp_*')
bash src/deepen_clones.sh "${CLONES[@]}"
