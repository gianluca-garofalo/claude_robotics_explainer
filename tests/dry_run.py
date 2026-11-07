#!/usr/bin/env python3
"""End-to-end dry run of the pipeline's deterministic parts on fictional fixtures; nothing leaves the machine.

Usage:
  python3 tests/dry_run.py [--keep] [--skip-browser] [--skip-video]   # exit 1 if a step fails; skips say why
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
FIX = REPO / "tests" / "fixtures" / "run"
PY = sys.executable
sys.path.insert(0, str(REPO / "tools"))
from gate import REVIEWERS  # noqa: E402
RESULTS: list[tuple[str, str, str]] = []


def run(name, cmd, expect=0, stdin=None, env=None, check=None, cwd=REPO):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, input=stdin, env=env)
    ok = r.returncode == expect
    detail = ""
    if ok and check:
        res = check(r)
        ok, detail = (res, "") if isinstance(res, bool) else res
    RESULTS.append((name, "ok" if ok else "FAIL", detail or (r.stdout.strip().splitlines() or [""])[-1][:110]))
    if not ok:
        print(f"--- {name} (exit {r.returncode}, expected {expect})\n{r.stdout[-2500:]}\n{r.stderr[-2500:]}")
    return r


def skip(name, why):
    RESULTS.append((name, "skip", why))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder and print its path")
    ap.add_argument("--skip-browser", action="store_true")
    ap.add_argument("--skip-video", action="store_true")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="explainer-dry-run-"))
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp))
    try:
        r = run("run.py new", [PY, "tools/run.py", "new", *testenv.COVERAGE_ARGS, "--root", str(tmp / "runs"), "--date", "2026-10-30",
                               "--focus", "fixture"])
        rundir = REPO / r.stdout.strip() if not Path(r.stdout.strip()).is_absolute() else Path(r.stdout.strip())
        if not rundir.is_dir():
            rundir = tmp / "runs" / "2026-10-30-scouting"
        for f in ("sources.json", "scores.json"):
            shutil.copy(FIX / f, rundir / f)
        run("validate sources+scores", [PY, "tools/validate.py", str(rundir)])
        run("rank_topics", [PY, "tools/rank_topics.py", str(rundir)],
            check=lambda r: (lambda md: ("1. T1" in r.stdout and "excluded: no primary source" in md,
                                         "T1 ranked first; T3 gated (no primary source, hype)"))(
                (rundir / "ranking.md").read_text()))
        bad_inputs = rundir.parent / "bad"
        shutil.copytree(rundir, bad_inputs)
        s = json.loads((bad_inputs / "scores.json").read_text())
        s["topics"][0]["scores"]["recency"] = {"score": 5, "why": "judged recency is not allowed", "sources": []}
        (bad_inputs / "scores.json").write_text(json.dumps(s))
        run("rank_topics rejects a judged recency", [PY, "tools/rank_topics.py", str(bad_inputs)], expect=1)
        shutil.rmtree(bad_inputs)

        rel_run = f"runs/{rundir.name}"
        ev = {"hook_event_name": "UserPromptExpansion", "command_name": "approve-topic", "session_id": "dry-run",
              "expansion_type": "slash_command", "command_args": f"{rel_run} T9", "prompt": f"/approve-topic {rel_run} T9"}
        run("approval hook blocks an unknown topic", [PY, "tools/hooks/record_approval.py"], stdin=json.dumps(ev),
            env=env, check=lambda r: (json.loads(r.stdout).get("decision") == "block" and not (rundir / "approval.json").exists(),
                                      json.loads(r.stdout).get("reason", "")[:100]))
        ev["command_args"] = f"{rel_run} T1 approved in the dry run"
        run("approval hook records the user's choice", [PY, "tools/hooks/record_approval.py"], stdin=json.dumps(ev),
            env=env, check=lambda r: ("additionalContext" in r.stdout and (rundir / "approval.json").exists(),
                                      "approval.json written by the hook"))
        run("run.py finalize", [PY, "tools/run.py", "finalize", str(rundir)])
        rundir = tmp / "runs" / "2026-10-30-fixture-descent-certificate"
        rel_run = f"runs/{rundir.name}"
        if not rundir.is_dir():
            RESULTS.append(("finalized folder name", "FAIL", f"{rundir.name} missing"))
            return report(tmp, a.keep)

        shutil.copytree(FIX / "draft", rundir / "draft", dirs_exist_ok=True)
        shutil.copytree(FIX / "code", rundir / "code", dirs_exist_ok=True)
        shutil.copy(FIX / "references.json", rundir / "references.json")
        run("run_code_checks", [PY, "tools/run_code_checks.py", str(rundir)])
        run("build_explainer --strict", [PY, "tools/build_explainer.py", str(rundir), "--strict"])
        run("lint_html --strict", [PY, "tools/lint_html.py", str(rundir / "explainer.html"), "--strict",
                                   "--run-dir", str(rundir)])

        def hook(name, script, payload, expect):
            run(name, [PY, f"tools/hooks/{script}"], stdin=json.dumps(payload), env=env, expect=expect)
        part = rundir / "draft" / "10-idea.html"
        hook("PostToolUse hook: clean draft part", "after_edit.py",
             {"tool_name": "Edit", "tool_input": {"file_path": str(part)}}, 0)
        broken = rundir / "draft" / "50-broken.html"
        broken.write_text('<section id="sec-x"><h2>X</h2><p>Costs $5 and [[eq:oops </p></section>\n')
        hook("PostToolUse hook: broken draft part -> exit 2", "after_edit.py",
             {"tool_name": "Write", "tool_input": {"file_path": str(broken)}}, 2)
        broken.unlink()
        hook("PostToolUse hook: file outside runs/ ignored", "after_edit.py",
             {"tool_name": "Write", "tool_input": {"file_path": str(tmp / "notes.txt")}}, 0)
        hook("PreToolUse hook: git -C . push blocked", "block_publish.py",
             {"tool_name": "Bash", "tool_input": {"command": "cd x && git -C . push origin main"}}, 2)
        hook("PreToolUse hook: youtube upload blocked", "block_publish.py",
             {"tool_name": "Bash", "tool_input": {"command": "sh -c 'youtube-upload --title T video.mp4'"}}, 2)
        hook("PreToolUse hook: harmless command allowed", "block_publish.py",
             {"tool_name": "Bash", "tool_input": {"command": "grep -n 'git push' CLAUDE.md"}}, 0)
        hook("reviewer guard: write to explainer blocked", "reviewer_write_guard.py",
             {"tool_name": "Write", "tool_input": {"file_path": str(rundir / "explainer.html")}}, 2)
        hook("reviewer guard: write under review/ allowed", "reviewer_write_guard.py",
             {"tool_name": "Write", "tool_input": {"file_path": str(rundir / "review" / "x.json")}}, 0)

        shutil.copytree(FIX / "review", rundir / "review", dirs_exist_ok=True)
        run("merge_reviews", [PY, "tools/merge_reviews.py", str(rundir)],
            check=lambda r: (json.loads((rundir / "review" / "summary.json").read_text())["open_blocker_major"] == [],
                             "TC-1 refuted by the verifier: 0 open blocker/major"))

        node = shutil.which("node")
        if a.skip_browser or not node:
            skip("check_html.js", "--skip-browser" if a.skip_browser else "node not found")
        else:
            cmd = ["node", "tools/check_html.js", str(rundir / "explainer.html"), "--json",
                   str(rundir / "review" / "check_html.json")]
            if os.environ.get("KATEX_DIST") or (REPO / "node_modules" / "katex").exists():
                cmd.append("--offline")
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
            if r.returncode == 3:
                skip("check_html.js", (r.stderr.strip().splitlines() or ["setup problem"])[-1][:110])
            else:
                RESULTS.append(("check_html.js (1400 px, 390 px)", "ok" if r.returncode == 0 else "FAIL",
                                r.stdout.strip().splitlines()[-1][:110]))
                if r.returncode:
                    print(r.stdout[-3000:], r.stderr[-1500:])

        manim = os.environ.get("MANIM") or (str(REPO / ".venv/bin/manim") if (REPO / ".venv/bin/manim").exists()
                                            else shutil.which("manim"))
        if a.skip_video or not manim:
            skip("render_video.sh --check", "--skip-video" if a.skip_video else "manim not found")
        else:
            for f in ("common.py", "voice.py", "reading_model.py", "scene_template.py"):
                shutil.copy(REPO / "templates" / "manim" / f, rundir / "video" / "scenes" / f)
            run("render_video.sh --check (template scene, -ql)", ["bash", "tools/render_video.sh", str(rundir), "--check"],
                env=dict(os.environ, MANIM=manim))

        if node:
            run("workflow review-fanout with stub agents", ["node", "-e", WORKFLOW_HARNESS,
                                                            str(REPO / ".claude" / "workflows" / "review-fanout.js")],
                check=lambda r: (lambda o: (o["run"] == "runs/fixture" and o["verdicts"] == ["TC-1: refuted (stub)"]
                                            and len(o["reviewers"]) == len(REVIEWERS) and o["failedReviewers"] == [],
                                            f"{len(o['reviewers'])} reviewers, {len(o['verdicts'])} verification, "
                                            "merge step called"))(
                    json.loads(r.stdout.strip().splitlines()[-1])))
        else:
            skip("workflow review-fanout with stub agents", "node not found")

        run("run.py status", [PY, "tools/run.py", "status", str(rundir)],
            check=lambda r: (bool(re.search(r"approval\s+done", r.stdout) and re.search(r"write\s+done", r.stdout)),
                             r.stdout.strip().splitlines()[-1][:110]))
        run("run.py package", [PY, "tools/run.py", "package", str(rundir)])
        return report(tmp, a.keep)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


WORKFLOW_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8').replace('export const meta', 'const meta');
const calls = [];
const g = {
  args: 'runs/fixture',
  log: m => calls.push(['log', m]),
  phase: t => calls.push(['phase', t]),
  agent: async (prompt, o = {}) => {
    calls.push(['agent', o.agentType || 'default', o.phase]);
    if (o.agentType === 'finding-verifier') return { finding: 'TC-1', verdict: 'refuted', reason: 'stub' };
    if (o.agentType) return { reviewer: o.agentType, findings: o.agentType === 'technical-correctness-reviewer'
      ? [{ id: 'TC-1', severity: 'major', location: 'eq. (1)', issue: 'stub' }, { id: 'TC-2', severity: 'nit', location: 'x', issue: 'stub' }] : [] };
    return 'merge: stub';
  },
  parallel: async thunks => Promise.all(thunks.map(t => t().catch(() => null))),
  pipeline: async (items, ...stages) => Promise.all(items.map(async (item, i) => {
    let prev = item;
    for (const s of stages) { prev = await s(prev, item, i); if (prev === null) return null; }
    return prev;
  }).map(p => p.catch(() => null))),
};
const fn = new Function(...Object.keys(g), `return (async () => {\n${src}\n})();`);
fn(...Object.values(g)).then(out => {
  const agents = calls.filter(c => c[0] === 'agent');
  if (agents.filter(c => c[1] === 'finding-verifier').length !== 1) throw new Error('expected one verifier call');
  console.log(JSON.stringify(out));
}).catch(e => { console.error(e.stack || e); process.exit(1); });
"""


def report(tmp: Path, keep: bool) -> int:
    w = max(len(n) for n, _, _ in RESULTS)
    print()
    for n, st, d in RESULTS:
        print(f"{st:5} {n:<{w}}  {d}")
    fails = [n for n, st, _ in RESULTS if st == "FAIL"]
    print(f"\ndry run: {'FAIL' if fails else 'ok'} ({sum(st == 'ok' for _, st, _ in RESULTS)} ok, "
          f"{sum(st == 'skip' for _, st, _ in RESULTS)} skipped, {len(fails)} failed)")
    if keep:
        print(f"kept: {tmp}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
