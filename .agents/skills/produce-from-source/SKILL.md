---
name: produce-from-source
description: Only when the user types /produce-from-source with a folder in sources/ (and an episode number). Plans the source's series when none exists, makes the next episode in release order and finishes it in the session up to the hand-over package the owner uploads by hand. One episode per call.
argument-hint: "sources/<name> [next | <episode number>] [series <slug>] [fresh]"
disable-model-invocation: true
---

# From a source document to a finished episode

Arguments: `$ARGUMENTS`. A source is a folder `sources/<name>/` with `explainer.html` and, when it has them, `code/`
(the companion scripts with `checks.toml`) and `data/`. Plans follow `config/pipeline.json` `series.plan_approval`;
the owner approves the finished video and uploads it by hand. Nothing here uploads, commits or pushes, and nothing
under `sources/` is edited.

## Stages

0. **Guards.** Before anything else run `git -C . push --dry-run guards-off-canary`: it names no remote, so it changes
   nothing even when it runs. The project's Bash hook must refuse it with "Blocked by project policy". Any other
   outcome (git's own error, a refused permission, another message) means this session did not load the project's
   settings, hooks and deny rules: reply "guards off: start the session at the repository root" and stop.
1. **Prerequisites.** `bash setup.sh --check`; when it reports something missing, `bash setup.sh
   --with-system-deps --no-browser` (inside Claude Code's sandbox it installs no system packages: give the owner the
   command it prints and stop). Check the narration voice as `finish-video` stage 1 says: when it cannot work here,
   say what is missing, make the plan and the episode up to its pre-render gates, and stop there (no fallback voice).
   Then the source: `python3 tools/check_source.py sources/<name>`. On an error (an external script in the page, a lint
   error, a manifest entry without its script), stop and give the owner the message with its fix line: the owner
   fixes the source. Warnings (a script the document names that `code/` lacks, scripts outside `checks.toml`, stale
   section tags) do not stop the run: list them in the report, and plan and make no episode whose numbers rest on a
   missing script.
2. **Plans.** `python3 tools/series.py from-source sources/<name>` lists the series made from the source, in release
   order. When it lists none, read `.agents/skills/plan-series/SKILL.md` and follow its stages with `sources/<name>`
   wherever it says `$ARGUMENTS` (its linked files are in the same folder). Then:
   - show the summary of each new `series/<slug>/PLAN.md` in your reply (story spine, episodes with their hooks and
     lengths, what was left out, open questions, release order);
   - send each new `series/<slug>/series.json` and `PLAN.md` to the owner with the session's file-sending tool: the
     plan exists only in this container until the owner commits it (otherwise the next session plans again,
     differently);
   - with `series.plan_approval` `required`, stop: the owner approves each plan (`./tools/human/approve_series.py
     series/<slug>`, in their own terminal) and types the command again. With `optional`, go on.
3. **Episode.** The series named with `series <slug>`, else the first in release order with an episode left; the
   episode number given, else `python3 tools/series.py next series/<slug>` (it counts the episodes in the committed
   `runs/ledger/` and those delivered in this checkout's `runs/`). Say early which episode you are making and why; when
   no number was given and the plan was committed before this session, add that an earlier session may have made it,
   so the owner can stop you.
4. **Make it.** Follow `.agents/skills/produce-episode/stages.md` with `series/<slug>` and `<n>` (and `fresh` when
   given), starting with `python3 tools/series.py start series/<slug> --episode <n> --by produce-from-source`, through
   its finish stage (`finish-video`).
5. **Hand over and report.** The `deliver/` files go to the owner (finish-video, stage 10). Report: the plan summary
   when it was made in this session, the episode and its run, the gate results, the final-cut findings and their
   resolutions, the files sent (the owner commits `ledger-<run>.json` as `runs/ledger/<run>.json`), that the container
   is temporary, and the exact command for the next episode in a new session:
   `/produce-from-source sources/<name> <next number>` (or with `series <slug>` when the next one is in another series).

## Adding a new source

The owner adds `sources/<name>/explainer.html` (one self-contained HTML page), with `code/` (the scripts that print its
numbers and draw its figures, a `checks.toml` listing them, a README) and `data/` when they exist, commits and pushes,
then types `/produce-from-source sources/<name>` in a new session. Never write under `sources/` (the sandbox refuses
it too): `python3 tools/check_source.py sources/<name>` says what the owner must fix (its
`--strip-external-scripts --write` is for the owner to run), and `python3 tools/run_code_checks.py sources/<name>
--logs runs/<run>/source-logs` runs the scripts in a temporary copy and writes the logs into a run, not the source.

## Gotchas

- No companion code: `tools/series.py plan` and `validate` warn, `start` gives the run an empty `code/` from
  `templates/run/`, and every number an episode shows comes from a script written there (listed in `checks.toml`, run
  by `tools/run_code_checks.py`), never from the page or from memory.
- `plan-series` is a user-only skill: read and follow its SKILL.md here, as stage 2 says. The episode stages are in
  `.agents/skills/produce-episode/stages.md`, shared with `/produce-episode`. `finish-video` and `final-cut-review`
  are invoked.
- `python3 tools/series.py write` writes the plan into `series/`, which the sandbox closes to every other command: it
  is the one way a plan gets there.
- One episode per invocation. A long render runs in the background; keep the session open until the hand-over.
- Without subagents, say so at the start: the red team and the final-cut review are then NOT independent; stop after
  the plan hand-over, so the owner can decide before an episode is made.
