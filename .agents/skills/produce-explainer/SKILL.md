---
name: produce-explainer
description: Only when the user types /produce-explainer. Runs the news pipeline in a dated run folder (scout, rank, topic approval, explainer, independent review, narrated scenes, hard gates), then outside GitHub Actions finish-video up to the hand-over package.
argument-hint: "[focus, e.g. humanoid locomotion] | resume runs/<run>"
disable-model-invocation: true
---

# Produce an explainer

Arguments: `$ARGUMENTS` (empty: any robotics topic; `resume runs/<run>`: continue that run).

0. **Guards.** Before anything else run `git -C . push --dry-run guards-off-canary`: it names no remote, so it changes
   nothing even when it runs. The project's Bash hook must refuse it with "Blocked by project policy". Any other
   outcome (git's own error, a refused permission, another message) means this session did not load the project's
   settings, hooks and deny rules: reply "guards off: start the session at the repository root" and stop.
1. Follow [stages.md](stages.md) from its stage 1 with that focus, or with the run to resume.
