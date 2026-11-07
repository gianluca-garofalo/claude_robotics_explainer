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
   depth a video can carry, and say what is left out. A series episode teaches the ideas of its plan entry and no
   more (`video/episode.md`, "Ideas": their budget sets the length); a result the plan does not list goes back to the
   series plan (`tools/series.py validate`), never into the video. The storyboard's pacing plan places each idea,
   the roadmap, the summaries, the restatements, the think prompts, the recap and every planned pause (see "Pacing"). Scenes of one idea each, 30 to 120 s;
   the opening hook (a full, moving picture from the first frame, music from 0 s, narration by 3 s, the question by 15
   s, then the stakes; no channel card (a title beat of about 4-6 s after the hook, with the "Episode n of N" lower
   third, is allowed); the body by 45 s; its first frame, first line, question, stakes and the picture the thumbnail
   uses are storyboard fields), the title beat (`title_beat()`) and the outro (15-20 s; v5: at least 1.5 s of
   picture and music after the last word, and a question asked aloud there also on the card; `outro()`: the takeaway card,
   the channel name, the right of the frame empty for the end screen); the music mode of each scene (`bed` in the
   hook, title beat and outro; `low` or `off` under explanation: background music under a narrated derivation lowers
   recall); the voice-over text with `<bookmark mark='x'/>` cues; what is on screen at each moment and how long it
   must stay (reading model below); the sources and data each scene uses. A series episode adds its beats from
   `video/episode.md` (see the `produce-episode` skill).
2. **Data.** Export what the scenes show with a script in `code/` (listed in `checks.toml`) that writes
   `video/data/<name>.npz`, or recompute closed forms from the explainer's equations. Nothing on screen is typed by hand.
3. **Scenes.** Copy `templates/manim/common.py`, `voice.py`, `reading_model.py` and `scene_template.py` into
   `video/scenes/`, one file per scene, rename the class. Scenes derive from `RAScene` (narration plus automatic reading
   holds); every `with self.voiceover(text=...)` block is narrated and becomes a caption. Place titles and captions with
   `title()` and `caption()` (graphics-safe area). Copy LaTeX from the explainer without its equation numbers or tags.
4. **Spoken-style rewrite pass** (after the narration draft, before any voicing; [spoken-script.md](spoken-script.md)).
   Read each scene's voiceover blocks aloud in order and rewrite them for the ear. Keep the facts, numbers, scene
   structure, bookmarks and meter resets. Remove colons, semicolons, dashes and brackets used as pauses, use
   contractions and connectives, vary sentence length, and word each required phrase (meter resets, title beat,
   teaser) for its own scene. Then run `python3 tools/video/check_script.py runs/<run> --stage draft` and score the
   ten criteria in `video/README.md` ("Spoken script": a score and one line of evidence each). Rewrite anything at 2
   or less.
5. **Plan** (`video/plan.json`, format in `tools/video/plan.py`): `title` (at most 90 characters, accurate, no
   clickbait), `summary` (two to four sentences for the description), `tags`, `scenes` in order with the explainer
   `section` id each one draws on (a source, for the review), its `chapter`, the title viewers see (written for the
   video, never the explainer's heading), its `role` (`hook` first, `outro` last; `context` and `recap` with
   `recap_of` in series episodes), its `music` mode when it differs from the role's default, `search_term` (the words
   viewers search for; the title, at most 60 characters, contains it and not the series name), and `thumbnail`
   (`scene` and `time`: a frame of the hook within its first 15 s, so the promise is shown early; `text` of at most
   three words; `layout` `picture` for a frame-first thumbnail with the title in a top band, keeping the top fifth of
   that frame empty, or `panel` with nothing where the title goes, the left half). `python3
   tools/ci/scene_matrix.py runs/<run>` must accept it; `check_series.py` warns about the opening and the packaging.
   v7: `ideas`, every idea unit where it lands (the plan's concepts, claims and starred results by their ids, and the
   roadmap, summaries, restatements, think prompts and recap), each with its `scene` and the `bookmark` at the start of
   the sentence that states it (or `says`), and `shows` for the picture that carries it; `glossary` for the episode's
   own terms. `tools/video/check_pacing.py` measures the rules on them.
6. **Draft check:** `bash tools/render_video.sh runs/<run> --check` (every scene at -ql, silent, with captions and
   layout logs), then
   `python3 tools/video/check_design.py runs/<run> --stage draft`,
   `python3 tools/video/check_reading.py runs/<run> --stage draft`,
   `python3 tools/video/check_numbers.py runs/<run> --stage draft`,
   `python3 tools/video/check_selfcontained.py runs/<run> --stage draft` and
   `python3 tools/video/check_series.py runs/<run> --stage draft` and
   `python3 tools/video/check_engagement.py runs/<run> --stage draft` and
   `python3 tools/video/check_script.py runs/<run> --stage draft` and
   `python3 tools/video/check_pacing.py runs/<run> --stage draft` (silent drafts keep the planned pauses, so the
   draft timeline is the final one). Fix every error (the pacing errors: under 2.5 s of silence after a starred
   result, a stretch over 90 s without a 1.5 s pause, a rate below -20 %); read the warnings (spacing,
   space use, motion, recall load, opening and ending, series beats, and the engagement report: frozen frames under
   narration, transforms, fades to empty, spoken symbols, slide titles, beats, the metaphor; and the spoken-script
   report: pause marks, contractions, connectives, rhythm, stock phrases, hype).
7. **Design review:** start the `video-design-reviewer` subagent on the run (it looks at the sampled frames and contact
   sheets in `review/design/draft/`), then one `finding-verifier` per blocker or major `VD-` finding, then
   `python3 tools/merge_reviews.py runs/<run> --set video`. Fix confirmed blockers and majors, record decisions in
   `review/video/resolutions.json` (same format as the explainer's), re-render, re-run step 6 and the merge. At most two
   rounds; open blockers stop the run at the gate.
8. **README:** `video/README.md` with scene -> file -> explainer section -> data and script, the colour meanings, and
   the voice: Azure Steffan HD by default, an AI voice disclosed in the description (`voice.service` and `voice.azure_voice` in `config/channel.json`; the keys
   `AZURE_SUBSCRIPTION_KEY` and `AZURE_SERVICE_REGION` come from the environment, never a file), Piper as the keyless
   voice (`--voice piper`), or `python3 tools/video/voice_script.py runs/<run>` lists the blocks to record for the
   user's own voice; and the "Spoken script" scores of step 4.

## Craft: one moving world, not a slide deck (tools/video/check_engagement.py; warnings first)

An independent review of episode 1 against the 3Blue1Brown bar (2026-11-04) measured the habits that make a narrated
slide deck; the storyboard's craft plan and these helpers in `common.py` avoid them:
- **Motion budget.** Something draws, moves or changes while the narration talks: a frozen picture under narration
  warns after 6 s and is an error after 12 s; aim for at least half of the runtime moving. Split long narration
  blocks with bookmarks and animate what is being said (`run_time=tracker.duration`).
- **Emphasis is not motion (v4).** `Indicate`, `Circumscribe`, `Flash` and `pulse()` name an object once, when the
  narration names it; narration over emphasis alone counts as a frozen picture (`layout_probe.py` logs every play),
  and an emphasis call in a loop, more than four per minute, or emphasis under more than a fifth of the narration
  are warnings. If nothing in the picture can move while a sentence is said, the sentence needs its own picture.
  Signal, do not pulse (v5): emphasis is still the right tool once, when a term or object is first named (Mayer's
  signaling principle); episode 1 v4 dropped it altogether, and new terms arrived with no cue. One short `Indicate`
  or colour flash per new term is within every limit above. Give the cue the object's own colour (or INK):
  `Indicate`'s default yellow is off the palette and reads as the amber of a cost (v6).
- **One world.** The episode's metaphor (`meter()` in this channel) and its objects stay on screen across chapters:
  end a scene with `carry_over(self, *keep)` and start the next with `self.carry_in()` of the same objects built by
  the same code (their texts count as read, so no reading hold freezes the first frame) (an episode module such as `epNN_world.py`). `FadeOut(Group(*self.mobjects))` belongs only to the last
  scene. Declare the metaphor in `plan.json` "metaphor" (`{"name": ..., "label": "left to pay"}`).
- **Picture first, then the formula grows out of it.** `TransformFromCopy(segment, cost_term)`; derivations with
  `derive(self, line, next_line)` (TransformMatchingTex plus a highlight beat on what changed) on `ceq(*pieces)`,
  which colours each quantity by `config/video.json` "quantities"; a `Brace` under "the rest of the sum" that turns
  into its symbol. Write the pieces that stay the same identically, so they stay put. An equation assembled from its
  pieces (`TransformFromCopy` into a piece, `FadeIn` of a piece, `LaggedStart` over the pieces) is checked like any
  text from v6 on: `layout_probe.py` logs it as one equation (before, its pieces were paths, and the design and
  reading-time checks never saw it: v5's chain of inequalities crossed by the bowls passed).
- **One picture per inequality.** `budget_bars(before, after, ...)` (blocks coloured by quantity) for every
  "what is lost covers what is spent" comparison of the episode.
- **Narration in meanings.** Say "the cost of one step" and let the coloured equation carry `L_d(q,q')`; at most one
  spoken symbol per 25 words; "you" and "we"; a question every couple of minutes; voice the likely misconception
  before the right idea. At most two new technical terms per narration block (`engagement.jargon`), each with its
  own picture: "Lyapunov function, asymptotically stable, terminal cost and terminal set" in one sentence is four.
- **One name per parameter.** A parameter keeps one name and one convention for the whole video ("the weight 1.2 of
  the end cost W = 1.2 * q^2/2" makes the textbook choice "weight 1", never "one half").
- **Faithful pictures.** The picture has the dimension and the units of the mathematics it illustrates: a scalar
  example is a number line or the graph of its bill V(q) (a bowl the dot slides down), never a 2-D path; numbers
  on screen sit on a picture drawn to their scale. Schematic pictures carry no numbers: say which a scene's picture
  is in `plan.json` (`"picture": "faithful"` or `"schematic"`, every scene, v6), and `check_engagement.py` warns at
  a live readout with digits or a decimal on a schematic one (episode 1 v5: "left to pay = 0.039" over the hook's
  2-D path in the title beat, because `meter()` shows its value unless told `show_value=False`).
- **Readouts and replays.** Paired readouts ("this step", "left to pay") update in the same `play()`; never say a
  conclusion over a rewind or a replay in which the metaphor moves the wrong way (the bill climbing while the
  narration says "certified").
- **The meter means one thing (v5).** Along the controller's path the bill only falls. `layout_probe.py` logs the
  meter's value (`meter()` sets `ra_value`), and `check_engagement.py` warns at every refill that `plan.json` does not
  declare: a scene lists its intended refills as `"metaphor_resets": [{"says": "<words of the narration block that
  announces it>", "why": "..."}]`, and the narration must say it, in words written for that scene (spoken-script.md,
  criterion 8: "let's rewind to where it started" for a replay, "put the controller at one" for a new start; never
  the same reset words in two scenes). v6: the meter refills while or after those words are said, never seconds before them (v5 refilled at a
  cut, 3.6 s before "start again"); and the words state the real reason: "start again from the same point" is true
  of a replay, not of a new example at a new point. A scan over hypothetical points belongs on the bowl or on a ghost meter, not on the meter (episode 1 v4:
  the meter refilled from 0.119 to 0.586 with no step paid, and climbed just before "the bill only goes down"). A
  body scene that shows the meter without ever changing it gets a warning too: let it follow the argument or leave it
  out of that scene.
- **No empty frame inside a scene (v5).** Transform the last picture into the next, or keep the meter on screen,
  instead of clearing the frame (v4's outro went blank for 0.3 s between the meter and the card).
- **Pacing (v7, the owner's pacing rules: `config/video.json` "pacing", `tools/video/check_pacing.py`).** Episode 1
  v6 ran at an ordinary 150 words per minute and was still hard to follow: too many ideas, and no time to take them
  in (2.2 s after its starred results, a median 0.26 s between blocks, 131 s without a pause). Time comes from
  pauses, and from reading the derivations and arguments slowly as whole blocks, never from slowing single sentences:
  - **Planned pauses are markup in the narration.** `[pause 2.5]` between two sentences of a block is an Azure
    `<break>` (at most `voice.azure.max_break_ms`, 4 s); `[pause S]` after a block's last word is a hold of the
    picture after the block (any length; `RAScene` plays a `Hold`), and every block ends with
    `voice.block_end_pause_s` (0.75 s) unless it ends with its own tag (`[pause 0]`: the next block follows at once).
    A pause longer than 4 s ends the block. The audio is never padded or spliced. Captions, word counts and the
    checks never see the markup. Prefer a hold for the long pauses (2.5 s and more: after a starred result, after a
    think prompt, at a chapter end): end the block there with `[pause 3]` and start the next block with the
    restatement or the answer. A hold is exact; Azure HD stretches a long break by seconds now and then (measured
    2026-11-07; the take check retakes it, at the cost of more takes). Keep breaks inside a block to about 2 s. The
    checks count a pause as a break in the flow from 1.5 s, and Azure returns a 1.5 s break as 1.46-1.76 s: so
    `[pause 2]` for a stretch break inside a block, `[pause 1.5]` only as a hold at a block end.
  - **After a starred result: at least 2.5 s of silence (3 s intended; an error below 2.5 s), then its plain-words
    restatement** within 10 s ("In words: ..."), declared in `plan.json` (`kind` `restatement`, `of`): the starred
    result's block ends with `[pause 3]`, and the picture holds still in it (no new label or equation). After other
    results 1.5 s (`[pause 1.8]` inside the block, or `[pause 1.5]` at its end); after a concept named in the
    pretraining segment 0.8 s; at a chapter turn 1-1.5 s.
  - **Slow blocks.** A derivation or an argument (the steps that lead to a result, the result itself, its "so
    what") is a slow block: `[slow]` before its first word, and Azure reads the whole block at
    `voice.azure.slow_rate_pct` (-15 %); everything else (the hook, the title beat, recaps, pictures described,
    transitions, the outro) stays at the base rate (-8 %). The owner chose this by ear on 2026-11-07, over slowing the
    key sentences alone, so `[key]` is retired: a starred result or think prompt that should be read slowly sits in
    its derivation's slow block, or in a slow block of its own (end the block before it; the holds around a block
    mark it off as well). Keep slow blocks to the derivations, at most two-thirds of the body's narration (P10 warns
    above it): the contrast with the rest is the only rate signal left. A slow block lasts about 8 % longer: plan its
    stretch breaks by time (P7), and the idea budget already counts the slower reading. Never anything below -20 %
    (an error). A block the pace cap cannot fix
    (breaks, then -15 %, where a slow block already starts) is flagged "rewrite" in the manifest: shorten it.
  - **Structure:** a roadmap within 20 s after the title beat; a one-sentence summary at the end of every body chapter
    over 90 s (chapters of 60-120 s); a think prompt every four minutes of body, the main one saying "pause here if you
    like", followed by 3.5-4 s of held picture, its answer in the next block; a recap of about 20 s before the outro.
    Open a recap of an earlier episode, and the end recap, with the question it answers ("Last time: what did one
    step of planning do to the bill?"), the picture held 2-3 s, then the card: recalling beats re-reading
    (retrieval practice; about 4 s per recap).
  - **The picture comes first:** each new label or equation is on screen no later than its words (at most 1.5 s after
    them), and a new equation is held max(3 s, 1 s per new symbol + 0.3 s per familiar one), at most 6 s, before the
    next idea; a longer one gets a restatement under the hold.
  - After the other key reveals (not a starred result: its block ends with `[pause 3]`) a `beat(self, 2.0)` (a
    `Hold`: no words, the picture still or one slow push-in, `push=1.04`) while the music swells; music-off scenes get a "low" swell in pauses of 1.8 s or more
    (`config/channel.json` music.off_beat_swell_s), so a beat is never digital silence. Holds of up to 4 s (8 s with a
    restatement) are exempt from the frozen-picture warnings. A "so what" sentence after every boxed result. An
    ellipsis inside a block still makes a 0.7 s break; Piper (the keyless voice) renders no planned pause inside a
    block.
- **Text economy.** No persistent slide titles (the chapter list names the chapter); at most about 25 words and terms
  on screen; on-screen sentences only for the takeaway.
- **Camera moves** (`MovingCameraScene`) are not supported yet: `layout_probe.py` and `check_design.py` read object
  coordinates, not the camera frame. Zoom by scaling the world group instead (the checks then stay correct).

## Spoken script (the standard in [spoken-script.md](spoken-script.md); tools/video/check_script.py reports)

Narration is heard once and never read, so write it for the ear. The reviewers score ten criteria from 1 to 5;
spoken-script.md gives the source and scale anchors for each:
1. Written for the ear: contractions and connectives, and no colons, semicolons, dashes or brackets as pauses.
2. Rhythm: varied sentence length, and no runs of short, flat sentences.
3. One idea per sentence, with the subject and verb up front.
4. The misconception, why it fails, then the fix.
5. An everyday analogy in the first 90 s.
6. Real questions and "you / we", not filler.
7. Signposts and re-engagement every 2-3 min.
8. Required phrases (meter resets, title beat, teaser) worded to fit their scene, never stock.
9. The read-aloud test: no unnatural pause inside a sentence, and about 140-160 words per minute.
10. A calm, honest register with no hype words.

`check_script.py` counts what can be counted (thresholds in config/video.json "script"):
- pause marks per 100 words;
- contractions and connectives;
- the mean and spread of sentence length, and runs of short sentences;
- phrases repeated across scenes;
- hype words;
- at the final stage, the pace, and pauses over 0.7 s inside a sentence, from the narration's word timings.

It reports and does not block (`script.errors_block_gate`). The voice (Azure) places its own pauses at commas and
sentence ends; the narration plans the others with `[pause S]` (see "Pacing"); an ellipsis ("...") still becomes a
break of `voice.azure.ellipsis_pause_s`. A planned pause is never reported as a stumble.

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
narration 130 to 150 words per minute; check_reading.py warns above 25 words and terms on screen. RAScene waits automatically before a FadeOut, Transform or removal takes text
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
- No footage, logos, images, sound files or URLs from the news sources in scenes: the gates reject unlicensed
  third-party media. Music is never added in a scene: `assemble.py` mixes the generated music by the plan's modes.
- `meter(value, vmax)` is the channel's signature object (a bar that drains, with a live `readout()`): use it for the
  quantity the episode is about, from the hook on; the value comes from `code/` or a closed form. While its level is
  schematic (a picture of the argument, not the worked numbers), show the label alone: `meter(..., show_value=False)`
  or `m.swap_readout(self, False)`; switch the number back on for the worked example.
- Setup problems (Pango headers, Debian pip, LaTeX packages, SoX) are covered in [manim-setup.md](manim-setup.md).
