---
name: finish-video
description: Finishes a video inside the session when no GitHub workflow will - Piper narration, the 1080p render, the final design and reading checks, assembly with captions and chapters, thumbnail and metadata, the final gates, the final-cut review (independent reviewer subagent, adversarial verification of blocker and major findings), the release gate, fixes and re-renders for blockers, and the hand-over package in deliver/ (video, captions, thumbnail, upload sheet with the YouTube Studio checklist) that the owner downloads and uploads by hand. Use after the pre-render gates of /produce-episode or /produce-explainer pass outside GitHub Actions, or when asked to finish, render or hand over a run. Never uploads, commits or pushes.
argument-hint: "runs/<run>"
---

# Finish a video in the session

Arguments: `$ARGUMENTS`, a run whose pre-render gates passed (`python3 tools/gate.py runs/<run> --stage pre-render`).
In GitHub Actions (`$GITHUB_ACTIONS` is `true`) stop here: the workflow's jobs do all of this. Nothing in this skill
uploads, publishes, commits or pushes: the owner downloads `deliver/`, watches the video and uploads it in YouTube
Studio. The steps are the same as the workflow's render, final and final-cut jobs.

## Stages

1. **Voice model.** `python3 tools/video/piper_model.py path` must find the Piper model (`voice.service` `piper` in
   `config/channel.json`); if it is missing, `python3 tools/video/piper_model.py fetch`. If the fetch stops on a host
   the network does not allow, name that host to the owner (the environment's Allowed domains need `huggingface.co`
   and `hf.co`: CLOUD-SESSION.md) and stop: there is no fallback voice, and silence is not a stand-in.
2. **Narration.** `python3 tools/video/synthesize_voice.py runs/<run>` reads the voice-over text from the scene files
   (never runs them) and writes `video/voice/` with its manifest (service, voice model, word timings).
3. **Render.** The scenes of `video/plan.json` (`python3 tools/ci/scene_matrix.py runs/<run>` lists them), each with
   `bash tools/render_video.sh runs/<run> --quality h --voice recorded --scene <file>:<class>` (1080p60 from the
   prepared narration). A scene takes minutes: run the renders in the background, one or two at a time, and read each
   log; a failed render is fixed in the scene (manim-video-producer skill), then rendered again.
4. **Checks of the renders.** `python3 tools/video/check_design.py runs/<run> --stage final --no-frames`,
   `python3 tools/video/check_reading.py runs/<run> --stage final` and
   `python3 tools/video/check_engagement.py runs/<run> --stage final` (motion, transforms, narration, text; the gate
   reports it, warnings first).
5. **Assemble.** `python3 tools/video/assemble.py runs/<run>` (scenes in plan order, captions, chapters; no channel
   card; the narration stem; original music from `tools/video/music.py` by the plan's per-scene modes, ducked under
   the voice; -14 LUFS with the true peak at most -1 dBTP measured after encoding; stings in pauses of the narration and ducked,
   no music element above -12 dB relative to the voice while it speaks: read the "audio:" line it prints), `python3 tools/video/thumbnail.py runs/<run>`, `python3 tools/video/metadata.py runs/<run>` (links as
   `config/channel.json` sets them; off by default), then `check_design.py --stage final --no-frames` again (the
   thumbnail at 168 x 94), `check_selfcontained.py`, `check_numbers.py` and, for an episode, `check_series.py`, each
   with `runs/<run> --stage final`.
6. **Final gates.** `python3 tools/gate.py runs/<run> --stage final --require-links`.
7. **Final-cut review.** Invoke the `final-cut-review` skill on the run: frames and contact sheets, an independent
   `final-cut-reviewer` subagent, a `finding-verifier` subagent for every blocker and major finding, the merge, then
   `python3 tools/gate.py runs/<run> --stage release`.
8. **Fix and render again.** A failed gate or a confirmed blocker sends the run back: fix the scenes with the
   `manim-video-producer` skill (never a reviewer's file), record the decisions in `review/final_cut/resolutions.json`,
   check the changed scenes as drafts, then repeat from stage 2 (unchanged narration blocks keep their audio; render
   again only the scenes that changed). At most two rounds: if a blocker is still open, stop and report it; do not
   hand over.
9. **Package.** `python3 tools/deliver.py runs/<run>` writes `runs/<run>/deliver/`: the MP4, the `.srt`, the
   thumbnail, `upload_sheet.md` (title, description with "Episode n of N" and the chapters, tags, settings, the YouTube
   Studio checklist with the end-screen times and the altered or synthetic content answer), `final_cut_review.md`,
   `youtube.json`, `SHA256SUMS`, and for an episode a copy of its series plan under `series/<slug>/`. It refuses
   unless the release gate passed for this very video.
10. **Hand over.** Send the files in `deliver/` to the owner with the session's file-sending tool: `upload_sheet.md`
    first, then the MP4, the `.srt`, `thumbnail.jpg`, `final_cut_review.md` and, when the sheet says the plan is new in
    this session, the plan files. Say plainly that the cloud container is temporary (download the files now) and that
    nothing was uploaded, committed or pushed.
11. **Report.** The files sent (names and sizes), the gate results, the final-cut findings and what was done about
    each, the narration voice, and what comes next (for a series: the next episode, `python3 tools/series.py next
    series/<slug>`, and the exact command to type in a new session).

## Without subagents

The final-cut-review skill's own section applies: the review is marked NOT independent, and so are the merged summary,
the release gate and the `final_cut_review.md` in the package. Say so at the top of the report.

## Gotchas

- The voice is Piper's (synthetic): the upload sheet answers "Altered or synthetic content: Yes". Only the owner's own
  recordings (`voice.service` `recorded`) make it No.
- A file the sending tool refuses (too large, or no such tool in this session): say which, with its path and size.
  For a large MP4, `split -b 90m runs/<run>/deliver/<slug>.mp4 runs/<run>/deliver/<slug>.mp4.part-` makes parts the
  owner joins with `cat <slug>.mp4.part-* > <slug>.mp4` and checks against `SHA256SUMS`.
- Never run `tools/publish/`, `git push` or anything that uploads; the owner uploads by hand with the sheet.
- A new session starts without this session's `runs/`: the report names the next episode by number.
