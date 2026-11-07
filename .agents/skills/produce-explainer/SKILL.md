---
name: produce-explainer
description: Runs the whole pipeline in a dated run folder - scout robotics news, rank topics, approve a topic (automatically with logged reasons, or by the user), write and verify the HTML explainer, independent review, narrated Manim scenes - through the hard gates; outside GitHub Actions it then finishes the video in the session (finish-video) up to the hand-over package. Only when the user types /produce-explainer.
argument-hint: "[focus, e.g. humanoid locomotion] | resume runs/<run>"
disable-model-invocation: true
---

# Produce an explainer

Arguments: `$ARGUMENTS` (empty: any robotics topic; `resume runs/<run>`: continue that run).

You coordinate; the stage skills and reviewer subagents do the work. After every stage run
`python3 tools/run.py status runs/<run>`: it derives the state from the files and names the next step. The scheduled
GitHub workflow (`.github/workflows/pipeline.yml`), when it is set up, runs the same stages unattended; in a session
the video is finished here and handed to the user, who uploads it by hand.

## Stages

1. **Setup and run folder.** `bash setup.sh --check`; if something is missing, stop and give the user the command.
   Then `python3 tools/run.py new --focus "<focus>"` (prints the run path), or `status` when resuming.
2. **Scout.** Invoke the `robotics-news-scout` skill on the run. Done when `python3 tools/validate.py runs/<run>` is clean.
3. **Rank.** `python3 tools/search_demand.py runs/<run>` (search data; a source that is unreachable is recorded as
   unavailable, which is fine), then invoke the `virality-ranker` skill. Done when `python3 tools/rank_topics.py
   runs/<run>` wrote `ranking.md`.
4. **Topic approval.** Read `topic_approval` in `config/pipeline.json`.
   - `auto` (default): run `python3 tools/auto_select.py runs/<run>`. It picks the best eligible, unpublished topic by
     a fixed rule and logs why in `selection.md`. If it exits 1, no topic qualifies: report that and stop.
   - `human`: show the ranking table and the top three, ask the user to type `/approve-topic runs/<run> <topic-id>`,
     and end your turn. Only that command's hook writes `approval.json`.
   Never pick a topic yourself and never write `selection.json` or `approval.json`.
5. **Write.** `python3 tools/run.py finalize runs/<run>` (renames the folder to the topic slug; use the printed path
   from now on), then invoke the `didactic-html-writer` skill.
6. **Verify.** All must pass, with output quoted in your report:
   `.venv/bin/python tools/run_code_checks.py runs/<run>`, `python3 tools/build_explainer.py runs/<run> --strict`,
   `node tools/check_html.js runs/<run>/explainer.html --json runs/<run>/review/check_html.json`.
7. **Review.** Invoke the `explainer-review` skill. Fix confirmed blocker and major findings, rebuild, re-run step 6.
   At most two review rounds; then report what remains open instead of looping.
8. **Video.** Invoke the `manim-video-producer` skill (narrated scenes, `video/plan.json`, draft renders, design and
   reading-time checks, the video design review).
9. **Gates.** `python3 tools/gate.py runs/<run> --stage pre-render` must pass. In GitHub Actions (`$GITHUB_ACTIONS`
   is `true`) the workflow does the rest (render, assembly, final-cut review, private upload, the user's review).
10. **Finish.** Outside GitHub Actions, invoke the `finish-video` skill on the run: narration, the 1080p render,
    assembly, the final gates, the final-cut review, the release gate and `tools/deliver.py`, whose `deliver/` files
    go to the user. The explainer itself is not published from a session.
11. **Close.** `python3 tools/run.py package runs/<run>`. Final report: run path, the selection and its reasons, what
    was verified and how (commands and key output lines), open findings, unverified claims, gate results, and the
    files handed over.

## Done means

`run.py status` shows every stage up to the gates done, the final report quotes the evidence, no blocker or major
finding is open, and every unverified claim is named.

## Gotchas

- Publishing happens only in the GitHub workflow after the user approves the finished video there, or by the user's
  own hand from `deliver/`. Never push, upload, post, release or stream from here: settings deny it and a hook blocks
  variants.
- Ask the user questions only in this conversation: subagents cannot ask, and forked skills cannot either.
- If a stage fails twice for the same reason, stop and ask instead of trying a third variant.
- A ranking that changes after the topic was approved makes the approval stale (`status` says so): rerun step 4.
- In `human` mode, if `/approve-topic` leaves no `approval.json`, hooks did not run (workspace not trusted, or hooks
  disabled). Tell the user; the manual fallback is in README.md and is run by the user, never by you.
- Keep long tool output out of the conversation: summarise and point to the files in the run.
