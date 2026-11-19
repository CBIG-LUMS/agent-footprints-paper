# AI Coding Agent Footprints in Bioinformatics Repositories

Code and data for the paper "AI Coding Agent Footprints in Bioinformatics Repositories".
We mine all commits since January 2024 of Bioconductor, nf-core and Biopython, flag commits with a visible
AI coding agent trace, and compare them with 2,317 GitHub repositories tagged with a bioinformatics topic.

- `src` contains the scripts, numbered in the order they run
- `data` contains the mined commits, the hand labels, the input lists and the result tables
- `notes` contains hand-checked commits, the ones the detection rules miss and the co-authored commits of nf-core-bot that we kept as bots
- `figures` contains Fig. 1
- `heuristics.yaml` is the list of detection rules; `local_rules.yaml` holds the rules we added to those of Robbes et al.

## Setup

Requires conda (Python 3.11, pandas, pyarrow, matplotlib, pyyaml).

    conda env create -f environment.yml -n footprints-paper
    conda activate footprints-paper

On a system other than Linux, create the environment by hand:

    conda create -n footprints-paper -c conda-forge python=3.11 pandas=3.1.0 pyarrow=25.0.0 matplotlib=3.11.2 pyyaml=6.0.3

## Reproducing the paper's results

This uses the mined data in `data` and takes about a minute:

    python src/10_results.py
    python src/11_figure_monthly.py
    python src/12_summary.py > data/results/summary.txt

`10_results.py` writes the tables in `data/results` (Tables I and II, monthly shares, policy windows, top
repositories, agents). `11_figure_monthly.py` draws `figures/monthly_share.pdf`. `12_summary.py` prints
the remaining numbers (repository counts, Assisted-by lines, AGENTS.md dates, Biopython pull requests,
validation, comparison group, RQ3 / Table III for both samples), each with the file it comes from.

## Running the whole study

This clones every repository again (several hours, about 30 GB) and needs git and the GitHub CLI
(`gh auth login`). The clone scripts can be rerun to resume after a failure.

    python src/02_list_bioc_packages.py      # Bioconductor package list
    bash src/03_clone_bioconductor.sh        # 2,418 packages
    bash src/04_clone_nfcore.sh              # nf-core pipelines, default and dev branches
    bash src/05_clone_biopython.sh           # Biopython and its pull requests
    python src/06_mine_commits.py            # -> data/commits.parquet
    python src/07_context_files.py           # -> data/repos.csv
    python src/13_topic_search.py            # comparison group (uses the saved search in data/raw/github_topic)
    python src/14_topic_filter.py
    bash src/15_clone_topic.sh
    python src/16_mine_topic.py              # -> data/results/topic_*.csv

then the three commands above. Repositories keep changing, so a new run also finds commits made after our
mining date (30 October to 3 November 2026) and gives slightly higher counts.

`01_build_heuristics.py` rebuilds `heuristics.yaml`. It needs the pattern files of Robbes et al., which are not
included here:

    mkdir -p third_party/robbes_agent_impact && cd third_party/robbes_agent_impact
    C=69b95b6d92f19adaee7d2720ccf81dd00a205cbf
    for f in authors bots branches labels files; do
      curl -sfLO https://raw.githubusercontent.com/labri-progress/agent-impact/$C/config/patterns/$f.csv
    done
    cd ../..
    python src/01_build_heuristics.py

The samples that were labelled by hand were drawn once by `08_validation_sample.py`, `09_rq3_sample.py` and
`17_topic_samples.py`; these scripts do not overwrite labelled files.

## Data

- `commits.parquet`: one row per commit since 2024, with the agent flag and the rule that fired
- `repos.csv`: AI context files per repository
- `policy_dates.csv`: proposal and effective date of each community's AI policy, with sources
- `validation.csv`, `topic_validation.csv`: precision checks
- `labels_all.csv`: RQ3 labels for 250 agent commits from Bioconductor, nf-core and Biopython
- `topic_labels.csv`: the same labels for 100 agent commits from the comparison group (73 repositories, at most two per repository)
- `topic_needs_check.csv`, `bio_keywords.txt`, `topic_exclusion_rules.md`: comparison group selection
- `raw`: package and repository lists, saved GitHub search results, Biopython pull requests
- `results`: the tables behind the paper

Both label files use the same columns. `change_type` is one of bug fix, feature, refactor, docs, tests, CI/config
and dependency. `touches_scientific_logic` is yes or no. `risk_category` is statistics, file-format parsing,
coordinates, genome build/annotation version, numerical precision or other, and none when the commit does not
touch scientific logic. `tests` says whether tests were added, modified or left out. `concern` is none, possible
or likely. `concern_note` is a sentence on how the commit went in and what happened later. `github_commit` and
`pr_link` point to the commit and its pull request, or say that it was pushed directly. In `topic_labels.csv`,
`risk_in_other_risk_category` names the topic of each change labelled other. We set all labels by hand from the
diff, the pull request and the later history of the files, and a second author checked them.

Developer names and emails are replaced by ids (`dev_xxxxxxxx`) in `commits.parquet`, the validation files and
`notes`; agent and bot accounts are kept as they are. `raw/bioc_release_VIEWS.txt` and `raw/biopython_prs.json`
keep only the fields the scripts use. The first RQ3 sample (ids 1-50) was drawn from an earlier version of the
commit table and cannot be redrawn exactly; the second (ids 51-250) can. The clones and the comparison group's
commit table (110 MB) are not included.

## Credits

Detection patterns come from Robbes et al., "Agentic Much? Adoption of Coding Agents on GitHub"
(https://arxiv.org/abs/2601.18341), https://github.com/labri-progress/agent-impact (commit 69b95b6).
