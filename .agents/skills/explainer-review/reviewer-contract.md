# Reviewer contract

Every reviewer and the finding-verifier follow this file.

## Files

- Write `<reviewer-name>.json` (format below) and `<reviewer-name>.md` (what you checked, how, what you found, what you
  could not check) in the run's review folder: `review/` (explainer), `review/video/` (video design),
  `review/final_cut/` (final cut) or `review/series_plan/` (series plan).
- Your own scripts, notes and tool outputs go in `review/checks/`, named with your id prefix in lower case (`tc_*`,
  `ref_*`, `pres_*`, `rt_*`, `lr_*`; the finding-verifier `verify_<finding-id>_*`); screenshots in `review/screens/`.
  `tools/validate.py` reads every other JSON file at the top of a review folder as a report.
- Write nothing outside `review/`: the writer fixes, you report (a hook enforces this).
- Run `python3 tools/validate.py runs/<run>` and fix your files until it is clean. Finish with a five-line summary
  (the finding-verifier: one line).

## Report

```json
{
  "schema_version": 1,
  "reviewer": "technical-correctness-reviewer",
  "summary": "Two or three sentences: overall verdict and the most important problem.",
  "checks_run": [
    {"command": ".venv/bin/python runs/<run>/review/checks/tc_riccati.py", "result": "residual 3e-16; matches eq. (7)"}
  ],
  "findings": [
    {
      "id": "TC-1",
      "severity": "major",
      "location": "Section 3.2, equation (7)",
      "issue": "What is wrong, in one or two sentences.",
      "evidence": "The command and output, the source passage, or the derivation step that shows it.",
      "suggested_fix": "The concrete change: corrected formula, number, wording or reference.",
      "confidence": "high"
    }
  ]
}
```

- Ids, one prefix per reviewer (`tools/validate.py` checks it): `TC-n` technical correctness, `REF-n` references,
  `PRES-n` presentation, `RT-n` claims red team, `LR-n` linear reader, `VD-n` video design, `FC-n` final cut (each
  finding also has `time_s`, seconds into the final video), `SRT-n` series red team.
- Evidence, not opinion: commands with their output, quotes of the location, record URLs. Report only what affects
  correctness or understanding; taste is not a finding. Say in the summary what you could not check.
- A review not made by an independent subagent (the session that made the work, without subagents) adds
  `"independent": false` and `"reviewed_by": "main session (no subagents)"` at the top level. The final-cut reviewer
  always writes both fields (`true`, `"final-cut-reviewer subagent"` when independent).

## Second round

If your report already exists, this is a later round: leave it as it is and write `<reviewer>.round2.json`
(`round3`, ...) beside it, numbering new findings after the highest id of the earlier rounds. `merge_reviews.py` reads
every round and stops on an id used twice or on a verdict (`verify/<id>.json`) or resolution whose finding no report
holds. A problem that persists after a fix the writer recorded is a new finding that names the earlier id.

## Severity

| Severity | Meaning |
|---|---|
| `blocker` | wrong: a result, equation, number, reference or claim a reader would rely on is incorrect |
| `major` | misleading: an unsupported or overstated claim, a missing condition, wrong units, a reference detail not found in any record |
| `major` | reader flow: a reader cannot follow a derivation or argument here: a missing link (a step that needs something not yet said, said only much later, or only implied), an unannounced change of meaning (a symbol or object rebound, a quantity defined from one function and later written from another), a worked example that does not say which earlier claim it checks |
| `minor` | plain wording: unclear or imprecise phrasing that a careful reader can still follow |
| `nit` | small and harmless (typo, inconsistent capitalisation); at most five per report |

A reader-flow `major` is verified and then needs a fix or a recorded resolution like any other. Expert knowledge does
not close a gap: a step the page never supplies is missing even if every reviewer can fill it in.

Videos (`VD-`, `FC-`): `blocker` = a viewer cannot read or follow it (illegible text or text hidden by an overlap, a
meaning carried by colour alone, content cut off, narration about something not on screen, a number in an unreadable
format such as 0.500000, a reference to material outside the video, an equation label, the series context missing or
wrong); `major` = it misleads or strains (wrong emphasis, inconsistent colour meaning or precision, clutter that hides
the point, a lopsided or wasted frame for a whole scene, narration out of step with the picture by more than a second,
a missing recap, content in the end-screen area); `minor` = polish; `nit` = at most five.

Series plans (`SRT-`): `blocker` = an episode would teach something wrong, or cannot be followed alone; `major` =
overloaded, unsourced numbers, a missing recap, a dishonest prerequisite; `minor` = clarity, order, length; `nit` = at
most five.

## Video reviews

Judge against AGENTS.md (Conventions), `.claude/rules/manim-scenes.md` and
`.agents/skills/manim-video-producer/spoken-script.md`. Confirm or dismiss every error and warning of the check
reports with what you see, and look for what they cannot see; evidence is the frame file and time, the caption text
and the tool output. Always `major`:
- the picture frozen, or only emphasis moving, for more than `engagement.frozen_narration_error_s` while the narration
  talks (the motion measure misses thin curves and small dots: judge its frozen stretches on the frames);
- a picture whose dimension or scale contradicts its mathematics or numbers; a parameter named two ways;
- a meter refill with no step paid that the narration does not announce;
- in the idea declarations (`plan.json` `ideas`, audited against what you hear): an undeclared result, a step (`of`)
  that needs its own explanation, a result the series plan (`episode.json` `ideas`) does not budget.

Both video reviewers add, at the top level, and as tables in the `.md`:

- `"rubric"`: the SoME rubric, `{"motivation" | "clarity" | "novelty" | "memorability": {"score": 1-5, "evidence":
  "frame file and time"}}`: why a viewer should care, and by when; whether each step can be followed from the
  picture; a view the viewer has not seen elsewhere; one image or sentence they will keep. A score of 2 or less on
  motivation or memorability is also a `major` finding with the fix.
- `"spoken_script"`: `{"ear" | "rhythm" | "one_idea" | "misconception" | "analogy" | "questions" | "signposts" |
  "required_phrases" | "read_aloud" | "register": {"score": 1-5, "evidence": "a quote and its time"}}`, scored as
  `.agents/skills/manim-video-producer/spoken-script.md` says.

## Symbol ledger (presentation-reviewer)

`review/symbol_ledger.json`: every symbol and named object, its meaning at first use in each section where it
appears, and whether each later use keeps it (`none`), changes it with an announcement in the text (`announced`) or
changes it silently (`unannounced`). `defined_from` names the function a quantity is built from (`p` from `W` in one
section and from `V` in another is a change). Every `unannounced` change is also a finding, named in `finding`:

```json
{
  "schema_version": 1,
  "reviewer": "presentation-reviewer",
  "symbols": [
    {"symbol": "S", "finding": "PRES-3", "uses": [
      {"section": "1.4", "location": "notation table, row Action", "meaning": "action of a path on [t, t_f], boundary term W included", "change": "first"},
      {"section": "5.1", "location": "equation (11)", "meaning": "action over the window, boundary term W included", "change": "none"},
      {"section": "6.2", "location": "first sentence", "meaning": "Hamilton's principal function (the minimized action, here V)", "change": "unannounced"}]},
    {"symbol": "p", "finding": "PRES-4", "uses": [
      {"section": "5.2", "location": "equation (14)", "meaning": "momentum field", "defined_from": "W", "change": "first"},
      {"section": "6.2", "location": "dictionary, row Momentum", "meaning": "momentum field", "defined_from": "V", "change": "unannounced"}]}
  ]
}
```

## Verdict (finding-verifier)

`verify/<finding-id>.json` in the review folder of the finding's report:

```json
{"schema_version": 1, "finding": "TC-1", "verdict": "confirmed", "reason": "What was re-checked and what it showed.",
 "checks_run": [{"command": "...", "result": "..."}]}
```
