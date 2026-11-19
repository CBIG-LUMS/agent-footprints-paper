"""Paper numbers that 10_results.py does not write.

Usage: python src/12_summary.py > data/results/summary.txt
Only reads files in data/ and notes/; no clones needed.
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
COMMS = ["bioconductor", "nf-core", "biopython"]
LABEL = "is_agent (yes/no/borderline)"


def title(t):
    print(f"\n--- {t} ---")


def load_commits():
    c = pd.read_parquet(D / "commits.parquet")
    c = c[c.agent_flag | (c.heuristic == "")]          # drop bot commits, as in 10_results.py
    return c[c.author_date >= pd.Timestamp("2024-01-01", tz="UTC")]


def policy_dates():
    p = pd.read_csv(D / "policy_dates.csv")
    return p.set_index(p.community.str.lower()).effective_date


def table1_repos(c):
    title("Table I: repositories with an agent commit or a context file")
    r = pd.read_csv(D / "repos.csv", keep_default_na=False)
    # nf-core: repositories with commits since 2024 (169)
    total = {"bioconductor": 2418, "nf-core": c[c.community == "nf-core"].repo.nunique(), "biopython": 1}
    for comm in COMMS:
        agent = set(c[(c.community == comm) & c.agent_flag].repo)
        ctx = set(r[(r.community == comm) & r.has_context_file].repo)
        both, either = agent & ctx, agent | ctx
        n = total[comm]
        print(f"{comm}: agent commit {len(agent)} ({100 * len(agent) / n:.1f}%), context file {len(ctx)}, "
              f"both {len(both)}, either {len(either)} of {n} ({100 * len(either) / n:.1f}%)")


def table1_agents(c):
    title("Table I: agent commits by agent")
    a = c[c.agent_flag]
    name = a.agent_name.str.lower()
    group = pd.Series("Other", index=a.index)
    group[name.str.contains("gemini|antigravity|jules")] = "Gemini and Jules"
    group[name.str.contains("cursor")] = "Cursor"
    group[name.str.contains("copilot")] = "Copilot"
    group[name.str.contains("claude")] = "Claude Code"
    group[name.str.contains(" and ")] = "Other"          # one commit names two agents
    print(pd.crosstab(group.rename("agent"), a.community).reindex(columns=COMMS, fill_value=0).to_string())
    share = (group == "Claude Code").groupby(a.community).mean() * 100
    print("Claude Code share:", ", ".join(f"{k} {v:.1f}%" for k, v in share.items()))


def local_rules(c):
    title("Commits found only by our local rules")
    a = c[c.agent_flag & ~c.heuristic.str.contains("robbes_")]
    print(a.community.value_counts().to_string())


def missed(c):
    title("Agent commits the rules miss (checked by hand, kind A)")
    flagged, every = set(c[c.agent_flag].sha), set(c.sha)
    files = [("bioconductor", "bioc_missed.csv", "FInal_kind (verified)"),
             ("nf-core", "nfcore_missed.csv", "final_kind (A/B/C/D/N)"),
             ("nf-core", "nfcore_missed_extra.csv", "final_kind (A/B/C/D/N)"),
             ("nf-core", "nfcore_dev_missed.csv", "final_kind (A/B/C/D/N)")]
    total = {}
    for comm, f, col in files:
        n = pd.read_csv(ROOT / "notes" / f, keep_default_na=False)
        kind_a = n[n[col].str.strip() == "A"].sha
        # short shas in the notes; count those in the commit table that are not flagged
        miss = sum(any(x.startswith(s) for x in every) and not any(x.startswith(s) for x in flagged) for s in kind_a)
        print(f"{f}: {len(kind_a)} kind A, {miss} not flagged")
        total[comm] = total.get(comm, 0) + miss
    print("not counted:", total)


def disclosure(c):
    title("Assisted-by lines and context-file dates")
    eff = policy_dates()
    a = c[c.agent_flag & c.heuristic.str.contains("local_msg_assisted_by")]
    for comm in ["bioconductor", "nf-core"]:
        x = a[a.community == comm]
        after = (x.author_date >= pd.Timestamp(eff[comm], tz="UTC")).sum()
        print(f"{comm}: {len(x)} Assisted-by commits, {after} from the policy date ({eff[comm]})")
    r = pd.read_csv(D / "repos.csv", keep_default_na=False)
    n = r[r.community == "nf-core"]
    for f in ["AGENTS.md", "CLAUDE.md"]:
        s = n[n[f] != ""][f]
        print(f"nf-core {f}: {len(s)} repositories, first added {s.min()} to {s.max()}")


def nfcore_busiest(c):
    title("nf-core monthly share, with and without the two busiest repositories")
    n = c[c.community == "nf-core"]
    month = n.author_date.dt.strftime("%Y-%m")
    for m in ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]:
        x = n[month == m]
        top = x[x.agent_flag].repo.value_counts().head(2)
        rest = x[~x.repo.isin(top.index)]
        print(f"{m}: {100 * x.agent_flag.mean():.1f}%, without top two {100 * rest.agent_flag.mean():.1f}% "
              f"({', '.join(f'{r} {k}' for r, k in top.items())})")


def biopython_prs():
    title("Biopython pull requests with an agent trace")
    prs = json.load(open(D / "raw" / "biopython_prs.json"))
    eff = policy_dates()["biopython"]
    # same traces as the commit rules: tool footers, co-author lines, agent branch names
    rx = re.compile(r"generated with \[?claude code|made with \[?cursor|co-authored-by:.*(claude|cursor|copilot)"
                    r"|^(codex|claude|cursor|copilot|devin)/", re.I | re.M)
    hits = []
    for p in prs:
        m = rx.search(p["body"] or "") or rx.search(p["headRefName"])
        if m:
            hits.append((p["number"], p["createdAt"][:10], p["mergedAt"], m.group(0)))
    print(f"{len(prs)} pull requests since 2024, {len(hits)} with a trace")
    for num, date, merged, trace in hits:
        when = "after" if date >= eff else "before"
        print(f"#{num} {date} ({when} policy), {'merged' if merged else 'not merged'}: {trace}")


def validation():
    title("Validation")
    v = pd.read_csv(D / "validation.csv", keep_default_na=False)
    print(pd.crosstab(v["sample"], v[LABEL].str.strip()).to_string())
    t = pd.read_csv(D / "topic_validation.csv", keep_default_na=False)
    print("comparison group:", t[LABEL].str.strip().value_counts().to_dict())


def comparison_group():
    title("Comparison group")
    r = pd.read_csv(D / "results" / "topic_repos.csv", keep_default_na=False)
    lab = pd.read_csv(D / "topic_needs_check.csv", keep_default_na=False)
    yes = set(lab[lab["is_bio_software (yes/no)"].str.strip().str.lower() == "yes"].repo)
    s = r[r.cloned.astype(bool) & ((r.needs_check == "") | r.repo.isin(yes))]
    traced = s.any_trace.astype(bool).sum()
    print(f"{len(s)} repositories, {traced} with an agent commit or context file ({100 * traced / len(s):.1f}%)")


def rq3_tables(file, label, other_col=False):
    """Table III numbers for one labelled sample (communities or comparison group)."""
    title(f"RQ3 / Table III, {label}")
    d = pd.read_csv(D / file, keep_default_na=False)
    sci = d[d.touches_scientific_logic == "yes"]
    per_repo = d.groupby("repo").size()
    print(f"{len(d)} commits from {per_repo.size} repositories, at most {per_repo.max()} per repository")
    print(pd.crosstab(d.community, d.touches_scientific_logic, margins=True).to_string())
    print("\nscientific logic, risk category by tests")
    print(pd.crosstab(sci.risk_category, sci.tests, margins=True).to_string())
    print("\nall commits, scientific logic by tests")
    print(pd.crosstab(d.touches_scientific_logic, d.tests, margins=True).to_string())
    print("\nchange types")
    print(d.change_type.value_counts().to_string())
    route = d.pr_link.map(lambda x: "PR" if x.startswith("https") else
                          "pushed directly" if "pushed" in x else "no GitHub repo")
    print("\nconcern by how the commit went in")
    print(pd.crosstab([d.community, route.rename("route")], d.concern, margins=True).to_string())
    print("\ncommits with a concern")
    print(d[d.concern != "none"][["id", "repo", "concern", "pr_link"]].to_string(index=False))
    if other_col:
        print("\nrisk category 'other', what the change was about")
        o = d[d.risk_category == "other"]
        print(o[["id", "repo", "risk_in_other_risk_category"]].to_string(index=False))
    print("\nscientific-logic commits with the note on how each went in")
    print(sci[["id", "repo", "concern", "concern_note"]].to_string(index=False, max_colwidth=120))


def rq3():
    rq3_tables("labels_all.csv", "communities")
    rq3_tables("topic_labels.csv", "comparison group", other_col=True)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    commits = load_commits()
    table1_repos(commits)
    table1_agents(commits)
    local_rules(commits)
    missed(commits)
    disclosure(commits)
    nfcore_busiest(commits)
    biopython_prs()
    validation()
    comparison_group()
    rq3()
