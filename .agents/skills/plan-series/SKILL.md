---
name: plan-series
description: The series planner - designs one or more video series from a finished explainer (story spine, episodes, what is left out and why, hooks, takeaways, a backward-only prerequisite graph with recaps, teasers, the ideas each episode teaches and the lengths they need, material sources, plan sentence, playlist description) with the series-curator subagent, has every episode checked by the independent series-red-team, and writes the series.json of each series (schema 2); the owner approves plans only when config/pipeline.json asks for it. Only when the user types /plan-series (or /produce-from-source follows it).
argument-hint: "<explainer run or source, e.g. sources/variational-whole-body-control> [focus]"
disable-model-invocation: true
---

# Plan a series

Arguments: `$ARGUMENTS`. The brief, with the rules every episode meets: [brief.md](brief.md). Nothing here makes an
episode. Plan approval follows `config/pipeline.json` `series.plan_approval`: `optional` (the plan is used as written,
after the red team) or `required` (the owner approves each plan before any episode). Run each named agent
(`.claude/agents/<name>.md`) as a subagent; if your tool has no such agent, use a general-purpose subagent or a fresh
context with that file's body as the prompt.

## Stages

0. **Check the source.** For a source folder, `python3 tools/check_source.py sources/<name>` first. On an error, stop
   and give the user its message and fix (only the owner changes `sources/`); warnings go to the curator (no episode
   may rest on a script the source lacks) and into the hand-over.
1. **Planning run.** `python3 tools/series.py plan <explainer run or source>` prints
   `runs/<date>-series-plan-<slug>/`: the explainer with its code and data, `series_plan/` for the proposals,
   `review/series_plan/` for the red team. A series made from a news run's explainer first gets its own source folder,
   `sources/<name>/` (explainer.html, code/, data/), which the plan's `source` names. A source without `code/` is
   allowed: tell the curator (brief.md, "A source without companion code") and say so in the hand-over.
2. **Curate.** Start one `series-curator` with the planning run path (and the user's focus, if any). It writes
   `series_plan/series.<slug>.v2.json` (one per series; it may propose two) and `series_plan/PLAN.md`, declares every
   episode's `ideas`, sets `length_min` from the range `python3 tools/series.py validate` prints, and runs `validate`
   until it reports no error.
3. **Red team.** Start one `series-red-team` with only the run path. It writes
   `review/series_plan/series-red-team.json`; `python3 tools/validate.py runs/<run>` must be clean.
4. **Verify.** For every `blocker` or `major` finding without a verdict, a `finding-verifier` (in parallel) writes
   `review/series_plan/verify/<id>.json`.
5. **Merge and fix.** `python3 tools/merge_reviews.py runs/<run> --set series_plan`; resume the curator with the
   confirmed findings (it edits the proposals, never the review), record decisions in
   `review/series_plan/resolutions.json`, merge again. At most two rounds; report what stays open.
6. **Write.** For each series, `python3 tools/series.py write runs/<run>/series_plan/series.<slug>.v2.json --plan
   runs/<run>/series_plan/PLAN.md` stores `series/<slug>/series.json`. It refuses while red-team findings are open,
   and will not overwrite an approved plan without `--replace`.
7. **Hand over.** Tell the user the series and their episodes (`python3 tools/series.py list series/<slug>`), the
   release order (`python3 tools/series.py from-source <source>`), what was left out, the open red-team findings and
   the open questions in PLAN.md. With `optional`, say in one line that episodes start from the plan as written; with
   `required`, name the step only the owner can take, in their own terminal: `./tools/human/approve_series.py
   series/<slug>`. Either way the plan exists only in this checkout until the owner commits `series/<slug>/` (a cloud
   session cannot push: say so).

## Without subagents

If this session cannot start subagents at all, say so plainly: the curation is done here and the red team is NOT
independent. Write the red-team report yourself, marked not independent (reviewer-contract.md), and tell the owner.
With `required` approval they decide whether to approve the plan anyway; with `optional`, stop after the hand-over, so
the owner decides before an episode is made.

## Gotchas

- Scope is set here, not in the video: never fit an over-packed episode by faster talk or shorter pauses. Cut, move
  or split as `validate` names (brief.md, "The idea budget").
