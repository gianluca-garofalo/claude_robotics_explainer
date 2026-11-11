# Remaining Action pipeline

Turns a source explainer (`sources/<name>/`) or robotics news into narrated Manim videos for the YouTube channel
Remaining Action, one run folder per video. People read README.md.

- Entry points, typed by the user: `/produce-from-source sources/<name> [n]` (plans the source's series if needed,
  makes one episode, finishes it up to `runs/<run>/deliver/`), `/produce-episode series/<slug> <n|next>`,
  `/produce-explainer [focus]`. Outside GitHub Actions `finish-video` renders, reviews and packages; the optional
  workflow (SETUP-AUTOMATION.md) runs the same skills.
- Skills: `.agents/skills/<name>/SKILL.md`; `/<name> args` means: follow that file with those arguments. A skill with
  `disable-model-invocation: true` runs only when the user asks for it.
- Reviewers: `.claude/agents/<name>.md`. Without named subagents, give that file's body as the prompt to a fresh
  context or a general-purpose subagent; with neither, follow the skill's "Without subagents" section.
- Read `.claude/rules/manim-scenes.md` before editing scenes, `.claude/rules/run-artifacts.md` before touching run or
  source folders.

## Commands

`python3 tools/<x>.py` runs under `.venv` once `bash setup.sh` has made it. Every tool has `--help`.

- Setup: `bash setup.sh` (`--check`: prerequisites only).
- Runs: `python3 tools/run.py status runs/<run>` (also `new [--window-days N] [--root DIR]`, `finalize`, `package`);
  `python3 tools/validate.py <run>` (any folder); `python3 tools/coverage.py <run>`.
- News: `python3 tools/search_demand.py runs/<run>`, then `tools/rank_topics.py`, then `tools/auto_select.py`.
- Explainer: `python3 tools/build_explainer.py runs/<run> --strict`; `python3 tools/lint_html.py FILE`; `node
  tools/check_html.js FILE` (1400 and 390 px); `python3 tools/explainer_text.py FILE --outline|--section N|--until N`;
  `python3 tools/html_features.py reinject FILE` (refreshes injected CSS and scripts; `--write` applies); `python3
  tools/run_code_checks.py runs/<run>`.
- Reviews: `python3 tools/merge_reviews.py runs/<run>` (`--set video`: the video review).
- Video drafts: `bash tools/render_video.sh runs/<run> --check`, then `check_design.py`, `check_reading.py`,
  `check_selfcontained.py`, `check_numbers.py`, `check_series.py`, `check_engagement.py` and `check_sync.py`
  (warnings first) and `check_script.py` (report only) from `tools/video/`, each with `runs/<run> --stage draft`.
- Voice: `voice.service` in `config/channel.json`: `azure` (the channel voice, Steffan HD,
  `en-US-Steffan:DragonHDLatestNeural`, -8 %; `AZURE_SUBSCRIPTION_KEY` and `AZURE_SERVICE_REGION` in the environment,
  never in a file), `piper` (keyless), `recorded`, `silent`. Drafts are silent; a final render whose voice fails
  stops: there is no fallback voice.
- Sources and series: `python3 tools/check_source.py sources/<name>` (errors stop; warnings go into the report);
  `python3 tools/series.py from-source sources/<name>` (release order), `list|next|validate|start series/<slug>`
  (`start --fresh`: without kept scenes); `/plan-series <run or sources/<name>>` (`series.py plan|write`).
- Gates: `python3 tools/gate.py runs/<run> --stage pre-render|final|release` (final and release: `finish-video` in a
  session, CI with the workflow); `/final-cut-review runs/<run>` before release; `python3 tools/deliver.py
  runs/<run>`.
- Tests: `python3 -m unittest discover -s tests`, `python3 tests/dry_run.py`, `python3 tests/automation_dry_run.py`,
  `python3 tools/lint_project.py`.

## Rules

- Nothing is published from the agent: no push, release, PR, upload, post or stream. The owner uploads `deliver/` by
  hand, or the workflow's `publish` job publishes after the owner approves there. Never approve, label, re-run or
  configure that workflow (`gh issue edit`, `gh api`, `gh variable`, `gh secret` are off limits).
- Topic choice: `topic_approval` in `config/pipeline.json` is `auto` (`tools/auto_select.py` writes `selection.json`)
  or `human` (the user types `/approve-topic`; a hook writes `approval.json`); `tools/series.py start` picks a series
  episode (`episode.json`). Never pick a topic, create or edit these files or `search.json`, or start writing without
  one.
- The owner's files, never edited: `config/`, `series/` (plans enter only through `tools/series.py write`; only the
  owner approves one, when `series.plan_approval` asks), `sources/`, `tools/hooks/`, `tools/human/`,
  `tools/publish/`, `tools/ci/`, `.github/`, `ci/`. During a run also leave `tools/`, `templates/` and `docker/`.

## Conventions

- Every number, table value and figure in an explainer is printed by a script in `code/`: copy from `code/logs/`,
  never from memory. The gate re-runs the scripts on a clean checkout.
- Generated, never edited: `explainer.html`, `ranking.*`, `selection.*`, `review/summary.*`, `review/gates.*`,
  `video/checks/`, `video/renders/`, `video/final/`.
- References: only details seen in a record during the run; never infer a DOI; mark secondary-only confirmations.
- Original figures, animations and sound; nothing copied; attribute every source. Music only from
  `tools/video/music.py`, per scene (`plan.json` `music`: `bed` in the hook, title beat and outro, `low` or `off`
  under explanation).
- One moving world, not slides: the picture moves while the narration talks (looping emphasis is not motion);
  derivations are transforms, one colour per quantity; objects carry across cuts; the meter only falls (a refill is
  declared in `plan.json` `metaphor_resets` and said aloud); numbers only on pictures drawn to scale (`plan.json`
  scenes[].picture); no persistent slide titles; narration in meanings (`check_engagement.py`). Reviewers score
  motivation, clarity, novelty, memorability.
- Pacing follows from the ideas: budgets in `series.json` and `plan.json` `ideas`, planned pauses `[pause S]`,
  `[slow]` (`check_pacing.py`). Cut scope in the plan; never speed up the voice.
- Reviewers write only under `review/`; the writer fixes and records decisions in `review/resolutions.json`.
- "Remaining Action" appears on the outro (`outro()`) and the thumbnail only; thumbnail and metadata come from tools.
- Self-contained videos: no text, narration, caption or chapter refers to the explainer, code, files, data, links or
  the description; no equation labels ((13), "Eq. 3"; `equation_numbers` in `config/video.json`). Nothing names the
  publication a video covers or its authors ("the paper", "the authors", a preprint): the result on its own terms,
  caveats as facts about the evidence ("so far only in simulation"); the description credits them. Other episodes by
  title or meaning only (series context, recaps, outro, or a result shown here), never by equation number or as
  required viewing. Show an equation again or name its meaning; numbers through `fmt()`; chapters are the plan's
  titles; explainer and code links only in the description, when links are on.
- Hook: a full, moving picture from the first frame, music from 0 s, narration by 3 s, the question by 15 s, then the
  stakes, the body by 45 s; no channel card (a 4-6 s title beat with the "Episode n of N" lower third is allowed).
  Outro: 15-20 s, takeaway card, channel name, teaser, the end-screen area empty.
- Packaging: a title of at most 60 characters with `plan.json` `search_term`, not the series name; a thumbnail of at
  most three words whose picture is in the hook's first 15 s (`layout: picture`).
- `series.plan_approval` `optional`: `start` notes it and goes on; `required`: `start` refuses an unapproved plan. The
  owner approves the finished video.

## Gotchas

- `check_html.js` needs `npm install` and `npx playwright install chromium`; `--offline` serves KaTeX 0.16.9 from
  `node_modules/` and refuses every other request.
- Manim: live numbers with `readout()`, never a `MathTex` inside `always_redraw`. Voice-over text is a string literal:
  CI synthesizes it from the parsed scene files. Scenes derive from `RAScene`, which holds text until it can be read;
  design errors (overlaps, safe areas, contrast, colour-blind pairs) fail the gate.

## Changing the pipeline

- Run "Tests" and `python3 tools/check_source.py --all`; CI adds actionlint and shellcheck. After an HTML template or
  CSS change, also `node tools/check_html.js` on a source and on the build `python3 tests/dry_run.py --keep` leaves.
- Tests are hermetic: `tests/fixtures/`, never `sources/`, `series/`, `config/` or wording. Each test module calls
  `testenv.activate()` before importing a tool; other preferences go through `testenv.variant()` and `testenv.env()`.
  Only `tests/test_sources_smoke.py` reads `sources/`; `tests/test_hermetic.py` enforces this. Test behaviour, not
  wording or copied constants; a skill or agent file only for its frontmatter, hooks and the names it cites. Change a
  fixture with its tests.
- Documents: shell blocks paste into zsh and bash (no comments, `<placeholders>` or unquoted `[ ] * ?`). No secrets,
  e-mail addresses, absolute paths or model identifiers anywhere; large binaries go to Git LFS or release assets.
- Rules for changing the owner's files (automation, hooks, `config/`): CONTRIBUTING.md.
- A skill: one job; `description` says when to use it; `SKILL.md` under 500 lines (inputs, outputs, the checks that
  define done, Gotchas with fixes), detail in linked files beside it, only what an agent cannot know; deterministic
  steps in a `tools/` script (`--help`, exit status, standard library where possible). Side effects or a human
  decision: `disable-model-invocation: true`. No `model` field in skills, agents or workflows.
- A reviewer: fresh context, read-mostly tools, the write guard hook, the format of
  `.agents/skills/explainer-review/reviewer-contract.md`, never the writer's reasoning. A new review dimension: the
  agent, a line in the explainer-review skill and `.claude/workflows/review-fanout.js`, its id prefix in
  `tools/validate.py` (`ID_PREFIX`), its name in `tools/gate.py` (`REVIEWERS`), a report in
  `tests/fixtures/run/review/`. A video reviewer: the same, but a line in the design-review step of
  `manim-video-producer` or in `final-cut-review`, its name in `VIDEO_REVIEWERS` and a report in
  `tests/fixtures/run/review/video/` or `final_cut/`. A new design check: a fixture from a real render in
  `tests/fixtures/design/`.
