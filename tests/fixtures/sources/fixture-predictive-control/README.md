# Fixture source (tests only)

A short source document in the house format, not a real explainer: the tests plan series from it, start episodes
from it and run its scripts, so that adding, replacing or editing a real source in `sources/` never changes a test.
`explainer.html` was built with `tools/build_explainer.py`; `code/` holds the scripts behind its numbers (with
`checks.toml` and the logs of their last run) and `data/` a small input file that episodes copy as `video/data/`.
