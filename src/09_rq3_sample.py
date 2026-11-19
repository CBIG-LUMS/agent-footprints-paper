"""RQ3 samples of agent commits, drawn once, plus their diffs; then the two label files combined.

Pool: agent commits since 2024 that change at least one file, without Copilot review suggestions
(175728472 co-author only; the agent did not write that code).
1. First sample  -> data/labels.csv, ids 1-50: Bioconductor 25, nf-core 24, Biopython 1 (its only agent commit).
2. Second sample -> data/labels_extra.csv, ids 51-250: Bioconductor 100, nf-core 100, not in the first sample,
   at most 5 commits per repository so that large repositories (e.g. nf-core/rnaseq) do not fill it. Each commit
   gets its GitHub commit and pull-request link (gh CLI; Bioconductor: the GitHub repo named in DESCRIPTION).
3. data/labels_all.csv = both files stacked (250 commits; Table III). The published folder keeps only this file;
   when it exists without the two sample files, nothing is drawn or overwritten.
Every commit's diff goes to data/rq3_diffs/<id>.txt. Label columns are left empty; they are filled by hand
(change_type, touches_scientific_logic, risk_category, tests, concern, concern_note).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
FIRST, EXTRA, ALL = D / "labels.csv", D / "labels_extra.csv", D / "labels_all.csv"
DIFFS = D / "rq3_diffs"
SEED_FIRST, SPLIT_FIRST = 20261106, {"bioconductor": 25, "nf-core": 24, "biopython": 1}
SEED_EXTRA, SPLIT_EXTRA = 20261112, {"bioconductor": 100, "nf-core": 100}
CAP = 5            # second sample: most commits from one repository
MAX_LINES = 600    # longer diffs are cut; the link shows the full commit
LABELS = ["change_type", "touches_scientific_logic", "risk_category", "tests", "concern", "concern_note"]
COLS = ["id", "community", "repo", "sha", "author_date", "agent_name", "subject", "files_changed",
        "lines_added", "lines_deleted", "link"] + LABELS


def link(community, repo, sha):
    if community in ("nf-core", "biopython"):
        return f"https://github.com/{repo}/commit/{sha}"
    return f"git --git-dir=data/clones/bioconductor/{repo}.git show {sha[:10]}"


def git_dir(community, repo):
    return D / "clones" / community / f"{repo.split('/')[-1]}.git"


def pool():
    c = pd.read_parquet(D / "commits.parquet")
    a = c[c.agent_flag & (c.author_date >= pd.Timestamp("2024-01-01", tz="UTC"))]
    suggestion = ((a.heuristic == "robbes_author_copilot") & a.message.str.contains("175728472+Copilot", regex=False)
                  & ~a.author.str.contains("Copilot"))
    return a[~suggestion & (a.files_changed > 0)]


def prepare(s, first_id):
    s = s.reset_index(drop=True)
    s.insert(0, "id", range(first_id, first_id + len(s)))
    s["subject"] = s.message.str.split("\n").str[0]
    s["link"] = [link(r.community, r.repo, r.sha) for r in s.itertuples()]
    s["author_date"] = s.author_date.dt.strftime("%Y-%m-%d")
    for col in LABELS:
        s[col] = ""
    return s


def write_diffs(s):
    DIFFS.mkdir(exist_ok=True)
    for r in s.itertuples():
        out = subprocess.run(["git", "--git-dir", str(git_dir(r.community, r.repo)), "show", "--stat", "--patch",
                              "--format=commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%B", r.sha],
                             capture_output=True, text=True, errors="replace").stdout.splitlines()
        text = "\n".join(out[:MAX_LINES])
        if len(out) > MAX_LINES:
            text += f"\n\n[... cut after {MAX_LINES} of {len(out)} lines; full commit: {r.link}]"
        (DIFFS / f"{r.id:02d}.txt").write_text(f"id {r.id} | {r.community} | {r.repo}\n\n{text}\n")


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def github_links(r):
    """(GitHub commit URL or reason, pull-request URL or 'no PR (pushed directly)')."""
    repo = r.repo if r.community == "nf-core" else None
    if repo is None:
        desc = subprocess.run(["git", "--git-dir", str(git_dir(r.community, r.repo)), "show", "HEAD:DESCRIPTION"],
                              capture_output=True, text=True, errors="replace").stdout
        m = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", desc)
        if m is None:
            return "no GitHub repo (Bioconductor git only)", ""
        repo = f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    if gh(f"repos/{repo}/commits/{r.sha}") is None:
        return f"commit not found on GitHub ({repo})", ""
    pulls = gh(f"repos/{repo}/commits/{r.sha}/pulls") or []
    return f"https://github.com/{repo}/commit/{r.sha}", (pulls[0]["html_url"] if pulls else "no PR (pushed directly)")


def first_sample():
    a = pool()
    s = pd.concat([a[a.community == comm].sample(n=min(n, (a.community == comm).sum()), random_state=SEED_FIRST)
                   for comm, n in SPLIT_FIRST.items()])
    s = prepare(s, 1)
    s[COLS].to_csv(FIRST, index=False, lineterminator="\n")
    write_diffs(s)
    print(f"wrote {FIRST.relative_to(ROOT)} ({len(s)} commits)\n" + s.groupby("community").size().to_string())


def second_sample():
    first = pd.read_csv(FIRST, keep_default_na=False)
    a = pool()
    a = a[~a.sha.isin(first.sha)]
    parts = []
    for comm, n in SPLIT_EXTRA.items():
        shuffled = a[a.community == comm].sample(frac=1, random_state=SEED_EXTRA)
        parts.append(shuffled.groupby("repo", sort=False).head(CAP).head(n))
    s = prepare(pd.concat(parts), first.id.max() + 1)
    print(f"looking up GitHub links for {len(s)} commits ...")
    s[["github_commit", "pr_link"]] = [github_links(r) for r in s.itertuples()]
    s[list(first.columns) if "pr_link" in first.columns else COLS + ["github_commit", "pr_link"]].to_csv(
        EXTRA, index=False, lineterminator="\n")
    write_diffs(s)
    print(f"wrote {EXTRA.relative_to(ROOT)} (ids {s.id.min()}-{s.id.max()})")
    print(s.groupby("community").agg(commits=("sha", "size"), repos=("repo", "nunique"),
                                     max_per_repo=("repo", lambda x: x.value_counts().max())).to_string())


def combine():
    d = pd.concat([pd.read_csv(f, keep_default_na=False) for f in (FIRST, EXTRA)]).sort_values("id")
    d.to_csv(ALL, index=False, lineterminator="\n")
    print(f"wrote {ALL.relative_to(ROOT)} ({len(d)} commits)")


def main():
    if ALL.exists() and not (FIRST.exists() and EXTRA.exists()):
        print(f"{ALL.relative_to(ROOT)} exists (the labelled 250 commits): nothing to draw or combine")
        return
    if FIRST.exists():
        print(f"{FIRST.relative_to(ROOT)} exists: first sample kept as it is")
    else:
        first_sample()
    if EXTRA.exists():
        print(f"{EXTRA.relative_to(ROOT)} exists: second sample kept as it is")
    else:
        second_sample()
    combine()


if __name__ == "__main__":
    sys.exit(main())
