#!/usr/bin/env python3
"""Reading-time check: every text and equation stays on screen long enough to read, and the narration is not too fast.

Usage:
  python3 tools/video/check_reading.py runs/<run> --stage draft|final [--out DIR]
  python3 tools/video/check_reading.py --layout X.layout.json [--out DIR]          # one scene

Checks: display-time, words-on-screen, narration-rate, recall-load (the reading model of
templates/manim/reading_model.py; thresholds in config/video.json "reading" and "recall"). Exit status 1 on an error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "templates" / "manim"))
sys.path.insert(0, str(ROOT / "tools" / "video"))
from _common import CONFIG, rel, resolve_run, sha256_file  # noqa: E402
import check_design as CD  # noqa: E402
import checks  # noqa: E402
import reading_model as RM  # noqa: E402
from checks import intervals  # noqa: E402


def overlap(a: tuple[float, float], spans: list[tuple[float, float]]) -> float:
    return sum(max(0.0, min(a[1], b) - max(a[0], s)) for s, b in spans)


def edge_items(log: dict) -> tuple[dict, dict]:
    """({content: seconds} of the texts visible from a scene's start, the same for those visible up to its end)."""
    end = float(log.get("duration", 0.0))
    first, last = {}, {}
    for item in log.get("timeline", []):
        if item.get("live") or item.get("axis"):
            continue
        spans = intervals(item.get("events", []), end)
        c = item.get("content", "")
        if spans and spans[0][0] <= 0.05:
            first[c] = max(first.get(c, 0.0), spans[0][1] - spans[0][0])
        if spans and spans[-1][1] >= end - 0.05:
            last[c] = max(last.get(c, 0.0), spans[-1][1] - spans[-1][0])
    return first, last


def scene_reading(name: str, log: dict, cfg: dict, findings: list, stats: dict, frame: dict | None = None,
                  design: dict | None = None, before: dict | None = None, after: dict | None = None) -> None:
    """before / after: {content: seconds} a text carried across the cut shows in the previous or next scene."""
    end = float(log.get("duration", 0.0))
    narr = [(v["start"], v["start"] + v["duration"]) for v in log.get("voiceovers", [])]
    checked = short = 0
    for item in log.get("timeline", []):
        if item.get("live") or item.get("axis"):
            continue
        for a, b in intervals(item.get("events", []), end):
            shown = b - a
            if shown <= 0.05:
                continue
            c = item.get("content", "")
            if a <= 0.05:
                shown += (before or {}).get(c, 0.0)
            if b >= end - 0.05:
                shown += (after or {}).get(c, 0.0)
            checked += 1
            narrated = shown > 0 and overlap((a, b), narr) / shown >= cfg["narration_overlap"]
            need = RM.required_seconds(item["kind"], item.get("content", ""), narrated, cfg)
            if shown + 0.1 >= need:
                continue
            short += 1
            hard = shown < cfg["error_fraction"] * need or shown < cfg["min_display_s"]
            text = (item.get("content") or "").replace("\n", " ")
            findings.append({"check": "display-time", "severity": "error" if hard else "warning", "scene": name,
                             "t": round(a, 2), "detail": f"'{text[:60]}' is visible {shown:.1f} s, needs {need:.1f} s"
                             + (" (narration plays meanwhile)" if narrated else ""), "shown_s": round(shown, 2),
                             "required_s": need})
    peak, peak_t = 0.0, 0.0
    for snap in log.get("snapshots", []):
        if not snap.get("settled"):
            continue
        texts = CD.front(snap, frame or {}, design)[0] if design else snap.get("texts", [])
        n = sum(RM.on_screen_words(x["kind"], x.get("content", "")) for x in texts
                if x.get("opacity", 1) >= 0.5 and not x.get("axis") and not x.get("live"))
        if n > peak:
            peak, peak_t = n, snap["t"]
    if peak > cfg["max_words_on_screen_warn"]:
        findings.append({"check": "words-on-screen", "scene": name, "t": round(peak_t, 2),
                         "severity": "error" if peak > cfg["max_words_on_screen_error"] else "warning",
                         "detail": f"{peak:.0f} words and equation terms on screen at once "
                                   f"(limit {cfg['max_words_on_screen_warn']})"})
    rates = []
    for v in log.get("voiceovers", []):
        if v["duration"] <= 0 or v["words"] < 4:
            continue
        wpm = 60.0 * v["words"] / v["duration"]
        rates.append(round(wpm))
        if wpm > cfg["narration_wpm_warn"]:
            findings.append({"check": "narration-rate", "scene": name, "t": round(v["start"], 2),
                             "severity": "error" if wpm > cfg["narration_wpm_error"] else "warning",
                             "detail": f"narration at {wpm:.0f} words per minute (target {cfg['narration_wpm_target']}): "
                                       f"'{v['text'][:50]}'"})
    stats[name] = {"appearances_checked": checked, "too_short": short, "peak_words_on_screen": round(peak, 1),
                   "narration_wpm": rates, "duration_s": end}


RECALL_DEFAULTS = {"window_s": 60, "max_callbacks": 3,
                   "phrases": [r"\brecall\b", r"\bremember\b", r"\bas we saw (?:before|earlier)\b"],
                   "named": [r"\bHamilton[-–]Jacobi (?:equation|condition)\b"]}


def recall_load(logs: list[tuple[str, dict]], rcfg: dict) -> list[dict]:
    """Warnings for narration that recalls or names an equation no longer on screen; logs: (scene, log) in order."""
    cfg = dict(RECALL_DEFAULTS, **rcfg)
    phrases = [re.compile(p, re.I) for p in cfg["phrases"]]
    named = [re.compile(p, re.I) for p in cfg["named"]]
    shown, blocks, offset = [], [], 0.0
    for name, log in logs:
        end = float(log.get("duration", 0.0))
        for item in log.get("timeline", []):
            if item.get("kind") == "math" and not item.get("live") and not item.get("axis"):
                for a, b in intervals(item.get("events", []), end):
                    shown.append((item.get("content", ""), offset + a, offset + b))
        for v in log.get("voiceovers", []):
            blocks.append((name, v["start"], offset + v["start"], offset + v["start"] + v["duration"], v["text"]))
        offset += end
    first, out = {}, []
    for scene, t_rel, t0, t1, text in blocks:
        visible = {c for c, a, b in shown if a < t1 and b > t0}
        hit = next((m.group() for rx in phrases for m in [rx.search(text)] if m), None)
        if hit and not visible:
            out.append({"check": "recall-load", "severity": "warning", "scene": scene, "t": round(t_rel, 2),
                        "detail": f"narration recalls an equation ('{hit}') while none is on screen: show it again, "
                                  "keep it pinned in a corner while it is used, or split the episode"})
            continue
        for i, rx in enumerate(named):
            m = rx.search(text)
            if not m:
                continue
            if i not in first:
                first[i] = visible
                continue
            if visible or not first[i]:
                continue
            last = max((b for c, a, b in shown if c in first[i] and b <= t0), default=None)
            if last is not None and t0 - last > cfg["window_s"]:
                out.append({"check": "recall-load", "severity": "warning", "scene": scene, "t": round(t_rel, 2),
                            "detail": f"narration names '{m.group()}', last on screen {t0 - last:.0f} s earlier "
                                      f"(limit {cfg['window_s']} s): show it again, pin it in a corner while it is "
                                      "used, or split the episode"})
    if len(out) > cfg["max_callbacks"]:
        out.append({"check": "recall-load", "severity": "warning", "scene": "(episode)", "t": 0.0,
                    "detail": f"{len(out)} callbacks to equations no longer on screen (limit {cfg['max_callbacks']}): "
                              "the material may be too heavy for one video; show equations again, pin them, or split "
                              "the episode"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--layout")
    ap.add_argument("--out")
    a = ap.parse_args()
    video_cfg = json.loads((CONFIG / "video.json").read_text(encoding="utf-8"))
    cfg = dict(RM.DEFAULTS, **video_cfg.get("reading", {}))
    findings, stats, logs = [], {}, []
    if a.layout:
        run, lp = None, Path(a.layout)
        logs = [(n, lp) for n in json.loads(lp.read_text(encoding="utf-8"))["scenes"]]
        out = Path(a.out) if a.out else lp.parent / "design"
    elif a.run:
        run = resolve_run(a.run)
        folder = run / "video" / ("checks" if a.stage == "draft" else "renders")
        plan = run / "video" / "plan.json"
        names = [s["class"] for s in json.loads(plan.read_text(encoding="utf-8")).get("scenes", [])] if plan.exists() \
            else sorted(p.name[:-len(".layout.json")] for p in folder.glob("*.layout.json"))
        logs = [(n, folder / f"{n}.layout.json") for n in names]
        out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    else:
        ap.error("give a run or --layout")
    sha, loaded, parsed = {}, [], []
    for name, lp in logs:
        if not lp.exists():
            findings.append({"check": "layout", "severity": "error", "scene": name, "t": 0.0,
                             "detail": f"no layout log {lp.name} (render with tools/render_video.sh)"})
            parsed.append(None)
            continue
        data = json.loads(lp.read_text(encoding="utf-8"))
        parsed.append((data, data["scenes"].get(name) or next(iter(data["scenes"].values()))))
    edges = [edge_items(x[1]) if x else ({}, {}) for x in parsed]
    for i, ((name, lp), x) in enumerate(zip(logs, parsed)):
        if x is None:
            continue
        data, log = x
        before = edges[i - 1][1] if i > 0 and parsed[i - 1] else {}
        after = edges[i + 1][0] if i + 1 < len(parsed) and parsed[i + 1] else {}
        scene_reading(name, log, cfg, findings, stats, data.get("frame", {}), video_cfg["design"], before, after)
        sha[name] = sha256_file(lp)
        loaded.append((name, log))
    findings += recall_load(loaded, video_cfg.get("recall", {}))
    errors, warnings = checks.summary(findings).values()
    md = [f"# Reading-time check ({a.stage})", "", f"{errors} error(s), {warnings} warning(s). Model: text at "
          f"{cfg['text_wpm']} words per minute plus {cfg['orientation_s']} s, equations "
          f"{cfg['equation_base_s']} s + {cfg['equation_term_s']} s per term (at least {cfg['equation_min_s']} s), "
          f"x{cfg['narration_factor']} while narration plays, never under {cfg['min_display_s']} s.", ""]
    md += checks.md_table(["Scene", "Checked", "Too short", "Peak words on screen", "Narration wpm"], (
        [n, s["appearances_checked"], s["too_short"], s["peak_words_on_screen"],
         ", ".join(map(str, s["narration_wpm"])) or "-"] for n, s in stats.items()))
    md += [""] + checks.md_table(["Severity", "Check", "Scene", "t (s)", "Detail"], (
        [f["severity"], f["check"], f["scene"], f"{f['t']:.2f}", f["detail"]]
        for f in sorted(findings, key=lambda f: (f["severity"] != "error", f["scene"], f["t"]))))
    checks.write_report(out, "check_reading", a.stage, findings, md, model={k: cfg[k] for k in RM.DEFAULTS},
                        scenes=stats, layout_sha256=sha)
    for f in findings:
        if f["severity"] == "error":
            print(f"ERROR   {f['scene']} t={f['t']:.2f}s {f['check']}: {f['detail']}")
    print(f"check_reading ({a.stage}): {'FAIL' if errors else 'ok'} ({errors} error(s), {warnings} warning(s)); "
          f"{rel(out / 'check_reading.md') if run else out / 'check_reading.md'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
