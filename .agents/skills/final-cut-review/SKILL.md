---
name: final-cut-review
description: Use after assembly and the final gates, before the private upload, or when asked whether someone watched the video - an independent final-cut-reviewer and linear-viewer watch the assembled video, their blocker and major findings are verified and merged, then the release gate; blockers send the run back.
argument-hint: "runs/<run>"
---

# Final-cut review

Precondition: the video is assembled and the final gates pass (`python3 tools/gate.py runs/<run> --stage final`). The
reviewers must not be the session that made the video: independence is the point of this step.

## Procedure

1. **Frames.** `python3 tools/video/final_frames.py runs/<run>` writes `review/final_cut/frames.json`, the frames and
   the contact sheets (a frame every 2 s, at every scene change and chapter start, and just after every scene).
2. **Watch, check, verify, merge.** Run the `review-fanout` workflow (`.claude/workflows/review-fanout.js`) with the
   args that `python3 tools/merge_reviews.py runs/<run> --set final_cut --workflow-args` prints. In parallel it starts
   one `final-cut-reviewer` and one `linear-viewer` (stage `final`), each with only the run path and its report path;
   they write `review/final_cut/final-cut-reviewer.json` (ids `FC-n`) and `review/final_cut/linear-viewer.json` (ids
   `LV-n`), each finding with `time_s`. It checks each report (`merge_reviews.py --pending`, the checks of
   `tools/validate.py`) and sends a failing reviewer back once with the errors, gives each report's blocker and major
   findings to one `finding-verifier` (`review/final_cut/verify/<id>.json`), and merges: `review/final_cut/summary.md`
   and `summary.json`, tied to the video's hash, with the independence flag.

   Without the Workflow tool (another coding agent, or workflows off), do the same by hand: each reviewer as a subagent
   (or a fresh context with `.claude/agents/<name>.md` as its prompt) given only the run path, the stage and its report
   path; `python3 tools/merge_reviews.py runs/<run> --set final_cut --pending <name>` clean (resume it once with the
   errors); one `finding-verifier` per report for what that lists under `verify`; then `python3 tools/merge_reviews.py
   runs/<run> --set final_cut`.
3. **Release gate.** `python3 tools/gate.py runs/<run> --stage release`: the final gates passed for this video, both
   reports are merged and no blocker or confirmed major is open.
4. **Fix.** A confirmed blocker sends the run back: fix the scenes with the `manim-video-producer` skill (never the
   reviewers' files), render again, assemble, run the final gates, then this skill again (each reviewer writes a round
   file: [reviewer-contract.md](../explainer-review/reviewer-contract.md), Second round); record decisions in
   `review/final_cut/resolutions.json`. In CI the release gate stops the run before the private upload, the job
   summary lists the findings, and the fix happens in a new run.

## Without subagents

If this session cannot start subagents at all, start your report with: "No subagents in this session: the final-cut
review is NOT independent." Then write both reports yourself, following `.claude/agents/final-cut-reviewer.md` and
`.claude/agents/linear-viewer.md`, with `"independent": false` and `"reviewed_by": "main session (no subagents)"`
(reviewer-contract.md), check them with `--pending`, skip the verification, and merge. The merged summary, the release
gate and the review issue all mark the review as not independent.

## Gotchas

- Look at every contact sheet: the deterministic checks see rest frames and layout logs, not the cut in motion.
- A caption shows the narration at that moment: compare what it names with the frame at the cue's start.
- `after-scene` frames catch leftovers that only exist for a few frames after a transition.
- The thumbnail and the description are what a viewer sees first; chapters must match the screen.
- The linear-viewer gets the run path and the stage, never the plan, the storyboard or the other report: compare its
  retelling (`summary`) with the intended takeaway.
- In a session whose permission mode does not prompt (`dontAsk`, CI), the workflow starts only with the allow rule
  `Workflow(review-fanout)`; otherwise use the paragraph without the Workflow tool.
