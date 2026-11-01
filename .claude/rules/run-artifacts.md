---
paths:
  - "runs/**"
  - "sources/**"
---

# Run folders

- Generated files, never edited by hand: `ranking.md`/`ranking.json` (tools/rank_topics.py), `selection.json` and
  `selection.md` (tools/auto_select.py), `explainer.html` (tools/build_explainer.py from `draft/`), `code/logs/`
  (tools/run_code_checks.py), `review/summary.*` (tools/merge_reviews.py), `review/gates.*` (tools/gate.py),
  `review/package.md`, `video/checks/`, `video/renders/`, `video/voice/manifest.json`, `video/final/`, `deliver/`
  (tools/deliver.py) and `publish/` (render, narration, assembly and upload tools). Change the inputs and rerun the
  tool.
- `approval.json` is written only by the user's `/approve-topic` command (a hook), `selection.json` only by
  tools/auto_select.py, `episode.json` only by tools/series.py, `search.json` only by tools/search_demand.py. Never
  create or edit them, and never choose the topic yourself.
- `review/design/` (check_design.py, check_reading.py: reports, frames, contact sheets) and `video/*/*.layout.json`
  (layout_probe.py) are generated. The video design review lives in `review/video/` (reviewer report, `verify/`,
  `resolutions.json`, `summary.*` from `merge_reviews.py --set video`).
- In a series run (`episode.json`), `explainer.html` and `code/` are copies of the series' source: never edit them.
  Exception: a source without companion code gives the run an empty `code/` (from `templates/run/`), where the
  episode writes the scripts that print its numbers.
- `published.json` is a read-only copy of the channel ledger: topics in it were already covered.
- Reviewers write only under `review/`; the writer never edits reviewers' files (record decisions in
  `review/resolutions.json`). `review/symbol_ledger.json` (presentation-reviewer) lists every symbol's meaning in each
  section and every unannounced change: fix the drafts from it.
- `sources/` holds the source documents of the series (explainer, companion code, data): read them, never modify
  them (a change to an explainer's content needs a new series plan). `tools/run_code_checks.py sources/<name>` runs
  the scripts in a temporary copy: only `code/logs/` changes.
- `python3 tools/run.py status runs/<run>` tells you what is done, stale or next.
