---
name: plan-series
description: Only when the user types /plan-series (or /produce-from-source follows it) - designs one or more video series from a finished explainer with the series-curator, has every episode checked by the independent series-red-team, and writes each series.json (schema 2) for the owner.
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
3. **Red team.** Run the `review-fanout` workflow (`.claude/workflows/review-fanout.js`) with the args that
   `python3 tools/merge_reviews.py runs/<run> --set series_plan --workflow-args` prints: one `series-red-team` with only
   the run path and its report path writes `review/series_plan/series-red-team.json`; the report is checked (a failing
   one goes back once with the errors), one `finding-verifier` verifies its blocker and major findings
   (`review/series_plan/verify/<id>.json`), and the set is merged. Without the Workflow tool, do the same by hand: the
   red team as a subagent (or a fresh context with `.claude/agents/series-red-team.md` as its prompt) given only the run
   path and its report path; `python3 tools/merge_reviews.py runs/<run> --set series_plan --pending series-red-team`
   clean (resume it once with the errors); one `finding-verifier` for what that lists under `verify`; then
   `python3 tools/merge_reviews.py runs/<run> --set series_plan`.
4. **Fix.** Resume the curator with the confirmed findings (it edits the proposals, never the review), record decisions
   in `review/series_plan/resolutions.json`, merge again. At most two rounds; report what stays open.
5. **Write.** For each series, `python3 tools/series.py write runs/<run>/series_plan/series.<slug>.v2.json --plan
   runs/<run>/series_plan/PLAN.md` stores `series/<slug>/series.json`. It refuses while red-team findings are open,
   and will not overwrite an approved plan without `--replace`.
6. **Hand over.** Tell the user the series and their episodes (`python3 tools/series.py list series/<slug>`), the
   release order (`python3 tools/series.py from-source <source>`), what was left out, the open red-team findings and
   the open questions in PLAN.md. With `optional`, say in one line that episodes start from the plan as written; with
   `required`, name the step only the owner can take, in their own terminal: `./tools/human/approve_series.py
   series/<slug>`. Either way the plan exists only in this checkout until the owner commits `series/<slug>/` (a cloud
   session cannot push: say so).

## Without subagents

If this session cannot start subagents at all, say so plainly: the curation is done here and the red team is NOT
independent. Write the red-team report yourself, with `"independent": false` and `"reviewed_by": "main session (no
subagents)"` (reviewer-contract.md), check it with `--pending`, merge, and tell the owner.
With `required` approval they decide whether to approve the plan anyway; with `optional`, stop after the hand-over, so
the owner decides before an episode is made.

## Gotchas

- Scope is set here, not in the video: never fit an over-packed episode by faster talk or shorter pauses. Cut, move
  or split as `validate` names (brief.md, "The idea budget").
- In a session whose permission mode does not prompt (`dontAsk`, CI), the workflow starts only with the allow rule
  `Workflow(review-fanout)`; otherwise do stage 3 by hand.
