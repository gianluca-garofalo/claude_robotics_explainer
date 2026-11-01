---
name: manim-video-producer
description: Produces the narrated Manim (Community Edition) scenes for a finished explainer of the Remaining Action channel - a storyboard that chooses less and different material than the explainer to tell one story, voice-over text, scenes driven by data from the run's code/, video/plan.json (title, summary, tags, chapters, roles, thumbnail) - and checks them with draft renders, the design, number-format, reading-time, self-contained and structure checks and an independent video design review. Use after the explainer passed review, for a series episode, or when asked for a Manim animation of an explainer.
argument-hint: "runs/<run> [number of scenes]"
---

# Manim video producer

Precondition: the explainer passed review (`python3 tools/run.py status runs/<run>`), or the run is a series episode
(`episode.json`, see the `produce-episode` skill). Output in `runs/<run>/video/`: `storyboard.md`, `scenes/*.py` with
`common.py`, `voice.py` and `reading_model.py`, `data/*.npz`, `plan.json`, draft renders and layout logs in `checks/`,
`README.md`; reviews in `runs/<run>/review/video/`. The 1080p60 narrated render, assembly, captions, chapters,
thumbnail, the final-cut review and the upload happen in GitHub Actions; nothing here is uploaded.

## Procedure

1. **Storyboard first** (`video/storyboard.md`, template in [storyboard.md](storyboard.md)). A video is not a walk
   through the explainer's sections: choose less, and different, material that tells one story for a viewer, at the
   depth a video can carry (about three new ideas), and say what is left out. Scenes of one idea each, 30 to 120 s;
   the opening hook (narration from 0 s, no channel card) and the outro (15-20 s, `outro()`: the takeaway card, the
   channel name, the right of the frame empty for the end screen); the voice-over text with `<bookmark mark='x'/>`
   cues; what is on screen at each moment and how long it must stay (reading model below); the sources and data each
   scene uses. A series episode adds its beats from `video/episode.md` (see the `produce-episode` skill).
2. **Data.** Export what the scenes show with a script in `code/` (listed in `checks.toml`) that writes
   `video/data/<name>.npz`, or recompute closed forms from the explainer's equations. Nothing on screen is typed by hand.
3. **Scenes.** Copy `templates/manim/common.py`, `voice.py`, `reading_model.py` and `scene_template.py` into
   `video/scenes/`, one file per scene, rename the class. Scenes derive from `RAScene` (narration plus automatic reading
   holds); every `with self.voiceover(text=...)` block is narrated and becomes a caption. Place titles and captions with
   `title()` and `caption()` (graphics-safe area). Copy LaTeX from the explainer without its equation numbers or tags.
4. **Plan** (`video/plan.json`, format in `tools/video/plan.py`): `title` (at most 90 characters, accurate, no
   clickbait), `summary` (two to four sentences for the description), `tags`, `scenes` in order with the explainer
   `section` id each one draws on (a source, for the review), its `chapter`, the title viewers see (written for the
   video, never the explainer's heading), its `role` (`hook` first, `outro` last; `context` and `recap` with
   `recap_of` in series episodes), and `thumbnail` (`scene`, `time` in seconds of a frame with nothing where the title
   goes, the left half; `text` of at most four words). `python3 tools/ci/scene_matrix.py runs/<run>` must accept it.
5. **Draft check:** `bash tools/render_video.sh runs/<run> --check` (every scene at -ql, silent, with captions and
   layout logs), then
   `python3 tools/video/check_design.py runs/<run> --stage draft`,
   `python3 tools/video/check_reading.py runs/<run> --stage draft`,
   `python3 tools/video/check_numbers.py runs/<run> --stage draft`,
   `python3 tools/video/check_selfcontained.py runs/<run> --stage draft` and
   `python3 tools/video/check_series.py runs/<run> --stage draft`. Fix every error; read the warnings (spacing, space
   use, motion, recall load, opening and ending, series beats).
6. **Design review:** start the `video-design-reviewer` subagent on the run (it looks at the sampled frames and contact
   sheets in `review/design/draft/`), then one `finding-verifier` per blocker or major `VD-` finding, then
   `python3 tools/merge_reviews.py runs/<run> --set video`. Fix confirmed blockers and majors, record decisions in
   `review/video/resolutions.json` (same format as the explainer's), re-render, re-run step 5 and the merge. At most two
   rounds; open blockers stop the run at the gate.
7. **README:** `video/README.md` with scene -> file -> explainer section -> data and script, the colour meanings, and
   the voice: Piper by default (`voice.service` in `config/channel.json`), or `python3 tools/video/voice_script.py
   runs/<run>` lists the blocks to record for the user's own voice.

## Self-contained video (house rule; tools/video/check_selfcontained.py fails the gate otherwise)

The viewer has only the video. Nothing on screen, in the narration, the captions or the chapters names the explainer,
its code, files, data, links or the description, and no equation carries a label or tag: no (13), (2), (★), `\tag`,
`\label`, "Eq. 3" or "recall equation 2" (`equation_numbers` in `config/video.json`, default false; true allows only
the video's own numbering, (1), (2), ... in order), never another episode's ("equation 4 of episode 2"). Other
episodes of a series may be named by title or meaning, in the series context, recaps and outro, and in the body only
when their result is shown in this video (a recap); never as a hard prerequisite ("you must have watched", "watch ...
first": the check rejects these; `check_series.py` warns about body mentions without a recap). The numbers still come from `code/` behind
the scenes; say a check result in the video's own words ("the residual is exactly zero"). To use an equation again,
show it again or keep it pinned in a corner with `pin()`; `check_reading.py` warns when narration refers back to an
equation that left the screen more than 60 s earlier, or when an episode has more than three such callbacks: then
show it again, pin it, or split the episode. Links to the explainer and code are a per-run decision for the YouTube
description only (`links.include`), never part of the video.

## Numbers (house rule; tools/video/check_numbers.py fails the gate on errors)

Every number goes through `fmt()` (config/video.json "numbers"): 2-3 significant digits for readouts, no trailing
zeros (0.5, never 0.500000), exact values shown exactly (`fmt(x, exact=True)`: "0", "½"; or say "exactly zero"), a
real minus sign, a space before a unit. Live readouts keep fixed decimals so their width does not jump:
`readout("∫ L dt", lambda: value, decimals=2)`; every number of one quantity in a scene has the same precision (not
1.28 beside 1.277). Say numbers as a person would ("about one point two eight"), never digit by digit.

## Layout (tools/video/check_design.py: spacing errors fail the gate; alignment and panels warn)

- Keep every text at least 0.15 units (about 20 px) from any line or shape: other texts, axis lines, and every strong
  stroke (curves, arrows, plot lines, box outlines), not only from strokes that cross it. A label that names or points
  at an object (a curve's name at its end, a dot's tag, a wall's value) may sit closer to that object: create it with
  `attach(label, obj)` (optionally `attach(label, obj, direction=RIGHT, buff=0.15)` to place it); it stays subject to
  every other stroke and to the crossing rule.
- Legends and blocks of readouts go in fixed columns with `legend_table(rows, aligns="clll", col_gap=0.3,
  row_gap=0.2)`: rows of cells (a Dot, a MathTex, a Text), aligned by construction, one row pitch; `min_widths={3: w}`
  reserves room for a label swapped in later with `table.place(new, i, 3)` (same column, same edge). Never place a
  column of tags with `next_to` row by row and then shift the group: the stagger stays.
- Split layouts (a picture on one side, equations or a legend on the other): end both sides at about the same height,
  or centre the shorter side on the taller one; a side column that grows over time grows around the middle (shift the
  shown part as items arrive), not down from the top.

## Reading model (config/video.json "reading", applied by RAScene and checked by check_reading.py)

Text needs 0.6 s plus 0.3 s per word (200 words per minute); an equation needs 1 s plus 0.6 s per term, at least 2 s;
both 1.4 times longer while narration plays; nothing under 1 s; at most 40 words and equation terms on screen at once;
narration 130 to 150 words per minute. RAScene waits automatically before a FadeOut, Transform or removal takes text
away too early; `self.read(*mobjects)` waits explicitly (before a cut or the end card). Live readouts are exempt.

## Gotchas

- Time animations to the narration: `run_time=tracker.duration` or `tracker.get_remaining_duration()`, and
  `self.wait_until_bookmark("x")` for a word. A fixed `run_time` drifts when the voice changes.
- Voice-over text is a string literal (`text="..."`; adjacent literals are fine; no f-strings, variables or
  conditionals): CI synthesizes the narration from the parsed scene files without running them, and the pre-render
  gate fails otherwise. Say only numbers the explainer states and show live numbers on screen, never where they come
  from. Spell out symbols as spoken ("x dot", "the integral of L dt"); keep each block to one or two sentences.
- Never put a `MathTex` whose string changes every frame in `always_redraw`: LaTeX then typesets every frame. Use
  `readout()` (Pango Text) for live numbers.
- `Transform` between two different captions morphs the glyphs illegibly; use `swap_caption()` (cross-fade). On-screen
  captions are optional: the narration already produces subtitles.
- Labels next to curves: the design check measures the curve's path through the label's box and its distance to the
  box, not just boxes; move the label off the curve (`next_to` with a direction away from it) rather than shrinking
  it. MathTex renders smaller than
  Text at the same font size: 24 is the minimum for both.
- Use only the palette in `common.py` (teal-green, amber, indigo, red): the old green/red pair was indistinguishable
  for deuteranopes. Still label every meaning in text.
- Fade whole groups out. A FadeOut of one member of an on-screen VGroup makes Manim split the group into separate
  top-level mobjects, and the clutter check then counts every piece; keep labels that leave early in their own group.
- Long data (500-point curves redrawn each frame) is slow at 1080p60: precompute paths, or reveal a fixed curve with a
  ValueTracker instead of rebuilding it.
- No footage, logos, images or URLs from the news sources in scenes: the gates reject third-party media.
- Setup problems (Pango headers, Debian pip, LaTeX packages, SoX) are covered in [manim-setup.md](manim-setup.md).
