# Source policy

For the scout, the ranker, the writer and the reference verifier. `tools/validate.py` enforces the parts marked
(checked).

## Primary and secondary

| kind | primary? | examples |
|---|---|---|
| `paper` | yes | journal or conference paper (publisher page, proceedings) |
| `preprint` | yes | arXiv, OpenReview submission, technical report hosted by the authors |
| `official_post` | yes, if it has technical content | lab or company blog post written by the people who did the work |
| `code`, `dataset` | yes | official repository or dataset release |
| `press_release` | no | promotional announcement, even from the company itself |
| `news` | no | IEEE Spectrum, trade press, newspapers |
| `video`, `social`, `other` | no | demo videos, posts, podcasts, aggregator pages |

Each source's `relation` to the candidate (checked; required for primary sources):

- `subject`: the candidate's own work (its paper, preprint, project post, code or data). Only a `subject` primary
  source satisfies the ranking gate, and recency is computed from `subject` sources only.
- `prior_work`: earlier work for context or the novelty comparison; cite it in the novelty score. It never satisfies
  the gate.
- `context`: background, coverage, awards, related news.

## Read levels (checked)

| `read` | what you saw | permits |
|---|---|---|
| `full` | the full text (HTML or PDF) of the source itself | any claim, number, method or figure in it |
| `abstract` | the source's own abstract, verbatim: on its canonical page, or through a metadata endpoint or index that reproduces it unchanged (that URL in `via`) | claims stated in the abstract, including its headline numbers |
| `search_abstract` | a search tool's summary of the canonical URL that presents its abstract (two or more sentences on method and result), when the source itself could not be opened | that the source exists, its title, date and topic; its claims become `provisional`, never `verified` |
| `snippet` | a fragment of a search result, or a secondary page's excerpt | finding the topic only; no claim above `unverified` |
| `unreadable` | nothing | nothing; list it in `unreadable` with the reason and a `cause` |

A search tool's text about a page you did not open is never `full` or `abstract`, however long. An aggregator's
summary (alphaXiv, news sites, blogs) is `snippet` for the primary source unless it reproduces the authors' abstract
verbatim (then `abstract`, with `via`).

## Access order

Stop at the first that works; record the level reached and, when it is not the source's own URL, `via`:

1. The canonical page: the arXiv abstract page (`arxiv.org/abs/<id>`) or PDF (`arxiv.org/pdf/<id>`), the DOI landing
   page, the OpenReview forum, the official post or repository.
2. A metadata endpoint of the same record: the arXiv API (`export.arxiv.org/api/query?id_list=<id>`), Crossref
   (`api.crossref.org/works/<doi>`), Semantic Scholar or OpenAlex: title, authors, date and usually the abstract
   (`abstract`).
3. The authors' own pages: project page, lab page, the repository README (a `code` source in its own right).
4. A WebSearch for the exact title or identifier, on the canonical host where possible (`site:arxiv.org <id>`): its
   summary of the canonical page is `search_abstract`.

Never use a mirror or cache that gets around a paywall, login, robots rule or the session's network policy, and stop
probing hosts once the network policy has refused one: record the refusal and carry on. Every failure goes into
`unreadable` with `reason` and `cause`: `network_policy`, `paywall`, `login`, `http_error`, `timeout`, `not_found` or
`other`. `tools/rank_topics.py` lists `network_policy` failures separately ("Sources unreadable from this network"):
a limitation of the run, not of the topic, fixed by allowing those hosts or rerunning where they are reachable.

## Claims (checked)

Each candidate's `central_claims` carry a `role` and a `status`.

Roles, which decide what the ranking gate counts:
- `central`: a claim the explainer would rely on (what the method is, the main result, the headline number). Only
  central claims count for the gate.
- `limitation`: a caveat, limit or failure case (simulation only, one robot, a metric that got worse). List every one;
  limitations never exclude a topic.
- `context`: affiliation, awards, coverage, relation to other work.

Statuses:
- `verified`: stated in a primary source read at `full` or `abstract`.
- `provisional`: stated in a primary source seen only at `search_abstract` (typically blocked by the network). Allowed
  by the gate, flagged in the ranking, and re-verified at `full` or `abstract` before writing.
- `unverified`: seen only in secondary sources, a video or a snippet, or not confirmed at all.
- `disputed`: sources contradict each other, or the primary source qualifies the claim the news makes.

Never upgrade a claim from memory: only what you saw in a source during this run counts.

## Copyright and attribution

- Our own words: no copied article text, abstracts or captions; a short quote (one sentence) only in quotation marks
  with the source cited.
- No third-party images, figures or video frames, not even "for reference" in a run folder: figures are redrawn from
  equations or our own data by scripts in `code/`, and their captions say so.
- Every source used ends up in `references.json` with its URL and access date; the explainer's References section and
  attribution statement are generated from it.
