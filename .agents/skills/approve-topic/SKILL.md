---
name: approve-topic
description: Only when the user types /approve-topic with a run and a topic id (topic_approval human in config/pipeline.json). A hook records approval.json from what the user typed; then the run continues with the explainer. Claude never runs it.
argument-hint: "runs/<run> <topic-id> [note]"
disable-model-invocation: true
---

The user typed `/approve-topic $ARGUMENTS`. Before this message reached you, the project's UserPromptExpansion hook
(`tools/hooks/record_approval.py`) either wrote `approval.json` in that run or blocked the command with a reason the
user saw. Never write or edit `approval.json` yourself.

1. `python3 tools/run.py status <run>`: the approval stage must be done. If it shows `waiting`, the hook did not run
   (workspace not trusted, or hooks disabled): tell the user, point to the manual fallback in README.md, and stop.
2. If `approval.json` has a `gate_status` starting with `excluded`, tell the user how the explainer will handle the
   gate reason (for example an evidence box that separates what the paper shows from what was only claimed).
3. Continue with `.agents/skills/produce-explainer/stages.md` from its stage 5 (Write) on that run, through stage 11:
   the stages of `/produce-explainer`, which only the user can invoke as a command.
