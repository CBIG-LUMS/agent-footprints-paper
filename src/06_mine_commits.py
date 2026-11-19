"""Mine commits from every clone in data/clones/<community>/*.git into data/commits.parquet.

Columns: community, repo, sha, author_date, author, committer, message,
files_changed, lines_added, lines_deleted, agent_flag, agent_name, heuristic.

Detection follows Robbes et al. heuristics.py: the commit author plus every
Co-authored-by trailer is matched ("name <email>", case-sensitive) against the author
rules first, then the bot rules. Message rules (local_rules.yaml) are checked as well.
A bot match is recorded in heuristic/agent_name with agent_flag = False, so bot commits
can be excluded from the denominator without an extra column.
File rules are repo-level (context files) and are handled in repos.csv, not here.
Merge commits are skipped (--no-merges), as in Robbes et al.
Window: commits with committer date since 2024-01-01 (clones are shallow since then).
Branches: the default branch, plus dev where 04_clone_nfcore.sh fetched it (nf-core).
"""
import re
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
CLONES = ROOT / "data" / "clones"
OUT = ROOT / "data" / "commits.parquet"
SINCE = "2024-01-01"
CO_AUTH = re.compile(r"[Cc]o-[Aa]uthored-[Bb]y:\s*([^<]+)<([^>]+)>")  # Robbes heuristics.py
ASSISTED = re.compile(r"(?im)^\s*Assisted-by:\s*(.+?)\s*$")
FMT = "%x1e%H%x1f%aI%x1f%an <%ae>%x1f%cn <%ce>%x1f%B%x1f"
# canonical spelling for agent names read from a match (local_msg_generated_by_agent)
AGENT_NAMES = {"claude": "Claude", "codex": "Codex", "cursor": "Cursor", "github copilot": "Copilot",
               "gpt": "GPT", "opencode": "OpenCode", "antigravity": "Antigravity", "grok": "Grok",
               "gemini": "Gemini"}

RULES = yaml.safe_load((ROOT / "heuristics.yaml").read_text())
AUTHOR_RULES = [(r["id"], re.compile(r["pattern"]), r["agent"]) for r in RULES if r["level"] == "author"]
BOT_RULES = [(r["id"], re.compile(r["pattern"]), r["agent"]) for r in RULES if r["level"] == "bot"]
MSG_RULES = [(r["id"], re.compile(r["pattern"]), r["agent"]) for r in RULES if r["level"] == "message"]


def first_match(rules, text):
    for rid, rx, agent in rules:
        if rx.search(text):
            return rid, agent
    return None


def classify(author, message):
    """Return (agent_flag, agent_name, heuristic)."""
    people = [author] + [f"{n.strip()} <{e.strip()}>" for n, e in CO_AUTH.findall(message)]
    fired, agents = [], []
    for p in people:
        m = first_match(AUTHOR_RULES, p)
        if m and m[0] not in fired:
            fired.append(m[0])
            agents.append(m[1])
    for rid, rx, agent in MSG_RULES:
        m = rx.search(message)
        if m:
            fired.append(rid)
            if agent == "from_trailer":
                agent = ASSISTED.search(message).group(1)
            elif agent == "from_match":  # named group "agent" in the rule pattern
                agent = AGENT_NAMES[m.group("agent").lower()]
            agents.append(agent)
    if fired:
        return True, agents[0], ";".join(fired)
    for p in people:  # Robbes: AI wins over Bot; Bot only if no AI match
        m = first_match(BOT_RULES, p)
        if m:
            return False, m[1], m[0]
    return False, "", ""


def repo_name(community, git_dir):
    name = git_dir.name.removesuffix(".git")
    # GitHub-hosted communities keep owner/name; Bioconductor packages are named alone
    return f"{community}/{name}" if community in ("biopython", "nf-core") else name


def revs(git_dir):
    """Default branch plus dev when 04_clone_nfcore.sh added it; git log lists each commit once."""
    has_dev = subprocess.run(["git", "-C", str(git_dir), "rev-parse", "-q", "--verify", "refs/heads/dev"],
                             capture_output=True).returncode == 0
    return ["HEAD", "dev"] if has_dev else ["HEAD"]


def mine(args):
    community, git_dir = args
    out = subprocess.run(["git", "-C", str(git_dir), "log", "--no-merges", f"--since={SINCE}",
                          f"--format={FMT}", "--numstat", *revs(git_dir)],
                         capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        return [], f"{git_dir}: {out.stderr.strip()[:200]}"
    rows = []
    for rec in out.stdout.split("\x1e")[1:]:
        sha, adate, author, committer, message, numstat = rec.split("\x1f")
        files = added = deleted = 0
        for line in numstat.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                files += 1
                added += int(parts[0]) if parts[0].isdigit() else 0
                deleted += int(parts[1]) if parts[1].isdigit() else 0
        flag, agent, rule = classify(author, message)
        rows.append({"community": community, "repo": repo_name(community, git_dir), "sha": sha,
                     "author_date": adate, "author": author, "committer": committer,
                     "message": message.strip(), "files_changed": files, "lines_added": added,
                     "lines_deleted": deleted, "agent_flag": flag, "agent_name": agent,
                     "heuristic": rule})
    return rows, None


def main():
    jobs = [(c.name, g) for c in sorted(CLONES.iterdir()) if c.is_dir()
            for g in sorted(c.glob("*.git")) if not g.name.startswith(".tmp_")]
    print(f"mining {len(jobs)} clones: " +
          ", ".join(f"{c} {sum(j[0] == c for j in jobs)}" for c in sorted({j[0] for j in jobs})))
    rows, errors = [], []
    with Pool(8) as pool:
        for r, err in pool.imap_unordered(mine, jobs, chunksize=4):
            rows.extend(r)
            if err:
                errors.append(err)
    df = pd.DataFrame(rows)
    df["author_date"] = pd.to_datetime(df["author_date"], utc=True)
    df = df.sort_values(["community", "repo", "author_date"]).reset_index(drop=True)
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(df)} commits")
    print(df.groupby("community").agg(commits=("sha", "size"), agent=("agent_flag", "sum"),
                                      repos=("repo", "nunique")).to_string())
    for e in errors:
        print("ERROR", e, file=sys.stderr)


if __name__ == "__main__":
    main()
