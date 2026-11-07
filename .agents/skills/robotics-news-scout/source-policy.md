# Source policy

Applies to the scout, the ranker, the writer and the reference verifier. `tools/validate.py` enforces the parts
marked (checked).

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

Each source also has a `relation` to the candidate (checked, required for primary sources):

- `subject`: the source presents this candidate's own work (its paper, preprint, project post, code or data). Only a
  `subject` primary source satisfies the ranking gate, and recency is computed from `subject` sources only.
- `prior_work`: earlier work used for context or the novelty comparison. Record it, cite it in the novelty score; it
  never satisfies the gate, however good it is.
- `context`: background, coverage, awards, related news.

## Read levels (checked): what was actually read, and what it permits

| `read` | what you saw | permits |
|---|---|---|
| `full` | the full text (HTML or PDF) of the source itself | any claim, number, method or figure in it |
| `abstract` | the source's own abstract, verbatim: on its canonical page, or through a metadata endpoint or index that reproduces it unchanged (record that URL in `via`) | claims stated in the abstract, including headline numbers there |
| `search_abstract` | a search tool's summary or snippet that presents the abstract of the source's canonical URL (two or more sentences on method and result), when the source itself could not be opened | the source exists, its title, date and topic; claims it states become `provisional`, never `verified` |
| `snippet` | a fragment of a search result, or a secondary page's excerpt | finding the topic only; supports no claim above `unverified` |
| `unreadable` | nothing | nothing; list it in `unreadable` with the reason and a `cause` |

A search tool's text about a page you did not open is never `full` or `abstract`, however long it is. A summary written
by an aggregator (alphaXiv, news sites, blogs) is `snippet` for the primary source unless it reproduces the authors'
abstract verbatim (then `abstract`, with `via`).

## Access, and fallbacks when a primary source cannot be fetched

Try, in this order, and stop at the first that works; record the level reached and, when it is not the source's own
URL, the `via` URL:

1. The canonical page: arXiv abstract page (`arxiv.org/abs/<id>`) or PDF (`arxiv.org/pdf/<id>`), DOI landing page,
   OpenReview forum, the official blog post or repository.
2. A metadata endpoint of the same record: the arXiv API (`export.arxiv.org/api/query?id_list=<id>`), Crossref
   (`api.crossref.org/works/<doi>`), Semantic Scholar or OpenAlex. They return title, authors, date and usually the
   abstract (read level `abstract`).
3. The authors' own pages: project page, lab page, the repository README (a `code` source in its own right).
4. A WebSearch for the exact title or identifier, restricted to the canonical host where possible
   (`site:arxiv.org <id>`): its summary of the canonical page is `search_abstract`.

Never use a mirror or cache that gets around a paywall, login, robots rule or the session's network policy, and do not
keep probing hosts once the network policy has refused one: record the refusal and carry on.

Every failure goes into `unreadable` with `reason` and `cause`: `network_policy` (the session's network refused the
host), `paywall`, `login`, `http_error`, `timeout`, `not_found` or `other`. `tools/rank_topics.py` reports
`network_policy` failures separately ("Sources unreadable from this network"): they are a limitation of the run, not of
the topics, and the fix is to allow those hosts (environment network settings) or to rerun where they are reachable.

## Claims

Each candidate lists its claims (`central_claims`), each with a `role` and a `status` (checked).

Roles, which decide what the ranking gate counts:

- `central`: a claim the explainer would rely on: what the method is, the main result, the number in the headline.
  Only central claims count for the gate.
- `limitation`: a caveat, limit or failure case (simulation only, one robot, a metric that got worse). List every one
  you find; limitations never exclude a topic, and stating them is part of the job.
- `context`: affiliation, awards, coverage, relation to other work.

Statuses:

- `verified`: stated in a primary source read at `full` or `abstract` level.
- `provisional`: stated in a primary source seen only at `search_abstract` level (typically because the network blocked
  it). Allowed by the gate, flagged in the ranking, and re-verified at `full` or `abstract` level before writing.
- `unverified`: seen only in secondary sources, a video or a snippet, or not confirmed at all.
- `disputed`: sources contradict each other, or the primary source qualifies the claim the news makes.

Never upgrade a claim from what you remember: only what you saw in a source during this run counts.

## Copyright and attribution

- Summaries and explainers are written in our own words. Do not copy article text, abstracts or captions; a short quote
  (one sentence) is allowed only in quotation marks with the source cited.
- No third-party images, figures or video frames, not even "for reference" in a run folder. Figures are redrawn from
  equations or from data we compute, by scripts in `code/`, and their captions say so.
- Every source used ends up in `references.json` with its URL and access date; the explainer's References section and
  attribution statement are generated from it.
