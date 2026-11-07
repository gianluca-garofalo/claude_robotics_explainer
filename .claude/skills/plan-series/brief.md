# Series brief (for the series-curator and the series-red-team)

The channel: Remaining Action explains robotics and control research with original animations, for researchers,
engineers and students. A series turns one finished explainer (and its companion code) into a sequence of narrated
videos that each work alone and together tell a story.

## What to design

- The story spine: the question the series answers, in one sentence (the `plan_sentence`, said in episode 1), and how
  each episode moves it forward (`story_beat`).
- The episodes: how many (each as long as its ideas need, at most 12 minutes: "The idea budget" below; fewer, deeper
  episodes beat many thin ones), in what order, each
  with a `short_title` (at most four words: it appears on the builds-on frame), a `hook` (the first 15-45 s, over a
  full moving picture, spoken by 3 s, its question by 15 s, paying off the title), an `outline`, a `takeaway` (one sentence of at most about 30 words and at most three
  equations: the card that ends the episode and recaps it later), a `teaser` ("In the next episode, ..."; none in the
  finale), `length_min`, a `target_viewer`, a `difficulty` (1-5) and whether it is a good `entry_point` from search.
- What is left out, and why (`material.notes`, PLAN.md): the explainer holds more than a series can show; choose.
- Prerequisites: `must` (a result the episode uses as a premise; it gets a recap) and `helpful` (context, not narrated
  beyond a clause), backward only; an episode of another series only if that series is released earlier
  (`related_series.follows`).
- Recaps: for each must, a recap of about 20-60 s that restates the result by meaning (`restates`) with its card
  (`card`, usually the earlier episode's takeaway equations); marked "Recap", its own chapter.
- The series context (`series_context`): the spoken sentence or two at the first natural break, about 30-90 s in
  (`at_s`), and the builds-on frame (`frame`: "Episode n of N" and the short titles it builds on). No map.
- Material: `material.section_ids` (the explainer sections it draws on: sources, not a mapping), `material.scripts`
  (the companion scripts that print its numbers) and the figures it reuses.
- The `playlist_description` (what the series is, for whom, in what order) and the release order (`release`).

## What makes an episode work (the red team checks these)

1. Watchable alone: a viewer arriving from search follows it; everything used is recapped; at most a soft pointer by
   title ("the episode on ... has the full story"), never "you must have watched" or "watch ... first".
2. Not overloaded: the declared ideas fit the budget (at most two starred results; the length follows from the
   ideas), and the declarations are honest: every result the episode states is declared.
3. Faithful: equations and claims match the explainer exactly; no new results.
4. Every number from a script in `code/` (or a closed form of the explainer); name the scripts.
5. Self-contained wording: nothing a viewer sees or hears names the explainer, code, files, links, sections, figures or
   equation numbers; other episodes only by title or meaning, never "equation 4 of episode 2".

## Format

Schema 2 (`python3 tools/series.py validate` checks it): series fields `schema_version`, `slug`, `title`, `source`,
`explainer_sha256`, `explainer_slug`, `playlist` (`title`, `privacy`), `plan_sentence`, `playlist_description`,
`related_series`, `release`; per episode `number`, `title`, `short_title`, `kind` (first, middle, finale by position),
`hook`, `length_min`, `takeaway` {`sentence`, `tex`}, `prerequisites` {`must`, `helpful`}, `recap`, `series_context`,
`teaser`, `ideas`, `material` {`section_ids`, `scripts`, `notes`}, `outline`, `story_beat`, `target_viewer`,
`difficulty`, `entry_point`.

## The idea budget (`ideas`; tools/video/idea_budget.py, config/video.json pacing.plan)

Every episode lists what it teaches, in story order, and the episode's length follows from that list:

```json
"ideas": [
  {"id": "remaining-action", "kind": "concept", "pretraining": true, "text": "the least cost still to pay, V_N"},
  {"id": "descent", "kind": "star", "uses": ["remaining-action"], "text": "the bill drops by at least each step's cost"},
  {"id": "feasible", "kind": "claim", "follows": "descent", "text": "the shifted plan stays feasible"},
  {"id": "worked-example", "kind": "claim", "example": true, "uses": ["descent"], "text": "weight 1.2 passes the test"}
]
```

- `kind`: `concept` (a new term or symbol the viewer must hold), `claim` (a result), `star` (a boxed or headline
  result: at most two per episode, the takeaway's). `id` is kebab-case and unique in the series: the producer
  declares the same ids where they land in the video, and a moved idea keeps its id.
- `uses`: the ideas it builds on, in this episode or an earlier one (never a later one). Declare them honestly: they
  decide what has to move together.
- `follows` (claims): an immediate consequence of another idea, said in a sentence or two. `names` (concepts): a term
  for an idea already taught ("the terminal cost" for the end cost). `pretraining` (concepts): named in the episode's
  one pretraining segment, before its first starred result (at most five). `example`, `side` (claims): the
  worked-example result and a side result, at most one each. `seconds`: more time for an idea that needs it, never
  less.
- Budget: 75-90 s per starred result or claim, 35 s per concept (20 s in pretraining), 10 s per consequence or
  term; starred results, claims and consequences 8 % more, because their derivations are read as slow blocks (-15 %,
  the owner's choice); plus consolidation (the hold and restatement after each starred result, a think prompt every
  four minutes, a summary per key idea, the pause after every narration block) and the fixed beats (hook, title beat,
  roadmap, end recap, outro, the recaps of earlier episodes). Write `seconds` at the ordinary pace: the slow reading is
  added to it. `python3 tools/series.py validate` prints what each episode needs; set
  `length_min` inside that range.
- Declare the ideas in story order: an idea builds only on ideas taught before it (in this episode or an earlier
  one); an idea assumed first and shown later is two ideas. A consequence `follows` a starred result or a claim of its
  own, never another consequence (a chain is a derivation: point it at the root, or give the step its own budget), and
  at most two follow one idea.
- Price the hard ones honestly with `seconds` [heuristic]: a starred result or claim whose explanation is a
  derivation of more than two steps held together (the Hamilton-Jacobi equation from the recursion: the step, the
  expansion, the limit) about 30 s more per step beyond two; a concept that is a transformation rather than a label
  (the Legendre transform) about 60 s. `names` is only for a term that adds nothing to the idea it names (no
  condition, no new object).
- The outline's beat minutes add up to what the ideas need (validate warns otherwise): the producer storyboards from
  them. A recap may list the ids it restates (`recap[].ideas`): they must be taught by the episodes it is `from`, so a
  recap card never shows a result that moved to another episode.
- An episode is over-packed when its ideas need more than 12 minutes or it has more than two starred results (or two
  example or side results): `validate` fails and names what to move, and where (the next episode, or the previous one
  for the finale), with what then stays and what the neighbour then needs, and what could be left to the explainer
  instead. Leave to the explainer the ideas `validate` names for a cut (nothing later builds on them: the coherence
  principle); move what later episodes need; or split the episode. Never plan a faster delivery.

Worked example, for the format only: two proposals made on 2026-10-31 from `sources/variational-whole-body-control`
are in [example/](example/). When you plan from that source, do not open them: the owner asked for a plan made anew
from the explainer, and an old plan would anchor it. For any other source, read them for the format, not the content.

## A source without companion code

A source folder may hold only `explainer.html` (no `code/`, no `data/`). Then no script prints the numbers yet:
plan every number an episode shows as a script the episode will write in its run's `code/` (name it in
`material.scripts`, marked as missing from the source) or as a closed form of the explainer. Never plan a number
read from the page or from memory. `tools/series.py validate` warns about such a source; PLAN.md says it too.
