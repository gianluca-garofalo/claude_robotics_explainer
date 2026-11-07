# Storyboard: Why Does MPC Converge? A One-Step Proof (episode 1 of 8, version 7)

Explainer: `../explainer.html` (a source: this video tells one story with less, and different, material). Audience:
students and engineers who have heard of MPC and want the stability argument in one line. Channel: Remaining Action.
One story on one picture: the controller's bill (the remaining action, on a meter) can only fall, by at least each
step's cost, because the old plan shifted by one step plus one reference step is always available, and one test on
that single step pays for it. Version 7 is built under the pacing rules of 2026-11-07 (`config/video.json` "pacing",
rules P1-P20): v6 was judged too fast to absorb (about 16 claims and 25 concepts in ten minutes, 2.2 s after its
starred results, 0.26 s between blocks, 131 s without a pause).

## What changed against v6 (released 2026-11-06)

- **Scope (the committed eight-episode plan).** The recursion, the principle of optimality, monotonicity and "a longer
  window is never worse" moved to episode 2: the Corollaries scene is gone. Episode 1 teaches the 18 ideas of
  `video/episode.md` and no more: 5 pretraining concepts, the reference step, the descent (starred), feasibility and
  stability (claims) with their two names, the one-step bill, the textbook names, the one-step test (starred), the
  window not mattering, and the example with its two consequences.
- **Time per idea.** 12.9 min for those ideas (v6: 10.1 min for about twice as many). The two starred results are 3 s
  of held, still picture each, then restated in plain words; every claim is followed by 1.8 s or more; no stretch
  of narration runs longer than 41.5 s without a pause of 1.5 s (v6: 106 s); blocks are 1.9 s apart (median; v6
  0.30 s). Times in this file are the Azure narration's (the final cut), not the silent drafts'.
- **Structure.** A roadmap after the title beat, a pretraining segment (five concepts, each named on its own object
  as it is said, then a summary, and only then the line that combines them), four think prompts (the main one says
  "pause here if you like" and is held 4 s), a one-sentence summary at the end of every long chapter, and an end
  recap that opens with its question.
- **Slow blocks.** The derivations and arguments, the definitions of the pretraining segment and the think prompts
  are read as `[slow]` blocks (-15 %); the hook, the title beat, transitions, pictures described, the recap and the
  outro stay at the base rate (-8 %). 40 % of the body's narration time is slow (at most 67 %).
- **Fewer symbols.** Four equations in the body instead of thirteen: the window problem in its short form
  V_N(q) = min[sum L_d + W] (three new symbols, after the summary), the bars as one line, the descent, and V_1 <= V_0.
  The test is shown as bars on the end-cost bowl and said in words; the chain of inequalities is left to the picture.
  The example's parameters are words on screen ("time step 0.1", "end cost weight 1.2"), not formulas.
- **Fewer spoken numbers.** Six in the example (0.6, 0.59, 0.11, 0.12, 0.24 and the weight 1.2), at most three in any
  20 s and each on screen as it is said (v6: seventeen, five in 20 s). The textbook comparison (its two bars, and the ratio readout at 1.01)
  is shown, not said.
- **Kept from v6.** The hook (narration with pacing markup), the title beat (now "of eight"), the bill as a meter
  that only falls, the shifted-plan bars, the slice through the target with its bowls, the walls of the bill with no
  steps left, the worked example's four logged steps (paired readouts for the spoken first one), the textbook comparison, the outro's silent
  callback and closing question, and all music modes. The meter's fills are declared and said in their own words:
  two in v7 (Bill's first fill, the example's new start), since the hook now holds the meter until it is named.

## The episode's craft plan

- Visual metaphor: the remaining-action meter (`meter()`, `plan.json` "metaphor", label "left to pay"), in the hook,
  every body scene and the outro's callback. Where its value changes: hook: held through the first run (it is not
  named yet), then drains with every step of the replay after "watch what's left to pay" (so the rewind needs no
  refill); title beat: drains to empty at the cut to the body's start; Bill: fills once, with the
  cheapest plan's stack, on "Now look at the meter" (declared); ShiftedPlan: drains from the bill to what is
  left from the new point as the descent is said; WhatItBuys: drains with the dot down the bowl; OneStepTest: set
  aside (said aloud: "its meter is empty, so let's set it aside") and back, still empty; Example: fills at "put the
  controller at one" (declared; a new start on the example's axis) and drains with the four steps; Recap: falls step
  by step under "Each time, the bill drops"; Outro: drains to the floor in the callback. Hypothetical points go on
  the bowl or a ghost dot (the ratio scan), never on the meter.
- Picture per scene (`plan.json` "picture"): Hook, SeriesContext, Bill, ShiftedPlan, WhatItBuys, OneStepTest, Recap
  and Outro schematic (no numbers: the meter shows its label alone); Example faithful (bowls and bars to the meter's
  scale, readouts at two decimals).
- Misconception first (ShiftedPlan): "The controller plans again at every step, and every plan is the best it can
  find. Surely that's enough to get there?" Refuted: "Today's best plan says nothing about how tomorrow's bill
  compares with today's", with a ghost bill wobbling up and down; the real question then becomes the main think
  prompt, and the shifted plan answers it.
- Analogy by 90 s: the bill ("watch what's left to pay" at 0:25; "like charges on a bill" at 1:31), used to the end.
- Picture before formula: the window problem grows out of the meter, the amber segments and the green end point
  (V_N(q) shown before "In symbols" is said); the inequality out of the meter, the "step paid" block and the blue
  "left to pay, from here" block; the descent out of the inequality (derive); V_1 <= V_0 out of the legend's two
  rows ("one step left", "no steps left").
- Which object becomes which: path segments -> amber blocks -> the sum term; the plan's end -> the green block -> W;
  the meter -> V_N(q); "step paid" block -> L_d(q,q+); "left to pay, from here" -> V_N(q+); the reference step's
  cost and the new end cost replace the old end cost under its old top; the legend rows -> V_1 and V_0.
- Colours by quantity (`config/video.json` "quantities", `ceq()`): blue = the remaining action V (meter, bowls of the
  bill, "left to pay" blocks, the drop bracket); amber = the cost of a step L_d (segments, cost blocks and bars);
  green = the end cost W and its region (end-cost blocks and bowl, the region); ink = the state and the reference
  step, boxes around results; red = failure, always with the word "fails".
- Think prompts: (1) main, ShiftedPlan 3:36: "After one step, is there a plan from the new point that costs no more
  than today's bill, minus the step we just paid? Pause here if you like." held 4 s, still; answered in the next
  block ("The answer is yes"). (2) OneStepTest 7:47: "And now take a point outside the region. With no steps left,
  what's the bill there?" held 3.8 s; answered ("The bill out there is infinite"). (3) OneStepTest 8:49: "What's in
  it, and what's missing?" held 4.4 s; answered ("The answer is the window"). (4) Example 10:07, a prediction: "With a
  single step to plan, will this end cost pass the test?" held 3.8 s; answered by the numbers.
- Planned beats: the starred results end their blocks with `[pause 3]` (still picture); other reveals end with
  holds of 1.5-2.5 s; a 2.5 s hold after "every plan gets its own total" (the viewer can pick the cheapest before it
  is named).
- What moves under every narration block: listed per scene below ("On screen").
- New terms (one per sentence; the glossary terms of `plan.json` and `pacing.glossary`): stage cost (Bill 1:25),
  end region (1:52), end cost (2:20), remaining action (2:36), reference step (ShiftedPlan 4:19), Lyapunov function
  (WhatItBuys 6:27), asymptotic stability (6:55), one-step bill (OneStepTest 8:06), terminal cost and terminal set
  (9:20, two sentences). Each appears as a label on its own object as it is said.
- Picture fidelity: the example is drawn to scale (one coordinate, the bills as bowls to the meter's scale, the drop
  and the cost as bars to scale); the plane of the hook and of Bill/ShiftedPlan, the bars of the argument and the
  schematic bowls of WhatItBuys/OneStepTest carry no numbers.
- Parameters: "weight 1.2" (end cost 1.2 x the textbook's 1/2 q^2), "the textbook weight one" (1/2 q^2), "time step
  0.1", speed and distance "both with weight one": one name each.
- "So what" after each result: descent: "Short window or long, it goes through the same way" and the summary "the old
  plan, shifted by a step and capped with a reference step, is why the bill can only fall"; the test: "You can check
  it once, before the controller ever runs, and pick the window for computing time, not for safety."
- Carried objects at each cut: hook -> title beat (target, trail, meter, dot, question); title beat -> Bill (region,
  dot, meter); Bill -> ShiftedPlan (region and its label, plan, dot, tag q, meter); ShiftedPlan -> WhatItBuys (region,
  plan, reference step, dot, meter, descent box, bars); WhatItBuys -> OneStepTest (the slice, both bowls, dot, meter,
  pinned descent); OneStepTest -> Example (the slice, end-cost bowl, dot, empty meter, pinned test); Example -> Recap
  (slice, bowls, dot, meter, pinned test); Recap -> Outro (the meter, in the outro's place).
- Outro callback: the hook's picture, small: the dot steps into the target while the meter drains; the teaser as the
  card's "Next: From Steps to Rates".
- Spoken script: the everyday analogy is the bill (a running total of charges), from the hook to the recap. Signposts:
  the roadmap; "Here's the real question, then"; "The answer is yes"; "Here's the one condition we need"; "And
  there's a bonus here"; "Everything now rests on that one test"; "Now read the same test as a bill"; "Before we go
  on"; "Now it's time for numbers"; "What made the bill fall, step after step?". Required phrases: meter refills
  "So let's rewind" (hook), "Now look at the meter" (Bill), "put the controller at one" (Example); title
  beat "Episode one of eight. The proof takes one step."; teaser "In the next episode, the step shrinks to zero. And a
  momentum shows up that nobody put in." Scores in `README.md`.

## The pacing plan

Times are from the Azure narration (`check_pacing.py --stage final`, `review/design/final/check_pacing.md`); the silent
drafts run about 20 s longer.

- Ideas (`plan.json` "ideas", the series plan's ids; each at the bookmark that starts its sentence, the picture that
  carries it in brackets):
  - receding-window, concept, pretraining, Bill 1:04 ["window" under a row of four slots]
  - stage-cost, concept, pretraining, Bill 1:25 ["stage cost" on a segment, then on the amber stack]
  - end-region, concept, pretraining, Bill 1:52 ["end region" under the region]
  - end-cost, concept, pretraining, Bill 2:20 ["end cost" beside the green block, after "one last charge"]
  - remaining-action, concept, pretraining, Bill 2:36 ["remaining action" over the meter]
  - reference-step, concept, ShiftedPlan 4:19 ["reference step" on the arrow]
  - end-test, claim (the condition, a step of the one-step test, "of": one-step-test), ShiftedPlan 4:32 ["the test"
    over the reference step's cost and the end cost it saves]
  - descent, star, ShiftedPlan 5:20 [the boxed line V_N(q^+) - V_N(q) <= -L_d(q,q^+), the meter falling]
  - feasibility, claim, WhatItBuys 6:03 [a ghost walks the shifted plan into the region]
  - lyapunov-name, concept, WhatItBuys 6:27 ["Lyapunov function" on the bowl]
  - stability, claim, WhatItBuys 6:47 [the dot slides down the bowl and settles]
  - asymptotic-stability, concept, WhatItBuys 6:55 ["asymptotic stability" at the bottom of the bowl]
  - one-step-bill, concept, OneStepTest 8:06 [the legend's row "one step left"]
  - one-step-test, star, OneStepTest 8:30 [V_1 <= V_0 boxed, the two bowls and the walls]
  - one-step-converse, claim (of one-step-test; added after the final-cut review, round 2), OneStepTest 8:43 [the
    best single step from q as a blue arrow; the dot takes it into the region and it turns the reference step's
    colour]: "When the best one-step bill is no higher than the end cost, its best step is a reference step that
    passes the test." It comes 10 s after the star's hold (P3 asks 20 s): the one pacing warning added on purpose.
  - window-free, claim, OneStepTest 8:58 [a row of slots appears and goes; the test's three ingredients light up]
  - terminal-names, concept, OneStepTest 9:20 ["terminal cost" on the bowl, "terminal set" under the region]
  - one-step-example, claim (the example), Example 10:21 ["end cost = 0.60", the meter "0.59"]
  - ratio, claim, Example 11:14 [a ghost point slides along both bowls with its two bars and a fixed ratio]
  - textbook-weight, claim (side), Example 11:34 ["textbook weight 1" and "fails"; its two bars at the start and the ratio 1.01]
  Two starred results, 190 s apart; claims at least 20 s apart (after a star, from the end of its hold); at most four
  claims and starred results in any 180 s; at most three concepts in any 60 s (inside the pretraining segment), two
  outside it.
- Runtime from the ideas: 11.7-12.6 min (the series plan's budget, `episode.json`); the scenes sum to 774 s = 12.9 min
  (hook 38.4, title beat 5.9, Bill 143.5, ShiftedPlan 173.4, WhatItBuys 60.8, OneStepTest 153.5, Example 144.2, Recap
  35.1, Outro 19.5). The 20 s over the budget's high end are the two extra think prompts and the spacing P3 asks
  between the second star and the example's claims (`review/video/resolutions.json`, VD-12).
- Pretraining segment (Bill 1:04-2:49): window, stage cost, end region, end cost, remaining action, each on its own
  object as it is named and followed by a held pause (1.2-2.5 s); at most three in any 60 s (they come 20.6, 27.5,
  27.7 and 15.9 s apart); then the summary "In short, the bill is the cheapest plan's stage costs plus its end cost."
  and 2 s held; the equation V_N(q) = min[sum L_d + W] only after it (2:57), held 1.8 s after the words.
- Roadmap (Bill 0:45, the first sentence after the title beat, its first chip on screen 0.8 s before it): "Here's the
  route we'll take. First, the bill, what the controller still has to pay. Then why one step always lowers it. And
  last, the one test behind it all, checked on an example." with three chips ("the bill", "why it falls", "one test")
  that come up as they are named and leave with the next block.
- Chapter summaries: Bill 2:49 (the pretraining summary) and 2:57 (the same in symbols); ShiftedPlan 5:49 "So that's
  the whole argument. The old plan, shifted by a step and capped with a reference step, is why the bill can only
  fall."; OneStepTest 9:26 "So a single test, on one step, is all it takes to certify the controller."; Example 11:49
  "So with weight one point two, one check at one point is enough to certify the controller, for every window
  length." (WhatItBuys is 61 s and needs none.)
- Restatements: descent, after its 3 s hold: "In plain words, with every step, the bill drops by at least what that
  step costs." (recap: "Each time, the bill drops by at least what that step costs."); the test: "In plain words, one
  step of planning never raises the bill." (recap: the same sentence).
- Recap (12:01, 35 s): it opens with "What made the bill fall, step after step?", on screen before it is said and
  held 2.5 s, beside a small copy of the argument's picture (the region, the plan, the dot); then the descent (boxed)
  in its plain words while the small picture replays the shifted plan and its reference step and the meter falls
  step by step; then the test, shown again under the descent, in its plain words, with an arrow from the test to the
  descent; "Together, they're the whole proof we needed."
- Pause plan (`[pause S]` after a block's last word is a hold of the picture; no break inside a block is used, so
  every planned pause is an exact scene hold): stars `[pause 3]`; prompts `[pause 4]`, `[pause 3.8]`, `[pause 4.4]`,
  `[pause 3.8]`; claims and steps of an argument `[pause 1.8]`; pretraining concepts `[pause 1.2]`-`[pause 1.6]`;
  "every plan gets its own total" `[pause 2.5]`; the pretraining summary `[pause 2]`; the inequality `[pause 2]` (its
  P13 hold); chapter ends `[pause 1.8]`; blocks that continue the same motion `[pause 0]` (in the hook, title beat);
  every other block the default 0.75 s. Stretches without a pause of 1.5 s: at most 41.5 s (the hook and the title
  beat; the first roadmap chip comes up in silence after the cut, so the stretch ends there). 18.4 % of the body is
  silence of 1.5 s or more; the median pause between blocks is 1.87 s.
- Slow blocks (`[slow]`, -15 %): Bill's five definitions (window, stage cost, end region, end cost, remaining
  action); ShiftedPlan's main prompt and its argument (the rest of the old plan, the condition, the cheaper plan, the
  bars as one line, the descent); WhatItBuys's two conditions and the settling; OneStepTest's test on the bowl, the
  bill with no steps left, the outside prompt, the one-step bill, the step under the end cost, the test in one line,
  and the "what's missing" prompt; Example's prediction prompt and the ratio argument. 39 % of the body's narration
  time. The hook, title beat, recap and outro have none. Measured: the pace cap (P20) slowed most ordinary blocks to
  -15 % as well (Steffan HD reads 160-175 words per minute at -8 %), so slow and ordinary sentences both speak at
  about 162-164 words per minute; the time is in the holds, the breaks at sentence ends and the shorter sentences.
- Pace cap (P20): every block at or under 160 words per minute with the planned pauses left out, after sentence-end
  breaks, a slower rate (never below -15 %) and, for 16 blocks of the first synthesis, a rewrite into shorter
  sentences or a new take.
- Numbers: only in the example, six spoken (one point two; zero point six and zero point five nine; zero point one
  one and zero point one two; zero point two four), at most three in any 20 s, each on screen as it is said; the ratio
  readouts (0.98 for weight 1.2, 1.01 for the textbook weight) are shown, not said.

## What this video leaves out of the explainer, and why

- The recursion (Bellman's principle), monotonicity in the window length, the window ladder and "a longer window is
  never worse": episode 2 (the series plan moved them there: episode 1 was over-packed at 17.8-19.7 min).
- The explicit-candidate proof as a written derivation: it is the picture (the shifted plan's bars) and the
  inequality, not five lines of sums.
- Comparison functions and the class-K sandwich of asymptotic stability: two mild conditions said in words.
- The A2 inequality and the chain V_1 <= L_d + W <= W = V_0 as formulas: the bars on the bowl and the words carry
  them; only V_1 <= V_0 is written.
- The rectangle-rule formula, the mass and the stiffness as symbols: words on screen.
- Why the weight is 1.2 and not 1: only that the textbook weight fails by a hair, for a later episode.
- The continuous limit, the momentum, Hamilton-Jacobi: the teaser of episode 2.

## Scene 1: Hook (38 s, role hook, music bed) - source: explainer Section 1.1 (sec-idea)

- Idea: a controller that keeps changing its mind; why should it ever arrive? Watch what is left to pay.
- First frame: the whole picture (`self.add()`): the target, the meter, the dot and its fan of plans; two steps in
  the first 1.6 s.
- First line (1.6 s): "Here's a controller that plans a whole path, takes one step, and throws the rest away."
- Question at about 11 s: "If it keeps changing its mind, why should it ever arrive?"; stakes: "It's model predictive
  control, and it steers robot arms, legged robots and cars. Yet nothing rules out circling forever."
- Thumbnail picture: the frame at 5.0 s (thick trail, big meter, no readout).
- Signature object: the meter, its level V_1(q_k) of the scalar example (`ep01_numbers.LOOP`), label only.
- Music: bed. Data: `ep01_numbers.py` (closed forms, checked against `code/logs/`).
- Voice-over (base rate): as in `scenes/s01_hook.py`, the v6 text with `[pause 0]` where the motion carries on, a
  0.7 s hold after the question, `[pause 0]` at the end (the title beat follows at once).

## Scene 2: SeriesContext (6 s, role context, bed)

- The hook's last picture stays; the title and the "Episode 1 of 8" lower third; then the cut to the body's start.
- Voice-over: "Episode one of eight. The proof takes one step." `[pause 0]`

## Scene 3: Bill, "What is left to pay" (144 s, body, low) - Sections 1.1-1.3, 2.1 (sec-window)

- On screen, block by block: the roadmap chips; the plan drawn, the window's slots filling (label "window", tag q);
  the first step highlighted, a ghost takes it and a new plan sprouts from where it lands; the segments turn amber
  ("stage cost"), thicken, and dashed rays measure the distance to the target; the costs fly into a stack beside the
  meter; the region brightens ("end region"), a ghost follows the plan in; two other plans, each with a ghost, end
  in it too; the end point turns green and becomes the green block ("end cost"); every plan's total as a dashed
  column; the cheapest boxed, "remaining action" over the meter; the stack pours into the meter; the plan glows for
  the summary; V_N(q) = min[sum L_d + W] grows from the meter, the segments and the end point.
- Voice-over: `scenes/s03_bill.py` (14 blocks; the pretraining definitions are `[slow]`).

## Scene 4: ShiftedPlan, "Why the bill falls" (173 s, body, off) - Section 3.2 (sec-descent)

- On screen: a ghost wanders along other plans; a dashed ghost bill ("tomorrow?") wobbles; for the main prompt the
  dot takes the first step, a dashed line at today's bill and an amber one a step lower, then 4 s still; the "step
  paid" block; a ghost walks the rest of the old plan, whose blocks stack up ("rest of the old plan"); the window's
  slots, one short, the reference step (a thick arrow from the plan's end most of the way to the target, labelled
  under it) fills the last slot; "the test" over the condition, and the extra cost and the new end cost replace the
  old end cost under its old top, with room to spare (schematic sizes chosen so the saving and the cost are visible),
  the cost steps out and back as "it pays for itself" is said, and the old end cost's outline shows the saving; the blocks merge
  into one blue block ("left to pay, from here"); the inequality grows from the meter and the blocks, then becomes
  the descent (boxed) while the meter falls; held 3 s; the drop bracket beside the meter with the step's cost beside
  it; a window of one slot grows to ten; a ghost walks the shifted plan once more.
- Voice-over: `scenes/s04_shifted.py` (14 blocks).

## Scene 5: WhatItBuys, "What the fall buys" (61 s, body, low) - Sections 3.2-3.3 (sec-asymptotic)

- On screen: a ghost walks the shifted plan into the region; the picture slices through the target: the axis, the
  region as an interval, the bill as a bowl with the dot at the meter's height (a dashed guide to the meter);
  "Lyapunov function" on the bowl; a step away from the target with its cost; the end-cost bowl drawn with a green
  dot sliding to zero; the dot slides down the bowl while the meter drains; "asymptotic stability" at the bottom.
- Voice-over: `scenes/s05_buys.py` (5 blocks).

## Scene 6: OneStepTest, "One test, on one step" (167 s, body, low) - Sections 2.3, 3.4 (sec-terminal)

- On screen: the meter set aside, the zoom into the region, centred in the frame; a point q, the reference step, the
  dot sliding down the end-cost bowl, the fall (green bar) and the step's cost (amber bar) under the old height; the
  legend "no steps left = end cost" as the bowl is traced; a probe dot moves on the outside part of the axis during
  the prompt, then 3.8 s still; green walls (V_0 outside the region) with infinity signs; "one step left": the plan's
  bars stay at the step's end, a dashed level carries the end cost at q to them and the plan's level runs to q, where
  the bill drops to the best one-step bill; the one-step bowl sweeps under the end cost and under the walls; V_1 <=
  V_0 fades in (V_1 blue, V_0 green) while the legend rows light up, boxed, 3 s still; the converse: the best step as a
  blue arrow that the dot takes and that turns the reference step's colour; the dot replays the step for the third
  prompt, then 4.4 s still; a labelled window row, which drops out of the test, then comes back changing length
  ("pick the window for computing time") and grows on "a longer window"; "terminal cost" and "terminal set"; the zoom
  out, the test pinned, the meter back.
- Voice-over: `scenes/s06_onestep.py` (15 blocks).

## Scene 7: Example, "One example, step by step" (144 s, body, low, faithful) - Sections 3.4, 6.4 (sec-numeric)

- On screen: "time step 0.1"; the tick 1; the region widens to the whole line; "end cost weight 1.2" and the
  end-cost bowl over the whole line; the prompt (the dot moves to 1), 3.8 s still; "end cost = 0.60", the one-step
  bowl, the meter fills to 0.59; four logged steps, the first said with its readouts, three silent, drop beside cost
  at every step (the readouts for the spoken first step only); the total drop beside the four costs stacked; the ghost scan with the fixed ratio 0.98; the
  textbook weight's bowls, "fails", its two bars at the start and the same ratio readout at 1.01; back to weight 1.2.
- Data: `ep01_numbers.py`, checked against `code/logs/note__sec4_3_one_step_example.py.log` ('rect 1.2', 'rect 1.0').
- Voice-over: `scenes/s07_example.py` (11 blocks).

## Scene 8: Recap (35 s, body, low) - Sections 3.2, 2.3

- On screen: a small copy of the argument's picture on the left (the region, the plan, the dot) and "What made the
  bill fall?" (before it is said), 2.5 s still; the descent boxed while the small dot takes the first step, the rest
  of the plan glows and the reference-step arrow grows, and the meter falls step by step; the pinned test leaves its
  corner and is shown again under the descent, an arrow from the test to the descent; both boxes pulse on "Together,
  they're the whole proof we needed."
- Voice-over: `scenes/s08_recap.py` (4 blocks, base rate).

## Scene 9: Outro (20 s, outro, bed; low from "In the next episode")

- A silent callback (about 2.5 s; the card's frame fades in as it goes), the card "One test, on one step" with
  V_1 <= V_0 => descent "for any window" (coloured by quantity, V_0 green), "Next:
  From Steps to Rates", the channel name, the closing question on screen, 1.6 s of picture after the last word;
  nothing right of x = 1.4.
- Voice-over: "One test, on one step, and that's why it arrives." / "In the next episode, the step shrinks to zero.
  And a momentum shows up that nobody put in." / "Until then, why does the textbook weight fail?"

## Plan (`video/plan.json`)

- Search term: MPC. Title: "Why Does MPC Converge? A One-Step Proof" (40 characters, the series plan's).
- Summary, tags, chapters as in `plan.json`; the chapters are the scenes' titles above ("Recap" is a 35 s chapter of
  its own on purpose: P16 asks 60 s of body chapters, P15 asks for this recap).
- Thumbnail: Hook at 5.0 s, "Why MPC converges", layout picture.
