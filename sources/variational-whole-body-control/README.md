# Source document: *From the Remaining Action to the Forces on a Task*

The explainer that video series are planned from (`/produce-from-source sources/variational-whole-body-control` or
`/plan-series`), with the code that produces every number in it and the data the episodes animate. Series runs copy
`explainer.html`, `code/` and `data/` from here unchanged (`tools/series.py start`); each series made from it points
here (`"source"` in its `series.json`) and records the explainer's hash.

| | |
|---|---|
| `explainer.html` | The merged document: 19 sections, 73 numbered equations, 7 original SVG figures, 63 references checked against publisher, repository or index records, a verification section (Section 18). It has the reader features of the explainer template (a dark-mode switch, equation numbers that link to their equation with a working Back button, a collapsible contents sidebar). Open it in a browser; KaTeX loads from the jsDelivr CDN. |
| `code/` | The complete companion code at the paths Section 18 uses, every file an unmodified copy except `note/sec7_symbolic_checks.py` (its check of the $u$-equation corrected on 2026-10-31) and `merged/fig_bases.py` (Figure 7 relabelled $\tau_x$), with `checks.toml` (the scripts `tools/run_code_checks.py` runs), a README mapping scripts to sections, and the logs of the last full run. |
| `data/` | What the arm episodes animate: `arm_A.npz` (start A: N = 10, 20, 40 and PD + gravity) and `arm_B.npz` (start B: N = 1, 10, 40 and PD + gravity), exported by `export_arm.py` from the closed-loop runs of `code/note/sec8_arm/closedloop.py`; the console output of the 2026-10-31 runs is in `closedloop_A10_40.log`, `closedloop_A20.log` and `closedloop_B.log`. |

The topic was chosen by the author before the pipeline existed: it is a research synthesis, not a news topic, so
there is no `sources.json`, `ranking.md` or `approval.json` here, and the explainer was not built from a `draft/`
folder by `tools/build_explainer.py`. The reviewer reports of the original work were not archived; their outcome is
recorded in Section 18 (Verification Status).

## Re-run the checks

From the repository root: every script in `checks.toml` (15 minutes in the last full run; the logs go to
`code/logs/`), the render check at 1400 px and 390 px, and the static HTML check:

```bash
.venv/bin/python tools/run_code_checks.py sources/variational-whole-body-control
node tools/check_html.js sources/variational-whole-body-control/explainer.html
python3 tools/lint_html.py sources/variational-whole-body-control/explainer.html
```

## Changing the explainer

Series plans made from this source refer to this file and record its hash. After a change to its content, plan again
(`/plan-series`) or check the existing plans against it; after a change to its HTML template alone,
`python3 tools/series.py rehash series/<series>` updates the hash (the plan hash leaves the explainer's byte hash out).
