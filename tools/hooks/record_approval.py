#!/usr/bin/env python3
"""UserPromptExpansion hook for /approve-topic: write approval.json from the arguments the user typed.

The event fires only when the user types a command, never when Claude invokes a skill, so the approval cannot be
produced by the model. On a problem the hook blocks the command and the reason is shown to the user.
Input (stdin): the hook JSON with command_name, command_args, session_id. Output: hook JSON on stdout.
"""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "human"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def reply(obj: dict) -> int:
    print(json.dumps(obj))
    return 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return reply({"decision": "block", "reason": "approve-topic hook: could not read the hook input"})
    if event.get("command_name", "").split(":")[-1] != "approve-topic":
        return 0
    try:
        args = shlex.split(event.get("command_args", "") or "")
    except ValueError as exc:
        return reply({"decision": "block", "reason": f"approve-topic: cannot parse arguments ({exc})"})
    if len(args) < 2:
        return reply({"decision": "block",
                      "reason": "usage: /approve-topic runs/<run> <topic-id> [note]  (topic ids are in ranking.md)"})
    from approve_topic import ApprovalError, record  # noqa: E402
    try:
        d = record(args[0], args[1], via="/approve-topic typed by the user (UserPromptExpansion hook)",
                   note=" ".join(args[2:]), session_id=event.get("session_id"))
    except ApprovalError as exc:
        return reply({"decision": "block", "reason": f"approve-topic: {exc}"})
    ctx = (f"approval.json was written by the approval hook: topic {d['topic_id']} \"{d['title']}\" "
           f"(rank {d['rank']}, total {d['total']}, {d['gate_status']}) approved at {d['approved_at']}.")
    return reply({"hookSpecificOutput": {"hookEventName": "UserPromptExpansion", "additionalContext": ctx}})


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
