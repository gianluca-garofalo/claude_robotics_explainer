---
paths:
  - "tools/**"
  - "tests/**"
  - ".claude/**"
  - ".agents/**"
  - "schemas/**"
  - ".github/**"
---

# Changing the pipeline

For whoever changes the tools, tests, agents, skills, schemas or CI (AGENTS.md points here); a run never does.

- Run the tests (AGENTS.md, Commands, Tests) and `python3 tools/check_source.py --all`; CI adds actionlint and
  shellcheck. After an HTML template or CSS change, also `node tools/check_html.js` on a source and on the build
  `python3 tests/dry_run.py --keep` leaves.
- Tests are hermetic: `tests/fixtures/`, never `sources/`, `series/`, `config/` or wording. Each test module calls
  `testenv.activate()` before importing a tool; other preferences go through `testenv.variant()` and `testenv.env()`.
  Only `tests/test_sources_smoke.py` reads `sources/`; `tests/test_hermetic.py` enforces this. Test behaviour, not
  wording or copied constants; a skill or agent file only for its frontmatter, hooks and the names it cites. Change a
  fixture with its tests.
- Documents: shell blocks paste into zsh and bash (no comments, `<placeholders>` or unquoted `[ ] * ?`). No secrets,
  e-mail addresses, absolute paths or model identifiers anywhere; large binaries go to Git LFS or release assets.
- Rules for changing the owner's files (automation, hooks, `config/`): CONTRIBUTING.md.
- A skill: one job; `description` starts with when to use it (about 300 characters at most); `SKILL.md` under 500
  lines (inputs, outputs, the checks that define done, Gotchas with fixes), detail in linked files beside it, only what
  an agent cannot know; deterministic steps in a `tools/` script (`--help`, exit status, standard library where
  possible). Side effects or a human decision: `disable-model-invocation: true`. No `model` field in skills, agents or
  workflows.
- An agent: `description` starts with when to use it, about 300 characters at most. A purely mechanical one (like
  `review-runner`) gets `effort: low`, only the tools it needs and `omitClaudeMd: true`.
- A reviewer: fresh context, read-mostly tools, the format of `.agents/skills/explainer-review/reviewer-contract.md`,
  the explainer read as text (`tools/explainer_text.py`), never the writer's reasoning; in its frontmatter the write
  guard (`tools/hooks/reviewer_write_guard.py`, PreToolUse) and the report check
  (`tools/hooks/reviewer_report_check.py`, Stop); with WebFetch, also the fetch guard
  (`tools/hooks/reviewer_fetch_guard.py`, PreToolUse on `WebFetch|Bash`).
  A new review dimension: the agent, a line in the explainer-review skill, its id prefix in `tools/validate.py`
  (`ID_PREFIX`), its name in `tools/gate.py` (`REVIEWERS`), a report in `tests/fixtures/run/review/`. A video
  reviewer: the same, but a line in the design-review step of `manim-video-producer` or in `final-cut-review`, its
  name in `VIDEO_REVIEWERS` and a report in `tests/fixtures/run/review/video/` or `final_cut/`. A new design check: a
  fixture from a real render in `tests/fixtures/design/`.
- The review workflow, `.claude/workflows/review-fanout.js`: one script for every review set. It gets the run, the set
  and the set's reviewers as args (`tools/merge_reviews.py --workflow-args`, from `tools/gate.py`), never a list of its
  own; a workflow script has no shell, so its commands run through the `review-runner` agent. `tests/dry_run.py` runs
  it with stub agents on two sets.
