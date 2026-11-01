---
name: explainer-review
description: Independent review of a built explainer - five reviewer subagents in parallel (technical correctness with numerical checks, reference verification, presentation and notation with a symbol ledger and the bridge test, red team on claims and novelty, and a linear reader who reads strictly front to back and reports every gap in the argument), adversarial verification of every blocker or major finding, then one merged and ranked summary. Use when an explainer builds cleanly and needs review, or as stage 7 of /produce-explainer.
argument-hint: "runs/<run>"
---

# Explainer review

Precondition: build, code checks and render check pass (`python3 tools/run.py status runs/<run>`). Reviewing a broken
build wastes five reviewers; fix the build first. The reviewers' output format and severity scale are in
[reviewer-contract.md](reviewer-contract.md); the reviewer subagents read the same file.

## Procedure

1. **Fan out.** In one message, start five subagents in parallel: `technical-correctness-reviewer` (`TC-`),
   `reference-verifier` (`REF-`), `presentation-reviewer` (`PRES-`, also writes `review/symbol_ledger.json`),
   `claims-red-team` (`RT-`) and `linear-reader` (`LR-`, reads strictly front to back and never fills a gap). Give
   each only the run path and the approved topic title. Do not pass your own view of the draft: reviewers that have
   not seen how it was written are the point.
2. **Validate.** When all five have finished: `python3 tools/validate.py runs/<run>` must be clean for every
   `review/<reviewer>.json` and for `review/symbol_ledger.json`. If one is invalid, resume that reviewer with the
   validator's message.
3. **Verify.** For every finding with severity `blocker` or `major`, start a `finding-verifier` subagent (in parallel,
   one per finding) with the finding id and the path of the report that contains it. Each writes
   `review/verify/<id>.json` with `confirmed`, `refuted` or `uncertain`.
4. **Merge.** `python3 tools/merge_reviews.py runs/<run>` writes `review/summary.md` and `summary.json`, ranked by
   severity and verdict.
5. **Fix** (you are the writer again, in the main conversation): confirmed blockers and majors first, then uncertain
   ones you agree with, then minors worth the change. Reader-flow findings (`LR-`, and `PRES-` bridges or symbol
   rebindings) are fixed in the text: add the bridging sentence, announce the change of meaning or rename the symbol,
   using `review/symbol_ledger.json` to find every place a symbol is used. Edit drafts, code or references, never the
   reviewers' files.
   Record every decision in `review/resolutions.json`
   (`{"resolutions": [{"finding": "TC-2", "status": "fixed" | "wontfix", "note": "..."}]}`), rebuild with
   `--strict`, rerun the code and render checks, then rerun `merge_reviews.py`.
6. **Second round, once.** If a blocker was fixed, rerun only the reviewer whose finding it was, on the changed
   sections. Never more than two rounds: report what is still open instead.
7. Show the user the summary table and the open items. In the unattended workflow, `tools/gate.py` stops the run if
   a blocker or a confirmed major is still open, or if a serious finding was never verified.

If dynamic workflows are enabled, `/review-fanout runs/<run>` runs steps 1 to 4 as a workflow
(`.claude/workflows/review-fanout.js`) with the same agents and output files.

## Gotchas

- A reviewer asked to find problems always finds something. Act on confirmed findings that affect correctness or
  understanding; style preferences are not findings.
- Expert reviewers fill gaps without noticing. A step the page never supplies, a symbol that silently changes meaning
  or an example that never says what it checks is `major` (reviewer-contract.md): fix it, or record why not in
  `review/resolutions.json`; the gate does not let it pass silently.
- Refuted is not wrong-by-default: read the verifier's reason before dismissing a finding.
- Reference findings often need the writer to remove a detail (a DOI, a page range) rather than to add one.
- Keep `review/` intact: it is the record of how the explainer was checked, and the final report cites it.
