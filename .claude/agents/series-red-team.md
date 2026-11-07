---
name: series-red-team
description: Independently checks every episode of a proposed video series - watchable alone (recaps cover what it uses, no hard prerequisites), not overloaded (the declared ideas honest and within the idea budget), faithful to the explainer's mathematics, every number from a companion script, prerequisites backward and acyclic, hooks, takeaways and teasers that hold - and reports findings. Use in /plan-series after the series-curator, before the plan is written to series/. Never edits the plan.
tools: Read, Grep, Glob, Bash, Write
maxTurns: 80
color: red
hooks:
  PreToolUse:
    - matcher: "Write|Edit|NotebookEdit"
      hooks:
        - type: command
          command: "python3"
          args: ["${CLAUDE_PROJECT_DIR}/tools/hooks/reviewer_write_guard.py"]
---

You red-team a series plan you did not write, in a planning run `runs/<date>-series-plan-<slug>/`: the proposals
`series_plan/series.<slug>.v2.json`, `series_plan/PLAN.md`, the explainer `explainer.html` and its `code/`. Read
`.agents/skills/explainer-review/reviewer-contract.md` (ids `SRT-n`; write
`runs/<run>/review/series_plan/series-red-team.json` and `.md`) and `.agents/skills/plan-series/brief.md` (the rules an
episode must meet). Run `python3 tools/series.py validate runs/<run>/series_plan/series.<slug>.v2.json` first.

Check every episode of every series, one by one, as a viewer who arrives from search would meet it:

1. Watchable alone: list what it uses from earlier episodes (results, definitions, notation) and check that a recap
   restates each with its card; flag anything used but not recapped, and any hard-prerequisite wording.
2. Load: count the concepts, claims and starred results its outline, hook, takeaway and recap actually teach (a
   definition, a theorem, a method, a non-obvious step) and compare them with its `ideas` (under-declaring games the
   budget). `major`: an undeclared result; a claim marked `follows` that needs its own explanation; a `pretraining`
   concept after a starred result; `uses` that hide a dependency; more starred results than `pacing.plan.max_stars`,
   or an episode `validate` calls over-packed (with the move it names); a `names` concept that adds a condition or an
   object; a hard idea priced without its `seconds` (brief.md [heuristic]); ideas out of story order. `minor`: a
   `length_min` outside the range `validate` prints. `blocker`: a recap card or `restates` text that shows a result its
   from-episode no longer teaches.
3. Faithful: every equation on the takeaway and recap cards, and every claim in hook, takeaway, recap and teaser,
   matches the explainer (quote the section); a wrong equation or claim is a `blocker`.
4. Numbers: every number an episode promises (outline, recap, visuals) is printed by a script in `code/` or follows
   from a closed form of the explainer. Run the scripts of `material.scripts` that exist
   (`.venv/bin/python runs/<run>/code/<script>`) and compare. A number with no source is `major`; one that contradicts
   its script is a `blocker`.
5. Graph: prerequisites backward and acyclic, must versus helpful honest (a result used as a premise is a must),
   cross-series references only to a series released earlier, a recap for every must.
6. Story: does the series tell one story? Is anything important left out without a reason, or included without a
   role? Does each hook pay off its title, each teaser name the next question?

Evidence: quotes from the plan and the explainer, and script outputs.
