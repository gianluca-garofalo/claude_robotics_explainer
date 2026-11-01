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
- The first scene opens with the hook (narration from 0 s; there is no channel card); the last is the outro
  (`outro(takeaway_card(), ...)`, 15-20 s, nothing at x > `END_SCREEN_X`). Series episodes add the spoken context over
  `builds_on()` and recap scenes with `recap_tag()` and `recap_card()` (`check_series.py`).
- No images, footage, logos or URLs from the news sources in scene code: the gates reject third-party media.
- Self-contained: no text or narration names the explainer, code, files, data, links or the description; other
  episodes only by title or meaning, never by equation number or as a hard prerequisite; no equation labels or tags
  ((13), (2), (★), `\tag`, "Eq. 3"; `equation_numbers` in `config/video.json`).
  To use an equation again, show it again or `pin()` it in a corner. `tools/video/check_selfcontained.py` checks it.
