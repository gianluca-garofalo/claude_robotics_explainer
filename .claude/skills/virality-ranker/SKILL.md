---
name: virality-ranker
description: Scores the scouted candidate topics with the project's explicit rubric (novelty, visual potential, audience fit, teachability, hype risk; recency, search demand and supply gap computed from dates and search data), with written reasons and cited sources, and produces the run's ranking.md. Use after the scout, when asked which topic is most likely to go viral, or as stage 3 of /produce-explainer.
argument-hint: "runs/<run>"
---

# Virality ranker

Input: `<run>/sources.json` (valid: run `python3 tools/validate.py <run>` first, wherever the run folder is) and
`search.json` if collected. Output: `<run>/scores.json` (your judgments) and `ranking.md` + `ranking.json`, generated
by `python3 tools/rank_topics.py <run>`. The ranking is a transparent heuristic for
choosing what to explain next, not a prediction of views; say so whenever you present it.

Read `config/rubric.json` (weights, gates, formula; the user's file, do not edit it) and the score anchors in
[rubric.md](rubric.md) before scoring.

## Procedure

1. For each candidate, score every judged criterion of the rubric (0-5 integers) and `hype_risk` (a penalty), each with
   one or two sentences of reasons and the source ids that support them (`novelty` and `hype_risk` must cite sources).
   Do not score `recency`, `search_demand` or `supply_gap`: the tools compute them from the newest primary-source
   date and from `search.json` (`python3 tools/search_demand.py runs/<run>`, run before ranking; YouTube suggestions,
   YouTube Data API views and competition, Google Trends). A source that could not be read leaves the criterion
   unknown ("?") and the total renormalises the other weights; never compensate for it in your judged scores.
   Search measures long-tail demand; viral spikes come from suggested and browse traffic, which nothing here sees.
2. Add `proposed_angle` (what the explainer would teach, one or two sentences) and `animation_idea` (one original
   animation, from equations or computed data).
3. Save `scores.json` (format below; a hook validates it on save), run `python3 tools/rank_topics.py runs/<run>`, read
   the generated `ranking.md` once, and fix anything that reads wrong by changing the scores' reasons, not the tool.
4. Present the top three (total, gate status, one-line reason, primary source link). The topic is then approved by
   `tools/auto_select.py` (automatic mode, a fixed rule over your scores) or by the user with `/approve-topic`
   (human mode, `config/pipeline.json`). Never approve, pick or start writing yourself: your influence is the scores
   and their written reasons, which the selection log quotes.

```json
{"schema_version": 1, "topics": [{"id": "T1",
  "scores": {"novelty": {"score": 4, "why": "...", "sources": ["S1"]},
             "visual_potential": {"score": 5, "why": "...", "sources": []},
             "audience_fit": {"score": 4, "why": "...", "sources": []},
             "teachability": {"score": 3, "why": "...", "sources": ["S1"]},
             "hype_risk": {"score": 1, "why": "...", "sources": ["S1", "S2"]}},
  "proposed_angle": "...", "animation_idea": "..."}]}
```

## Gotchas

- Score each criterion separately against its anchors; do not back-solve scores to reach a total you like.
- Popularity of a company is not novelty, and many news articles about one demo is not evidence; it raises hype risk.
- Controversy is a penalty in this rubric: a topic that spreads because it is misleading costs credibility.
- Teachability is about our toy model: if you cannot name the equation and the script that would reproduce a number,
  it is at most 2.
- Scores of 5 should be rare. If more than one candidate gets 5 on the same criterion, re-read the anchors.
- The gate counts only claims with role `central` that are `unverified` or `disputed`, and needs a primary source with
  relation `subject`. Limitations never count, prior work never satisfies it, `provisional` claims pass but are
  flagged for re-verification. Do not compensate in your scores for a gate result, and do not ask the scout to drop
  limitations to pass it.
- If ranking.md reports "Sources unreadable from this network", say so when you present the ranking: the reader must
  know which claims are provisional because of the network rather than because of the topic.
- A stale `search.json` (collected for an earlier `sources.json`) is ignored by the tool: rerun
  `tools/search_demand.py`.
