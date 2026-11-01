# Cloud sessions: from a source document to the finished episode

The channel runs from Claude Code cloud sessions on this repository. One session, one command: it plans the series of
a source document when none exists, makes the next episode with every check and review, renders it, has an
independent reviewer watch it, and sends you the finished files. You watch the video and upload it yourself in
YouTube Studio. Nothing else is needed: no GitHub Actions setup, no keys, no uploads by Claude.

## Once: the cloud environment

In Claude Code on the web, connect GitHub and pick this repository (it can be private). Then edit the cloud
environment the sessions use (the environment menu in the session's title bar, then Edit):

1. **Network access.** Choose the level with **Allowed domains** ("Limited"; in an app that has not updated, "Custom")
   and keep **Allow package managers** ticked ("Also include default list of common package managers"). Add, one
   per line:

   ```text
   huggingface.co
   hf.co
   *.hf.co
   ```

   `huggingface.co` serves the Piper voice model (`rhasspy/piper-voices`), and its downloads come from hosts under
   `hf.co` (`cdn-lfs.hf.co`, `cdn-lfs-us-1.hf.co`, `cas-bridge.xethub.hf.co`). The package managers cover Ubuntu's
   apt, PyPI and npm, which the setup script uses. Nothing else is needed for series episodes.
2. **Setup script.** Paste this (it runs as root on Ubuntu 24.04 when a session's environment is prepared, in the
   folder above the repository; if your repository has another name, change the folder in the second line):

   ```text
   #!/bin/bash
   cd claude_robotics_explainer
   ./setup.sh --with-system-deps --no-browser
   ```

   It installs what is missing without asking anything (apt runs non-interactively as root), builds `.venv` (Manim,
   the scientific stack, Piper), installs the npm packages and downloads the Piper voice into `.cache/piper/`.
   `--no-browser` skips Chromium, which only new explainers need, not series episodes. The first session spends some
   minutes here. If the voice download is refused, the network entries above are missing.
3. **Environment variables and secrets:** none. Piper works offline and nothing is uploaded.

Do not loosen anything else: the repository's `.claude/settings.json` already allows the pipeline's own commands and
denies `git push` and uploads. In the mode menu next to the prompt box, **Auto** (when your organization offers it)
lets most commands run without asking; in the other modes the session asks before commands outside those allow
rules.

## Each episode

1. Open a new session on the repository and type:

   ```text
   /produce-from-source sources/variational-whole-body-control
   ```

   The first time, it plans the series (no approval needed: `series.plan_approval` is `optional` in
   `config/pipeline.json`), summarises each plan in its reply and sends you the plan files, then makes episode 1. A
   later session continues with the number you give: `/produce-from-source sources/variational-whole-body-control 2`
   (add `series <slug>` for an episode of another series). The report of each session ends with the exact command
   for the next one.
2. Let it run: scenes, checks, reviews and the 1080p render take hours. Keep the session open until it hands over.
3. Download what it sends, in that session: the cloud container is temporary, and its files go with it.
   - `upload_sheet.md`: title, description ("Episode n of N · <series>", the chapters), tags, settings and the YouTube
     Studio checklist (altered or synthetic content: Yes, for the Piper voice; playlist; captions; thumbnail; the
     chapters check; the end screen at its exact times).
   - the MP4, its `.srt` captions, `thumbnail.jpg`, `final_cut_review.md`, `youtube.json`, `SHA256SUMS`.
   - the plan files `series/<slug>/series.json` and `PLAN.md`, the first time: put them in your copy of the repository
     under `series/<slug>/`, commit and push, or the next session plans again (Claude cannot push).
4. Watch the video. Upload it in YouTube Studio with the sheet; tick the boxes as you go.

## A new source

Put `sources/<name>/explainer.html` in the repository (with `code/`, its `checks.toml` and `data/` when the explainer
has companion scripts), commit and push, then type `/produce-from-source sources/<name>` in a new session. The
session first runs `python3 tools/check_source.py sources/<name>` and stops on an error with its fix (for example a
script tag a viewer added when the page was saved: `--strip-external-scripts --write` removes it); the checks
workflow runs the same check on every push. README.md, "Adding a new source", has the details; without companion
code the episodes write their own scripts.

## When something is missing

- "the network refused the download" for the Piper model: add the three network entries above, start a new session.
- The setup script failed: the session says which command; fix it under Setup script and start a new session. The
  session can also run `bash setup.sh --with-system-deps --no-browser` itself (it asks first).
- No subagents in the session: the report says so at the start, and the red team and the final-cut review are then
  not independent; the plan is handed over before any episode is made.
