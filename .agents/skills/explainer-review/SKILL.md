---
name: explainer-review
description: Independent review of a built explainer - five reviewer subagents in parallel (technical correctness with numerical checks, reference verification, presentation and notation with a symbol ledger and the bridge test, red team on claims and novelty, and a linear reader who reads strictly front to back and reports every gap in the argument), adversarial verification of every blocker or major finding, then one merged and ranked summary. Use when an explainer builds cleanly and needs review, or as stage 7 of /produce-explainer.
argument-hint: "runs/<run>"
---

# Explainer review

Precondition: the build, code checks and render check pass (`python3 tools/run.py status runs/<run>`); fix a broken
build first. The reviewers' format and severities: [reviewer-contract.md](reviewer-contract.md). Run each named agent
(`.claude/agents/<name>.md`) as a subagent; if your tool has no such agent, use a general-purpose subagent or a fresh
context with that file's body as the prompt.

## Procedure

1. **Fan out.** In one message, start five reviewers in parallel: `technical-correctness-reviewer` (`TC-`),
   `reference-verifier` (`REF-`), `presentation-reviewer` (`PRES-`, also `review/symbol_ledger.json`),
   `claims-red-team` (`RT-`) and `linear-reader` (`LR-`, strictly front to back). Give each only the run path and the
   approved topic title, never your own view of the draft: independence is the point.
2. **Validate.** When all five have finished, `python3 tools/validate.py runs/<run>` must be clean for every report
   and the symbol ledger; resume a reviewer with the validator's message otherwise.
3. **Verify.** For every `blocker` or `major` finding without a verdict, start a `finding-verifier` (in parallel, one
   per finding) with the finding id and the path of its report; each writes `review/verify/<id>.json`.
4. **Merge.** `python3 tools/merge_reviews.py runs/<run>` writes `review/summary.md` and `summary.json`.
5. **Fix** (you are the writer again): confirmed blockers and majors first, then uncertain ones you agree with, then
   minors worth the change. Fix reader-flow findings (`LR-`, `PRES-` bridges and rebindings) in the text: add the
   bridging sentence, announce the change of meaning or rename the symbol, using `review/symbol_ledger.json` to find
   every use. Edit drafts, code or references, never the reviewers' files. Record every decision in
   `review/resolutions.json` (`{"resolutions": [{"finding": "TC-2", "status": "fixed" | "wontfix", "note": "..."}]}`),
   rebuild with `--strict`, rerun the code and render checks, then `merge_reviews.py`.
6. **Second round, once.** If a blocker was fixed, rerun only the reviewer whose finding it was, on the changed
   sections (a round file: reviewer-contract.md, Second round), verify its new serious findings and merge.
   Never more than two rounds: report what is still open.
7. Show the user the summary table and the open items. The gate stops a run with an open blocker or confirmed major,
   or a serious finding never verified.

In Claude Code with dynamic workflows, `/review-fanout runs/<run>` (`.claude/workflows/review-fanout.js`) runs steps 1
to 4 with the same agents and files.

## Gotchas

- A reviewer asked to find problems always finds something: act on confirmed findings that affect correctness or
  understanding.
- A step the page never supplies, a symbol that silently changes meaning or an example that never says what it checks
  is `major`: fix it, or record why not in `review/resolutions.json`.
- Refuted is not wrong-by-default: read the verifier's reason before dismissing a finding.
- Reference findings often need a detail removed (a DOI, a page range) rather than added.
- Keep `review/` intact: it is the record of how the explainer was checked, and the final report cites it.
