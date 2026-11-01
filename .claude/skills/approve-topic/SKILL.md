---
name: approve-topic
description: Records the user's approval of one ranked topic so that writing can start, when config/pipeline.json sets topic_approval to human. The user types it; Claude never runs it.
argument-hint: "runs/<run> <topic-id> [note]"
disable-model-invocation: true
---

The user typed `/approve-topic $ARGUMENTS`.

Before this message reached you, the project's UserPromptExpansion hook (`tools/hooks/record_approval.py`) either
wrote `approval.json` in that run or blocked the command with a reason the user saw. You never write or edit
`approval.json` yourself.

1. Run `python3 tools/run.py status <run>`. The approval stage must show the topic as done. If it shows `waiting`, the
   hook did not run (workspace not trusted or hooks disabled): tell the user, point to the manual fallback in
   README.md, and stop.
2. If `approval.json` has a `gate_status` starting with `excluded`, tell the user how the explainer will handle the gate
   reason (for example an evidence box that separates what the paper shows from what was only claimed).
3. Continue the pipeline: `python3 tools/run.py finalize <run>` (renames the folder to the topic slug), then the
   `didactic-html-writer` skill, then the remaining stages of `/produce-explainer` from its step 6.
