"""Draw the precision validation sample -> data/validation.csv (+ data/validation_messages.txt for reading).

50 flagged and 50 unflagged commits, labelled by hand. Stratified per community (2026-11-04):
flagged Bioconductor 25, nf-core 24, Biopython 1 (its only agent commit); unflagged the same split.
Bot commits are excluded from both halves. Unflagged commits come from the study period (author date
2025-01-01 onward; 2024 is the baseline with no agent commits). Fixed seed, so the sample can be redrawn.
The label columns are left empty and filled by hand.
Refuses to overwrite an existing data/validation.csv, so labels are never lost by a rerun.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "validation.csv"
MSG = ROOT / "data" / "validation_messages.txt"
SEED = 20261105
SPLIT = {"bioconductor": 25, "nf-core": 24, "biopython": 1}
STUDY_START = pd.Timestamp("2025-01-01", tz="UTC")


def url(community, repo, sha):
    if community in ("nf-core", "biopython"):
        return f"https://github.com/{repo}/commit/{sha}"
    return f"git --git-dir=data/clones/bioconductor/{repo}.git show {sha[:10]}"


def main():
    if OUT.exists():
        sys.exit(f"{OUT.relative_to(ROOT)} exists; move it away first if you really want a new sample")
    c = pd.read_parquet(ROOT / "data" / "commits.parquet")
    c = c[~((~c.agent_flag) & (c.heuristic != ""))]  # drop bot commits
    parts = []
    for comm, n in SPLIT.items():
        g = c[c.community == comm]
        flagged = g[g.agent_flag]
        unflagged = g[~g.agent_flag & (g.author_date >= STUDY_START)]
        parts.append(flagged.sample(n=min(n, len(flagged)), random_state=SEED).assign(sample="flagged"))
        parts.append(unflagged.sample(n=n, random_state=SEED).assign(sample="unflagged"))
    s = pd.concat(parts).reset_index(drop=True)
    s.insert(0, "id", range(1, len(s) + 1))
    s["subject"] = s.message.str.split("\n").str[0]
    s["link"] = [url(r.community, r.repo, r.sha) for r in s.itertuples()]
    s["is_agent (yes/no/borderline)"] = ""
    s["evidence_outside_commit (PR/issue/none)"] = ""
    s["note"] = ""
    cols = ["id", "sample", "community", "repo", "sha", "author_date", "author", "subject", "agent_name",
            "heuristic", "link", "is_agent (yes/no/borderline)", "evidence_outside_commit (PR/issue/none)", "note"]
    s["author_date"] = s.author_date.dt.strftime("%Y-%m-%d")
    s[cols].to_csv(OUT, index=False, lineterminator="\n")
    with open(MSG, "w") as f:
        for r in s.itertuples():
            f.write(f"=== id {r.id} | {r.sample} | {r.repo} {r.sha[:10]} | {r.author_date} | {r.author}\n"
                    f"rule: {r.heuristic or '-'}\n{r.message}\n\n")
    print(f"wrote {OUT.relative_to(ROOT)} and {MSG.relative_to(ROOT)}: {len(s)} commits")
    print(s.groupby(["community", "sample"]).size().to_string())


if __name__ == "__main__":
    main()
