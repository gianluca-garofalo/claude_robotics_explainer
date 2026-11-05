# Remaining Action explainer pipeline

Turns a source explainer (or robotics news) into narrated Manim videos for the Remaining Action channel, one run
folder per video. Entry points: `/produce-from-source sources/<name> [n]` (plans the source's series when none exists,
then makes one episode and finishes it in the session up to `deliver/`, which the owner uploads by hand),
`/produce-episode series/<series> <n|next>`, `/produce-explainer [focus]`. Outside GitHub Actions the `finish-video`
skill renders, reviews and packages; the optional GitHub workflow runs the same skills unattended. README.md has the
map, CLOUD-SESSION.md the cloud environment, SETUP-AUTOMATION.md the optional automation.

## Commands

- Setup, or check prerequisites only: `bash setup.sh`, `bash setup.sh --check` (people type `./setup.sh`; the
  `bash` form is the one the allow rules match, here and for `bash tools/render_video.sh`)
- Python with the scientific stack, Manim and manim-voiceover: `.venv/bin/python`; the tools also run with `python3`
- Run state and next step: `python3 tools/run.py status runs/<run>` (also `new [--window-days N] [--root DIR]`,
  `finalize`, `package`); coverage of the channel (ledger, sources, series): `python3 tools/coverage.py <run>`
- Validate run JSON (any run folder, also outside runs/): `python3 tools/validate.py <run>`; search data:
  `python3 tools/search_demand.py runs/<run>`;
  ranking: `python3 tools/rank_topics.py runs/<run>`
- Automatic topic selection (deterministic, logged): `python3 tools/auto_select.py runs/<run>`
- Build the explainer from `draft/`: `python3 tools/build_explainer.py runs/<run> --strict`
- HTML checks: `python3 tools/lint_html.py FILE` (static); `node tools/check_html.js FILE` (render, 1400 and 390 px);
  the page in reading order, one section at a time: `python3 tools/explainer_text.py FILE --outline|--section N|--until N`;
  refresh the injected reader-features CSS and scripts of a built page: `python3 tools/html_features.py reinject FILE`
  (dry run; `--write` to apply)
- Companion code: `.venv/bin/python tools/run_code_checks.py runs/<run>`; merge reviews: `tools/merge_reviews.py`
- Video drafts: `bash tools/render_video.sh runs/<run> --check` (-ql, silent, layout logs); design
  and reading time: `python3 tools/video/check_design.py runs/<run> --stage draft`, `python3
  tools/video/check_reading.py runs/<run> --stage draft`, `python3 tools/video/check_selfcontained.py runs/<run>`,
  `check_numbers.py`, `check_series.py`, `check_engagement.py` (motion budget, transforms, narration, text; warnings
  first);
  video review merge: `python3 tools/merge_reviews.py runs/<run> --set video`; voice: one setting, `voice.service` in
  `config/channel.json` (piper, the voice of final renders | azure | recorded | silent); drafts are silent, and a final
  render without the Piper model stops (`./setup.sh` downloads it): there is no fallback voice
- Series: `python3 tools/series.py from-source sources/<name>` (a source's series in release order),
  `list|next|validate|start series/<series>` (`start --fresh`: leave out kept scenes); planning: `/plan-series
  <explainer run or sources/<name>>` (`tools/series.py plan|write`). Sources are `sources/<name>/` (explainer.html,
  code/ and data/ when they exist); `series/` holds only plans made from them. Check a source first:
  `python3 tools/check_source.py sources/<name>` (errors stop; warnings go into the report)
- Final-cut review of an assembled video: `/final-cut-review runs/<run>` (`tools/video/final_frames.py`), then
  `python3 tools/gate.py runs/<run> --stage release`; hand-over package: `python3 tools/deliver.py runs/<run>`
- Gates: `python3 tools/gate.py runs/<run> --stage pre-render|final|release` (a session runs final and release in
  `finish-video`; with the workflow, CI does)
- Tests: `python3 -m unittest discover -s tests`, `python3 tests/dry_run.py`, `python3 tests/automation_dry_run.py`
  (they use only `tests/fixtures/`; CONTRIBUTING.md, Testing); config and CI lint: `python3 tools/lint_project.py`

## Rules with no exceptions (enforced by settings, hooks and the CI job boundaries)

- Nothing is published from Claude Code: no push, release, PR, upload, post or stream. The owner uploads the files
  of `deliver/` by hand, or the GitHub workflow's `publish` job publishes after the owner approves there. Never try to
  approve, label, re-run or configure that workflow (`gh issue edit`, `gh api`, `gh variable`, `gh secret` are off
  limits).
- Topic choice: `config/pipeline.json` `topic_approval` is `auto` (tools/auto_select.py picks by a fixed rule and
  writes `selection.json`) or `human` (the user types `/approve-topic`; a hook writes `approval.json`); a series
  episode is chosen with `tools/series.py start` (`episode.json`). Never pick a topic yourself, never create or edit
  these files or `search.json`, and never start writing without one of them.
- `config/` holds the user's preferences (rubric, scout, search, pipeline, channel, video), `series/` the series
  plans and `sources/` their source documents: read them, do not edit them (a new plan goes there only through
  `tools/series.py write`; only the owner approves plans, when `series.plan_approval` asks for it). Do not edit
  `tools/`, `templates/`, `.github/`, `ci/` or `docker/` during a run.

## Conventions

- Every number, table value and figure in an explainer is printed by a script in the run's `code/`; copy values from
  `code/logs/`, never from memory. The gate job re-runs the scripts on a clean checkout: output must be reproducible.
- `explainer.html`, `ranking.*`, `selection.*`, `review/summary.*`, `review/gates.*` and everything under
  `video/checks/`, `video/renders/`, `video/final/` are generated: change inputs, rerun the tool.
- References carry only details seen in a record during the run; never infer a DOI; mark secondary-only confirmations.
- Original figures, animations and sound only; no copied text, images, footage, logos or music; attribute every
  source. Music is generated by `tools/video/music.py` (seeded, reproducible, stamped in `video/final/music.json`;
  the gate checks the stamp), per scene (`plan.json` `music`: `bed` in the hook, title beat and outro, `low` or `off`
  under explanation), mixed by `assemble.py` to -14 LUFS with the true peak at most -1 dBTP after encoding.
- One moving world, not a slide deck: the picture's content moves while the narration talks (emphasis alone, pulsing
  or looping borders, is not motion), derivations are transforms with
  one colour per quantity, objects carry across cuts, the meter only falls along the path (a refill is declared in
  `plan.json` `metaphor_resets` and said aloud as it happens), numbers only on pictures drawn to scale (`plan.json`
  scenes[].picture), no persistent slide titles, narration in meanings
  (`tools/video/check_engagement.py`, thresholds in `config/video.json` "engagement"; reviewers score the SoME rubric:
  motivation, clarity, novelty, memorability).
- Reviewers report and write only under `review/`; the writer fixes and records decisions in `review/resolutions.json`.
- Branding is "Remaining Action" (`config/channel.json`): the name appears on the outro (`outro()`) and the thumbnail
  only; thumbnail and metadata come from the tools.
- Videos are self-contained: nothing on screen, in narration, captions or chapters refers to the explainer, code,
  files, data, links or the description, and no equation carries a label or tag ((13), (2), (★), "Eq. 3";
  `equation_numbers` in `config/video.json`). Other episodes of a series: by title or meaning only, in the series
  context, recaps and outro, or in the body when their result is shown in this video; never by equation number, never
  "you must have watched". Show an equation again or name it by its meaning; numbers through `fmt()`. Chapters are the
  plan's own titles. Links to the explainer and code go only in the description, and only when links are on.
- Every video opens with its hook: a full, moving picture from the first frame, music from 0 s, narration by 3 s, the
  question by 15 s, then the stakes; no channel card (a title beat of about 4-6 s after the hook, with the "Episode n
  of N" lower third, is allowed); the body by 45 s. It ends with a 15-20 s outro (takeaway card, channel name, teaser,
  the end-screen area empty). Packaging: a title of at most 60 characters with the search term (`plan.json`
  `search_term`), not the series name; a thumbnail of at most three words whose picture appears in the hook's first 15
  s (`layout: picture` puts the frame first). Series are planned with `/plan-series`; plan approval follows
  `config/pipeline.json` `series.plan_approval` (`optional`: `start` notes it and goes on; `required`: `start` refuses
  an unapproved plan). The owner approves the finished video.

## Gotchas

- Project hooks and allow rules apply only after the workspace trust dialog has been accepted.
- `check_html.js` needs `npm install` (and `npx playwright install chromium`); with `--offline` it serves KaTeX 0.16.9
  from `node_modules/` and refuses every other request.
- Manim: live numbers with `readout()` (Pango Text), never a `MathTex` inside `always_redraw`. Voice-over text must be
  a string literal: CI synthesizes the narration from the parsed scene files. Scenes derive from `RAScene`, which holds
  text until it can be read; design errors (overlaps, safe areas, contrast, colour-blind pairs) fail the gate.
