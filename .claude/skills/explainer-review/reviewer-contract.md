# Reviewer contract (output format and severity scale)

Every reviewer subagent writes two files in `runs/<run>/review/`:

- `<reviewer-name>.json`, validated by `python3 tools/validate.py runs/<run>` (run it before you finish), and
- `<reviewer-name>.md`, a short narrative for humans (what you checked, how, what you found, what you could not check).

Everything else you make (your own scripts, notes, tool outputs such as the JSON of `tools/check_html.js` or
`tools/check_html_features.js`) goes in `runs/<run>/review/checks/`, named with your id prefix in lower case: `tc_*`,
`ref_*`, `pres_*`, `rt_*`, `lr_*` (the finding-verifier: `verify_<finding-id>_*`). Screenshots go in
`runs/<run>/review/screens/`. Only reports, the symbol ledger and other records of the pipeline sit at the top of
`review/`, where `tools/validate.py` reads every JSON file as a report; it and `tools/merge_reviews.py` never read
`review/checks/`.

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

Ids: `TC-n` technical correctness, `REF-n` references, `PRES-n` presentation, `RT-n` red team, `LR-n` linear
reader. `tools/validate.py` checks that each reviewer uses its own prefix.

| Severity | Meaning |
|---|---|
| `blocker` | wrong: a result, equation, number, reference or claim a reader would rely on is incorrect |
| `major` | misleading: an unsupported or overstated claim, a missing condition, wrong units, a reference detail not found in any record |
| `major` | a reader cannot follow a derivation or argument here: a missing link (a step that needs something not yet said, said only much later, or only implied), an unannounced change of meaning (a symbol or object rebound, a quantity defined from one function and later written from another), a worked example that does not say which earlier claim it checks |
| `minor` | plain wording: unclear or imprecise phrasing that a careful reader can still follow; affects understanding, not correctness |
| `nit` | small and harmless (typo, inconsistent capitalisation); at most five per report |

A reader-flow `major` goes through the finding-verifier like any other: the gate then needs a fix or a recorded
resolution (`review/resolutions.json`). Expert knowledge does not close a gap: a step the page never supplies is
missing even if every reviewer can fill it in.

Rules: evidence, not opinion (commands with outputs, quotes of the location, record URLs). Report only problems that
affect correctness or understanding; taste is not a finding. Never edit anything outside `review/`: the writer fixes,
you report (a hook enforces this). If you could not check something, say so in the summary rather than guessing.

The presentation-reviewer also writes `review/symbol_ledger.json`, the symbol ledger the writer works from: every
symbol and named object, its meaning at first use in each section where it appears, and whether each later use keeps
that meaning (`none`), changes it with an announcement in the text (`announced`) or changes it silently
(`unannounced`). `defined_from` names the function a quantity is built from (`p` from `W` in one section, from `V` in
another is a change). An `unannounced` change is always also a finding, named in `finding`:

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

The finding-verifier writes `review/verify/<finding-id>.json`:

```json
{"schema_version": 1, "finding": "TC-1", "verdict": "confirmed", "reason": "What was re-checked and what it showed.",
 "checks_run": [{"command": "...", "result": "..."}]}
```
