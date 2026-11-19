"""Paper numbers for RQ1/RQ2 from data/commits.parquet -> data/results/*.csv, plus a printed summary.

Definitions:
- Bot commits are left out of every count (a bot match has agent_flag False and a heuristic).
- Dates are author dates, UTC. Commits authored before 2024-01-01 (old commits that entered the
  window by a later commit date) and months after October 2026 (LAST_MONTH, the last full month before
  the mining date) are left out of the monthly table.
- Headline share: agent commits / non-bot commits from 2024-01-01 on.
- 2026 share (headline_2026.csv): the same, for commits authored from 2026-01-01 (RECENT) to the mining
  date; agent_of_all_pct = this period's agent commits / all agent commits since 2024 (row "all" = total).
- Without borderline (agent_without_borderline): agent commits minus those whose only trace is an accepted
  Copilot review suggestion (175728472 co-author on a human-authored commit), labelled borderline in the validation.
- Policy windows: 5 months before the date vs 5 months from the date (pd.DateOffset(months=5)),
  for the effective and the proposal date in data/policy_dates.csv.
- Concentration: share of a community's agent commits in its top 1 / top 5 repos.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "results"
START = pd.Timestamp("2024-01-01", tz="UTC")
WINDOW = pd.DateOffset(months=5)
LAST_MONTH = "2026-10"  # last full month before the mining date
RECENT = pd.Timestamp("2026-01-01", tz="UTC")  # start of the 2026 share in Table II
COMMUNITY = {"Bioconductor": "bioconductor", "nf-core": "nf-core", "Biopython": "biopython"}


def load():
    c = pd.read_parquet(ROOT / "data" / "commits.parquet",
                        columns=["community", "repo", "sha", "author_date", "author", "message",
                                 "agent_flag", "agent_name", "heuristic"])
    c = c[~((~c.agent_flag) & (c.heuristic != ""))]  # drop bot commits
    c = c[c.author_date >= START].copy()
    c["borderline"] = (c.agent_flag & (c.heuristic == "robbes_author_copilot")
                       & c.message.str.contains("175728472+Copilot", regex=False)
                       & ~c.author.str.contains("Copilot"))
    c["month"] = c.author_date.dt.strftime("%Y-%m")
    return c


def share(x):
    n, a = len(x), int(x.agent_flag.sum())
    return {"commits": n, "agent": a, "share_pct": round(100 * a / n, 2) if n else None,
            "agent_repos": x[x.agent_flag].repo.nunique()}


def main():
    OUT.mkdir(exist_ok=True)
    c = load()
    # Last full month before the mining date (30 Oct - 3 Nov 2026), fixed so a later rerun gives the same
    # monthly table and Fig. 1 (a later month would hold only a few days of data).
    last_full = LAST_MONTH
    policy = pd.read_csv(ROOT / "data" / "policy_dates.csv")

    head, monthly, windows, conc, agents = [], [], [], [], []
    for comm, g in c.groupby("community"):
        h = share(g)
        h.update({"community": comm, "repos": g.repo.nunique(), "agent_without_borderline": int((g.agent_flag & ~g.borderline).sum()),
                  "first_agent_commit": g[g.agent_flag].author_date.min().date() if h["agent"] else None})
        head.append(h)

        for m, x in g[g.month <= last_full].groupby("month"):
            monthly.append({"community": comm, "month": m, **share(x)})

        for _, p in policy[policy.community.map(COMMUNITY) == comm].iterrows():
            for kind in ["effective_date", "proposal_date"]:
                if pd.isna(p[kind]):
                    continue
                e = pd.Timestamp(p[kind], tz="UTC")
                b = g[(g.author_date >= e - WINDOW) & (g.author_date < e)]
                a = g[(g.author_date >= e) & (g.author_date < e + WINDOW)]
                row = {"community": comm, "date_kind": kind.removesuffix("_date"), "date": e.date(),
                       "after_window_end": (e + WINDOW).date()}
                row.update({f"before_{k}": v for k, v in share(b).items()})
                row.update({f"after_{k}": v for k, v in share(a).items()})
                windows.append(row)

        per_repo = g[g.agent_flag].repo.value_counts()
        if len(per_repo):
            conc.append({"community": comm, "agent_repos": len(per_repo),
                         "top1_pct": round(100 * per_repo.iloc[:1].sum() / per_repo.sum(), 1),
                         "top5_pct": round(100 * per_repo.iloc[:5].sum() / per_repo.sum(), 1),
                         "median_per_repo": per_repo.median(), "repos_with_one": int((per_repo == 1).sum()),
                         "top5": "; ".join(f"{r} {n}" for r, n in per_repo.iloc[:5].items())})
        # ties ordered by name, so a rerun writes the same file
        counts = g[g.agent_flag].agent_name.value_counts().rename_axis("agent_name").reset_index(name="n")
        for name, n in counts.sort_values(["n", "agent_name"], ascending=[False, True]).itertuples(index=False):
            agents.append({"community": comm, "agent_name": name, "agent_commits": n})

    # Table II: Jan 2026 to the mining date, same rules as the headline.
    recent = []
    for comm, g in list(c.groupby("community")) + [("all", c)]:
        r = g[g.author_date >= RECENT]
        recent.append({"community": comm, "from": RECENT.date(), **share(r),
                       "agent_without_borderline": int((r.agent_flag & ~r.borderline).sum()),
                       "agent_since_2024": int(g.agent_flag.sum()),
                       "agent_of_all_pct": round(100 * r.agent_flag.sum() / g.agent_flag.sum(), 1)})

    tables = {"headline": head, "headline_2026": recent, "monthly": monthly, "policy_windows": windows,
              "concentration": conc, "agent_names": agents}
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(OUT / f"{name}.csv", index=False, lineterminator="\n")
    print(f"wrote data/results/: {', '.join(f'{n}.csv' for n in tables)} (monthly up to {last_full})\n")

    pd.set_option("display.width", 200)
    cols = ["community", "commits", "agent", "share_pct", "agent_repos", "repos", "agent_without_borderline", "first_agent_commit"]
    print("HEADLINE (non-bot commits since 2024-01-01)\n" + pd.DataFrame(head)[cols].to_string(index=False))
    print("\nSHARE IN 2026 (non-bot commits from 2026-01-01 to the mining date)\n"
          + pd.DataFrame(recent).to_string(index=False))
    w = pd.DataFrame(windows)
    print("\nPOLICY WINDOWS (5 months before vs 5 months from the date)\n" + w[
        ["community", "date_kind", "date", "before_commits", "before_agent", "before_share_pct", "before_agent_repos",
         "after_commits", "after_agent", "after_share_pct", "after_agent_repos"]].to_string(index=False))
    print("\nCONCENTRATION\n" + pd.DataFrame(conc).to_string(index=False))


if __name__ == "__main__":
    main()
