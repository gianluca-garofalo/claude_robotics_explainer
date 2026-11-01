# Companion code

Scripts that reproduce every number, check and figure of `../explainer.html`. Nothing in the explainer is typed
by hand: a number in the text is copied from the output of one of these scripts (see `logs/`).

Requirements: Python 3.11+ with `numpy`, `scipy`, `sympy`, `matplotlib` (the project's `.venv`).

Run every check (from the repository root):

```bash
.venv/bin/python tools/run_code_checks.py runs/RUN_FOLDER
```

or one script from its own folder, e.g. `cd code && python3 example.py`. Figures are written to `figures/` and
inlined into the explainer by `tools/build_explainer.py`.

## Map to `explainer.html`

| Section(s) | Script | What it does | Kind |
|---|---|---|---|
| 2.1, Figure 1 | `make_concept_figure.py` | Draws Figure 1 from the closed-form solution. | figure |
| 3.2 (table) | `example.py` | Computes the values in the table of Section 3.2. | exact / numerical / sampled |

"Exact" = symbolic identity; "numerical" = floating-point evaluation with the residual reported;
"sampled" = random or grid search, which can miss a counterexample and is not a proof.
