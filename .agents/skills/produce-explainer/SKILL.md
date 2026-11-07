---
name: produce-explainer
description: Runs the whole pipeline in a dated run folder - scout robotics news, rank topics, approve a topic (automatically with logged reasons, or by the user), write and verify the HTML explainer, independent review, narrated Manim scenes - through the hard gates; outside GitHub Actions it then finishes the video in the session (finish-video) up to the hand-over package. Only when the user types /produce-explainer.
argument-hint: "[focus, e.g. humanoid locomotion] | resume runs/<run>"
disable-model-invocation: true
---

# Produce an explainer

Arguments: `$ARGUMENTS` (empty: any robotics topic; `resume runs/<run>`: continue that run). You coordinate; the stage
skills and the reviewers do the work. After every stage run `python3 tools/run.py status runs/<run>`: it derives the
state from the files and names the next step. The GitHub workflow (`.github/workflows/pipeline.yml`), when set up,
runs the same stages unattended.

## Stages

1. **Setup.** `bash setup.sh --check`; if something is missing, stop and give the user the command. Then
   `python3 tools/run.py new --focus "<focus>"` (prints the run path), or `status` when resuming.
2. **Scout.** Invoke the `robotics-news-scout` skill on the run; done when `python3 tools/validate.py runs/<run>` is
   clean.
3. **Rank.** `python3 tools/search_demand.py runs/<run>` (an unreachable source is recorded as unavailable, which is
   fine), then the `virality-ranker` skill; done when `python3 tools/rank_topics.py runs/<run>` wrote `ranking.md`.
4. **Topic approval** (`topic_approval` in `config/pipeline.json`; never pick, and never write `selection.json` or
   `approval.json`: AGENTS.md, Rules):
   - `auto`: `python3 tools/auto_select.py runs/<run>` picks the best eligible, unpublished topic by a fixed rule and
     logs why in `selection.md`. Exit status 1: no topic qualifies; report that and stop.
   - `human`: show the ranking table and the top three, ask the user to type `/approve-topic runs/<run>
     <topic-id>`, and end your turn.
5. **Write.** `python3 tools/run.py finalize runs/<run>` (renames the folder to the topic slug: use the printed path
   from now on), then the `didactic-html-writer` skill.
6. **Verify.** All must pass, with their output quoted in your report:
   `.venv/bin/python tools/run_code_checks.py runs/<run>`, `python3 tools/build_explainer.py runs/<run> --strict`,
   `node tools/check_html.js runs/<run>/explainer.html --json runs/<run>/review/check_html.json`.
7. **Review.** The `explainer-review` skill. Fix confirmed blockers and majors, rebuild, repeat step 6. At most two
   rounds; then report what is open instead of looping.
8. **Video.** The `manim-video-producer` skill (a standalone video: it declares its own ideas).
9. **Gates.** `python3 tools/gate.py runs/<run> --stage pre-render` must pass. In GitHub Actions (`$GITHUB_ACTIONS` is
   `true`) stop: the workflow renders, assembles, has the final cut reviewed, uploads privately and asks the user.
10. **Finish.** Elsewhere, invoke the `finish-video` skill on the run. The explainer itself is not published from a
    session.
11. **Close.** `python3 tools/run.py package runs/<run>`. Report: run path, the selection and its reasons, what was
    verified and how (commands and key output lines), open findings, unverified claims, gate results, the files handed
    over.

Done means: `run.py status` shows every stage up to the gates done, the report quotes the evidence, no blocker or
major finding is open, and every unverified claim is named.

## Gotchas

- Nothing is published, pushed or uploaded from here (AGENTS.md, Rules).
- Ask the user questions only in this conversation: subagents cannot ask.
- A stage that fails twice for the same reason: stop and ask instead of trying a third variant.
- A ranking that changes after the approval makes it stale (`status` says so): rerun step 4.
- In `human` mode, no `approval.json` after `/approve-topic` means the hooks did not run (workspace not trusted, or
  hooks disabled). Tell the user; the manual fallback in README.md is theirs to run, never yours.
- Keep long tool output out of the conversation: summarise and point to the files in the run.
