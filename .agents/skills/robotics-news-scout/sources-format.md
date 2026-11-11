# sources.json format

`tools/validate.py` is the executable schema. An example with one candidate (placeholder URLs):

```json
{
  "schema_version": 1,
  "run_date": "2026-10-30",
  "window_days": 14,
  "queries": ["humanoid whole-body control new paper October 2026", "site:arxiv.org 2610 humanoid MPC", "..."],
  "unreadable": [{"url": "https://example.org/blocked", "reason": "host refused by the session's network policy",
                  "cause": "network_policy"}],
  "candidates": [
    {
      "id": "T1",
      "title": "Short descriptive title, no clickbait",
      "slug": "short-kebab-slug",
      "summary": "Two or three sentences in our own words: what was done, what is new, why it matters for robotics or control.",
      "coverage": {"status": "new", "by": [], "note": ""},
      "central_claims": [
        {"claim": "The controller runs at 1 kHz on the onboard computer.", "role": "central", "status": "verified",
         "support": ["S1"]},
        {"claim": "Tested on one humanoid only.", "role": "limitation", "status": "verified", "support": ["S1"]},
        {"claim": "It works on any humanoid.", "role": "central", "status": "unverified", "support": ["S2"]}
      ],
      "visual_hooks": ["contact forces switching on and off along a gait cycle"],
      "search_queries": ["humanoid contact forces", "whole body control explained"],
      "sources": [
        {"id": "S1", "url": "https://arxiv.org/abs/0000.00000", "title": "Paper title", "publisher": "arXiv",
         "authors": ["A. Author", "B. Author"], "kind": "preprint", "primary": true, "relation": "subject",
         "published": "2026-10-21", "accessed": "2026-10-30", "read": "full", "notes": "v2 posted 2026-10-25"},
        {"id": "S2", "url": "https://example.org/news", "title": "Article title", "publisher": "Example News",
         "kind": "news", "primary": false, "relation": "context", "published": "2026-10-22",
         "accessed": "2026-10-30", "read": "full"},
        {"id": "S3", "url": "https://doi.org/10.0000/example", "title": "Earlier method", "publisher": "Example Journal",
         "kind": "paper", "primary": true, "relation": "prior_work", "published": "2019-05-01",
         "accessed": "2026-10-30", "read": "abstract", "via": "https://api.crossref.org/works/10.0000/example"}
      ]
    }
  ]
}
```

What the validator enforces:

- Ids `T1..` and `S1..` (source ids unique across the file); kebab-case slugs; the summary's length; `window_days`
  equal to the run's (`run.json`).
- `primary: true` only for paper, preprint, official_post, code, dataset; every primary source has a `relation`; `via`
  is an http(s) URL; `read` is one of the levels of source-policy.md; `authors` (optional, as the record lists them)
  is a list: the video's description credits them.
- ISO dates, none after the run date; the newest dated `subject` primary source lies inside the window (error); a
  candidate without one gets a warning (recency unknown; the gate fails without a subject primary source).
- Claims: `role` (missing counts as central, with a warning) and `status`; `verified` needs a primary source read at
  `full` or `abstract`, `provisional` one read at least at `search_abstract`; every support id belongs to the same
  candidate.
- `coverage` is required when the run has `covered.json`; a candidate marked `new` that shares keywords with a covered
  item gets a warning.
- `unreadable` entries need `url` and `reason`, and should give a `cause`.
