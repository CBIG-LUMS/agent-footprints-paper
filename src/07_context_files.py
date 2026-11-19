"""Agent context files per repo -> data/repos.csv.

One row per repo. Columns: community, repo, has_context_file, then one column per file type holding the author date
of the first commit (default branch, since 2024-01-01) that added it; empty if never added.
"<2024-01-01" means the file was already in the shallow boundary commit (added before the window).
has_context_file is True if any listed file exists at HEAD (or on dev, where 04_clone_nfcore.sh fetched it).
First-seen dates search the default branch and dev together.
"""
import csv
import subprocess
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONES = ROOT / "data" / "clones"
OUT = ROOT / "data" / "repos.csv"
# column name -> git pathspec (repo root, as in Robbes et al. file rules)
FILES = {
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "CLAUDE.md",
    "GEMINI.md": "GEMINI.md",
    ".cursorrules": ".cursorrules",
    ".cursor/rules/": ".cursor/rules/",
    ".github/copilot-instructions.md": ".github/copilot-instructions.md",
}  # the six context files searched in the paper


def repo_name(community, git_dir):  # same as 06_mine_commits.py
    name = git_dir.name.removesuffix(".git")
    return f"{community}/{name}" if community in ("biopython", "nf-core") else name


def git(git_dir, *args):
    return subprocess.run(["git", "-C", str(git_dir), *args], capture_output=True, text=True,
                          errors="replace").stdout


def revs(git_dir):
    """Same as 06_mine_commits.py: default branch plus dev when 04_clone_nfcore.sh added it; git log lists each commit once."""
    has_dev = subprocess.run(["git", "-C", str(git_dir), "rev-parse", "-q", "--verify", "refs/heads/dev"],
                             capture_output=True).returncode == 0
    return ["HEAD", "dev"] if has_dev else ["HEAD"]


def scan(args):
    community, git_dir = args
    shallow = set(git(git_dir, "rev-parse", "--shallow").split())  # empty if not shallow
    at_head = [l for rev in revs(git_dir)
               for l in git(git_dir, "ls-tree", "-r", "--name-only", rev, "--", *FILES.values()).split("\n")]
    row = {"community": community, "repo": repo_name(community, git_dir),
           "has_context_file": any(l for l in at_head)}
    # oldest first; each record: sha, date, then the added paths (--no-renames: a rename counts as an add)
    log = git(git_dir, "log", "--reverse", "--no-renames", "--diff-filter=A", "--format=%x1e%H %aI",
              "--name-only", *revs(git_dir), "--", *FILES.values())
    for col, spec in FILES.items():
        row[col] = ""
        for rec in log.split("\x1e")[1:]:
            head, *paths = rec.strip().split("\n")
            if any(p == spec or (spec.endswith("/") and p.startswith(spec)) for p in paths):
                sha, date = head.split()
                row[col] = "<2024-01-01" if sha in shallow else date[:10]
                break
    return row


def main():
    jobs = [(c.name, g) for c in sorted(CLONES.iterdir()) if c.is_dir()
            for g in sorted(c.glob("*.git")) if not g.name.startswith(".tmp_")]
    with Pool(8) as pool:
        rows = pool.map(scan, jobs, chunksize=8)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["community", "repo", "has_context_file", *FILES],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} repos")
    for comm in sorted({r["community"] for r in rows}):
        rs = [r for r in rows if r["community"] == comm]
        ever = sum(any(r[c] for c in FILES) for r in rs)
        print(f"  {comm}: {sum(r['has_context_file'] for r in rs)} with a context file at HEAD, "
              f"{ever} ever added since 2024 (of {len(rs)})")


if __name__ == "__main__":
    main()
