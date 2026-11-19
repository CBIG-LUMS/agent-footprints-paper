"""List GitHub repositories tagged with a bioinformatics topic.

GitHub search returns at most 1000 results per query, so each topic is queried in
star ranges small enough to stay under that cap. Every raw API page is cached in
data/raw/github_topic/ and reused on rerun.
Usage: python src/13_topic_search.py [--min-stars 10] [--pushed-since 2025-01-01]
Output: data/raw/github_topic/github_topic_repos.tsv
"""
import argparse
import csv
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "github_topic"
OUT = RAW / "github_topic_repos.tsv"
CAP = 1000


def search(q, page):
    cache = RAW / f"{q.replace(' ', '_').replace(':', '-').replace('>', 'gt').replace('.', '_')}_p{page}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    for attempt in range(5):  # search API allows 30 requests/min; network also drops
        res = subprocess.run(["gh", "api", "-X", "GET", "search/repositories",
                              "-f", f"q={q}", "-f", "per_page=100", "-f", f"page={page}"],
                             capture_output=True, text=True)
        if res.returncode == 0:
            break
        time.sleep(15 * (attempt + 1))
    else:
        raise SystemExit(f"search failed 5 times: {q} page {page}\n{res.stderr}")
    out = res.stdout
    cache.write_text(out)
    time.sleep(2)
    return json.loads(out)


def collect(q):
    """Return all items for q, or None if q has more results than the search cap."""
    first = search(q, 1)
    if first["total_count"] > CAP:
        return None
    items = first["items"]
    for page in range(2, (first["total_count"] + 99) // 100 + 1):
        items += search(q, page)["items"]
    return items


def collect_range(base, lo, hi):
    """Split the star range [lo, hi] until every piece is under the cap."""
    stars = f"stars:{lo}..{hi}" if hi else f"stars:>={lo}"
    items = collect(f"{base} {stars}")
    if items is not None:
        return items
    if hi and hi - lo < 1:
        raise SystemExit(f"cannot split further: {base} {stars}")
    mid = lo + max(1, ((hi or lo * 4) - lo) // 2)
    return collect_range(base, lo, mid) + collect_range(base, mid + 1, hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-stars", type=int, default=10)
    ap.add_argument("--pushed-since", default="2025-01-01")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    topics = [l.strip() for l in (ROOT / "data" / "bio_keywords.txt").read_text().splitlines()
              if l.strip() and not l.startswith("#")]

    repos = {}
    for t in topics:
        base = f"topic:{t} pushed:>={args.pushed_since} fork:false archived:false"
        for it in collect_range(base, args.min_stars, None):
            r = repos.setdefault(it["full_name"], {**it, "matched": set()})
            r["matched"].add(t)
        print(f"{t}: {sum(t in r['matched'] for r in repos.values())} repos")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["repo", "stars", "language", "pushed_at", "owner_type", "matched_topics", "all_topics",
                    "description"])
        for r in sorted(repos.values(), key=lambda r: -r["stargazers_count"]):
            w.writerow([r["full_name"], r["stargazers_count"], r["language"] or "", r["pushed_at"][:10],
                        r["owner"]["type"], ";".join(sorted(r["matched"])), ";".join(r.get("topics", [])),
                        " ".join((r["description"] or "").split())])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(repos)} unique repos")


if __name__ == "__main__":
    main()
