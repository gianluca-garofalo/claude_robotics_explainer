---
name: explainer-review
description: Use when a built explainer needs its independent review, or as stage 7 of /produce-explainer - six reviewer subagents in parallel (technical, references, presentation and notation, claims red team, linear reader, experiment audit), verification of blocker and major findings, one merged and ranked summary.
argument-hint: "runs/<run>"
---

# Explainer review

Precondition: the build, code checks and render check pass (`python3 tools/run.py status runs/<run>`); fix a broken
build first. The reviewers' format and severities: [reviewer-contract.md](reviewer-contract.md).

## Procedure

1. **Review: fan out, check, verify, merge.** `python3 tools/merge_reviews.py runs/<run> --workflow-args` prints the
   run, the set and its reviewers (`tools/gate.py` `REVIEWERS`). Run the `review-fanout` workflow
   (`.claude/workflows/review-fanout.js`, the Workflow tool) with that object as its args. It starts the six reviewers
   in parallel, each with only the run path and its report path: `technical-correctness-reviewer` (`TC-`),
   `reference-verifier` (`REF-`), `presentation-reviewer` (`PRES-`, also `review/symbol_ledger.json`),
   `claims-red-team` (`RT-`), `linear-reader` (`LR-`, strictly front to back) and `experiment-auditor` (`EA-`, the
   run's own code behind each result, its probes in `review/audit/`). It checks each report with
   `merge_reviews.py --pending <name>` (the checks of `tools/validate.py` and the independence fields) and sends a
   reviewer whose report fails back once with the errors; gives the blocker and major findings of each report to one
   `finding-verifier` (`review/verify/<id>.json`); then merges (`review/summary.md`, `summary.json`). Its result names
   the reviewers that failed, the reports still invalid and the merge output: rerun or fix those first.

   Without the Workflow tool (another coding agent, or workflows off), do the same by hand: start each reviewer as a
   subagent (or a fresh context with `.claude/agents/<name>.md` as its prompt) with only the run path and its report
   path, never your view of the draft; when one finishes, `python3 tools/merge_reviews.py runs/<run> --pending <name>`
   must show no errors (resume or restart it once with them); give the findings it lists under `verify` to one
   `finding-verifier` per report; then `python3 tools/merge_reviews.py runs/<run>`. With no subagents at all, write each
   report yourself from the agent's file, marked `"independent": false` (reviewer-contract.md), and say so.
2. **Fix** (you are the writer again): confirmed blockers and majors first, then uncertain ones you agree with, then
   minors worth the change. Fix reader-flow findings (`LR-`, `PRES-` bridges and rebindings) in the text: add the
   bridging sentence, announce the change of meaning or rename the symbol, using `review/symbol_ledger.json` to find
   every use. Edit drafts, code or references, never the reviewers' files. Record every decision in
   `review/resolutions.json` (`{"resolutions": [{"finding": "TC-2", "status": "fixed" | "wontfix", "note": "..."}]}`),
   rebuild with `--strict`, rerun the code and render checks, then `merge_reviews.py`.
3. **Second round, once.** If a blocker was fixed, rerun only the reviewer whose finding it was, on the changed
   sections (a round file: reviewer-contract.md, Second round): the workflow with `reviewers` cut to that one name and
   `focus` naming the changed sections (their numbers, never your view of them), or by hand as above. Never more than
   two rounds: report what is still open.
4. Show the user the summary table and the open items. The gate stops a run with an open blocker or confirmed major,
   or a serious finding never verified.

## Gotchas

- A reviewer asked to find problems always finds something: act on confirmed findings that affect correctness or
  understanding.
- A step the page never supplies, a symbol that silently changes meaning or an example that never says what it checks
  is `major`: fix it, or record why not in `review/resolutions.json`.
- Refuted is not wrong-by-default: read the verifier's reason before dismissing a finding.
- Reference findings often need a detail removed (a DOI, a page range) rather than added.
- Keep `review/` intact: it is the record of how the explainer was checked, and the final report cites it.
- In a session whose permission mode does not prompt (`dontAsk`, CI), the workflow starts only with the allow rule
  `Workflow(review-fanout)`; otherwise use the paragraph without the Workflow tool.
