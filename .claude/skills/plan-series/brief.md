# Series brief (for the series-curator and the series-red-team)

The channel: Remaining Action explains robotics and control research with original animations, for researchers,
engineers and students. A series turns one finished explainer (and its companion code) into a sequence of narrated
videos that each work alone and together tell a story.

## What to design

- The story spine: the question the series answers, in one sentence (the `plan_sentence`, said in episode 1), and how
  each episode moves it forward (`story_beat`).
- The episodes: how many (each about 8-12 minutes; fewer, deeper episodes beat many thin ones), in what order, each
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
2. Not overloaded: about three new ideas at most.
3. Faithful: equations and claims match the explainer exactly; no new results.
4. Every number from a script in `code/` (or a closed form of the explainer); name the scripts.
5. Self-contained wording: nothing a viewer sees or hears names the explainer, code, files, links, sections, figures or
   equation numbers; other episodes only by title or meaning, never "equation 4 of episode 2".

## Format

Schema 2 (`python3 tools/series.py validate` checks it): series fields `schema_version`, `slug`, `title`, `source`,
`explainer_sha256`, `explainer_slug`, `playlist` (`title`, `privacy`), `plan_sentence`, `playlist_description`,
`related_series`, `release`; per episode `number`, `title`, `short_title`, `kind` (first, middle, finale by position),
`hook`, `length_min`, `takeaway` {`sentence`, `tex`}, `prerequisites` {`must`, `helpful`}, `recap`, `series_context`,
`teaser`, `material` {`section_ids`, `scripts`, `notes`}, `outline`, `story_beat`, `target_viewer`, `difficulty`,
`entry_point`.

Worked example, for the format only: two proposals made on 2026-10-31 from `sources/variational-whole-body-control`
are in [example/](example/). When you plan from that source, do not open them: the owner asked for a plan made anew
from the explainer, and an old plan would anchor it. For any other source, read them for the format, not the content.

## A source without companion code

A source folder may hold only `explainer.html` (no `code/`, no `data/`). Then no script prints the numbers yet:
plan every number an episode shows as a script the episode will write in its run's `code/` (name it in
`material.scripts`, marked as missing from the source) or as a closed form of the explainer. Never plan a number
read from the page or from memory. `tools/series.py validate` warns about such a source; PLAN.md says it too.
