---
name: finish-video
description: Use after the pre-render gates pass outside GitHub Actions, or when asked to finish, render or hand over a run. Narration in the configured voice, 1080p render, final checks and gates, final-cut review, fixes, then the deliver/ package the owner uploads by hand. Never uploads, commits or pushes.
argument-hint: "runs/<run>"
---

# Finish a video in the session

Arguments: `$ARGUMENTS`, a run whose pre-render gates passed (`python3 tools/gate.py runs/<run> --stage pre-render`).
In GitHub Actions (`$GITHUB_ACTIONS` is `true`) stop here: the workflow's render, final and final-cut jobs do these
steps. Nothing here uploads, publishes, commits or pushes: the owner downloads `deliver/`, watches the video and
uploads it in YouTube Studio.

## Stages

1. **Voice.** The narration voice is `voice.service` in `config/channel.json` (`.venv/bin/python
   templates/manim/voice.py resolve` prints it); `.venv/bin/python templates/manim/voice.py check <name>` says whether
   it works here, and the fix:
   - `azure` (the channel's voice) needs `AZURE_SUBSCRIPTION_KEY` and `AZURE_SERVICE_REGION` in the environment,
     never in a file;
   - `piper` (the keyless voice) needs its model: `python3 tools/video/piper_model.py fetch`, from the hosts
     `huggingface.co` and `hf.co` (README.md, Quick start); fetch it only for this service;
   - `recorded` needs the owner's recordings in `video/voice/` (`python3 tools/video/voice_script.py runs/<run>` lists
     the blocks).
   When the voice cannot work here, tell the owner what is missing (a key, a host, a file) and stop: no other voice
   stands in, and silence is not a stand-in.
2. **Narration.** `python3 tools/video/synthesize_voice.py runs/<run>` reads the voice-over text from the scene files
   (never runs them) and writes `video/voice/` with its manifest (service, voice, word timings, pacing).
3. **Render.** Each scene of `video/plan.json` (`python3 tools/ci/scene_matrix.py runs/<run>` lists them) with
   `bash tools/render_video.sh runs/<run> --quality h --voice recorded --scene <file>:<class>` (1080p60 from the
   prepared narration). A scene takes minutes: run the renders in the background, one or two at a time, and read each
   log; fix a failed render in the scene (manim-video-producer skill) and render it again.
4. **Check the renders.** `python3 tools/video/<check>.py runs/<run> --stage final` for `check_design` (with
   `--no-frames`), `check_reading`, `check_engagement` and `check_script` (the pace and the pauses inside sentences,
   from the word timings; reported, not blocking).
5. **Assemble.** `python3 tools/video/assemble.py runs/<run>` (scenes in plan order, captions, chapters, the narration
   stem, the generated music by the plan's modes; read the "audio:" line it prints), `python3
   tools/video/thumbnail.py runs/<run>`, `python3 tools/video/metadata.py runs/<run>` (links as `config/channel.json`
   sets them). Then, each with `runs/<run> --stage final`: `check_design.py --no-frames` again (the thumbnail),
   `check_selfcontained.py`, `check_numbers.py`, `check_pacing.py` (on the narration stem and the word timings; its
   errors send the run to stage 8), `check_sync.py` (labels against the narration's word timings) and, for an
   episode, `check_series.py`.
6. **Final gates.** `python3 tools/gate.py runs/<run> --stage final --require-links`.
7. **Final-cut review.** Invoke the `final-cut-review` skill on the run: frames, the independent reviewer, a verifier
   per blocker and major finding, the merge, then `python3 tools/gate.py runs/<run> --stage release`.
8. **Fix and render again.** A failed gate or a confirmed blocker sends the run back: fix the scenes with the
   `manim-video-producer` skill (never a reviewer's file), record the decisions in `review/final_cut/resolutions.json`,
   check the changed scenes as drafts, then repeat from stage 2 (unchanged narration blocks keep their audio; render
   again only the scenes that changed). At most two rounds: if a blocker is still open, stop and report it; do not
   hand over.
9. **Package.** `python3 tools/deliver.py runs/<run>` writes `runs/<run>/deliver/`: the MP4, the `.srt`, the
   thumbnail, `upload_sheet.md` (title, description with "Episode n of N" and the chapters, tags, settings, the YouTube
   Studio checklist with the end-screen times and the altered or synthetic content answer), `final_cut_review.md`,
   `youtube.json`, `ledger-<run>.json` (a copy of the `runs/ledger/<run>.json` it writes), `SHA256SUMS`, and for an
   episode a copy of its series plan under `series/<slug>/`. It refuses unless the release gate passed for this very
   video.
10. **Hand over.** Send the files in `deliver/` to the owner with the session's file-sending tool: `upload_sheet.md`
    first, then the MP4, the `.srt`, `thumbnail.jpg`, `final_cut_review.md`, `ledger-<run>.json` (the owner commits it
    as `runs/ledger/<run>.json`) and, when the sheet says the plan is new in this session, the plan files. Say plainly
    that the cloud container is temporary (download the files now) and that nothing was uploaded, committed or pushed.
11. **Report.** The files sent (names and sizes), the gate results, the final-cut findings and what was done about
    each, the narration voice, and what comes next (for a series: the next episode, `python3 tools/series.py next
    series/<slug>`, and the exact command to type in a new session).

## Without subagents

The final-cut-review skill's own section applies: the review, the merged summary, the release gate and the packaged
`final_cut_review.md` are all marked NOT independent. Say so at the top of the report.

## Gotchas

- An AI voice (`azure`, `piper`) makes the upload sheet answer "Altered or synthetic content: Yes"; only the owner's
  own recordings (`recorded`) make it No.
- A file the sending tool refuses (too large, or no such tool in this session): say which, with its path and size.
  For a large MP4, `split -b 90m runs/<run>/deliver/<slug>.mp4 runs/<run>/deliver/<slug>.mp4.part-` makes parts the
  owner joins with `cat <slug>.mp4.part-* > <slug>.mp4` and checks against `SHA256SUMS`.
- Never run `tools/publish/`, `git push` or anything that uploads (AGENTS.md, Rules).
- Narration refused by the sandbox (the proxy's `403` for the speech host) means the region of `AZURE_SERVICE_REGION`
  is not in `sandbox.network.allowedDomains` of `.claude/settings.json`: tell the owner which host (README.md,
  Sandbox); no other voice stands in.
- A new session starts without this session's `runs/`: the report names the next episode by number.
