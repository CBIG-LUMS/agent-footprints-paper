# Exclusion rules for GitHub topic repos


1. **overlap**: the repo belongs to one of the three studied communities. This means it is in the nf-core, Bioconductor or biopython GitHub org, or its URL is listed as a package URL/BugReports in the Bioconductor release VIEWS file (Bioconductor packages hosted on personal accounts, e.g. lpantano/DEGreport).
2. **not_software**: the repo is not software. This is decided by words in the repo name, description or topics:
   - awesome
   - course
   - tutorial
   - workshop
   - teaching
   - lecture
   - notes
   - book
   - cheatsheet
   - learning
   - roadmap
   - interview

   "learning" and "book(s)" count only in the repo name or topics, not in the description
   (descriptions of real tools say "deep learning"; one uses a :book: emoji). Checked 2026-11-02.
   Also excluded: descriptions containing the phrase "curated list" or "list of resources".
3. **ai_topic**: the repo is about AI agents or LLMs. This is decided by the topics:
   - ai-agent, ai-agents, agent, agents, agentic
   - llm, llms, mcp, mcp-server
   - claude, claude-code
   - agent-skills, ai-scientist
4. **manual**: removed by hand after a look at the repo (list in `MANUAL` in src/14_topic_filter.py).
   - carpentries-incubator/bioc-project: course material (a Carpentries lesson); the name and description
     have none of the rule-2 words. Found in the topic validation sample.

