---
name: produce-episode
description: Series mode - makes one narrated episode of a video series (schema 2, in series/) from its source explainer - no scouting, ranking or writing - with the series beats (a hook with a full moving picture from frame 0 and the question by 15 s, a short title beat with the spoken series context, recaps of what it uses, outro with takeaway card and teaser), the design, number, reading-time, self-contained and pacing checks and the video design review, then the pre-render gates; outside GitHub Actions it finishes the video in the session (finish-video) up to the hand-over package for the owner's own upload. Only when the user types /produce-episode (or /produce-from-source follows it).
argument-hint: "series/<series> <episode number | next> [fresh] | resume runs/<run>"
disable-model-invocation: true
---

# Produce a series episode

Arguments: `$ARGUMENTS`. `python3 tools/series.py list series/<series>` shows the episodes, their prerequisites and the
plan's approval state; `python3 tools/series.py from-source sources/<name>` the series of a source in release order.

## Stages

1. **Start.** `python3 tools/series.py start series/<series> --episode <n|next>` (with `--fresh` when the arguments
   say `fresh`) prints the run path; or use the run given with `resume`. `series.plan_approval` in
   `config/pipeline.json`: `optional` notes it and starts from the plan as written; `required` refuses a plan the owner
   has not approved, or one changed since (the owner runs `./tools/human/approve_series.py series/<series>`, never
   you). `next` follows the release order, skips episodes delivered in `runs/` and waits for prerequisites in another
   series. The run gets the source's explainer and `code/` unchanged (no `code/` in the source: an empty one from
   `templates/run/`), its `data/` as `video/data/`, the scene helpers, `video/episode.md` (the brief and house rules),
   `video/series_context.json` (episode n of N, what it builds on, the takeaway and recap cards, the teaser),
   `episode.json`, and the kept scenes of `series/<series>/episodes/epNN/scenes/` unless `--fresh`. Never edit
   `explainer.html`, `episode.json` or `series_context.json`.
2. **Read** `video/episode.md`, the explainer sections it lists (`material.section_ids`: sources, not a mapping), the
   companion scripts that make the numbers, and the kept scenes, if any.
3. **Scenes.** Invoke the `manim-video-producer` skill on the run: the episode tells its own story with the material
   the plan selected (kept scenes are a starting point). The series beats, with the helpers in `common.py`:
   - the hook (AGENTS.md, Conventions);
   - right after it, the title beat (`title_beat()`: the title and the "Episode n of N" lower third with what it
     builds on, the hook's objects still on screen) and one or two spoken sentences: where this episode sits, what it
     builds on, a welcome for viewers joining here;
   - one recap scene per must prerequisite: `recap_tag()` for the whole scene, `recap_card(i)` (the earlier episode's
     card, from the same data as its outro), the restatement by meaning, at most a soft pointer by title;
   - the outro: `outro(takeaway_card(), next_title=...)` and the spoken "In the next episode, ..." (none in the
     finale), the end-screen area empty.
4. **Plan** (`video/plan.json`): the episode title (the series goes in the description), summary, tags, one entry per
   scene with `section` (context and outro may omit it), `chapter`, `role` (`hook`, `context`, `recap` with
   `recap_of`, `body`, `outro`), the thumbnail. Recap chapters start with "Recap".
5. **Checks and design review**: steps 6 and 7 of `manim-video-producer`.
6. **Gates.** `.venv/bin/python tools/run_code_checks.py runs/<run>`, then `python3 tools/gate.py runs/<run> --stage
   pre-render` must pass (it also checks that the plan is approved when required and unchanged since the start).
7. **Finish.** In GitHub Actions (`$GITHUB_ACTIONS` is `true`) stop: the workflow renders, assembles, has the final cut
   reviewed and asks the owner. Anywhere else invoke the `finish-video` skill on the run.
8. **Close.** Report the run path, the episode, what changed in the scenes and why, the gate results, the open
   findings, and outside CI the files handed over and the next episode (`python3 tools/series.py next
   series/<series>`).

## Gotchas

- A series run reuses the published explainer: its gates (lint, reviews, references) are not repeated, but the
  companion code is re-run, so every number on screen comes from `code/` or `video/data/`.
- With companion code, `code/` stays the source's copy (no new export script): read values from its scripts and
  `code/logs/`, or compute the explainer's closed forms in the scene. Without it, write the scripts that print the
  episode's numbers in the empty `code/`, list them in `code/checks.toml`, describe them in `code/README.md` and run
  them. Never a number from the page or from memory.
- Other episodes: by title or meaning, in the body only when their result is shown in this video (AGENTS.md,
  Conventions; `check_selfcontained.py` and `check_series.py` enforce it).
- One episode per run. Nothing is published from a session (AGENTS.md, Rules).
