---
name: didactic-html-writer
description: Writes the didactic HTML explainer for an approved topic in the house style (numbered sections, KaTeX equations, definition/insight/algorithm boxes, original SVG figures, author-year citations, verification section), with every number produced by a script in the run's code/ folder. Use after a topic is approved, or to revise an explainer's drafts.
argument-hint: "runs/<run>"
---

# Didactic HTML writer

Precondition: `python3 tools/run.py status runs/<run>` shows the topic approval done (`selection.json` from
`tools/auto_select.py`, or `approval.json` from the user's `/approve-topic`); otherwise stop. A topic with
`provisional` central claims (its primary source seen only through a search summary): first read that source at `full`
or `abstract` level; a claim you still cannot confirm stays out of the explainer.

Inputs: the approved topic, `sources.json`, `ranking.md`. Outputs in the run: `draft/` (`meta.json`, `outline.md`,
`NN-name.html` parts), `code/` (scripts, `checks.toml`, `README.md`, `figures/`), `references.json` and the built
`explainer.html`. Read [style-guide.md](style-guide.md) first. The markup of every component is in
`templates/explainer/components.html`; the reference for quality and tone is
`sources/variational-whole-body-control/explainer.html`.

## Procedure

1. **Read the primary sources** of the approved topic: note what they show and what they only claim.
2. **Outline** in `draft/outline.md`: the one-sentence takeaway; the sections, one idea each; the toy model; the
   equations to number; the figures; for each number, the script that will print it; for each section, its bridge
   (what it takes from earlier sections and what it adds); for each worked example, the claim it checks; the symbol
   table (style guide, Symbols).
3. **Code first.** Scripts in `code/` (numpy, scipy, sympy, matplotlib), the manifest `code/checks.toml` and
   `code/README.md` (scripts mapped to sections); figures to `code/figures/NAME.svg`. Run
   `.venv/bin/python tools/run_code_checks.py runs/<run>` and copy every number from `code/logs/`. Every simulated or
   numerical result states its model beside it: step size, input limits, what is checked and how often (at the
   samples only, or along the path between them), seeds and trials. Before you write a result, check that it holds
   with the step size halved and with new seeds (the same conclusion, its numbers within their stated precision), in a
   script listed in `checks.toml` that prints the check and fails when it does not hold: the gate re-runs it.
4. **References.** `references.json` from the records you opened (format below): every field as the record shows it,
   a DOI only if you saw it there, `checked_against` naming those records. A record counts as seen only if you fetched
   it during this run (a search result or a page that did not load is not): cite prior work from a reachable record
   (arXiv, Crossref by DOI), otherwise mark it `secondary_only`. `unverified` is for drafting only: the strict build
   refuses it.
5. **Draft parts** `draft/NN-name.html` with the markers of components.html, and `draft/meta.json` (`title`,
   `subtitle`, `date`, optional `html_title`). End with the verification section (`sec-verification`).
6. **Build and check** until clean: `python3 tools/build_explainer.py runs/<run> --strict`, then
   `node tools/check_html.js runs/<run>/explainer.html --json runs/<run>/review/check_html.json`.
7. Report the build stats, the check results and the claims you could not verify.

`references.json` entries: `key` (surname + year, lowercase), `type` (article, inproceedings, book, chapter, preprint,
web, press, video, software, dataset, report, thesis), `authors` (a list; an organisation for web pages), `title`,
`venue`, `year`, optional `volume`, `number`, `pages`, `publisher`, `doi`, `arxiv`, `url`, `accessed`, `note`,
`cite_as`, and `verification` = `{status: verified | secondary_only | unverified, checked_against: [...],
doi_seen_in: "..."}`. A hook validates it on save (`tools/validate.py`).

## Gotchas

- `explainer.html` is generated: edit `draft/` and rebuild. Never type a section, equation or figure number: use
  `[[sec:..]]`, `\tag{[[eq:..]]}`, `[[eq:..]]`, `[[figdef:..]]`, `[[fig:..]]`, `[[cite:..]]`, `[[citet:..]]`.
- KaTeX auto-render works per text node: math cannot span an HTML tag, and every `$` opens math (write "USD 5", never
  "$5"). A `<` inside math starts a tag: write `\lt`, `\gt` or `&lt;`. Only display math (`$$...$$`) may carry `\tag`.
- A phone shows about 35 characters of display math: break long formulas with `\begin{aligned}...\end{aligned}` and
  keep each display in an `equation-block`, or the tag overlaps the formula at 390 px.
- Matplotlib SVGs: `plt.rcParams["svg.hashsalt"] = "explainer"` and `savefig(..., metadata={"Date": None})`, so reruns
  produce identical files; give the `<svg>` an `aria-label` (the build adds `role="img"`).
- When a script's output changes, the text changes too: rerun the checks and search the drafts for the old value.
- Read your draft front to back as a reader who knows only what the page has said so far (style guide, Bridges and
  Symbols): `python3 tools/explainer_text.py runs/<run>/explainer.html --section <n>` prints one section at a time. In
  a revision, fix every unannounced change that `review/symbol_ledger.json` lists.
- "Exact" only for symbolic identities, "sampled" for random or grid searches (not proofs); report residuals.
- "First", "new", "outperforms": only as the primary source states it, attributed to it ("the authors report"). Our
  own novelty claims wait for the claims-red-team.
- News topics: an `evidence` box separates what the paper shows from what a video or press release claims.
- The explainer is complete in itself: never "see the video" (the video never refers to it either: AGENTS.md,
  Conventions).
- No third-party text or images: paraphrase, and redraw from equations or our own data; captions say "drawn by
  code/x.py".
