# series/

One folder per video series made from a source document: `series.json` (the plan) and `PLAN.md` (the same plan for
people), written only by `tools/series.py write` (`/plan-series sources/<name>`, or the first step of
`/produce-from-source`), never by hand. `episodes/epNN/scenes/` may hold scenes kept for an episode made again after a
fix; `tools/series.py start --fresh` leaves them out.

- `python3 tools/series.py from-source sources/<name>`: the series of a source, in release order.
- `python3 tools/series.py list series/<slug>` shows the episodes, `next` the next one in release order.
- Plan approval follows `series.plan_approval` in `config/pipeline.json`: `optional` (the owner approves only the
  finished video) or `required` (read `PLAN.md`, run `./tools/human/approve_series.py series/<slug>` in your own
  terminal and commit `series/`; a changed plan needs a new approval).
