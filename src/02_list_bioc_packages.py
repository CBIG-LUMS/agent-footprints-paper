"""List every Bioconductor release software package with its download score.

Population = packages in the release VIEWS file (current release only).
The saved data/raw/bioc_release_VIEWS.txt keeps only the fields the scripts read (Package, URL, BugReports),
with maintainer names and emails removed; the full file is public at the VIEWS URL below.
Download score comes from bioc_pkg_scores.tab; packages missing there get NA.
Both inputs are cached in data/raw/ and fetched only if absent.
"""
import csv
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
VIEWS = RAW / "bioc_release_VIEWS.txt"
SCORES = RAW / "bioc_pkg_scores.tab"
OUT = RAW / "bioc_packages.tsv"
URLS = {
    VIEWS: "https://bioconductor.org/packages/release/bioc/VIEWS",
    SCORES: "https://bioconductor.org/packages/stats/bioc/bioc_pkg_scores.tab",
}


def fetch(path):
    if not path.exists():
        urllib.request.urlretrieve(URLS[path], path)


def read_views(path):
    """Parse the DCF VIEWS file into a list of dicts (continuation lines joined)."""
    records = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        rec, key = {}, None
        for line in block.splitlines():
            if line[:1] in (" ", "\t") and key:
                rec[key] += " " + line.strip()
            elif ":" in line:
                key, val = line.split(":", 1)
                rec[key] = val.strip()
        if "Package" in rec:
            records.append(rec)
    return records


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for p in URLS:
        fetch(p)
    with open(SCORES, encoding="utf-8") as f:
        scores = {r["Package"]: r["Download_score"] for r in csv.DictReader(f, delimiter="\t")}
    pkgs = read_views(VIEWS)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["package", "download_score"])
        for r in sorted(pkgs, key=lambda r: r["Package"].lower()):
            w.writerow([r["Package"], scores.get(r["Package"], "NA")])
    missing = sum(1 for r in pkgs if r["Package"] not in scores)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(pkgs)} packages ({missing} without a download score)")


if __name__ == "__main__":
    main()
