---
name: robotics-news-scout
description: Finds recent robotics news and research (papers, preprints, official lab or company posts, code releases) and records candidate topics with their primary sources in the run folder's sources.json. Use for "what is hot in robotics", for scouting explainer topics, or as stage 2 of /produce-explainer.
argument-hint: "runs/<run> [focus]"
---

# Robotics news scout

Input: a run folder (`python3 tools/run.py new [--window-days N] [--root DIR]` makes one, anywhere) and an optional
focus. Output: `<run>/sources.json`, clean under `python3 tools/validate.py <run>`. Run that command yourself before you
finish: a hook also validates on every save, but only for files it can see in this session.

Read `config/scout.json` (candidates, search angles, domains, exclusions; the user's file, do not edit it) and the
run's `run.json`: its `window_days` is this run's search window (default from `config/scout.json`, or the
`--window-days` the run was created with). `sources.json` must carry the same window.

## Procedure

1. **Search** within the window. WebSearch has no date filter, so put the dates into the queries: the month and year
   ("October 2026"), arXiv identifiers of the window's months (`site:arxiv.org 2610` for October 2026), conference
   names with the year. Run one query per search angle in the config, plus the focus if given; record every query
   you actually ran in `queries`. When arxiv.org is reachable, its subject listings (`arxiv.org/list/cs.RO/2026-10`,
   `arxiv.org/list/cs.RO/recent`) are the most complete dated index: filter titles there and record the listing as a
   query; keep to a few requests (arXiv rate-limits bursts).
2. **Group** results into candidate topics: one technical idea per candidate, not one article per candidate. Drop what
   matches `exclude`. Check `covered.json` in the run (made by `tools/run.py new` from the ledger `published.json`,
   `sources/` and `series/`) and set each candidate's `coverage`: `new`, `partly_covered` (say how the angle differs)
   or `covered` (drop it, or keep it marked so the ranking excludes it), with `by` naming the covered items. Keep
   between `min_candidates` and `max_candidates`.
3. **Read the primary source** of each candidate, following the access order and fallbacks in
   [source-policy.md](source-policy.md): canonical page (arXiv abs or PDF, DOI page, project page), then metadata
   endpoints, then the authors' pages, then a search summary of the canonical page. Record the level you reached in
   `read` (`full`, `abstract`, `search_abstract`, `snippet`, `unreadable`, defined in the policy) and `via` when you
   read it elsewhere. Every failure goes into `unreadable` with `reason` and `cause` (`network_policy` when the
   session's network refused the host): never drop a source silently and never summarise a page you did not see.
4. **Mark each source's relation**: `subject` for the candidate's own paper, post, code or data; `prior_work` for
   earlier work you cite for novelty; `context` for coverage and background. Only a dated `subject` primary source
   inside the window makes a candidate current; the validator rejects candidates whose newest subject source is older.
5. **Write** the summary (two or three sentences, your own words), the claims, each with a `role` (`central`,
   `limitation`, `context`) and a `status` (`verified`, `provisional`, `unverified`, `disputed`), one to three visual
   hooks (from equations or data, never someone else's footage), and one to four `search_queries`: the plain phrases a
   student would type into YouTube to learn this idea (not the paper title, not hype words).
6. **Save** `sources.json`, run `python3 tools/validate.py <run>` and fix every error.
7. **Report**: candidates found, their coverage, which have no subject primary source, sources unreadable from this
   network (list the hosts the user could allow) versus unreadable for other reasons, anything that looked like hype.

The file format, with an example, is in [sources-format.md](sources-format.md).

## Gotchas

- News articles recycle press releases: two articles quoting the same release are one source, not two.
- arXiv: `published` is the v1 date; note later versions in `notes`. A preprint is not peer reviewed; say so in claims.
- A search tool's description of a paper can be wrong (one test described a humanoid paper by a technique that was not
  its title's subject): read the abstract page before writing claims, and keep search-level claims `provisional`.
- Demo videos: teleoperation, speed-up and cherry-picked takes are common and often undisclosed. A claim supported only by
  a video or press release is `unverified`, whatever the headline says.
- List limitations as claims with role `limitation`: they never cost a topic its place, and the explainer needs them.
- Benchmarks and "first" claims need the paper's own numbers and setup; otherwise mark them `unverified`.
- Funding, hiring and product-launch news without a technical result is not a candidate.
- Never bypass a paywall, login or the session's network policy; when a host is refused, stop trying more hosts of the
  same kind and use the fallbacks.
- Dates are calendar dates in the user's time zone (the run date in run.json), not UTC.
