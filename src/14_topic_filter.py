"""Apply data/topic_exclusion_rules.md to the GitHub topic repo list.

Rules are plain string matches so the result is reproducible; see the rules file.
Input:  data/raw/github_topic/github_topic_repos.tsv, data/raw/bioc_release_VIEWS.txt
Output: data/raw/github_topic/topic_repos_included.tsv  (with a needs_check column)
        data/raw/github_topic/topic_repos_excluded.tsv  (with the rule that excluded it)
"""
import csv
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
read_views = importlib.import_module("02_list_bioc_packages").read_views

RAW = ROOT / "data" / "raw" / "github_topic"
IN = RAW / "github_topic_repos.tsv"
COMMUNITY_ORGS = {"nf-core", "bioconductor", "biopython"}
NOT_SOFTWARE = {"awesome", "course", "courses", "tutorial", "tutorials", "workshop", "workshops",
                "teaching", "lecture", "lectures", "notes", "book", "books", "cheatsheet",
                "learning", "roadmap", "interview"}
# "learning" and "book" also appear in descriptions of real tools ("deep learning",
# ":book:" emoji), so they are matched only in the repo name and topics.
DESC_IGNORE = {"learning", "book", "books"}
AI_TOPICS = {"ai-agent", "ai-agents", "agent", "agents", "agentic", "llm", "llms", "mcp",
             "mcp-server", "claude", "claude-code", "agent-skills", "ai-scientist"}
NOT_SOFTWARE_PHRASES = ("curated list", "list of resources")
BROAD = {"dna", "rna", "genome", "wgs", "sequencing"}
# Rule 4 (data/topic_exclusion_rules.md): repos removed by hand after a manual look, with the reason.
MANUAL = {"carpentries-incubator/bioc-project":
          "course material (Carpentries lesson), found in the topic validation sample"}
GH_URL = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def bioc_github_repos():
    repos = set()
    for rec in read_views(ROOT / "data" / "raw" / "bioc_release_VIEWS.txt"):
        for field in ("URL", "BugReports"):
            for owner, name in GH_URL.findall(rec.get(field, "")):
                name = re.sub(r"(\.git)?[.,;)]*$", "", name)
                repos.add(f"{owner}/{name}".lower())
    return repos


def words(text):
    return set(re.split(r"[^a-z0-9]+", text.lower()))


def main():
    bioc = bioc_github_repos()
    with open(IN, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    included, excluded = [], []
    for r in rows:
        repo = r["repo"].lower()
        topics = set(filter(None, r["all_topics"].lower().split(";")))
        if repo.split("/")[0] in COMMUNITY_ORGS or repo in bioc:
            excluded.append({**r, "excluded_by": "overlap"})
        elif repo in MANUAL:
            excluded.append({**r, "excluded_by": "manual"})
        elif ((words(r["repo"].split("/")[1]) | (words(r["description"]) - DESC_IGNORE) | topics) & NOT_SOFTWARE
              or any(p in r["description"].lower() for p in NOT_SOFTWARE_PHRASES)):
            excluded.append({**r, "excluded_by": "not_software"})
        elif topics & AI_TOPICS:
            excluded.append({**r, "excluded_by": "ai_topic"})
        else:
            checks = []
            if not r["language"]:
                checks.append("no_language")
            if set(r["matched_topics"].split(";")) <= BROAD:
                checks.append("broad_topics_only")
            included.append({**r, "needs_check": ";".join(checks)})

    for path, data, extra in ((RAW / "topic_repos_included.tsv", included, "needs_check"),
                              (RAW / "topic_repos_excluded.tsv", excluded, "excluded_by")):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + [extra], delimiter="\t",
                               lineterminator="\n")
            w.writeheader()
            w.writerows(data)

    by_rule = {}
    for r in excluded:
        by_rule[r["excluded_by"]] = by_rule.get(r["excluded_by"], 0) + 1
    flagged = sum(1 for r in included if r["needs_check"])
    print(f"{len(rows)} repos -> {len(included)} included ({flagged} flagged needs_check), "
          f"{len(excluded)} excluded {by_rule}")


if __name__ == "__main__":
    main()
