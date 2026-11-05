---
paths:
  - "runs/**/video/**/*.py"
  - "templates/manim/**/*.py"
---

# Manim scenes

- Scenes derive from `RAScene` (in `common.py`: manim-voiceover narration plus automatic reading holds from
  `reading_model.py`); narration goes in `with self.voiceover(text="...")` blocks whose text is a string literal (CI
  synthesizes it from the parsed file, without running the scene). Use `self.read()` before cuts.
- Text stays inside the graphics-safe area (`title()`, `caption()`, `SAFE_X`, `SAFE_Y`), never touches another text
  or crosses a curve, and keeps 0.15 units from any line or shape (`attach(label, obj)` for a label that points at its
  object); `tools/video/check_design.py` checks this on every draft render, `check_reading.py` the holds.
- Legends and readout blocks in fixed columns (`legend_table()`), never staggered tags; the two sides of a split
  layout end at about the same height (a growing side column grows around the middle).
- Import the palette and helpers from `common.py`; keep the colour meanings stated in the run's `video/README.md`.
- Live numbers use `readout(label, value, decimals=k)` (Pango Text, fixed decimals; `sign=True` when the sign is the
  point, never a signed zero); never a `MathTex` inside `always_redraw`, never a raw f-string format. Every number
  on screen and in the narration goes through `fmt()` (`check_numbers.py`).
- Numbers on screen come from `video/data/*.npz` (exported by a script in `code/`) or are computed from the
  explainer's equations in the scene; never typed by hand.
- Render through `bash tools/render_video.sh runs/<run> --check` (drafts are silent), not bare `manim`. Final
  renders (Piper voice, no fallback), assembly and the final-cut review run in CI.
- The first scene opens with the hook: a full, moving picture from the first frame, music from 0 s, narration by 3 s,
  the question by 15 s, then the stakes; no channel card (a title beat of about 4-6 s after the hook, with the
  "Episode n of N" lower third, is allowed); the body by 45 s. Build the first picture with `self.add()` before the
  first `play()`; show the episode's end picture (the thumbnail's image, often the `meter()` draining) within 15 s.
  The title beat (`title_beat()`, role `context` in a series) carries the hook's objects on and hands them to the body
  instead of fading to an empty frame. The last scene is the outro (`outro(takeaway_card(), ...)`, 15-20 s, nothing at
  x > `END_SCREEN_X`). Series episodes add recap scenes with `recap_tag()` and `recap_card()` (`check_series.py`).
- Music is per scene (`plan.json` `music`: `bed`, `low` or `off`; default by role): no sound files in scene code or
  data; `assemble.py` adds the generated music.
- No images, footage, logos, audio or URLs from the news sources in scene code: the gates reject unlicensed
  third-party media (audio needs the music generator's stamp).
- Self-contained: no text or narration names the explainer, code, files, data, links or the description; other
  episodes only by title or meaning, never by equation number or as a hard prerequisite; no equation labels or tags
  ((13), (2), (★), `\tag`, "Eq. 3"; `equation_numbers` in `config/video.json`).
  To use an equation again, show it again or `pin()` it in a corner. `tools/video/check_selfcontained.py` checks it.
- Craft (`tools/video/check_engagement.py`, warnings first): keep the picture moving while the narration talks (a
  frozen frame under narration warns after 6 s, errors after 12 s); derive equations with `derive()` on `ceq()`
  pieces (one colour per quantity, `config/video.json` "quantities"), not by writing each line afresh; end scenes with
  `carry_over()` (no `FadeOut(Group(*self.mobjects))` except in the last scene); no persistent slide titles; at most
  about 25 words and terms on screen; narration says meanings, not symbols; plan `beat()`s after the reveals and a
  "so what" sentence after every boxed result; the episode's metaphor (`plan.json` "metaphor", the `meter()`) in the
  hook, most body scenes and the outro. No `MovingCameraScene`: the layout checks read object coordinates; zoom by
  scaling the world group.
- The meter means one thing (v5): along the path it only falls; each intended refill is listed in `plan.json`
  scenes[].metaphor_resets with the words of the narration block that announces it; hypothetical points go on the
  bowl or a ghost meter. No empty frame inside a scene; the outro keeps 1.5 s after its last word and shows any
  question it asks. v6: the refill comes as or after its words; each scene's `plan.json` "picture" is faithful or
  schematic, and a schematic one shows no numbers (`meter(..., show_value=False)`).
- Emphasis is not motion (v4): `Indicate`, `Circumscribe`, `Flash`, `pulse()` name an object once when the narration
  names it; never loop them to fill time (the check counts narration over emphasis alone as a frozen picture). Beats
  hold still, or make one slow push-in, while the music swells. At most two new technical terms per narration block;
  one name per parameter; pictures with the dimension and scale of the maths they carry (no numbers on schematic
  pictures); paired readouts update in the same `play()`.
