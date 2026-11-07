---
name: produce-from-source
description: One entry point from a source document (a folder in sources/) to a finished episode - plans its series with the plan-series procedure when none exists (curator and independent red team; it may make several series), then makes the next episode in release order with the produce-episode procedure and finishes it in the session (Piper narration, 1080p render, final-cut review, release gate) up to the hand-over package the owner downloads and uploads to YouTube by hand. One episode per invocation. Only when the user types /produce-from-source.
argument-hint: "sources/<name> [next | <episode number>] [series <slug>] [fresh]"
disable-model-invocation: true
---

# From a source document to a finished episode

Arguments: `$ARGUMENTS`. A source is a folder `sources/<name>/` with `explainer.html` and, when it has them, `code/`
(the companion scripts with `checks.toml`) and `data/`. The owner approves only the finished video: plans follow
`config/pipeline.json` `series.plan_approval` (`optional` since 2026-11-01), and the owner uploads by hand. Nothing
here uploads, commits or pushes, and nothing under `sources/` is edited.

## Stages

0. **Prerequisites.** `bash setup.sh --check`. When it reports something missing (the environment's setup script
   normally installed everything), run `bash setup.sh --with-system-deps --no-browser`. Then
   `python3 tools/video/piper_model.py path`; when the model is missing, `python3 tools/video/piper_model.py fetch`.
   If the fetch stops on a host the network refuses, name the host (CLOUD-SESSION.md lists the entries), make the
   plan and the episode up to its pre-render gates, and stop there: there is no fallback voice.
   Then the source itself: `python3 tools/check_source.py sources/<name>`. On an error (an external script in the
   page, a lint error, a manifest entry without its script) stop and give the owner the message with its fix line:
   the owner fixes the source, Claude never edits `sources/`. Warnings (a script the document names that `code/`
   lacks, scripts outside `checks.toml`, stale section tags) do not stop the run: list them in the report, and plan
   and make no episode whose numbers rest on a missing script.
1. **Plans.** `python3 tools/series.py from-source sources/<name>` lists the series made from the source, in release
   order. When it lists none, read `.claude/skills/plan-series/SKILL.md` and follow its stages with the source as the
   argument (the planning run, the `series-curator`, the independent `series-red-team`, verification, merge and
   fixes, `tools/series.py write`); a source without `code/` gets the warning and the brief's rules for it. Then:
   - show the summary of each new `series/<slug>/PLAN.md` in your reply (story spine, episodes with their hooks and
     lengths, what was left out, open questions, release order);
   - send each new `series/<slug>/series.json` and `PLAN.md` to the owner with the session's file-sending tool: the
     plan exists only in this container until the owner commits it to `series/<slug>/` (otherwise the next session
     plans again, differently);
   - with `series.plan_approval` `required`, stop here: the owner approves each plan
     (`./tools/human/approve_series.py series/<slug>`, in their own terminal) and types the command again. With
     `optional`, go on.
2. **Episode.** The series named with `series <slug>`, else the first in release order with an episode left. The
   episode number given, else `python3 tools/series.py next series/<slug>` (it counts the episodes delivered in this
   checkout's `runs/`; a new session does not have the earlier sessions' runs, so the owner names the number there).
   Say early in your reply which episode you are making and why; when no number was given and the plan was already
   committed before this session, add that an earlier session may have made it, so the owner can stop you.
3. **Make it.** Read `.claude/skills/produce-episode/SKILL.md` and follow it with `series/<slug> <n>` (and `fresh`
   when given): the start (`python3 tools/series.py start series/<slug> --episode <n> --by produce-from-source`), the
   scenes and their checks, the video design review, the pre-render gates, then its finish stage, which invokes the
   `finish-video` skill: narration, the 1080p render, assembly, the final gates, the final-cut review, the release
   gate, fixes, and `python3 tools/deliver.py runs/<run>`.
4. **Hand over and report.** The `deliver/` files go to the owner with the file-sending tool (finish-video, stage
   10). Report: the plan summary when it was made in this session, the episode and its run, the gate results, the
   final-cut findings and their resolutions, the files sent, that the container is temporary, and the exact command
   for the next episode in a new session: `/produce-from-source sources/<name> <next number>` (or with
   `series <slug>` when the next one is in another series).

## Adding a new source

The owner adds `sources/<name>/explainer.html` (one self-contained HTML page), with `code/` (the scripts that print
its numbers and draw its figures, a `checks.toml` listing them, a README) and `data/` when they exist, commits and
pushes, then types `/produce-from-source sources/<name>` in a new session. Claude never writes under `sources/`:
`python3 tools/check_source.py sources/<name>` says what the owner must fix (its `--strip-external-scripts --write`
is for the owner to run), and `python3 tools/run_code_checks.py sources/<name>` runs the scripts in a temporary copy
and leaves the folder as it is, except `code/logs/`.

## Gotchas

- No companion code: `tools/series.py plan` and `validate` warn, `start` gives the run an empty `code/` from
  `templates/run/`, and every number an episode shows comes from a script written there (listed in `checks.toml`,
  run by `tools/run_code_checks.py`), never from the page or from memory.
- `plan-series` and `produce-episode` are user-only skills: read and follow their SKILL.md files here; the
  `final-cut-review` and `finish-video` skills are invoked.
- One episode per invocation. A long render runs in the background; keep the session open until the hand-over.
- Without subagents, say so at the start: the red team and the final-cut review are then NOT independent; stop after
  the plan hand-over in that case, so the owner can decide before an episode is made.
