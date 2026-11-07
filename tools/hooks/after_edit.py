#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): lint or validate a run's explainer, draft parts and JSON records once written.

A run is runs/<run>/ or any folder with a run.json; problems go to stderr with exit 2. Standard library only.
"""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import _common  # noqa: E402,F401  re-executes under .venv before stdin is read
MAX_LINES = 25


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    fp = (event.get("tool_input") or {}).get("file_path") or (event.get("tool_input") or {}).get("notebook_path")
    if not fp:
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or TOOLS.parent).resolve()
    path = Path(fp).resolve()
    run = None
    try:
        parts = path.relative_to(project).parts
        if len(parts) >= 3 and parts[0] == "runs":
            run = project / parts[0] / parts[1]
    except ValueError:
        parts = ()
    if run is None:                        # a run folder anywhere: the nearest ancestor with a run.json
        for anc in list(path.parents)[:4]:
            if (anc / "run.json").exists():
                run = anc
                break
    if run is None:
        return 0
    sub = path.relative_to(run).parts
    parts = (run.name,) + sub
    msgs = []
    if sub == ("explainer.html",):
        import lint_html
        msgs = [f"{i['level']}: [{i['code']}] {i['message']}" + (f" (line {i['line']})" if i["line"] else "")
                for i in lint_html.lint(path, run) if i["level"] == "error"]
        if any((run / "draft").glob("*.html")):
            msgs.append("note: explainer.html is generated from draft/ by tools/build_explainer.py; edit the draft "
                        "parts and rebuild, or this edit will be overwritten")
    elif len(sub) == 2 and sub[0] == "draft" and sub[1].endswith(".html"):
        import lint_html
        msgs = [f"error: [{i['code']}] {i['message']}" + (f" (line {i['line']})" if i["line"] else "")
                for i in lint_html.lint(path, run, part=True) if i["level"] == "error"]
    else:
        import validate
        kind = validate.kind_for(path)
        if kind:
            rep = validate.validate_file(kind, path, run)
            msgs = [f"error: {e}" for e in rep.errors]
    if not msgs:
        return 0
    shown = msgs[:MAX_LINES] + ([f"... and {len(msgs) - MAX_LINES} more"] if len(msgs) > MAX_LINES else [])
    print(f"Check of {'/'.join(parts)} after this edit:\n" + "\n".join(shown), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
