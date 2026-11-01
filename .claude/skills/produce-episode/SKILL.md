---
name: produce-episode
description: Series mode - makes one narrated episode of a video series (schema 2, in series/) from its source explainer - no scouting, ranking or writing - with the series beats (hook from 0 s, spoken series context over the builds-on frame, recaps of what it uses, outro with takeaway card and teaser), the design, number, reading-time and self-contained checks and the video design review, then the pre-render gates; outside GitHub Actions it finishes the video in the session (finish-video) up to the hand-over package for the owner's own upload. Only when the user types /produce-episode (or /produce-from-source follows it).
argument-hint: "series/<series> <episode number | next> [fresh] | resume runs/<run>"
disable-model-invocation: true
---

# Produce a series episode

Arguments: `$ARGUMENTS`. Series are planned with `/plan-series` (or by `/produce-from-source`, which then runs this
procedure); `python3 tools/series.py list series/<series>` shows the episodes, their prerequisites and the plan's
approval state, and `python3 tools/series.py from-source sources/<name>` the series of a source in release order.

## Stages

1. **Start.** `python3 tools/series.py start series/<series> --episode <n|next>` prints the run path (or use the run
   given with `resume`). Plan approval follows `config/pipeline.json` `series.plan_approval`: with `optional` (the
   owner's setting since 2026-11-01) it prints an informational note and starts from the plan as written; with
   `required` it refuses a plan the owner has not approved, or one changed since (the owner approves it with
   `./tools/human/approve_series.py series/<series>`; never Claude). `next` follows the plan's release order, skips
   episodes delivered in `runs/` and waits for prerequisites in another series. It copies the source's explainer and
   `code/` unchanged (a source without `code/`: an empty one from `templates/run/` for the episode's own scripts)
   and its `data/` as `video/data/`, the scene helpers, `video/episode.md` (the brief from the plan and the house
   rules), `video/series_context.json` (episode n of N, what it builds on, the takeaway and recap cards, the teaser)
   and `episode.json`, plus the episode's kept scenes when `series/<series>/episodes/epNN/scenes/` holds any (an
   episode made again after a fix; with `fresh` in the arguments add `--fresh` to leave them out). Never edit
   `explainer.html`, `episode.json` or `series_context.json`.
2. **Read.** `video/episode.md`, the explainer sections it lists as sources (`material.section_ids`: sources, not a
   mapping), the companion scripts that make the numbers, and the kept scenes if there are any.
3. **Scenes.** Invoke the `manim-video-producer` skill on the run. The episode tells its own story with the material
   the plan selected (kept scenes, when there are any, are a starting point). Build the series beats with the helpers
   in `common.py`:
   - the hook first, narration from 0 s (no channel card anywhere);
   - the series context at the first natural break (about 30-90 s): one or two spoken sentences (where this episode
     sits, what it builds on, a welcome for viewers joining here) over `builds_on()` for 4-6 s;
   - one recap scene per must prerequisite: `recap_tag()` for the whole scene, `recap_card(i)` (the earlier
     episode's card, from the same data as its own outro), the restatement by meaning, at most a soft pointer by title;
   - the outro (15-20 s): `outro(takeaway_card(), next_title=...)`, the spoken "In the next episode, ..." (none in the
     finale), nothing in the right ~40 % of the frame (end screen).
4. **Plan.** `video/plan.json`: title (the episode title; the series goes in the description), summary, tags, one
   entry per scene with `section` (a source; context and outro may omit it), `chapter`, `role` (`hook`, `context`,
   `recap` with `recap_of`, `body`, `outro`), thumbnail. Recap chapters start with "Recap".
5. **Checks and design review** are part of `manim-video-producer` (draft renders, `check_design.py`,
   `check_reading.py`, `check_numbers.py`, `check_selfcontained.py`, `check_series.py`, the `video-design-reviewer`
   subagent, finding verification, `merge_reviews.py --set video`).
6. **Gates.** `.venv/bin/python tools/run_code_checks.py runs/<run>`, then `python3 tools/gate.py runs/<run> --stage
   pre-render` must pass (it also checks the plan: approved when approval is required, unchanged since the start).
7. **Finish.** In GitHub Actions (`$GITHUB_ACTIONS` is `true`) stop here: the workflow renders, assembles, has the
   final cut reviewed, uploads privately and asks the owner. Anywhere else (a cloud or local session) invoke the
   `finish-video` skill on the run: Piper narration, the 1080p render, assembly, thumbnail and metadata, the final
   gates, the final-cut review, the release gate, fixes for blockers, and `tools/deliver.py`, whose `deliver/` folder
   goes to the owner with the session's file-sending tool.
8. **Close.** Final report: run path, episode, what changed in the scenes and why, gate results, open findings, and
   outside CI the files handed over and the next episode (`python3 tools/series.py next series/<series>`).

## Gotchas

- Series runs reuse the published explainer: the explainer-level gates (lint, reviews, references) are not repeated,
  but the companion code is re-run, so every number on screen must still come from `code/` or `video/data/`.
- Numbers: when the source has companion code, a series run cannot add an export script to `code/` (it must stay
  the source's copy). Read values from the companion scripts and their logs in `code/logs/`, or compute the
  explainer's closed forms in the scene. When the source has no companion code, `code/` starts empty (from
  `templates/run/`): write the scripts that print the episode's numbers there, list them in `code/checks.toml`,
  describe them in `code/README.md` and run them; never type a number from the page or from memory. Format every
  number with `fmt()` (readouts with fixed decimals: `readout(label, value, decimals=k)`).
- Voice: draft renders are silent; final renders use Piper, `voice.service` in `config/channel.json`, whose model the
  CI image holds (a session: `./setup.sh` downloads it, which needs huggingface.co and hf.co). A final render
  without the model stops with that instruction: there is no fallback voice.
- Other episodes: by title or meaning, and only when their result is shown in this video (a recap); never by equation
  number ("equation 4 of episode 2"); never "you must have watched" or "watch ... first" (`check_selfcontained.py`
  rejects these; `check_series.py` warns about body mentions without a recap).
- The video stays self-contained: no explainer, code, files, links, description, section or equation numbers.
- One episode per run. Nothing is published from a session: the owner uploads the `deliver/` files by hand; with
  the GitHub workflow, publishing, playlists and uploads happen only there, after the owner approves.
