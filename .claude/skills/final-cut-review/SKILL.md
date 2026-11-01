---
name: final-cut-review
description: Final-cut review of an assembled video - frames for the reviewer, an independent final-cut-reviewer subagent that watches the video like a viewer (space, overlaps in motion, number formats, narration-picture sync, reading time, leftovers, self-containedness, series beats, thumbnail, chapters, end-screen area), adversarial verification of blocker and major findings, merge, and the release gate; blockers send the run back to fix and re-render. Use after assembly and the final gates, before the private upload, or when asked whether someone watched the video.
argument-hint: "runs/<run>"
---

# Final-cut review

Precondition: the video is assembled and the final gates pass (`python3 tools/gate.py runs/<run> --stage final`).
The reviewer must not be the session that made the video: independence is the point of this step.

## Procedure

1. **Frames.** `python3 tools/video/final_frames.py runs/<run>` writes `review/final_cut/frames.json`, the frames and
   the contact sheets (a frame every 2 s, at every scene change and chapter start, and just after every scene).
2. **Watch.** Start one `final-cut-reviewer` subagent with only the run path. It writes
   `review/final_cut/final-cut-reviewer.json` (ids `FC-n`, each with `time_s`).
3. **Validate.** `python3 tools/validate.py runs/<run>` must be clean; resume the reviewer with the message if not.
4. **Verify.** For every `blocker` or `major` finding, start a `finding-verifier` subagent (in parallel, one per
   finding) with the finding id and `review/final_cut/final-cut-reviewer.json`. Each writes
   `review/final_cut/verify/<id>.json`.
5. **Merge.** `python3 tools/merge_reviews.py runs/<run> --set final_cut` writes `review/final_cut/summary.md` and
   `summary.json` (tied to the video's hash, with the independence flag).
6. **Release gate.** `python3 tools/gate.py runs/<run> --stage release`: the final gates passed for this video and no
   blocker or confirmed major is open.
7. **Fix.** A confirmed blocker sends the run back: fix the scenes with the `manim-video-producer` skill (never the
   reviewer's files), render again, assemble, run the final gates, then this skill again; record decisions in
   `review/final_cut/resolutions.json`. In CI the release gate stops the run before the private upload and the job
   summary lists the findings; the fix happens in a new run.

## Without subagents

If this session cannot start subagents (no Agent tool), say so in plain words at the start of your report: "No
subagents in this session: the final-cut review is NOT independent." Then do steps 2 and 3 yourself, following
`.claude/agents/final-cut-reviewer.md`, with `"independent": false` and `"reviewed_by": "main session (no
subagents)"` in the report, skip step 4, and merge. The merged summary, the release gate and the review issue all
mark the review as not independent.

## Gotchas

- Look at every contact sheet: the deterministic checks see rest frames and layout logs, not the cut in motion.
- A caption shows the narration at that moment: compare what it names with the frame at the cue's start.
- `after-scene` frames catch leftovers that only exist for a few frames after a transition.
- The thumbnail and the description are part of what a viewer sees first; chapters must match the screen.
