#!/usr/bin/env python3
"""Run folders: create one, report its pipeline status, rename it after the topic approval, zip it.

Usage:
  python3 tools/run.py new [--focus "legged locomotion"] [--slug scouting] [--date YYYY-MM-DD] [--root runs]
                          [--window-days N] [--ledger L] [--sources DIR] [--series DIR]   # the last two: tests
  python3 tools/run.py status runs/<run> [--json]
  python3 tools/run.py finalize runs/<run>        # after the topic approval: rename to runs/<date>-<slug>
  python3 tools/run.py package runs/<run> [--out ZIP]   # deterministic zip next to the run (never uploaded)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (RUNS, SLUG_RE, TEMPLATES, CONFIG, die, load_json, parse_date, ranking_inputs, read_json,  # noqa: E402
                     read_ledger, rel, resolve_run, sha256_file, today_local, write_json)
import validate as V  # noqa: E402

SUBDIRS = ["draft", "code/figures", "code/logs", "review", "video/scenes", "video/data", "video/renders",
           "video/final"]
PACKAGE_SKIP_DIRS = {"media", "__pycache__", "checks", "screens", ".ipynb_checkpoints"}


def cmd_new(a) -> int:
    date = a.date or today_local()
    parse_date(date)
    slug = a.slug or "scouting"
    if not SLUG_RE.match(slug):
        die("slug must be kebab-case")
    root = Path(a.root) if a.root else RUNS
    ledger = read_ledger(a.ledger, root)
    base = root / f"{date}-{slug}"
    run, n = base, 2
    while run.exists():
        run = Path(f"{base}-{n}")
        n += 1
    for d in SUBDIRS:
        (run / d).mkdir(parents=True, exist_ok=True)
    scout = load_json(CONFIG / "scout.json")
    window = a.window_days or scout["window_days"]
    if window <= 0:
        die("--window-days must be positive")
    write_json(run / "run.json", {"schema_version": 1, "run_date": date, "focus": a.focus or "",
                                  "window_days": window,
                                  "window_source": "--window-days" if a.window_days else "config/scout.json"})
    readme = (TEMPLATES / "run" / "code_README.md").read_text(encoding="utf-8")
    (run / "code" / "README.md").write_text(readme.replace("runs/RUN_FOLDER", rel(run)), encoding="utf-8")
    shutil.copy(TEMPLATES / "run" / "checks.toml", run / "code" / "checks.toml")
    write_json(run / "published.json", ledger)
    import coverage
    cov = coverage.build(run, Path(a.series) if a.series else None, Path(a.sources) if a.sources else None)
    write_json(run / "covered.json", cov)
    for skipped in cov["skipped"]:
        print(f"warning: coverage skipped {skipped}", file=sys.stderr)
    print(rel(run))
    return 0


def _newer(target: Path, sources: list[Path]) -> bool:
    if not target.exists():
        return False
    t = target.stat().st_mtime
    return all(s.stat().st_mtime <= t + 1e-6 for s in sources if s.exists())


def status(run: Path) -> list[dict]:
    st = []

    def add(stage, state, detail, human=False):
        st.append({"stage": stage, "state": state, "detail": detail, "human": human})

    src = run / "sources.json"
    if not src.exists():
        add("scout", "todo", "sources.json missing (robotics-news-scout)")
    else:
        rep = V.validate_file("sources", src, run)
        data = read_json(src) if not rep.errors else {}
        n = len(data.get("candidates", []))
        add("scout", "fail" if rep.errors else "done",
            f"{len(rep.errors)} error(s) in sources.json" if rep.errors else
            f"{n} candidates, {len(data.get('unreadable', []))} unreadable source(s) surfaced")

    rk = run / "ranking.json"
    if not (run / "scores.json").exists():
        add("rank", "todo", "scores.json missing (virality-ranker)")
    elif not rk.exists() or not (run / "ranking.md").exists():
        add("rank", "todo", "run tools/rank_topics.py")
    else:
        r = read_json(rk)
        sj = run / "search.json"
        search_stale = sj.exists() and load_json(sj).get("sources_sha256") not in (None, sha256_file(run / "sources.json"))
        if search_stale:
            add("rank", "stale", "search.json was collected for an earlier sources.json: rerun tools/search_demand.py, "
                                 "then tools/rank_topics.py")
        elif ranking_inputs(run) != r.get("inputs_sha256"):
            add("rank", "stale", "inputs changed since ranking: rerun tools/rank_topics.py")
        else:
            top = next((x for x in r["ranking"] if x["eligible"]), None)
            add("rank", "done", f"recommended {top['id']} ({top['total']})" if top else "no topic passes the gates")

    auto = load_json(CONFIG / "pipeline.json").get("topic_approval", "auto") == "auto"
    ap = next((run / n for n in ("approval.json", "selection.json") if (run / n).exists()),  # the user's choice wins
              run / ("selection.json" if auto else "approval.json"))
    auto = ap.name == "selection.json"
    if not ap.exists():
        if auto:
            add("approval", "todo", "automatic topic approval: python3 tools/auto_select.py " + rel(run))
        else:
            add("approval", "waiting", f"the user types /approve-topic {rel(run)} <topic-id>", human=True)
    else:
        a = read_json(ap)
        if not (run / "ranking.md").exists() or a.get("ranking_sha256") != sha256_file(run / "ranking.md"):
            add("approval", "stale", "ranking.md changed after the topic was approved: approve again"
                + ("" if auto else " (the user)"), human=not auto)
        elif auto:
            add("approval", "done", f"{a['topic_id']} '{a['title']}' selected automatically {a['selected_at']} "
                                    "(reasons in selection.md)")
        else:
            add("approval", "done", f"{a['topic_id']} '{a['title']}' approved {a['approved_at']} via {a['via']}")

    html = run / "explainer.html"
    inputs = sorted((run / "draft").glob("*")) + [run / "references.json"] + sorted((run / "code" / "figures").glob("*.svg"))
    if not html.exists():
        add("write", "todo", "explainer.html missing (didactic-html-writer, then tools/build_explainer.py)")
    elif (run / "draft").exists() and any((run / "draft").glob("*.html")) and not _newer(html, inputs):
        add("write", "stale", "drafts, references or figures changed: rerun tools/build_explainer.py")
    else:
        import lint_html
        errs = [i for i in lint_html.lint(html, run, strict=True) if i["level"] == "error"]
        add("write", "fail" if errs else "done", f"strict lint: {len(errs)} error(s)" if errs else "strict lint clean")

    logs = run / "code" / "logs" / "summary.json"
    code_files = [p for p in (run / "code").rglob("*.py")] + [run / "code" / "checks.toml"]
    if not logs.exists():
        add("code checks", "todo", "run tools/run_code_checks.py")
    else:
        s = read_json(logs)
        bad = [c["script"] for c in s.get("checks", []) if not c.get("ok")]
        if bad:
            add("code checks", "fail", "failing: " + ", ".join(bad))
        elif not _newer(logs, code_files):
            add("code checks", "stale", "scripts changed since the last run")
        else:
            add("code checks", "done", f"{len(s.get('checks', []))} script(s) ran clean")

    rc = run / "review" / "check_html.json"
    if not rc.exists():
        add("render check", "todo", "node tools/check_html.js explainer.html --json review/check_html.json")
    else:
        r = read_json(rc)
        if not _newer(rc, [html]):
            add("render check", "stale", "explainer.html changed since the render check")
        else:
            add("render check", "done" if r.get("pass") else "fail", f"{len(r.get('errors', []))} error(s)")

    rs = run / "review" / "summary.json"
    if not rs.exists():
        add("review", "todo", "explainer-review (six reviewers, verification, tools/merge_reviews.py)")
    else:
        s = read_json(rs)
        open_ = [f for f in s.get("findings", []) if f.get("severity") in ("blocker", "major")
                 and f.get("verdict") != "refuted" and f.get("status", "open") == "open"]
        add("review", "fail" if open_ else "done",
            f"{len(open_)} open blocker/major finding(s)" if open_ else
            f"{len(s.get('findings', []))} finding(s), none open at blocker/major level")

    final = run / "video" / "final" / "check.json"
    drafts = run / "video" / "checks" / "check.json"
    renders = run / "video" / "renders" / "check.json"         # final renders of the scenes, before assembly
    vc = next((p for p in (final, drafts, renders) if p.exists()), None)
    if vc is None:
        add("video", "todo", "manim-video-producer, then tools/render_video.sh --check")
    else:
        v = read_json(vc)
        what = {final: "final video checked", drafts: "draft renders checked at -ql (the narrated 1080p60 render "
                "and assembly follow: finish-video in a session, the workflow in CI)",
                renders: f"{len(v.get('videos', []))} final render(s) checked"}[vc]
        add("video", "done" if v.get("pass") else "fail", what)
    gp = run / "review" / "gates.json"
    if gp.exists():
        gt = read_json(gp)
        bad = [c["name"] for c in gt["checks"] if not c["ok"]]
        add("gates", "done" if gt["passed"] else "fail", f"{gt['stage']}: " + ("all passed" if not bad else
                                                                                "failed: " + ", ".join(bad)))
    else:
        add("gates", "todo", "python3 tools/gate.py " + rel(run) + " --stage pre-render")
    sheet = run / "deliver" / "upload_sheet.md"
    gates = read_json(gp, {})
    released = gates.get("stage") == "release" and gates.get("passed") is True
    if sheet.exists():
        add("hand-over", "done", f"{rel(sheet.parent)}: the files for the owner's own upload")
    elif released:
        add("hand-over", "todo", "python3 tools/deliver.py " + rel(run))
    else:
        add("hand-over", "todo", "outside CI, the finish-video skill: narration, 1080p render, final gates, final-cut "
                                 "review, release gate, tools/deliver.py")
    return st


def next_step(st: list[dict]) -> str:
    for s in st:
        if s["state"] != "done":
            who = "HUMAN" if s["human"] else "Claude"
            return f"{who}: {s['stage']} -> {s['detail']}"
    return ("all stages done. Nothing is published from Claude Code: the owner uploads deliver/ by hand (with the "
            "workflow, CI publishes only after the owner approves the video)")


def cmd_status(a) -> int:
    run = resolve_run(a.run)
    st = status(run)
    if a.json:
        print(json.dumps({"run": rel(run), "stages": st, "next": next_step(st)}, indent=2))
        return 0
    print(f"run {rel(run)}")
    for s in st:
        print(f"  {s['stage']:<13} {s['state']:<8} {s['detail']}")
    print(f"next: {next_step(st)}")
    return 0


def cmd_finalize(a) -> int:
    run = resolve_run(a.run)
    ap = next((run / n for n in ("selection.json", "approval.json") if (run / n).exists()), None)
    if ap is None:
        die("no selection.json or approval.json: no topic has been approved yet")
    appr = read_json(ap)
    date = read_json(run / "run.json")["run_date"]
    want = run.parent / f"{date}-{appr['slug']}"
    if run == want:
        print(rel(run))
        return 0
    target, n = want, 2
    while target.exists():
        target = Path(f"{want}-{n}")
        n += 1
    run.rename(target)
    print(rel(target))
    return 0


def cmd_package(a) -> int:
    run = resolve_run(a.run)
    out = Path(a.out) if a.out else run.parent / f"{run.name}.zip"
    files = []
    for root, dirs, names in os.walk(run):
        dirs[:] = sorted(d for d in dirs if d not in PACKAGE_SKIP_DIRS)
        for n in sorted(names):
            if n.endswith((".pyc", ".DS_Store")):
                continue
            files.append(Path(root) / n)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            info = zipfile.ZipInfo(f"{run.name}/{f.relative_to(run).as_posix()}", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())
    print(f"wrote {rel(out)} ({out.stat().st_size / 1e6:.2f} MB, {len(files)} files); nothing was uploaded")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--focus")
    n.add_argument("--slug")
    n.add_argument("--date")
    n.add_argument("--window-days", type=int, help="search window for this run (default: config/scout.json)")
    n.add_argument("--ledger", help="a ledger.json (the Pages ledger) merged with <root>/ledger/ into published.json "
                                    "(default: <root>/ledger/ alone)")
    n.add_argument("--root", help="parent folder (default: runs/)")
    n.add_argument("--sources", help="folder of source documents for covered.json (default: sources/; tests)")
    n.add_argument("--series", help="folder of series plans for covered.json (default: series/; tests)")
    s = sub.add_parser("status")
    s.add_argument("run")
    s.add_argument("--json", action="store_true")
    f = sub.add_parser("finalize")
    f.add_argument("run")
    p = sub.add_parser("package")
    p.add_argument("run")
    p.add_argument("--out")
    a = ap.parse_args()
    return {"new": cmd_new, "status": cmd_status, "finalize": cmd_finalize, "package": cmd_package}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
