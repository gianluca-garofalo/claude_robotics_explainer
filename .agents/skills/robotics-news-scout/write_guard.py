#!/usr/bin/env python3
"""PreToolUse hook of the news-scout subagent: file tools write only <run>/sources.json (exit 2 otherwise).

A run folder is one that holds run.json (tools/run.py new). Standard library only; anything unexpected blocks.
"""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import os
from pathlib import Path


def allowed(file_path: str, cwd: str) -> bool:
    p = Path(file_path)
    if not p.is_absolute():
        p = Path(cwd) / p
    p = p.resolve()
    return p.name == "sources.json" and (p.parent / "run.json").is_file()


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:                  # fail closed: an unreadable event blocks the call
        print("Remaining Action hook: could not read the hook input; blocked to stay safe", file=sys.stderr)
        return 2
    ti = event.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    if fp and allowed(fp, cwd):
        return 0
    print("The scout writes only the run's sources.json (a folder with run.json). Put everything else in your "
          "report; never write other files.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
