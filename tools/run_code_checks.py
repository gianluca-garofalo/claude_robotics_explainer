#!/usr/bin/env python3
"""Run every script listed in <folder>/code/checks.toml and record the evidence in code/logs/.

Usage:
  python3 tools/run_code_checks.py runs/<run> [--only SCRIPT] [--python PYTHON]
  python3 tools/run_code_checks.py sources/<name> [--logs DIR]       # runs in a temporary copy (see below)

Each script runs from its own folder with a timeout (MPLBACKEND=Agg, PYTHONHASHSEED=0). A check passes when the
script exits 0, every `expect` substring appears in its output and every `produces` file exists afterwards.
Output: code/logs/<script>.log (stdout+stderr) and code/logs/summary.json, or the same files in --logs DIR. Exit
status 1 if any check fails. Warnings: scripts under code/ missing from the manifest, manifest scripts missing from
code/README.md.

A run folder's scripts run in place: the figures and files they write belong to the run. A source document
(sources/<name>/, or any folder given with --copy) is read-only: its folder is copied to a temporary directory, the
scripts run there and their outputs are checked there and then discarded, so the source stays byte-identical except
for code/logs/ (the evidence of the last run, written on purpose), or byte-identical with --logs DIR.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402


def _copy_ignore(root: Path):
    """copytree filter: no caches anywhere, no code/logs/ (the copy writes no evidence)."""
    def ignore(folder: str, names: list[str]) -> set[str]:
        skip = {n for n in names if n in ("__pycache__", ".pytest_cache")}
        if Path(folder).resolve() == (root / "code").resolve() and "logs" in names:
            skip.add("logs")
        return skip
    return ignore


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--only", help="run only this script (path as in checks.toml)")
    ap.add_argument("--python", default=sys.executable, help="interpreter (default: the one running this tool)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--copy", action="store_true",
                      help="run in a temporary copy of the folder (the default for sources/<name>)")
    mode.add_argument("--in-place", action="store_true", help="run in the folder itself, also for sources/<name>")
    ap.add_argument("--logs", metavar="DIR", help="write the logs and summary.json to DIR instead of code/logs/")
    a = ap.parse_args()
    run = resolve_run(a.run)
    code = run / "code"
    manifest = code / "checks.toml"
    if not manifest.exists():
        print(f"error: {rel(manifest)} missing", file=sys.stderr)
        return 1
    checks = tomllib.loads(manifest.read_text(encoding="utf-8")).get("check", [])
    if a.only:
        checks = [c for c in checks if c.get("script") == a.only]
    if not checks:
        print("error: no [[check]] entries to run", file=sys.stderr)
        return 1
    copy = a.copy or (run.parent.name == "sources" and not a.in_place)
    logs = Path(a.logs).resolve() if a.logs else code / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tmp = None
    work = code                                   # where the scripts run and write
    if copy:
        tmp = Path(tempfile.mkdtemp(prefix="code-checks-"))
        shutil.copytree(run, tmp / run.name, ignore=_copy_ignore(run), symlinks=True)
        work = tmp / run.name / "code"
        print(f"running in a temporary copy of {rel(run)} (its files stay as they are"
              f"{'' if a.logs else ' apart from code/logs/'})")
    try:
        results = _run_checks(checks, code, work, logs, a.python)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    listed = {c["script"] for c in tomllib.loads(manifest.read_text(encoding="utf-8")).get("check", [])}
    readme = (code / "README.md").read_text(encoding="utf-8") if (code / "README.md").exists() else ""
    warnings = []
    for py in sorted(code.rglob("*.py")):
        r = py.relative_to(code).as_posix()
        if r.startswith(("logs/", "figures/")) or "__pycache__" in r:
            continue
        if r not in listed:
            warnings.append(f"{r} is not in checks.toml (fine for helper modules imported by checks)")
    for s in sorted(listed):
        if Path(s).name not in readme:
            warnings.append(f"{s} is not described in code/README.md")
    for w in warnings:
        print(f"warning: {w}")
    write_json(logs / "summary.json", {"schema_version": 1, "ran_at": utc_now(), "python": Path(a.python).name,
                                        "manifest_sha256": sha256_file(manifest), "checks": results,
                                        "warnings": warnings, "ran_in": "temporary copy" if copy else "in place"})
    failed = [r for r in results if not r["ok"]]
    print(f"run_code_checks: {'FAIL' if failed else 'ok'} ({len(results) - len(failed)}/{len(results)} passed); "
          f"logs in {rel(logs)}")
    return 1 if failed else 0


def _run_checks(checks: list[dict], code: Path, work: Path, logs: Path, python: str) -> list[dict]:
    """Run each check with cwd in `work` (code/ itself, or its temporary copy); logs and hashes name `code`."""
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    results = []
    for c in checks:
        script = c["script"]
        path, run_path = code / script, work / script
        log = logs / (script.replace("/", "__") + ".log")
        res = {"script": script, "sections": c.get("sections", []), "claims": c.get("claims", ""), "ok": False,
               "log": rel(log), "sha256": sha256_file(path) if path.exists() else None}
        if not run_path.exists():
            res["error"] = "script not found"
            results.append(res)
            print(f"FAIL  {script}: not found")
            continue
        t0 = time.time()
        try:
            p = subprocess.run([python, run_path.name, *map(str, c.get("args", []))], cwd=run_path.parent, env=env,
                               capture_output=True, text=True, timeout=c.get("timeout", 300))
            out, rc = p.stdout + ("\n--- stderr ---\n" + p.stderr if p.stderr.strip() else ""), p.returncode
        except subprocess.TimeoutExpired as exc:
            out, rc = (exc.stdout or "") if isinstance(exc.stdout, str) else "", None
            res["error"] = f"timeout after {c.get('timeout', 300)} s"
        secs = round(time.time() - t0, 2)
        log.write_text(f"# {script} {' '.join(map(str, c.get('args', [])))}\n# exit {rc}, {secs} s\n{out}",
                       encoding="utf-8")
        missing_expect = [e for e in c.get("expect", []) if e not in out]
        missing_prod = [f for f in c.get("produces", []) if not (work / f).exists()]
        res.update(rc=rc, seconds=secs, missing_expect=missing_expect, missing_produces=missing_prod)
        res["ok"] = rc == 0 and not missing_expect and not missing_prod
        results.append(res)
        why = "" if res["ok"] else f" (exit {rc}; missing output {missing_expect}; missing files {missing_prod})"
        print(f"{'ok  ' if res['ok'] else 'FAIL'}  {script}  {secs:.1f} s{why}")
    return results


if __name__ == "__main__":
    sys.exit(main())
