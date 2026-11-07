# runs/

One folder per local run, git-ignored (see `.gitignore`): `YYYY-MM-DD-<slug>` (created as `YYYY-MM-DD-scouting` and
renamed once the topic is chosen), or `YYYY-MM-DD-<series>-epNN-<slug>` for a series episode. README.md, "Layout",
shows what a run holds; `python3 tools/run.py status runs/<run>` shows what is done, stale or next. Runs of the
scheduled workflow live in its artifacts (`run-final`, 90 days) and, once published, on the `gh-pages` branch.
