# Series brief (for the series-curator and the series-red-team)

A series turns one finished explainer and its companion code into narrated videos for robotics and control
researchers, engineers and students; each works alone, and together they tell one story. It is not a walk through the
sections: choose what to show, in what order and at what depth, and say what is left out and why. Fewer, deeper
episodes beat many thin ones.

## What to design (schema 2; `python3 tools/series.py validate` checks the format and the lengths)

- Series: `schema_version`, `slug`, `title`, `source`, `explainer_sha256`, `explainer_slug`, `playlist` (`title`,
  `privacy`), `plan_sentence` (the question the series answers, said in episode 1), `playlist_description` (what, for
  whom, in what order), `related_series`, `release` (the release order).
- Each episode: `number`, `title`, `short_title` (on the builds-on frame), `kind` (first, middle, finale), `hook`
  (paying off the title: AGENTS.md, Conventions), `length_min`, `takeaway` {`sentence`, `tex`} (the card that ends it
  and recaps it later), `prerequisites` {`must`, `helpful`}, `recap`, `series_context`, `teaser` ("In the next
  episode, ..."; none in the finale), `ideas`, `material` {`section_ids`, `scripts`, `notes`}, `outline`, `story_beat`
  (how it moves the spine), `target_viewer`, `difficulty` (1-5), `entry_point` (a good start from search).
- What is left out, and why: `material.notes` and PLAN.md.
- Prerequisites point backward: `must` is a result used as a premise (it gets a recap); `helpful` is context, never
  narrated beyond a clause; an episode of another series only if that series is released earlier
  (`related_series.follows`).
- One `recap` per must: `title` starting "Recap", `from`, `seconds`, `card` (usually the earlier takeaway's
  equations), `restates` (the result by meaning), optional `ideas` (taught by its `from` episodes, so a card never
  shows a result that moved away). It is its own chapter.
- `series_context`: `spoken` (a sentence or two at the first natural break, `at_s`) and `frame` ("Episode n of N" and
  the short titles it builds on). No map.
- `material.section_ids`: the sections it draws on (sources, not a mapping); `material.scripts`: the scripts that print
  its numbers.
- Episodes are made fresh from the plan; scenes are kept only for an episode made again after a fix
  (`series/<slug>/episodes/epNN/scenes/`).

## What makes an episode work (the red team checks these)

1. Watchable alone: a viewer from search follows it; everything it uses is recapped; at most a soft pointer by title
   ("the episode on ... has the full story"), never "you must have watched" or "watch ... first".
2. Not overloaded: its ideas fit the budget below and are declared honestly: every result it states.
3. Faithful: equations and claims match the explainer exactly; no new results.
4. Every number from a script in `code/` (in `material.scripts`) or a closed form of the explainer.
5. Self-contained wording (AGENTS.md, Conventions): no explainer, code, files, links, sections, figures or equation
   numbers; other episodes by title or meaning only.

## The idea budget (`ideas`; tools/video/idea_budget.py, config/video.json `pacing.plan`)

Each episode lists what it teaches, in story order; its length follows from the list:

```json
"ideas": [
  {"id": "remaining-action", "kind": "concept", "pretraining": true, "text": "the least cost still to pay, V_N"},
  {"id": "descent", "kind": "star", "uses": ["remaining-action"], "text": "the bill drops by at least each step's cost"},
  {"id": "feasible", "kind": "claim", "follows": "descent", "text": "the shifted plan stays feasible"},
  {"id": "worked-example", "kind": "claim", "example": true, "uses": ["descent"], "text": "weight 1.2 passes the test"}
]
```

- `kind`: `concept` (a new term or symbol to hold), `claim` (a result) or `star` (a boxed or headline result, the
  takeaway's). `id`: kebab-case, unique in the series; the producer declares the same ids where they land in the
  video, and a moved idea keeps its id.
- `uses`: the ideas it builds on, here or in an earlier episode, never a later one; declared honestly, they decide
  what moves together. An idea builds only on ideas taught before it; one assumed first and shown later is two ideas.
- `follows` (claims): an immediate consequence, said in a sentence or two, of a starred result or claim, never of
  another consequence (a chain is a derivation: point it at the root, or budget the step). `names` (concepts): a term
  for an idea already taught that adds nothing (no condition, no new object). `pretraining` (concepts): named in the
  one pretraining segment, before the first starred result. `example`, `side` (claims): the worked-example result and
  a side result. `seconds`: more time, never less, at the ordinary pace.
- Price the hard ones with `seconds` [heuristic]: about 30 s per step beyond two for a starred result or claim whose
  explanation is a derivation of more than two steps held together (the Hamilton-Jacobi equation from the recursion);
  about 60 s for a concept that is a transformation, not a label (the Legendre transform).
- `pacing.plan` sets the time per kind, the consolidation, the fixed beats, the slow reading and the limits (starred,
  example, side and pretraining ideas, consequences per idea, the episode's length). `python3 tools/series.py
  validate` prints what each episode needs: set `length_min` inside that range, and make the outline's beat minutes
  add up to it.
- Over-packed: `validate` fails and names what to move and where (the next episode; the previous one for the
  finale), what then stays, and what could be left to the explainer instead. Leave those ideas to the explainer
  (nothing later builds on them), move what later episodes need, or split the episode. Never plan a faster delivery.

Format example: [example/](example/). Never open it when planning from `sources/variational-whole-body-control`; for
other sources, read it for the format only.

## A source without companion code

With only `explainer.html`, plan every number as a script the episode will write in its run's `code/` (in
`material.scripts`, marked as missing from the source) or as a closed form of the explainer; never a number from the
page or from memory. `validate` warns about such a source; PLAN.md says so too.
