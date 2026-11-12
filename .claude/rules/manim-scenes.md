---
paths:
  - "runs/**/video/**/*.py"
  - "templates/manim/**/*.py"
---

# Manim scenes

Rules for `video/scenes/*.py`. House rules for every video: AGENTS.md, Conventions. Narration wording:
`.agents/skills/manim-video-producer/spoken-script.md`. Thresholds: `config/video.json` and `config/channel.json`,
measured by the check named in each heading.

## Scene files

- Derive from `RAScene` (`common.py`): each `with self.voiceover(text="...")` block is narrated and captioned, and
  text is held until it can be read (`reading`; check_reading.py). `self.read(*mobjects)` before a cut or the end card;
  live readouts are exempt. Plan the narration so the holds fit; never stretch the scene.
- Voice-over text is a string literal (adjacent literals allowed; no f-strings, variables or conditionals): the
  narration is synthesized from the parsed files without running them, and the pre-render gate fails otherwise.
- Time animations to the narration: `run_time=tracker.duration` or `tracker.get_remaining_duration()`,
  `self.wait_until_word("cars")` for any word or words of the block (`self.time_until_word(...)` as a `run_time`),
  `self.wait_until_bookmark("x")` for a word marked `<bookmark mark='x'/>`; never a fixed `run_time`. Piper's word
  timings are estimated per sentence: keep word-timed animations tolerant of a few tenths of a second.
- Reveal on the word (check_sync.py, `sync`): each new picture, label or equation appears when the narration names
  it: `self.wait_until_word("cars")` before its `play()`; never a group whose members are named later in one
  `LaggedStart` at the block's start; the hook's opening frame is the exception.
- Render with `bash tools/render_video.sh runs/<run> --check`, never bare `manim`.
- Only the palette and helpers of `common.py`; every colour meaning also said in text and listed in `video/README.md`;
  one colour per quantity (`ceq()`, `quantities`).
- No images, footage, logos, sound files or URLs from any source: the gates reject third-party media, and
  `assemble.py` adds the generated music. The channel's own logo is code (`brand.py`), shown only by `title_sting()`
  and `outro()`.
- Self-contained (AGENTS.md; check_selfcontained.py): LaTeX without equation numbers or tags; to use an equation
  again, show it again or `pin()` it in a corner (check_reading.py `recall`).

## Opening and ending (check_series.py)

- The hook's first picture is built with `self.add()` before the first `play()`; the thumbnail's picture (often the
  draining `meter()`) is on screen by `series.thumbnail_by_s`.
- The title beat (role `context`) comes right after the hook and carries its objects into the body, never through an
  empty frame: `self.carry_in(...)` of the hook's last picture, then `clear = title_sting(self)` (the logo sting, 2.5 s
  without narration over the dimmed picture; never in the hook), then the title on its sentence:
  `self.play(*clear, FadeIn(head), FadeIn(lower))` with `head, lower = title_beat()`.
- `outro(takeaway_card(), ...)` (the channel's logo bottom left) keeps x > `END_SCREEN_X` empty and holds picture and
  music after the last word (`engagement.outro_tail_min_s`); a question it asks aloud is also on the card, in the same
  words.
- Series: recap scenes with `recap_tag()` for the whole scene and `recap_card(i)`.

## Numbers (check_numbers.py, `numbers`)

- Every number on screen and in the narration goes through `fmt()`: no trailing zeros, exact values exactly
  (`fmt(x, exact=True)`, or "exactly zero"), a real minus sign, a space before a unit, one precision per quantity in a
  scene.
- Live numbers: `readout(label, value, decimals=k)` (fixed decimals; `sign=True` only when the sign is the point, never
  a signed zero). Never a `MathTex` in `always_redraw` (it typesets every frame), never a raw f-string format.
- Values come from `video/data/*.npz` (written by a script in `code/`) or from the explainer's equations computed in
  the scene; never typed by hand.

## Layout (check_design.py: spacing errors fail the gate)

- Text inside the graphics-safe area (`title()`, `caption()`, `SAFE_X`, `SAFE_Y`) and at least `design.min_gap_warn`
  from other text and from every strong stroke (curves, arrows, axes, box edges), crossing or not. Only a label that
  names or points at an object may sit closer to it: `attach(label, obj)`.
- Move a label off its curve (`next_to` away from it) rather than shrink it; font size at least 24 for Text and
  MathTex.
- Legends and readout blocks in fixed columns: `legend_table(rows, ...)` (`min_widths` reserves room for a cell
  swapped in later with `table.place()`); never per-row `next_to` plus a shift.
- Split layouts: both sides end at about the same height, or the shorter is centred on the taller; a growing side
  column grows around the middle.
- Plots that share an axis (time) are stacked with `stacked_axes()`, with the same range, length and left edge, so one
  instant is one vertical line.
- `swap_caption()` between captions, never `Transform`. Fade whole groups out (fading one member splits the group);
  labels that leave early get their own group.
- No `MovingCameraScene` (the checks read object coordinates): zoom by scaling the world group.
- Long data (500-point curves): precompute paths, or reveal a fixed curve with a ValueTracker.

## One moving world (check_engagement.py, `engagement`)

- The picture's content draws, moves or changes while the narration talks (`frozen_narration_*`; at least half the
  runtime moving); split long blocks with bookmarks and animate what is said. The motion measure compares grayscale
  frames at low resolution (`motion_size`), so a thin curve being drawn or a small moving dot can read as frozen:
  check such warnings on the frames.
- Emphasis is not motion: `Indicate`, `Circumscribe`, `Flash`, `pulse()` name an object once, as the narration names
  it (one short cue per new term, in the object's colour or `INK`, never the default yellow); never looped or as
  filler. A sentence during which nothing can move needs its own picture.
- One world: the metaphor (`meter()`, `plan.json` `metaphor`) and its objects stay across chapters: end a scene with
  `carry_over(self, *keep)`, start the next with `self.carry_in()` of the same objects built by the same code (an
  episode module such as `epNN_world.py`). `FadeOut(Group(*self.mobjects))` only in the last scene; inside a scene,
  transform the last picture into the next, never through an empty frame.
- Picture first, then the formula grows out of it: `TransformFromCopy(segment, term)`, `derive(self, line,
  next_line)` on `ceq(*pieces)` (unchanged pieces written identically), a `Brace` that turns into its symbol,
  `budget_bars(before, after, ...)` for every "what is lost covers what is spent" comparison.
- Faithful pictures: the dimension and units of the mathematics (a scalar example on a number line or as the graph of
  its bill, never a 2-D path); numbers only on pictures drawn to their scale. Each scene's `plan.json` `picture` is
  `faithful` or `schematic`; a schematic one shows no numbers (`meter(..., show_value=False)`, or
  `m.swap_readout(self, False)` until the worked example).
- The meter shows the episode's quantity from the hook on (from `code/` or a closed form) and along the path only
  falls. Each intended refill is in `plan.json` scenes[].`metaphor_resets` (`says`: words of the block announcing it;
  `why`), happens while or after those words, and the words state the true reason (spoken-script.md, criterion 8).
  Hypothetical points go on the bowl or a ghost meter. A body scene that shows the meter changes it, or drops it.
- Paired readouts update in the same `play()`; no conclusion narrated over a replay that moves the metaphor the wrong
  way. One name and one convention per parameter.
- No persistent slide titles; at most about `reading.max_words_on_screen_warn` words and terms on screen; on-screen
  sentences only for the takeaway.

## Pacing (check_pacing.py: rules P1-P20 in its `--help`, values in `pacing`)

- Narration markup (never read, captioned or counted):
  - `[pause S]` between sentences: a voice break of at most `voice.azure.max_break_ms`; keep it to about 2 s
    (`[pause 2]` for a stretch break). A longer pause ends the block.
  - `[pause S]` after a block's last word: a hold of the picture, any length; use holds for 2.5 s and more, and
    `[pause 1.5]` only there. Other blocks end with `voice.block_end_pause_s`; `[pause 0]`: none.
  - `[pause 0]` only when the sentence continues into the next block (P8).
  - `[slow]` first in a derivation or argument (its steps, result and "so what"): the whole block at
    `voice.azure.slow_rate_pct`; hook, title beat, recaps, transitions and outro never (P10, `slow_share_max`).
    Shorten a block the voice manifest flags `rewrite` (P20).
  - An ellipsis is a break of `voice.azure.ellipsis_pause_s`; Piper renders no planned pause inside a block.
  - Never pad or splice audio, never `self.wait()` inside a voiceover block.
- A starred result's block ends with `[pause 3]` over a still picture (no new label or equation); the next block
  restates it in plain words (P6). Other results: `[pause 1.8]` inside the block or `[pause 1.5]` at its end. Chapter
  turns 1-1.5 s (P8). No stretch without a pause beyond P7.
- Pretraining segment (P4): each concept on its own object as named, then `[pause 0.8]`; then a one-sentence summary
  and `[pause 2]`; the equation combining them only after it.
- After other key reveals, `beat(self, 2.0)`: no words, the picture still or one slow push-in (`push=1.04`), the
  music swelling. A "so what" sentence after every boxed result.
- A roadmap after the title beat, a one-sentence summary ending each long body chapter (P15, P16); think prompts
  (P11), the main one saying "pause here if you like", each followed by a held picture, the answer in the next block;
  every recap opens with the question it answers and holds the picture 2-3 s before its card.
- Each new label or equation appears no later than its words (P14) and is held before the next idea (P13), a long
  one with its restatement under the hold. Each spoken number is on screen as it is said (P12).
- Each idea is declared in `plan.json` `ideas` with a `<bookmark>` at the start of the sentence that states it.
