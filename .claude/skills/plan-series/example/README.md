# Worked example: the first series plan

Two series proposed by the curator from the variational whole-body control explainer (2026-10-31; its source folder
is now `sources/variational-whole-body-control`): `series.mpc-mechanics.v2.json` ("The Mechanics of Predictive
Control", five episodes) and `series.forces-on-a-task.v2.json` ("Forces on a Task", five episodes, released after the
first). The fields that pointed at the scenes of an earlier pilot were removed on 2026-10-31, when the series were set
to start fresh.
They show the format, filled in. They are not plans: the series made from that source were removed on 2026-11-01,
when the owner asked for new plans made from the explainer by `/plan-series` (or `/produce-from-source`). A curator
planning from `sources/variational-whole-body-control` does not open this folder (see brief.md).
`python3 tools/series.py validate .claude/skills/plan-series/example/series.mpc-mechanics.v2.json` shows what the
validator checks.
