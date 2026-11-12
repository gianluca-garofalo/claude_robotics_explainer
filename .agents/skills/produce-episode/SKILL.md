---
name: produce-episode
description: Only when the user types /produce-episode with a series and an episode (or resume with a run). Makes one narrated episode of a planned series from its source explainer (series beats, checks, design review, pre-render gates), then outside GitHub Actions finish-video up to the hand-over package.
argument-hint: "series/<series> <episode number | next> [fresh] | resume runs/<run>"
disable-model-invocation: true
---

# Produce a series episode

Arguments: `$ARGUMENTS`: a series folder and an episode (`next` or a number, `fresh` to start without kept scenes),
or `resume` with a run.

0. **Guards.** Before anything else run `git -C . push --dry-run guards-off-canary`: it names no remote, so it changes
   nothing even when it runs. The project's Bash hook must refuse it with "Blocked by project policy". Any other
   outcome (git's own error, a refused permission, another message) means this session did not load the project's
   settings, hooks and deny rules: reply "guards off: start the session at the repository root" and stop.
1. Follow [stages.md](stages.md) with that series and episode, or with the run to resume.
