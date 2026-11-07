---
name: robotics-news-scout
description: Finds recent robotics news and research (papers, preprints, official lab or company posts, code releases) and records candidate topics with their primary sources in the run folder's sources.json. Use for "what is hot in robotics", for scouting explainer topics, or as stage 2 of /produce-explainer.
argument-hint: "runs/<run> [focus]"
---

# Robotics news scout

Input: a run folder (`python3 tools/run.py new [--window-days N] [--root DIR]` makes one, anywhere) and an optional
focus. Output: `<run>/sources.json` (format in [sources-format.md](sources-format.md)), clean under
`python3 tools/validate.py <run>`: run it yourself before you finish (the hook on save sees only this session's files).
Read `config/scout.json` (candidates, search angles, domains, exclusions) and the run's `run.json`: its `window_days`
is this run's search window, and `sources.json` carries the same. [source-policy.md](source-policy.md) says what is
primary, what each read level permits and what a claim may say.

## Procedure

1. **Search** within the window. WebSearch has no date filter, so put the dates in the queries: the month and year
   ("October 2026"), arXiv identifiers of the window's months (`site:arxiv.org 2610` for October 2026), conference
   names with the year. One query per search angle of the config, plus the focus; record every query you ran in
   `queries`. When arxiv.org is reachable, its subject listings (`arxiv.org/list/cs.RO/2026-10`,
   `arxiv.org/list/cs.RO/recent`) are the most complete dated index: filter titles there and record the listing as a
   query, in few requests (arXiv rate-limits bursts).
2. **Group** results into candidates: one technical idea per candidate, not one article. Drop what matches `exclude`.
   Set each candidate's `coverage` from the run's `covered.json` (made from the ledger `published.json`, `sources/` and
   `series/`): `new`, `partly_covered` (say how the angle differs) or `covered` (drop it, or keep it marked so the
   ranking excludes it), with `by` naming the covered items. Keep between `min_candidates` and `max_candidates`.
3. **Read the primary source** of each candidate in the policy's access order, and record the level reached in `read`
   (with `via` when read elsewhere). Every failure goes into `unreadable` with `reason` and `cause` (`network_policy`
   when the session's network refused the host): never drop a source silently, never summarise a page you did not see.
4. **Relation** of each source: `subject`, `prior_work` or `context` (policy). Only a dated `subject` primary source
   inside the window makes a candidate current.
5. **Write** the summary (two or three sentences, your own words), the claims, each with a `role` and a `status`
   (policy), one to three visual hooks (from equations or data, never someone else's footage), and one to four
   `search_queries`: the plain phrases a student would type into YouTube to learn this idea (not the paper title, no
   hype words).
6. **Save** `sources.json`, run `python3 tools/validate.py <run>` and fix every error.
7. **Report**: the candidates and their coverage, which have no subject primary source, sources unreadable from this
   network (list the hosts the user could allow) versus unreadable for other reasons, anything that looked like hype.

## Gotchas

- Two articles quoting the same press release are one source, not two.
- arXiv: `published` is the v1 date; note later versions in `notes`. A preprint is not peer reviewed: say so in
  claims.
- A search tool's description of a paper can be wrong: read the abstract page before writing claims, and keep
  search-level claims `provisional`.
- Demo videos often hide teleoperation, speed-up and cherry-picked takes: a claim supported only by a video or press
  release is `unverified`, whatever the headline says.
- List limitations as claims with role `limitation`: they never cost a topic its place, and the explainer needs them.
- Benchmarks and "first" claims need the paper's own numbers and setup; otherwise they are `unverified`.
- Funding, hiring and product-launch news without a technical result is not a candidate.
- Never bypass a paywall, login or the session's network policy; once a host is refused, stop trying hosts of the same
  kind and use the fallbacks.
- Dates are calendar dates in the user's time zone (the run date in run.json), not UTC.
