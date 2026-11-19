"""Hand-check files for the GitHub topic repos. Run once after 16_mine_topic.py.

1. data/topic_needs_check.csv: the needs_check repos (no main language, or only broad topics such as dna/genome)
   that have an agent trace. One author fills is_bio_software (yes/no). 16_mine_topic.py keeps a needs_check repo
   only if it is labelled yes; needs_check repos without a trace are left out (they only change the
   denominator, by less than one percentage point).
2. data/topic_validation.csv (+ topic_validation_messages.txt): 20 flagged non-bot commits since 2024-01-01,
   one per repo, from 20 repos drawn at random (seed below), so one very active repo (JBrowse) cannot fill
   the sample. One author labels is_agent (yes/no/borderline) as in data/validation.csv.

  python src/17_topic_samples.py --replace 4   redraw row 4 of topic_validation.csv (e.g. its repo was
  excluded later): a new random repo from the study set not yet in the sample, seed SEED + id. Every other
  row and label is kept; the replaced row's label columns are emptied; the messages file is rewritten.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "github_topic"
SEED = 20261109
N = 20


def write_once(path, df):
    if path.exists():
        print(f"{path.relative_to(ROOT)} exists, not overwritten")
        return False
    df.to_csv(path, index=False, lineterminator="\n")
    print(f"wrote {path.relative_to(ROOT)}: {len(df)} rows")
    return True


def write_messages(s):
    with open(ROOT / "data" / "topic_validation_messages.txt", "w", encoding="utf-8") as f:
        for _, r in s.iterrows():
            f.write(f"===== {r.id}  {r.repo}  {r.sha}\n{r.link}\nauthor: {r.author}\n"
                    f"rule: {r.heuristic}\n\n{r.message}\n\n")
    print("wrote data/topic_validation_messages.txt")


def replace(ids):
    out = ROOT / "data" / "topic_validation.csv"
    if (out.parent / f".~lock.{out.name}#").exists():
        sys.exit("topic_validation.csv is open in LibreOffice: close it first")
    v = pd.read_csv(out, keep_default_na=False, dtype=str)
    c = pd.read_parquet(RAW / "topic_commits.parquet")
    c = c[c.agent_flag & (c.author_date >= pd.Timestamp("2024-01-01", tz="UTC"))]
    # study set as in 16_mine_topic.py, from the current included list and needs_check labels
    inc = pd.read_csv(RAW / "topic_repos_included.tsv", sep="\t", keep_default_na=False)
    lab = pd.read_csv(ROOT / "data" / "topic_needs_check.csv", keep_default_na=False)
    yes = set(lab[lab["is_bio_software (yes/no)"].str.strip().str.lower() == "yes"].repo)
    study = set(inc[(inc.needs_check == "") | inc.repo.isin(yes)].repo)
    for i in ids:
        old = v.loc[v.id == str(i)].iloc[0]
        pool = sorted(set(c.repo) & study - set(v.repo))
        repo = pd.Series(pool).sample(1, random_state=SEED + i).iloc[0]
        r = c[c.repo == repo].sample(1, random_state=SEED).iloc[0]
        new = {"id": str(i), "repo": repo, "sha": r.sha, "author_date": r.author_date.strftime("%Y-%m-%d"),
               "author": r.author, "subject": r.message.split("\n")[0], "agent_name": r.agent_name,
               "heuristic": r.heuristic, "link": f"https://github.com/{repo}/commit/{r.sha}"}
        for col in v.columns:
            v.loc[v.id == str(i), col] = new.get(col, "")
        print(f"row {i}: {old.repo} -> {repo} ({r.agent_name}, {new['author_date']})")
    # same sha can sit in several repos (forks), so look messages up by (repo, sha)
    m = v.merge(c[["repo", "sha", "message"]].drop_duplicates(["repo", "sha"]), on=["repo", "sha"], how="left")
    v.to_csv(out, index=False, lineterminator="\n")
    write_messages(m.assign(id=m.id.astype(int)))


def main():
    if "--replace" in sys.argv:
        return replace([int(a) for a in sys.argv[sys.argv.index("--replace") + 1:]])
    repos = pd.read_csv(ROOT / "data" / "results" / "topic_repos.csv", keep_default_na=False)
    meta = pd.read_csv(RAW / "topic_repos_included.tsv", sep="\t", keep_default_na=False)[["repo", "description"]]
    nc = repos[(repos.needs_check != "") & (repos.any_trace.astype(str) == "True")].merge(meta, on="repo")
    nc = nc.assign(link="https://github.com/" + nc.repo, **{"is_bio_software (yes/no)": "", "note": ""})
    write_once(ROOT / "data" / "topic_needs_check.csv",
               nc[["repo", "needs_check", "matched_topics", "language", "stars", "agent_commits",
                   "context_files_at_head", "description", "link", "is_bio_software (yes/no)", "note"]])

    c = pd.read_parquet(RAW / "topic_commits.parquet")
    c = c[c.agent_flag & (c.author_date >= pd.Timestamp("2024-01-01", tz="UTC"))]
    picked = pd.Series(sorted(c.repo.unique())).sample(N, random_state=SEED)
    s = pd.concat([c[c.repo == r].sample(1, random_state=SEED) for r in picked]).reset_index(drop=True)
    s.insert(0, "id", range(1, len(s) + 1))
    s["author_date"] = s.author_date.dt.strftime("%Y-%m-%d")
    s["subject"] = s.message.str.split("\n").str[0]
    s["link"] = "https://github.com/" + s.repo + "/commit/" + s.sha
    for col in ["is_agent (yes/no/borderline)", "evidence_outside_commit (PR/issue/none)", "note"]:
        s[col] = ""
    out = ROOT / "data" / "topic_validation.csv"
    if write_once(out, s[["id", "repo", "sha", "author_date", "author", "subject", "agent_name", "heuristic", "link",
                          "is_agent (yes/no/borderline)", "evidence_outside_commit (PR/issue/none)", "note"]]):
        write_messages(s)


if __name__ == "__main__":
    main()
