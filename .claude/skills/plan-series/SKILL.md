---
name: plan-series
description: The series planner - designs one or more video series from a finished explainer (story spine, episodes, what is left out and why, hooks, takeaways, a backward-only prerequisite graph with recaps, teasers, lengths, material sources, plan sentence, playlist description) with the series-curator subagent, has every episode checked by the independent series-red-team, and writes the series.json of each series (schema 2); the owner approves plans only when config/pipeline.json asks for it. Only when the user types /plan-series (or /produce-from-source follows it).
argument-hint: "<explainer run or source, e.g. sources/variational-whole-body-control> [focus]"
disable-model-invocation: true
---

# Plan a series

Arguments: `$ARGUMENTS`. A series tells a story with material selected from an explainer: the depth and amount of
material differ from the HTML, so episodes choose, reorder and leave out (the owner's position; the brief in
[brief.md](brief.md)). Nothing here makes an episode. Plan approval follows `config/pipeline.json`
`series.plan_approval`: `optional` (the owner's setting since 2026-11-01: the plan is used as written, after the red
team) or `required` (the owner approves each plan once before any episode).

## Stages

0. **Check the source.** For a source folder, `python3 tools/check_source.py sources/<name>` first: on an error stop
   and give the user its message and fix (only the owner changes `sources/`); warnings go to the curator (no episode
   may rest on a script the source lacks) and into the hand-over.
1. **Planning run.** `python3 tools/series.py plan <explainer run>` prints `runs/<date>-series-plan-<slug>/` with the
   explainer, its code and data copied in, `series_plan/` for the proposals and `review/series_plan/` for the red
   team. A series made from a news run's explainer gets its own source folder, `sources/<name>/` (explainer.html,
   code/, data/), before `write`: the plan's `source` points there. A source without `code/` is allowed: say so to
   the curator (brief.md, "A source without companion code") and in the hand-over; every number must then come from
   scripts the episodes write in their run's `code/`, never from memory.
2. **Curate.** Start one `series-curator` subagent with the planning run path (and the focus, if the user gave one).
   It writes `series_plan/series.<slug>.v2.json` (one per series; it may propose two) and `series_plan/PLAN.md`, and
   runs `python3 tools/series.py validate` on each until it reports no error.
3. **Red team.** Start one `series-red-team` subagent with only the run path. It checks every episode (watchable alone,
   about three new ideas at most, faithful to the mathematics, every number from a script, the prerequisite graph) and
   writes `review/series_plan/series-red-team.json`. `python3 tools/validate.py runs/<run>` must be clean.
4. **Verify.** For every `blocker` or `major` finding, a `finding-verifier` subagent (in parallel) writes
   `review/series_plan/verify/<id>.json`.
5. **Merge and fix.** `python3 tools/merge_reviews.py runs/<run> --set series_plan`; resume the curator with the
   confirmed findings (it edits the proposals, never the review), record decisions in
   `review/series_plan/resolutions.json`, merge again. At most two rounds; report what stays open.
6. **Write.** For each series: `python3 tools/series.py write runs/<run>/series_plan/series.<slug>.v2.json --plan
   runs/<run>/series_plan/PLAN.md` stores `series/<slug>/series.json` (it refuses with open red-team findings, and
   will not overwrite an approved plan without `--replace`).
7. **Hand over.** Tell the user: the series and their episodes (`python3 tools/series.py list series/<slug>`), the
   release order (`python3 tools/series.py from-source <source>`), what was left out, the open red-team findings
   and the open questions in PLAN.md. With `series.plan_approval` `optional` there is no approval step: say in one
   line that episodes start from the plan as written. With `required`, name the step only the owner can take, in
   their own terminal: `./tools/human/approve_series.py series/<slug>`. Either way the plan exists only in this
   checkout until the owner commits `series/<slug>/` (a cloud session cannot push: say so).

## Without subagents

If this session cannot start subagents, say so plainly: the curation is done in the main session and the red team is
NOT independent. Write the red-team report yourself with `"independent": false` and `"reviewed_by": "main session (no
subagents)"`, and tell the owner (with approval `required`, they decide whether to approve the plan anyway; with
`optional`, stop after the hand-over instead of going on to an episode, so the owner can decide).

## Gotchas

- Episodes are not sections: `material.section_ids` are sources; `tools/video/plan.py` accepts any heading of the
  explainer as a scene's source.
- A must prerequisite means the episode uses that result as a premise; it needs a recap in the episode. Helpful ones do
  not, and are not narrated beyond a clause.
- Every episode is made fresh from its plan entry. Scenes are kept only for an episode made again after a fix, in
  `series/<slug>/episodes/epNN/scenes/` (the plan does not list them).
