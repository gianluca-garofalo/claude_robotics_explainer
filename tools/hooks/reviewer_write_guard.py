#!/usr/bin/env python3
"""PreToolUse hook of the reviewer subagents: file tools write only under runs/<run>/review/ (exit 2 otherwise)."""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import os
import sys
from pathlib import Path


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:                  # fail closed: an unreadable event blocks the call
        print("Remaining Action hook: could not read the hook input; blocked to stay safe", file=sys.stderr)
        return 2
    ti = event.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp:
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    try:
        parts = Path(fp).resolve().relative_to(project).parts
    except ValueError:
        parts = ()
    if len(parts) >= 4 and parts[0] == "runs" and parts[2] == "review":
        return 0
    print("Reviewers write only under runs/<run>/review/ (reports, check scripts, screenshots). Do not edit the "
          "explainer, drafts, code or references: describe the fix in your report (suggested_fix) instead.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
