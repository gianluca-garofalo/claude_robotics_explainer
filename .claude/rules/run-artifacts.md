---
paths:
  - "runs/**"
  - "sources/**"
---

# Run folders

- Generated, never edited by hand (change the inputs and rerun the tool): `ranking.*` (tools/rank_topics.py),
  `selection.*` (tools/auto_select.py), `explainer.html` (tools/build_explainer.py from `draft/`), `code/logs/`
  (tools/run_code_checks.py), `review/summary.*` (tools/merge_reviews.py), `review/gates.*` (tools/gate.py),
  `review/package.md`, `review/design/` (the video checks' reports, frames and contact sheets),
  `video/*/*.layout.json` (layout_probe.py), `video/checks/`, `video/renders/`, `video/voice/manifest.json`,
  `video/final/`, `deliver/` (tools/deliver.py) and `publish/`.
- Never create or edit `approval.json` (the user's `/approve-topic`), `selection.json` (tools/auto_select.py),
  `episode.json` (tools/series.py) or `search.json` (tools/search_demand.py): AGENTS.md, Rules. `published.json` is a
  read-only copy of the channel ledger.
- Reviews live in `review/` (explainer), `review/video/`, `review/final_cut/` and `review/series_plan/`. Reviewers
  write only there; the writer never edits their files and records decisions in the folder's `resolutions.json`.
  `review/symbol_ledger.json` lists every symbol's meaning per section: fix the drafts from it.
- In a series run (`episode.json`), `explainer.html` and `code/` are copies of the source: never edit them. A source
  without companion code gives the run an empty `code/` (from `templates/run/`) for the episode's own scripts.
- `sources/` holds the series' source documents: read them, never modify them (a changed explainer needs a new series
  plan). `tools/run_code_checks.py sources/<name>` runs the scripts in a temporary copy; only `code/logs/` changes.
- `python3 tools/run.py status runs/<run>` tells you what is done, stale or next.
