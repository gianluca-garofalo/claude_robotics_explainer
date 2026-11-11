# Spoken script

Narration is heard once, at the voice's pace: write it the way a calm, clear person talks to one listener.
`tools/video/check_script.py` counts what can be counted (config/video.json `script`; it reports, never blocks); the
reviewers score the ten criteria below. Planned pauses and slow blocks are markup (`.claude/rules/manim-scenes.md`,
Pacing): never read aloud or captioned, never a stumble.

The target register:

> Here's a controller that plans a whole path, takes a single step, and then throws the rest of the plan away. Then
> it does it again. And again. So if it keeps changing its mind, why should it ever get anywhere?

Say meanings, not symbols: "the cost of one step", while the coloured equation carries `L_d(q,q')` (spoken symbols and
new terms per block: `engagement.notation_words_per_token`, `jargon_new_per_block_warn`; each new term gets its own
picture). Spell out the symbols you do say ("x dot"). Say only numbers the explainer states, as a person says them
("about one point two eight").

Say what was found, never who published it: the result on its own terms ("a planner that solves only for the touches
handled a million robots"), caveats as facts about the evidence ("so far only idealized robots in simulation"), never
"the paper", "the authors" or "a preprint" (check_selfcontained.py); the description credits the source.

## The ten criteria

Each is scored 1-5 under its key: 1 fails throughout, 3 mixed, 5 holds everywhere.

1. **Written for the ear** (`ear`; check: pause marks, contractions, connectives): contract where speech does
   ("it's"), join clauses with connectives ("so", "which means"), never a colon, semicolon, dash or bracket as a
   pause. 1: reads like a paper; 5: every sentence could be said as written.
2. **Rhythm** (`rhythm`; check: sentence lengths and runs): a long sentence carries an idea, a short one lands it; no
   runs of short, flat sentences. 1: uniform or staccato; 5: lengths follow the meaning.
3. **One idea per sentence** (`one_idea`): subject and verb first, then the qualifications; never open on a
   subordinate clause or a list; one or two sentences per block. 1: two or three ideas, the verb late; 5: one claim,
   the verb early.
4. **Misconception, why it fails, then the fix** (`misconception`). 1: no wrong idea to beat; 3: named, not refuted
   in the picture; 5: voiced fairly, failing on screen, the fix growing from the failure.
5. **An everyday analogy in the first 90 s** (`analogy`), used again later. 1: none, or late; 3: named once and
   dropped; 5: kept in use.
6. **Real questions, "you" and "we"** (`questions`; `engagement.address_per_100_words`, `question_every_s`): ask what
   the viewer wonders at that moment and answer it; no filler ("So what does this mean?" before every result). 1: none,
   or one before every paragraph; 3: in the hook only; 5: at each turn of the argument.
7. **Signposts and re-engagement every 2-3 min** (`signposts`): say where we are and what comes next ("That's the
   first half. Now the harder part."), and bring something new every 2-3 min: a question, a turn, a surprise, a new
   picture. 1: no orientation; 3: a slack stretch over 3 min; 5: the viewer always knows where they are.
8. **Required phrases fit their scene** (`required_phrases`; check: stock): the meter resets (`metaphor_resets`
   `says`), the title beat ("episode n of N") and the teaser ("next episode") are worded for, and true in, their
   scene: "let's rewind to where it started" for a replay, "put the controller at one" for a new start. Never the same
   reset words in two scenes, never the hook's sentence as the outro's. 1: one formula in several scenes, or untrue
   where said; 5: each written for its moment.
9. **Read-aloud test** (`read_aloud`; final-stage check: the pace and pauses inside sentences): read every block
   aloud, or listen to the voice: no unnatural pause inside a sentence, no stumble over a word cluster. 1: in most
   blocks; 5: none.
10. **A calm, honest register** (`register`; check: hype): no hype ("amazing", "secret"), no condescension
    ("obviously"), no over-claiming; say plainly what the result does not show. 1: in several blocks; 3: one
    over-claim; 5: calm, precise, honest about limits ("it fails this test, by a hair").

## The rewrite pass (after the narration draft, before voicing)

Keep the facts and numbers, the scene structure, the bookmarks, each block's job and every meter reset at the moment
the meter refills. Then:

1. Read each scene's blocks aloud in order, as one passage.
2. Replace every colon, semicolon, dash or bracket used as a pause with a connective or a new sentence; contract where
   speech would.
3. Break flat runs: join two short sentences, or let a short one land after a long one.
4. Reword every required phrase for its scene. Run `python3 tools/video/check_script.py runs/<run> --stage draft` and
   fix its stock warnings, unless the phrase is a deliberate refrain (`script.refrain_allow`).
5. Timing: the hook still ends in time (check_series.py), every synced animation keeps its words, every bookmark sits
   on its word.
6. Score the ten criteria in `video/README.md` ("Spoken script": score and one line of evidence each); rewrite
   anything at 2 or less before voicing.

At the final stage `check_script.py --stage final` measures the pace and the pauses inside sentences on the narration
(`video/voice/`): a long pause inside a sentence means its punctuation misleads the voice; rewrite the sentence, never
tune the voice.

## How the reviewers score it

The video-design-reviewer (draft) and the final-cut-reviewer score the criteria with evidence (a quote and its time)
in the report's `spoken_script` (reviewer-contract.md) and as a table in the `.md`. A score of 2 or less is a finding
with the rewritten sentence: `major` for ear, rhythm, required phrases and read-aloud, `minor` otherwise. A required
phrase that is untrue where it is said is `major`. Confirm or dismiss each `check_script.md` warning by reading or
listening.
