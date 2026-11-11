---
name: final-cut-review
description: Final-cut review of an assembled video - frames for the reviewers, an independent final-cut-reviewer subagent that watches the video like a viewer (space, overlaps in motion, number formats, narration-picture sync, reading time, leftovers, self-containedness, series beats, thumbnail, chapters, end-screen area, pacing, narration) and a linear-viewer subagent that checks the explanation can be followed from the video alone, adversarial verification of blocker and major findings, merge, and the release gate; blockers send the run back to fix and re-render. Use after assembly and the final gates, before the private upload, or when asked whether someone watched the video.
argument-hint: "runs/<run>"
---

# Final-cut review

Precondition: the video is assembled and the final gates pass (`python3 tools/gate.py runs/<run> --stage final`). The
reviewers must not be the session that made the video: independence is the point of this step. Run each named agent
(`.claude/agents/<name>.md`) as a subagent; if your tool has no such agent, use a general-purpose subagent or a fresh
context with that file's body as the prompt.

## Procedure

1. **Frames.** `python3 tools/video/final_frames.py runs/<run>` writes `review/final_cut/frames.json`, the frames and
   the contact sheets (a frame every 2 s, at every scene change and chapter start, and just after every scene).
2. **Watch.** In parallel, start one `final-cut-reviewer` with only the run path and one `linear-viewer` with only the
   run path and `final`. They write `review/final_cut/final-cut-reviewer.json` (ids `FC-n`) and
   `review/final_cut/linear-viewer.json` (ids `LV-n`), each finding with `time_s`.
3. **Validate.** `python3 tools/validate.py runs/<run>` must be clean; otherwise resume that reviewer with the message.
4. **Verify.** For every `blocker` or `major` finding without a verdict, start a `finding-verifier` (in parallel, one
   per finding) with the finding id and its report; each writes `review/final_cut/verify/<id>.json`.
5. **Merge.** `python3 tools/merge_reviews.py runs/<run> --set final_cut` writes `review/final_cut/summary.md` and
   `summary.json` (tied to the video's hash, with the independence flag).
6. **Release gate.** `python3 tools/gate.py runs/<run> --stage release`: the final gates passed for this video, both
   reports are merged and no blocker or confirmed major is open.
7. **Fix.** A confirmed blocker sends the run back: fix the scenes with the `manim-video-producer` skill (never the
   reviewers' files), render again, assemble, run the final gates, then this skill again (each reviewer writes a round
   file: [reviewer-contract.md](../explainer-review/reviewer-contract.md), Second round); record decisions in
   `review/final_cut/resolutions.json`. In CI the release gate stops the run before the private upload, the job
   summary lists the findings, and the fix happens in a new run.

## Without subagents

If this session cannot start subagents at all, start your report with: "No subagents in this session: the final-cut
review is NOT independent." Then do steps 2 and 3 yourself, following `.claude/agents/final-cut-reviewer.md` and
`.claude/agents/linear-viewer.md`, mark the reports not independent (reviewer-contract.md), skip step 4, and merge. The
merged summary, the release gate and the review issue all mark the review as not independent.

## Gotchas

- Look at every contact sheet: the deterministic checks see rest frames and layout logs, not the cut in motion.
- A caption shows the narration at that moment: compare what it names with the frame at the cue's start.
- `after-scene` frames catch leftovers that only exist for a few frames after a transition.
- The thumbnail and the description are what a viewer sees first; chapters must match the screen.
- The linear-viewer gets the run path and the stage, never the plan, the storyboard or the other report: compare its
  retelling (`summary`) with the intended takeaway.
