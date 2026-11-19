"""Agent traces in the GitHub topic repos cloned by 15_clone_topic.sh.

Same detection as the three communities: classify() from 06_mine_commits.py (heuristics.yaml), and the
context-file list from 07_context_files.py. Same window and rules as 10_results.py: non-merge commits
authored since 2024-01-01, bot commits left out of every count.
Clones are partial (no file contents), so there are no size columns; git is run with --no-renames and
without --numstat so it never needs file contents.
Outputs:
  data/raw/github_topic/topic_commits.parquet  one row per commit (bots included, as in commits.parquet)
  data/results/topic_repos.csv                 one row per repo: commits, agent commits, context files
  data/results/topic_summary.csv               totals overall and per matched topic
  data/results/topic_monthly.csv               monthly agent-commit share of the study set
  data/results/topic_policy_windows.csv        study set over each community's policy windows (RQ2 comparison)
  data/results/topic_agent_names.csv           agents in the study set; last row = all Claude name variants (RQ1)
"""
import importlib
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
m06 = importlib.import_module("06_mine_commits")
CONTEXT = importlib.import_module("07_context_files").FILES

CLONES = ROOT / "data" / "clones_topic"
RAW = ROOT / "data" / "raw" / "github_topic"
RES = ROOT / "data" / "results"
SINCE = "2024-01-01"
LAST_MONTH = "2026-10"  # last full month before the mining date
FMT = "%x1e%H%x1f%aI%x1f%an <%ae>%x1f%cn <%ce>%x1f%B"


def git(g, *args):
    return subprocess.run(["git", "-C", str(g), *args], capture_output=True, text=True, errors="replace")


def mine(g):
    repo = g.name.removesuffix(".git").replace("__", "/", 1)
    out = git(g, "log", "--no-merges", f"--since={SINCE}", f"--format={FMT}", "HEAD")
    if out.returncode != 0:
        return repo, [], {}, out.stderr.strip()[:200]
    rows = []
    for rec in out.stdout.split("\x1e")[1:]:
        sha, adate, author, committer, message = rec.split("\x1f")
        flag, agent, rule = m06.classify(author, message)
        rows.append({"repo": repo, "sha": sha, "author_date": adate, "author": author, "committer": committer,
                     "message": message.strip(), "agent_flag": flag, "agent_name": agent, "heuristic": rule})
    at_head = [l for l in git(g, "ls-tree", "-r", "--name-only", "HEAD", "--", *CONTEXT.values()).stdout.split("\n") if l]
    present = [c for c, spec in CONTEXT.items()
               if any(p == spec or (spec.endswith("/") and p.startswith(spec)) for p in at_head)]
    added = git(g, "log", "--no-renames", "--diff-filter=A", f"--since={SINCE}", "--format=%aI", "HEAD",
                "--", *CONTEXT.values()).stdout.split()
    ctx = {"context_files_at_head": ";".join(present),
           "first_context_file_added": min(added)[:10] if added else ""}
    return repo, rows, ctx, None


def main():
    RES.mkdir(exist_ok=True)
    meta = pd.read_csv(RAW / "topic_repos_included.tsv", sep="\t", keep_default_na=False)
    clones = sorted(g for g in CLONES.glob("*.git") if not g.name.startswith(".tmp_"))
    print(f"mining {len(clones)} clones of {len(meta)} included repos")
    rows, ctx, errors = [], {}, []
    with Pool(8) as pool:
        for repo, r, c, err in pool.imap_unordered(mine, clones, chunksize=4):
            rows.extend(r)
            ctx[repo] = c
            if err:
                errors.append(f"{repo}: {err}")
    cols = ["repo", "sha", "author_date", "author", "committer", "message", "agent_flag", "agent_name", "heuristic"]
    c = pd.DataFrame(rows, columns=cols)
    c["author_date"] = pd.to_datetime(c.author_date, utc=True)
    c = c.sort_values(["repo", "author_date"]).reset_index(drop=True)
    c.to_parquet(RAW / "topic_commits.parquet", index=False)

    # as 10_results.py: drop bots, keep author date >= 2024-01-01
    n = c[~((~c.agent_flag) & (c.heuristic != "")) & (c.author_date >= pd.Timestamp(SINCE, tz="UTC"))]
    per = n.groupby("repo").agg(commits=("sha", "size"), agent_commits=("agent_flag", "sum"),
                                first_agent_commit=("author_date", lambda s: ""))
    first = n[n.agent_flag].groupby("repo").author_date.min().dt.strftime("%Y-%m-%d")
    names = n[n.agent_flag].groupby("repo").agent_name.agg(lambda s: ";".join(sorted(set(s))))
    per["first_agent_commit"] = first
    per["agent_names"] = names
    repos = meta[["repo", "stars", "language", "owner_type", "matched_topics", "needs_check"]].copy()
    repos["cloned"] = repos.repo.isin(ctx)
    repos = repos.merge(per, left_on="repo", right_index=True, how="left")
    repos = repos.merge(pd.DataFrame.from_dict(ctx, orient="index"), left_on="repo", right_index=True, how="left")
    repos[["commits", "agent_commits"]] = repos[["commits", "agent_commits"]].fillna(0).astype(int)
    repos = repos.fillna({"first_agent_commit": "", "agent_names": "", "context_files_at_head": "",
                          "first_context_file_added": ""})
    repos["any_trace"] = (repos.agent_commits > 0) | (repos.context_files_at_head != "")
    repos.sort_values(["agent_commits", "stars"], ascending=False).to_csv(
        RES / "topic_repos.csv", index=False, lineterminator="\n")

    # Study set for the paper: repos without needs_check, plus needs_check repos labelled
    # is_bio_software = yes in data/topic_needs_check.csv (written by 17_topic_samples.py).
    checked = ROOT / "data" / "topic_needs_check.csv"
    yes = set()
    if checked.exists():
        lab = pd.read_csv(checked, keep_default_na=False)
        yes = set(lab[lab["is_bio_software (yes/no)"].str.strip().str.lower() == "yes"].repo)
    study = set(repos[repos.cloned & ((repos.needs_check == "") | repos.repo.isin(yes))].repo)
    # Last full month before the mining date (30 Oct - 3 Nov 2026), fixed so a later rerun gives the same
    # monthly table and Fig. 1 (a later month would hold only a few days of data).
    last_full = LAST_MONTH
    sn = n[n.repo.isin(study)].assign(month=n.author_date.dt.strftime("%Y-%m"))
    monthly = (sn[sn.month <= last_full].groupby("month")
               .agg(commits=("sha", "size"), agent=("agent_flag", "sum"), active_repos=("repo", "nunique"))
               .reset_index())
    monthly["share_pct"] = (100 * monthly.agent / monthly.commits).round(2)
    monthly.insert(0, "community", "github-topic")
    monthly.to_csv(RES / "topic_monthly.csv", index=False, lineterminator="\n")
    # Comparison for RQ2: the topic study set over the same policy windows as 10_results.py
    # (5 months before each community's date vs 5 months from it), commit-weighted share.
    W = pd.DateOffset(months=5)
    policy = pd.read_csv(ROOT / "data" / "policy_dates.csv")
    win = []
    for _, p in policy.iterrows():
        for kind in ["effective_date", "proposal_date"]:
            if pd.isna(p[kind]):
                continue
            e = pd.Timestamp(p[kind], tz="UTC")
            row = {"policy_of": p.community, "date_kind": kind.removesuffix("_date"), "date": e.date(),
                   "after_window_end": (e + W).date()}
            for side, x in [("before", sn[(sn.author_date >= e - W) & (sn.author_date < e)]),
                            ("after", sn[(sn.author_date >= e) & (sn.author_date < e + W)])]:
                row.update({f"{side}_commits": len(x), f"{side}_agent": int(x.agent_flag.sum()),
                            f"{side}_share_pct": round(100 * x.agent_flag.mean(), 2) if len(x) else None,
                            f"{side}_agent_repos": x[x.agent_flag].repo.nunique()})
            win.append(row)
    win = pd.DataFrame(win)
    win.to_csv(RES / "topic_policy_windows.csv", index=False, lineterminator="\n")
    print("TOPIC GROUP AT EACH COMMUNITY'S POLICY DATES (data/results/topic_policy_windows.csv)\n"
          + win.to_string(index=False) + "\n")
    # Agents in the study set, as data/results/agent_names.csv for the communities. The last row adds up
    # every name containing "Claude" (Claude Code, Claude, Claude Code:claude-opus-..., ...), as in the paper.
    ag = sn[sn.agent_flag]
    names = ag.groupby("agent_name").agg(agent_commits=("sha", "size"), repos=("repo", "nunique"))
    names = names.sort_values("agent_commits", ascending=False).reset_index()
    cl = ag[ag.agent_name.str.contains("claude", case=False)]
    names = pd.concat([names, pd.DataFrame([{"agent_name": "Claude, all name variants",
                                             "agent_commits": len(cl), "repos": cl.repo.nunique()}])])
    names["share_pct"] = (100 * names.agent_commits / len(ag)).round(1)
    names.insert(0, "community", "github-topic")
    names.to_csv(RES / "topic_agent_names.csv", index=False, lineterminator="\n")
    print(f"CLAUDE IN THE STUDY SET: {len(cl)}/{len(ag)} agent commits ({100 * len(cl) / len(ag):.1f}%), "
          f"{cl.repo.nunique()} repos (data/results/topic_agent_names.csv)\n")
    st = repos[repos.repo.isin(study)]
    print(f"STUDY SET: {len(st)} repos ({len(yes)} needs_check repos labelled yes), "
          f"{int(st.any_trace.sum())} with any trace ({100 * st.any_trace.mean():.1f}%), "
          f"{int(st.agent_commits.sum())}/{int(st.commits.sum())} agent commits; "
          f"data/results/topic_monthly.csv up to {last_full}\n")

    def summ(label, r):
        act = r[r.commits > 0]
        return {"group": label, "repos": len(r), "cloned": int(r.cloned.sum()), "active_since_2024": len(act),
                "commits": int(act.commits.sum()), "agent_commits": int(act.agent_commits.sum()),
                "agent_share_pct": round(100 * act.agent_commits.sum() / act.commits.sum(), 2) if len(act) else None,
                "repos_agent_commit": int((act.agent_commits > 0).sum()),
                "repos_context_file": int((r.context_files_at_head != "").sum()),
                "repos_any_trace": int(r.any_trace.sum()),
                "repos_any_trace_pct": round(100 * r.any_trace.sum() / max(r.cloned.sum(), 1), 1)}
    s = [summ("all", repos)]
    for t in sorted(set(";".join(repos.matched_topics).split(";"))):
        s.append(summ(t, repos[repos.matched_topics.str.split(";").apply(lambda x: t in x)]))
    s = pd.DataFrame(s)
    s.to_csv(RES / "topic_summary.csv", index=False, lineterminator="\n")

    pd.set_option("display.width", 200)
    print(f"wrote {RAW.relative_to(ROOT)}/topic_commits.parquet ({len(c)} commits), "
          "data/results/topic_repos.csv, data/results/topic_summary.csv\n")
    print("TOPIC REPOS (non-bot commits since 2024-01-01; a repo counts once per matched topic)")
    print(s.sort_values("repos", ascending=False).to_string(index=False))
    print("\nAGENTS\n" + n[n.agent_flag].agent_name.value_counts().to_string())
    print("\nTOP 10 REPOS BY AGENT COMMITS\n" + repos.sort_values("agent_commits", ascending=False).head(10)[
        ["repo", "stars", "commits", "agent_commits", "agent_names", "context_files_at_head"]].to_string(index=False))
    for e in errors:
        print("ERROR", e, file=sys.stderr)


if __name__ == "__main__":
    main()
