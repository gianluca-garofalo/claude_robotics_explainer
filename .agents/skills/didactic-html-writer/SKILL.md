---
name: didactic-html-writer
description: Writes the didactic HTML explainer for an approved topic in the house style (numbered sections, KaTeX equations, definition/insight/algorithm boxes, original SVG figures, author-year citations, verification section), with every number produced by a script in the run's code/ folder. Use after a topic is approved, or to revise an explainer's drafts.
argument-hint: "runs/<run>"
---

# Didactic HTML writer

Precondition: `python3 tools/run.py status runs/<run>` shows the topic approval as done (`selection.json` written by
`tools/auto_select.py`, or `approval.json` from the user's `/approve-topic`). If not, stop: you never approve topics.
If the topic has `provisional` central claims (its primary source was seen only through a search summary), first read
that source at `full` or `abstract` level; a claim you still cannot confirm is not used in the explainer.
Inputs: the approved topic, `sources.json`, `ranking.md`. Outputs, all in the run:
`draft/` (meta.json, outline.md, NN-name.html parts), `code/` (scripts, checks.toml, README.md, figures/),
`references.json`, and the built `explainer.html`.

Read [style-guide.md](style-guide.md) before writing. Markup for every component is in
`templates/explainer/components.html`; the reference for quality and tone is
`sources/variational-whole-body-control/explainer.html`.

## Procedure

1. **Read the primary sources** listed for the approved topic. Note what they show and what they only claim.
2. **Outline** in `draft/outline.md`: the one-sentence takeaway, sections (one idea each), the toy model, the equations
   that will be numbered, the figures, and for each number the script that will print it. For each section, the
   bridge: what it takes from earlier sections and what it adds; for each worked example, the claim it checks. A
   symbol table: every symbol, its meaning, the function it is built from, and where (if anywhere) that changes.
3. **Code first.** Write the scripts in `code/` (numpy, scipy, sympy, matplotlib), the manifest `code/checks.toml` and
   `code/README.md` (map scripts to sections). Figures go to `code/figures/NAME.svg`. Run
   `.venv/bin/python tools/run_code_checks.py runs/<run>` and copy numbers from `code/logs/`, never from memory.
4. **References.** Write `references.json` from the records you opened (format below): every field as the record
   shows it, a DOI only if you saw it there, `checked_against` naming those records. `unverified` is for drafting
   only: the strict build refuses it. The reference-verifier subagent re-checks everything independently in review.
5. **Draft parts** `draft/NN-name.html` with the markers of components.html, and `draft/meta.json`
   (`title`, `subtitle`, `date`, optional `html_title`). End with the verification section (`sec-verification`).
6. **Build and check** until clean: `python3 tools/build_explainer.py runs/<run> --strict`, then
   `node tools/check_html.js runs/<run>/explainer.html --json runs/<run>/review/check_html.json`.
7. Report the build stats, the check results and the claims you could not verify.

`references.json` entries: `key` (surname + year, lowercase), `type` (article, inproceedings, book, chapter, preprint,
web, press, video, software, dataset, report, thesis), `authors` (list; an organisation for web pages), `title`,
`venue`, `year`, optional `volume`, `number`, `pages`, `publisher`, `doi`, `arxiv`, `url`, `accessed`, `note`,
`cite_as`, and `verification` = `{status: verified | secondary_only | unverified, checked_against: [...],
doi_seen_in: "..."}`. Validated on save by a hook (`tools/validate.py`).

## Gotchas

- Never edit `explainer.html`: it is generated. Edit `draft/` and rebuild. Never type a section, equation or figure
  number: use `[[sec:..]]`, `\tag{[[eq:..]]}`, `[[eq:..]]`, `[[figdef:..]]`, `[[fig:..]]`, `[[cite:..]]`, `[[citet:..]]`.
- KaTeX auto-render works per text node: math cannot span an HTML tag, and every `$` opens math. Write prices as
  "USD 5", never "$5".
- A `<` inside math starts an HTML tag: write `\lt`, `\gt` or `&lt;`. Only display math (`$$...$$`) may carry `\tag`.
- A phone shows about 35 characters of display math: break long formulas with `\begin{aligned}...\end{aligned}` and
  keep each display in an `equation-block`, or the tag overlaps the formula at 390 px.
- Matplotlib SVGs: set `plt.rcParams["svg.hashsalt"] = "explainer"` and `savefig(..., metadata={"Date": None})` so
  reruns produce identical files; give the `<svg>` an `aria-label` (the build adds `role="img"`).
- When a script's output changes, the text must change too: rerun the checks and search the drafts for the old value.
- Read your draft front to back as a reader who knows only what the page has said so far (style guide, Bridges and
  Symbols): `python3 tools/explainer_text.py runs/<run>/explainer.html --section <n>` prints one section at a time.
  In a revision, `review/symbol_ledger.json` lists every symbol's meaning per section; fix every unannounced change.
- Say "exact" only for symbolic identities, "sampled" for random or grid searches (not proofs), and report residuals.
- "First", "new", "outperforms": only as the primary source states it, attributed to it ("the authors report").
  Our own novelty claims wait for the claims-red-team reviewer.
- News topics: an `evidence` box separates what the paper shows from what a video or press release claims.
- The channel's narrated video of this explainer stands on its own: it never refers back to the explainer, its code
  or its equation numbers, and links to them appear only in the YouTube description when the user turns links on.
  Write the explainer complete in itself as well; do not rely on "see the video".
- No third-party text or images: paraphrase and redraw from equations or our own data; captions say "drawn by code/x.py".
