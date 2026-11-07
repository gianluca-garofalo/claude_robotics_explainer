# Explainer style guide

Distilled from the reference document, `sources/variational-whole-body-control/explainer.html`. The presentation-reviewer subagent reviews against this file.

## Audience and promise

Robotics and control researchers and graduate students. They know linear algebra, ODEs, basic optimisation and
mechanics; they may not know the specific method. The promise of every explainer: after reading, the reader can state
the idea in one sentence, reproduce one key number with the companion code, and say what the news does and does not show.

## Structure

1. Header: title (what the idea is, not a headline), subtitle (the angle), date.
2. Abstract box: the news in one sentence, the idea, what the reader will compute, how numbers were checked, with the
   primary source cited.
3. Sections, one idea each, in this order of ideas: the picture (a figure before any formula) -> the toy model ->
   the key equation(s) -> a worked numerical example -> what changes on a real robot -> what the news shows and does
   not show (evidence box) -> takeaways.
4. Part labels only for documents longer than about eight sections.
5. A notation table when more than about eight symbols are used; one meaning per symbol in the whole document (see
   Symbols below).
6. Verification Status section: a `table.ver` (Claim | Script | Result) and a literature-checks paragraph.
7. References and the attribution statement are appended by the build; do not write them in drafts.

Length: 2,500 to 6,000 words for a news explainer; 6 to 12 numbered sections.

## Bridges (the bridge test)

Write for a reader who reads front to back and fills no gap with their own knowledge (the linear-reader reviewer
reads exactly so; a gap it finds is a `major` finding).

- Every section and subsection opens by saying what it takes from earlier sections and what it adds: one sentence
  such as "Section 5 gave the momentum field $p=-\nabla W$; here $W$ is the remaining action itself, so ...".
- Every worked example names the earlier claim or prediction it verifies ("this checks the condition (16) of Section
  5.3 on a problem where it can be solved exactly"), and says how its setting differs from the sections around it
  (no boundary term, an infinite horizon, another model).
- A result that is used again later says so where it first appears ("we use this again in Section 7").
- No step relies on something stated only later or only implied: say it first, or point forward explicitly and say
  that the reader can take it on trust until then.

## Symbols

- One meaning per symbol in the whole document. When a symbol must change meaning, or a quantity defined from one
  function is later written from another (a momentum field $p=-\nabla W$ written later as $p=-\nabla V$), say so at
  that point and say when the two agree; otherwise use a new symbol.
- A minimized or derived quantity is written out where it is first used ($V_\delta(q)=\min_v S_\delta(q,v)$), not
  left for the reader to reconstruct.
- Keep the symbol table of `draft/outline.md` (symbol, meaning, the function it is built from, where it changes and
  the sentence that announces the change) up to date; the presentation-reviewer checks the built page against the same
  idea and saves its own version as `review/symbol_ledger.json`.

## Voice

- Concrete before general: an example with numbers, then the statement.
- Define every term before using it; give the intuition in one sentence next to each formal definition.
- Short declarative sentences. Active voice. No hype words (revolutionary, game-changing, unprecedented).
- Attribute claims precisely: "the authors report", "the video shows", "we computed".
- Say what is exact, what is numerical (with residuals) and what is sampled (not a proof).

## Components and what they are for

| Component | Use it for | Do not use it for |
|---|---|---|
| `.definition` | a precise statement the reader will come back to | general commentary |
| `.insight` | the consequence or the "why it matters" | repeating the paragraph above |
| `.margin-note` | conventions, sign choices, side caveats | content the main line needs |
| `.algorithm` | steps of a method, the steps of a proof | prose lists |
| `.evidence` | verified vs unverified vs disputed claims of a news topic | our own results |
| `table` | dictionaries, numerical results, notation | layout |
| `figure` + inline SVG | original figures produced by code/ | screenshots or third-party images |

## Equations

- Number an equation only if it is referred to later. Use `\tag{[[eq:label]]}` inside `$$...$$` in an `equation-block`.
- Every symbol in a displayed equation is defined in the sentence before or right after it.
- Check units and limiting cases in the text when they help understanding (for example, h -> 0).
- Prefer one aligned block over three consecutive displays.

## Figures

- Drawn by a script in `code/` (matplotlib to SVG, or hand-written SVG from a script), with the same colour meanings as
  the video palette: blue reference, amber contrast, green holds or verified, red failure (always also labelled in text).
- Caption: what to look at, then what it shows, then the script that drew it.
- Width up to 680 px; text in figures at least 11 px; an `aria-label` describing the figure in one sentence.

## Citations and numbers

- Author-year links through `[[cite:key]]` and `[[citet:key]]`. Cite the primary source for every technical claim;
  secondary sources only for coverage or context.
- Every number in the text, a table or a figure is printed by a script; the verification table names it.

## Accessibility and layout

- Must pass `tools/check_html.js` at 1400 px and 390 px: no horizontal overflow, no overlapping equation tags.
- Colour is never the only carrier of meaning. Tables have header rows. Links say where they go.
