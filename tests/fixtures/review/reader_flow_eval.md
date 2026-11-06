# Manual eval: reader-flow findings (presentation-reviewer and linear-reader)

A regression check for the two review prompts that judge reader flow: the presentation-reviewer (bridge test, symbol
ledger) and the linear-reader. Prompts cannot be judged by a unit test, so this one is run by hand, with independent
subagents. `tests/test_review.py` checks only that the agents are wired.

## Material

The pre-fix version of `sources/variational-whole-body-control/explainer.html`: SHA-256
`0860176d796b62ad8115567b619f7c4fe09771cffad725acd060b75cb4dd6183`, 569,960 bytes. It is not kept in the repository
(the fixed text replaced it); whoever runs the eval keeps a copy and checks its hash first.

## Run

1. Make a scratch run folder outside `runs/`, for example `review-eval/` in a temporary directory, holding the copy as
   `explainer.html` and an empty `review/` folder.
2. Start a `presentation-reviewer` and a `linear-reader` subagent on that folder, each with only the folder path and
   the title ("From the Remaining Action to the Forces on a Task"). Do not tell them what to look for.
3. Run `python3 tools/validate.py` on the folder, then compare `review/presentation-reviewer.json`,
   `review/symbol_ledger.json` and `review/linear-reader.json` with the three expected findings below.

## Expected findings

All three are `major` under the reader-flow row of `.claude/skills/explainer-review/reviewer-contract.md`: a reader
cannot follow the argument there.

**(a) A momentum field defined from one function and later written from another.**
- Where: Section 5.2 (`sec-momentum`), before equation (14): "Define the momentum field $p(q):=-\nabla W(q)$", built
  from the boundary term $W$. Section 6.2 (`sec-signs`), dictionary rows "Momentum | $p=-\nabla V$" and
  "Hamilton–Jacobi equation | $\partial_tV=H(q,-\nabla V)$", built from the remaining action $V$.
- Missing: no sentence at 6.2 says that the field is now taken from $V$ instead of $W$, or when the two agree. That
  $W=V_\infty$ solves the stationary equation is stated in 5.3 as a fact of the verification theorem, and "$W=V$"
  appears again only in the "A finite window" paragraph of 6.3. (The dictionary of 1.3 already ties $p$ to $V$, in
  the costate row "$\eta=\nabla V=-p$", so 5.2 switches too; either way no sentence reconciles the definitions, and a
  verifier should not refute the finding on the strength of that row.)
- Expected from: the linear-reader (unannounced switch of object); the presentation-reviewer's ledger, symbol `p`
  with `defined_from` `W` at 5.2 and `V` at 6.2, change `unannounced`, and the `PRES-` finding it names.

**(b) A worked example that does not say what it checks.**
- Where: Section 6.3 (`sec-scalar`), "Worked example: the hilltop", first sentence: "Take $\dot q=v$ and the
  variational Lagrangian (18)".
- Missing: the example never says how it connects to Sections 5 to 6.2. Its setting differs without being said: no
  boundary term $W$ (it appears only in the closing "A finite window" paragraph) and an infinite horizon. It never
  names the earlier claim it verifies (for example $p=-\nabla V$ and $H(q,-\nabla V)=0$ of 6.2, the descent identity
  $\dot V=-L$, or the statement of 5.3 that the remaining action solves the stationary equation).
- Expected from: the linear-reader (an example whose purpose is unclear); the presentation-reviewer (bridge test: a
  worked example without the claim it checks and without its change of setting).

**(c) One letter for two objects, and a minimized quantity never written.**
- Where: $S$ includes the boundary term in Section 1.3 (dictionary, "Total cost over the horizon | Action $S$"),
  Section 1.4 (notation, "Action on $[t,t_f]$ | $S$ | $\int_t^{t_f}L\,dt'+W(q(t_f))$") and Section 5.1, equations
  (11) and (12) ($S_\delta(q,v)=\int_t^{t+\delta}L\,dt'+W(q(t+\delta))$). In Section 6.2, first sentence, $S$ is
  "Hamilton's principal function", with $\partial S/\partial q_{\text{final}}=p$ and the differential $dS$ below the
  table: the minimized action as a function of the endpoints, which is $V$ in the document's initial-point reading.
- Missing: the change of meaning is not announced. Section 5 also never writes $V_\delta(q)=\min_v S_\delta(q,v)$,
  so the link between $S_\delta$ of (11) and the remaining action is left to the reader.
- Expected from: the presentation-reviewer's ledger, symbol `S` with change `unannounced` at 6.2 and its `PRES-`
  finding; the linear-reader (an unannounced switch, and a minimized quantity that is used but never defined).

## Pass criteria

- The linear-reader reports (a), (b) and (c); the presentation-reviewer reports (b) with the bridge test and marks `S`
  and `p` as unannounced changes in its ledger, each with a finding.
- Each is `major`, and its location points at the passages above (the section number and a quote are enough).
- Record the outcome: the date, which prompt found which finding, and anything the finding-verifier refuted.
- On the fixed document the same run should no longer report these three (it may report others).

## Eval runs

### Run 1, 2026-10-31: the prompts as first written

Independent subagents ran the full five-reviewer review on the pre-fix document. Passed overall: each expected finding
was reported by at least one prompt, but (b) was under-rated and the linear-reader missed most of its share.

| Expected | presentation-reviewer | linear-reader |
|---|---|---|
| (a) momentum field from $W$, later from $V$ | found: `PRES-2`, major | partly: reported that plain $V$ is never defined, not the switch from $W$ |
| (b) the hilltop example does not say what it checks | partly: `PRES-5`, rated minor, one finding grouping the openings of 4.3, 6.3, 6.5 and 7.6 | missed |
| (c) $S$ rebound; $V_\delta=\min_v S_\delta$ never written | found: `PRES-1`, major | found: `LR-4`, major |

Changes after this run: both agents now state that an example which does not say what it checks, and a symbol whose
meaning changes silently, are `major`, with an example in neutral wording; several such places may not be folded into
one minor finding; the linear-reader reports a switch from one function to another in the same role even when both
are defined. The next run should show (b) as `major` from both prompts and (a) from the linear-reader.
