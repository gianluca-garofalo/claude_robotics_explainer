# series/

One folder per video series: `series/<slug>/series.json` (the plan, schema 2) and `series/<slug>/PLAN.md` (the same
plan for people). Series are made from a source document, `sources/<name>/`, by `/plan-series sources/<name>`, or as
the first step of `/produce-from-source sources/<name>`: a curator subagent proposes one or more series, an independent
red team checks every episode, and `tools/series.py write` stores the plans here.

- `python3 tools/series.py from-source sources/<name>` lists the series made from a source, in release order.
- `python3 tools/series.py list series/<slug>` shows the episodes; `python3 tools/series.py next series/<slug>` names
  the next one in the plan's release order.
- Plan approval follows `config/pipeline.json` `series.plan_approval`: `optional` (the owner approves only the
  finished video) or `required` (the owner runs `./tools/human/approve_series.py series/<slug>` before any episode).
- `series/<slug>/episodes/epNN/scenes/` may hold scenes kept for an episode that is made again after a fix;
  `tools/series.py start --fresh` leaves them out.

Edit a plan only through `/plan-series` (`tools/series.py write --replace`), never by hand.
