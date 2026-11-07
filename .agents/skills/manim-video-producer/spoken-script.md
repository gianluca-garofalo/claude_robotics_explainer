# Spoken script: the standard for narration

The narration is heard once, at the voice's pace, and never read. Write it the way a calm, clear person talks to
one listener. The owner found episode 1 v5's cadence unnatural. An A/B with the same Azure voice (2026-11-05)
showed that the script, not the voice, was the main cause:
- colons, semicolons and brackets used as pauses;
- runs of short, flat sentences;
- few contractions and connectives;
- stock phrases the checks require, worded generically ("start again from the same point" in the hook, where
  nothing had started yet).

The owner preferred this rewrite of the hook:

> Here's a controller that plans a whole path, takes a single step, and then throws the rest of the plan away. Then
> it does it again. And again. So if it keeps changing its mind, why should it ever get anywhere?

Two tools enforce the standard:
- `tools/video/check_script.py` counts what can be counted (config/video.json "script"; report only, at the draft
  and final stages);
- the reviewers score the ten criteria below, 1 to 5, with a quote and a time as evidence.

Pauses are part of the script (v7, the pacing rules; SKILL.md "Pacing"): write `[pause S]` where the listener needs
time (3 s after a starred result, 1.5 s after other results, at chapter ends), and `[slow]` before the first word
of a derivation or an argument, which the voice then reads as a whole at -15 %. They are directions to the voice and
to the scene, never read aloud, never in the captions; a planned pause is not a stumble (criterion 9).

Sources:
- **INSPIRATION** is the research note on successful channels behind the craft rules. Its rule table numbers the
  rules: rule 7 says narration speaks meanings conversationally, rule 8 covers designed pauses and re-engagement,
  and rule 20 is the anti-template guard. It also has a channel table and a section on the evidence.
- **A/B** is the owner's voice test of 2026-11-05.

## The ten criteria

Each criterion has a 1-5 scale: **1** fails throughout, **3** mixed (some blocks pass, some do not), **5** holds
everywhere. The anchors below say what 1, 3 and 5 look like.

1. **Written for the ear.** Use contractions where speech uses them ("it's", "can't", "here's"). Join clauses with
   connectives ("so", "but", "which means", "and then"). Never use a colon, semicolon, dash or bracket as a pause:
   the listener hears punctuation only as the voice's pauses, and the voice puts odd ones there.
   *Source:* A/B (pause marks 2.3 per 100 words in v5, 0.9 in the rewrite; contractions 1.1 and 2.6; connectives
   1.1 and 7.0); INSPIRATION evidence section 3 (Mayer's personalization principle: a conversational style beats a
   formal one). *Check:* pauses, contractions and connectives.
   *1:* reads like a paper, with colons introducing every result. *3:* contractions in some blocks, and the
   formulas still introduced by colons. *5:* every sentence could be said as written; no pause marks.
2. **Rhythm.** Vary sentence length: a long sentence that carries an idea, then a short one that lands it. Don't
   string together runs of short, flat sentences.
   *Source:* A/B (sentence-length spread 2.8 words in v5, 5.8 in the rewrite, which sets 21, 5 and 2-word sentences
   side by side); INSPIRATION rule 8 (pace may vary from block to block). *Check:* rhythm (mean, spread, runs of 3
   or more sentences under 8 words).
   *1:* every sentence 10-14 words, or staccato runs. *3:* varied in places, with a flat stretch. *5:* lengths vary
   with the meaning, and short sentences mark the turns.
3. **One idea per sentence, subject and verb up front.** The listener can't look back. Say who does what first,
   then the qualifications. Never open on a subordinate clause or a list.
   *Source:* INSPIRATION channel table (MATLAB Tech Talks: short parts, one reason at a time; The Efficient Engineer:
   "crisp, no-nonsense"); this skill's rule of one or two sentences per voiceover block.
   *1:* two or three ideas per sentence, with the verb late. *3:* mostly clear, with a few nested sentences.
   *5:* each sentence makes one claim, and the verb arrives within the first few words.
4. **Misconception, why it fails, then the fix.** Voice what a viewer is likely to believe, show why it doesn't
   hold, and only then give the right idea.
   *Source:* INSPIRATION evidence section 1 (Muller: purely expository videos can raise confidence in wrong ideas);
   channel table (Reducible: a naive argument, why it fails, the fix; Sebastian Lague: try, fail, improve);
   rule 5.
   *1:* the result is stated with no wrong idea to beat. *3:* a misconception is named but not refuted in the
   picture. *5:* the tempting idea is voiced fairly, fails on screen, and the fix grows out of that failure.
5. **An everyday analogy in the first 90 s.** Give one picture from ordinary life that the viewer already
   understands, and use it again later.
   *Source:* INSPIRATION channel table (MATLAB Tech Talks: MPC as a driver previewing the road); rule 12.
   *1:* none, or only after 90 s. *3:* an analogy named once and dropped. *5:* an analogy by 90 s that the narration
   keeps using (in episode 1, the bill still left to pay).
6. **Real questions and "you / we", not filler.** Ask a question the viewer is actually wondering about at that
   moment, and answer it. "You" and "we" do the work together. Avoid rhetorical filler ("So what does this mean?"
   before every result).
   *Source:* INSPIRATION rule 7 ("you / we" at least once per 100 words, a question every couple of minutes);
   channel table (Reducible: "how would *you* invent this?"); evidence section 3 (personalization).
   *1:* no questions, or a question before every paragraph. *3:* real questions in the hook only. *5:* a real
   question at each turn of the argument, with "you" and "we" throughout.
7. **Signposts and re-engagement every 2-3 min.** Say where we are and what comes next ("That's the first half.
   Now the harder part."). Every 2-3 minutes, give the viewer something new: a question, a turn, a surprise or a new
   picture.
   *Source:* INSPIRATION rule 8 (a re-engagement beat at least every 2-3 min); evidence section 9 (the first-minute
   doctrine: plan re-engagement points); channel table (Welch Labs: cliffhangers).
   *1:* one long stretch with no orientation. *3:* chapter turns marked, with a slack stretch longer than 3 min.
   *5:* the viewer always knows where they are, and something new arrives every 2-3 min.
8. **Required phrases fit their scene; never stock.** The checks require some words:
   - meter resets (`plan.json` metaphor_resets "says");
   - the title beat ("episode n of N");
   - the teaser ("next episode").
   Word each one for what happens in its scene. Say "let's rewind to where it started" for a replay, and "put the
   controller at one" for a new start. Don't reuse the same reset words in two scenes. Don't reuse the hook's
   sentence as the outro's.
   *Source:* A/B ("start again from the same point" in the hook, before anything had started); INSPIRATION rule 20
   (anti-template guard: repeated templates read as mass-produced, evidence section 8, YouTube's inauthentic-content
   policy). *Check:* stock (configured stock phrases, phrases repeated across scenes, the same reset words twice).
   *1:* the same formula in several scenes, or a phrase that isn't true where it is said. *3:* true everywhere,
   with one or two generic phrasings. *5:* each required beat sounds written for its moment.
9. **Read-aloud test.** Read every block aloud at about 140-160 words per minute, or listen to the synthesized
   voice. There should be no unnatural pause inside a sentence and no stumble over a word cluster. Spell out
   numbers and symbols the way a person says them.
   *Source:* INSPIRATION rule 8 (pace 130-160 words per minute); A/B (Samuel paused at the v5 colons); config/video.json
   reading.narration_wpm_*. *Check:* pace and mid pauses (final stage: words per minute, and pauses over 0.7 s inside
   a sentence, from the word timings).
   *1:* stumbles and odd pauses in most blocks. *3:* a few. *5:* none; it sounds like someone talking.
10. **A calm, honest register.** Don't use hype words ("amazing", "mind-blowing", "secret"). Don't condescend
    ("obviously", "trivially"). Don't over-claim. Let the result's strength speak, and say plainly what it doesn't
    show.
    *Source:* INSPIRATION channel table (Sebastian Lague: the calm, non-bombastic voice is part of the appeal; The
    Efficient Engineer: no-nonsense; Veritasium: truthful curiosity, not clickbait). *Check:* hype.
    *1:* hype or condescension in several blocks. *3:* calm, with one over-claim. *5:* calm and precise throughout,
    and honest about limits ("it fails this test, by a hair").

## The rewrite pass (after the narration draft, before voicing)

The first draft gets the facts and the structure right. The rewrite pass makes it sound spoken without changing
what it says. It keeps:
- the facts and the numbers (the numbers on screen still come from `fmt()` and `readout()`, and the spoken ones
  stay the ones the explainer states);
- the scene structure, the bookmarks and each block's job;
- every meter reset, at the moment the meter refills.

Then:
1. Read each scene's blocks aloud in order, as one passage.
2. Replace every colon, semicolon, dash or bracket used as a pause with a connective or a new sentence ("which
   means", "so", "that's"). Contract wherever speech would.
3. Break flat runs. Join two short sentences with a connective, or let one short sentence land after a long one.
4. Reword every required phrase for its own scene. Run `python3 tools/video/check_script.py runs/<run> --stage
   draft` and fix its stock warnings, unless a phrase is a deliberate refrain (`script.refrain_allow`).
5. Check the timing:
   - the hook stays at or under 45 s (fewer words if the rewrite grew);
   - every animation synced with `tracker.duration` or a bookmark still has the words it needs;
   - a bookmark stays on the word it marks.
6. Score the draft against the ten criteria in `video/README.md` (a "Spoken script" table: score, one line of
   evidence). Anything at 2 or less gets rewritten before voicing.

At the final stage, `check_script.py --stage final` adds the pace and the mid-sentence pauses from the synthesized
narration (`video/voice/`). A pause over 0.7 s inside a sentence usually means the punctuation there misleads the
voice: rewrite the sentence rather than tuning the voice.

## How the reviewers score it

`video-design-reviewer` (draft) and `final-cut-reviewer` (final cut) score the ten criteria 1-5 with evidence (a
quote and its time). They write the scores in their report as `"spoken_script": {"ear": {...}, "rhythm": {...},
"one_idea": {...}, "misconception": {...}, "analogy": {...}, "questions": {...}, "signposts": {...},
"required_phrases": {...}, "read_aloud": {...}, "register": {...}}`, each `{"score": n, "evidence": "..."}`, and as a
table in the `.md`. A score of 2 or less is a finding with the rewrite. It is `major` for criteria 1, 2, 8 and 9,
the cadence problems the owner flagged, and `minor` otherwise. `check_script.md` is evidence; confirm or dismiss
its warnings by listening.
