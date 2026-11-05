# Storyboard template (copy to runs/<run>/video/storyboard.md)
 Explainer: `../explainer.html` (a source: choose less, and different, material that tells one story; do not walk its
sections). Audience: robotics and control researchers and students. Channel: Remaining Action. The video opens with
the hook: a full, moving picture from the first frame, music from 0 s, narration by 3 s, the question by 15 s, then
the stakes; no channel card (a title beat of about 4-6 s after the hook, with the "Episode n of N" lower third, is
allowed); the body by 45 s. Then a short title beat (`title_beat()`) and the body; it ends with the outro scene (15-20
s: `outro(takeaway_card(...))`, the channel name, the teaser in a series; the right of the frame empty for the end
screen). Music per scene: `bed` in the hook, title beat and outro; `low` (at least 20 LU under the voice) or `off`
under explanation (the coherence principle: background music under narrated explanation lowers recall). Pacing:
130-150 spoken words per minute; hold each new equation 2-3 s before speaking over it. Reading time
(config/video.json): text 0.6 s + 0.3 s per word, equations 1 s + 0.6 s per term (at least 2 s), x1.4 while the
narration talks; at most 40 words and terms on screen at once. RAScene enforces the holds; plan the narration so they
fit instead of stretching the scene. Self-contained: the video never names the explainer, code, files, links or other
episodes by equation number and shows no equation numbers; refer back to an equation by showing it again or by its
meaning. Numbers through `fmt()`: 2-3 significant digits, no trailing zeros, one precision per quantity.

Craft (the review against the 3Blue1Brown bar, 2026-11-04; `tools/video/check_engagement.py` measures it): never
narrate over a frozen picture for more than 6 s (12 s is an error), at least half of the runtime moving; derive by
transform (`derive()`, `TransformFromCopy`, a brace that turns into its symbol), never by writing each line afresh;
one colour per quantity (`ceq()`, `config/video.json` "quantities"); objects carried across cuts (`carry_over()`),
no fade to an empty frame except at the very end; no persistent slide titles, at most about 25 words and terms on
screen; narration in meanings ("the cost left with one step fewer"), not symbols read aloud, talking to the viewer
("you", "we") with a question every two minutes or so. Emphasis is not motion (v4): `Indicate`/`Circumscribe`/`pulse`
name an object once and do not count as motion; at most two new technical terms per narration block; one name and
one convention per parameter; pictures with the dimension and scale of the maths they carry (a scalar example on a
number line or as the graph of its bill), and no numbers on a schematic picture.

## The episode's craft plan (fill every field)

- Visual metaphor (one object, what it means, in which scenes; `plan.json` "metaphor" with its on-screen label;
  v5: where its value changes in each scene, and every refill with the sentence that announces it, which go into
  `plan.json` scenes[].metaphor_resets; hypothetical points go on the bowl or a ghost meter; v6: the refill comes
  as or after its sentence is said, and the sentence states the true reason):
- Picture per scene (v6, `plan.json` scenes[].picture): faithful (drawn to the scale of its numbers) or schematic
  (an illustration; no numbers on it, not even in a readout):
- Misconception first (what a viewer is likely to believe, voiced, then refuted, and in which scene):
- Analogy or real-world anchor (by 90 s):
- Picture before formula (for each new equation: the picture shown first, and for how long):
- Which object becomes which (the transforms: path segment -> cost term, bar -> symbol, line -> next line):
- Colours by quantity (each quantity's colour, the same in pictures, bars and equations):
- Pause-and-ponder (the one question the viewer is asked to think about, and the beat after it):
- Planned beats (2-3 pauses of 1.5-3 s without words right after the key reveals, the picture still or one slow
  push-in, music swelling; `beat()`):
- What moves under every narration block (one line per block: the content that changes, not a highlight):
- New terms (each technical term, the block that introduces it, and its picture; at most two per block):
- Picture fidelity (for each picture with numbers: its dimension and scale match the maths; which pictures are
  schematic and therefore carry no numbers):
- Parameters (each parameter's one name and convention, as said and as shown):
- "So what" after each result (one sentence of consequence after every boxed result):
- Carried objects at each cut (what stays on screen from one scene to the next):
- Outro callback (the hook's picture again, moving) and the teaser as a picture:

## What this video leaves out of the explainer, and why

- ...

## Scene 1: <title> (<length> s, role hook) - source: explainer Section <n>

- Idea (one sentence):
- First frame (already full, `self.add()` before the first `play()`; what moves in 0-2 s, before the first word):
- First line (a claim, a question or a surprise, not set-up; spoken by 3 s):
- Question at (s, by 15 s) and the stakes (what could go wrong, why it matters):
- The picture the thumbnail uses (the episode's end picture, shown within 15 s; bold at 168 x 94: thick strokes, the
  key object large, no readouts or labels in the frame):
- Signature object (`meter()`: which quantity it shows, from which data):
- Objects carried into the title beat and the body:
- Music mode (bed | low | off):
- Data: `data/<file>.npz` from `code/<script>.py` (or: closed forms of equation (<k>))
- On screen (each item, how long it stays, reading time it needs; what moves during each narration block):
- Colours: blue = <...>, amber = <...>, green = <...> (palette in common.py; label every meaning in text too)
- End card: <the one equation or sentence to remember>

Voice-over, one block per `with self.voiceover(text="...")`, literal text, `<bookmark mark='x'/>` where an animation
must start on a word:

> 1. One idea per scene. `<bookmark mark='law'/>` Here is the equation that carries it.
> 2. ...
> 3. (end card) ...

## Scene 2: ...

## Plan (`video/plan.json`)

- Search term (what viewers type, e.g. "MPC"):
- Title (at most 60 characters shown in full, accurate, no clickbait, with the search term, without the series name):
- Summary (two to four sentences for the description):
- Tags:
- Scenes in order, each with the explainer section id it explains and its chapter title for viewers:
- Thumbnail: a frame of the hook within its first 15 s (click match: the video shows its promise at once), one bold
  picture (the signature object), text of at most three words; layout `picture` (the frame first, the title in a
  top band: keep the top fifth of the frame empty) or `panel` (nothing where the title goes, the left half)
  (tools/video/thumbnail.py composes it with the Remaining Action layout)

## Shorts (optional, not automated)

Vertical 1080x1920 cut of one scene (`manim -r 1080,1920 ...`), at most 60 s, same palette, burned-in captions.
