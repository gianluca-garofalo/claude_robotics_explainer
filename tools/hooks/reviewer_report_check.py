#!/usr/bin/env python3
"""Stop hook of the reviewer subagents (Claude Code runs it as SubagentStop): a reviewer finishes only when the report
it was asked to write passes tools/validate.py; otherwise exit 2 with the errors, so it fixes its own report.

Its files: the reports and verdicts its prompt names (a named report means its newest round), which must exist and be
written by this agent, and the JSON files it wrote at the top of a review folder or in verify/. A subagent's report
also states "independent" and "reviewed_by" (reviewer-contract.md). Standard library only; after MAX_BLOCKS blocks the
agent may stop, and the review-fanout workflow's or the skill's own check takes over.
"""
import sys
if sys.version_info < (3, 7):          # fail closed: an old python3 must never let a blocked action through
    sys.stderr.write("Remaining Action hook: python3 %d.%d is too old (3.7 or later is needed); blocked to stay safe. "
                     "Put a newer Python first in PATH.\n" % sys.version_info[:2])
    sys.exit(2)
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
MARK = "Report check (tools/hooks/reviewer_report_check.py)"
MAX_BLOCKS = 3
BLOCK_RE = re.compile(re.escape(MARK) + r", attempt (\d+) of \d+")
WRITERS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
IN_REVIEW = r"(?<![\w./-])/?(?:[\w.-]+/)*review/(?:[\w-]+/)?"     # a path whose folder is review/ or review/<set>/
VERDICT_RE = re.compile(IN_REVIEW + r"verify/[A-Z]+-\d+\.json(?![\w.-])")
ROUND_RE = re.compile(r"^(?P<base>.+?)(?:\.round(?P<n>\d+))?\.json$")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def epoch(stamp):
    try:
        return dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_transcript(path):
    """(the prompt, when the agent started in epoch seconds or None, the files it wrote, this hook's earlier blocks)."""
    prompt, start, written = "", None, []
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return prompt, start, written, 0
    for line in raw.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(msg, dict):
            continue
        if entry.get("type") == "user" and not prompt and not entry.get("isMeta"):
            prompt, start = text_of(msg.get("content")), epoch(entry.get("timestamp"))
        elif entry.get("type") == "assistant" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in WRITERS:
                    args = block.get("input") or {}
                    if args.get("file_path") or args.get("notebook_path"):
                        written.append(str(args.get("file_path") or args.get("notebook_path")))
    return prompt, start, written, len(set(BLOCK_RE.findall(raw)))


def resolve(path: str, project: Path) -> Path:
    p = Path(path).expanduser()
    return (p if p.is_absolute() else project / p).resolve()


def newest_round(path: Path) -> Path:
    """The newest round of a named report (<name>.json, <name>.round2.json, ...): a later round goes beside it."""
    base = ROUND_RE.match(path.name).group("base")
    rounds = [(1, path.parent / (base + ".json"))] if (path.parent / (base + ".json")).exists() else []
    for p in path.parent.glob(base + ".round*.json"):
        m = ROUND_RE.match(p.name)
        if m and m.group("base") == base and m.group("n"):
            rounds.append((int(m.group("n")), p))
    return max(rounds)[1] if rounds else path


def show(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def validator_errors(run: Path):
    """{file: [errors]} for the files tools/validate.py fails in this run, or None and the reason it did not run."""
    try:
        r = subprocess.run([sys.executable, str(REPO / "tools" / "validate.py"), str(run)], capture_output=True,
                           text=True, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "tools/validate.py did not run ({})".format(exc)
    failing, current = {}, None
    for line in r.stdout.splitlines():
        m = re.match(r"^\[(ok|FAIL)\] (.+?): \d+ error\(s\), \d+ warning\(s\)$", line)
        if m:
            current = failing.setdefault(resolve(m.group(2).split(": ", 1)[-1], REPO), []) \
                if m.group(1) == "FAIL" else None
        elif current is not None and line.startswith("  ERROR"):
            current.append(line.strip()[len("ERROR"):].strip())
    if r.returncode not in (0, 1):
        return None, "tools/validate.py failed: " + " ".join((r.stderr or r.stdout).strip().splitlines()[-3:])
    return failing, ""


def block(problems, attempt: int) -> int:
    """Exit 2 with the problems on stderr; the same as a JSON decision on stdout, so that no stderr wording can turn
    the block into a non-blocking error."""
    reason = ("{}, attempt {} of {}: finish only when the files you were asked to write pass. Fix these, then finish "
              "again:\n".format(MARK, attempt, MAX_BLOCKS) + "\n".join("- " + p for p in problems))
    print(json.dumps({"decision": "block", "reason": reason}))
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:                                # fail closed: an unreadable event blocks the stop
        event = None
    if not isinstance(event, dict):
        print("Remaining Action hook: could not read the hook input; blocked to stay safe", file=sys.stderr)
        return 2
    agent = str(event.get("agent_type") or "")
    prompt, start, written, blocks = read_transcript(event.get("agent_transcript_path")
                                                     or event.get("transcript_path"))
    if blocks >= MAX_BLOCKS:                          # the workflow's or the skill's check takes over
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    named = [m.group(0) for m in VERDICT_RE.finditer(prompt)]
    if agent:
        named += [m.group(0) for m in re.finditer(IN_REVIEW + re.escape(agent) + r"(?:\.round\d+)?\.json(?![\w.-])",
                                                  prompt)]
    problems, files, reports = [], [], set()
    for path in dict.fromkeys(resolve(p, project) for p in named):
        is_report = path.parent.name != "verify"
        path = newest_round(path) if is_report else path
        if not path.exists():
            problems.append("{} has not been written: write it (reviewer-contract.md)".format(show(path)))
            continue
        if start is not None and path.stat().st_mtime < start:
            problems.append("{} is older than this review: write it now{}".format(show(path), (
                " (a later round goes in {}.round{}.json beside it: reviewer-contract.md, Second round)".format(
                    ROUND_RE.match(path.name).group("base"), int(ROUND_RE.match(path.name).group("n") or 1) + 1)
                if is_report else "")))
            continue
        files.append(path)
        if is_report:
            reports.add(path)
    for p in written:                                 # the validator reads what lies at the top of a review folder
        path = resolve(p, project)
        if path.suffix == ".json" and path.exists() and any(a.name == "review" for a in list(path.parents)[:3]):
            files.append(path)
    runs = {}
    for path in dict.fromkeys(files):
        top = next((a for a in path.parents if a.name == "review"), None)
        if top is not None:
            runs.setdefault(top.parent, []).append(path)
    for run, paths in runs.items():
        failing, why = validator_errors(run)
        if failing is None:
            problems.append(why)
            continue
        for path in paths:
            problems += ["{}: {}".format(show(path), e) for e in failing.get(path, [])]
    if event.get("hook_event_name", "SubagentStop") == "SubagentStop":
        for path in sorted(reports):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue                              # the validator has said why
            if isinstance(data, dict) and not (isinstance(data.get("independent"), bool)
                                               and str(data.get("reviewed_by") or "").strip()):
                problems.append('{}: add "independent": true and "reviewed_by": "{} subagent" at the top level '
                                "(reviewer-contract.md, Report)".format(show(path), agent))
    return block(problems, blocks + 1) if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - fail closed: a crash blocks the action and says why
        sys.stderr.write(f"Remaining Action hook {Path(__file__).name} failed ({type(exc).__name__}: {exc}); "
                         "blocked to stay safe\n")
        sys.exit(2)
