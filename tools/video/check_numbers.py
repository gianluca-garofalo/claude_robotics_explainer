#!/usr/bin/env python3
"""Number-format check (house rule): every number a viewer sees or hears reads the way a person would write it.

Usage:
  python3 tools/video/check_numbers.py runs/<run> [--stage draft|final]
  python3 tools/video/check_numbers.py --layout X.layout.json [--srt X.srt] [--text "narration ..."]   # ad hoc

Sources: the layout logs (video/checks/ for drafts, video/renders/ for the final renders): every text item, and live
readouts sampled over time (the "values" the probe records); the narration of video/scenes/*.py; the captions; the
plan's chapter titles and thumbnail text. Rules (thresholds in config/video.json "numbers"; templates/manim/common.py
fmt() writes numbers that pass):
  digits         more significant digits than the role allows (max_sig: screen 4, live readout 3, narration 3,
                 captions 4); an error from error_extra_sig more ("V₁ = 0.500000")
  trailing-zero  a static number ending in zeros after the point ("0.50"; an error from trailing_zeros_error zeros).
                 Live readouts may keep fixed decimals: their width must not jump while they update
  exact-zero     "0.00" in static text: write 0, or "exactly 0"
  signed-zero    a zero with a sign, also in a live readout ("−H = −0.00", "+0.00"): it reads as a small non-zero value
                 (fmt() and readout() never sign a zero). Math items ignore exponents, subscripts and TeX layout lengths
                 (\\makebox[5.0em], \\hspace{1cm})
  precision      one quantity, one precision within a scene: a readout whose number of decimals changes while it
                 updates; the same label ("V(q) = ...") with different decimals; two numbers on screen together that
                 agree within compare_rel_tol but not in decimals ("sum = 1.28" beside "∫ L dt = 1.277")
  minus          a hyphen before a digit in on-screen text: use the minus sign − (U+2212)
  sci            e-notation on screen ("1e-12"): write 10⁻¹²
  unit-space     a number glued to a unit ("1.2s"; the units list)
  spoken         narration or captions that read out more digits than narration_max_spoken_digits ("zero point five
                 zero zero zero zero zero"), or write such a number
Writes review/design/<stage>/check_numbers.json and .md; exit status 1 when there is an error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import voice_script as VS  # noqa: E402

HELPERS = {"common.py", "voice.py", "reading_model.py"}
DEFAULTS = {"max_sig": {"screen": 4, "readout": 3, "narration": 3, "captions": 4}, "error_extra_sig": 2,
            "trailing_zeros_error": 3, "compare_rel_tol": 0.02, "narration_max_spoken_digits": 3,
            "units": ["s", "ms", "rad", "deg", "m", "cm", "mm", "kg", "N", "Nm", "Hz", "kHz", "J", "W"]}
NUM = re.compile(r"(?<![\w.\\^_])([−\-+]?)(\d+(?:\.\d+)?)(?:[eE]([−\-+]?\d+))?")
LABELLED = re.compile(r"([^=,;:\n]{1,40}?)\s*=\s*[−\-+]?(\d+(?:\.\d+)?)")
DIGIT_WORDS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
               "eight": 8, "nine": 9}
SPOKEN = re.compile(r"\bpoint((?:\s+(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)\b)+)", re.I)
TEX_NOISE = re.compile(r"\\[a-zA-Z]+\d*|\^\{?\d+\}?|_\{?\d+\}?")
TEX_DIM = re.compile(r"(?:(?<=[\[{])|(?<=\\kern)|(?<=\\mkern)|(?<=\\hskip)|(?<=\\vskip)|(?<=\\mskip))\s*[−\-+]?\d*\.?\d+"
                     r"\s*(?:em|ex|pt|bp|mu|sp|pc|dd|cc|cm|mm|in)\b")      # layout lengths: \makebox[5.0em], \hspace{1cm}


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG / "video.json").get("numbers", {}))
    return cfg


def numbers_in(text: str, kind: str = "text") -> list[dict]:
    """Numbers in a piece of text: {raw, value, decimals, sig, trailing, sci, start}. LaTeX commands, exponents,
    subscripts and layout lengths are ignored in math items (\\tfrac12, q^2 and \\makebox[5.0em] hold no numbers a
    viewer reads as values)."""
    blank = lambda m: " " * len(m.group())  # noqa: E731
    src = TEX_NOISE.sub(blank, TEX_DIM.sub(blank, text)) if kind == "math" else text
    out = []
    for m in NUM.finditer(src):
        body = m.group(2)
        whole, _, frac = body.partition(".")
        digits = (whole + frac).lstrip("0") or "0"
        sign = -1.0 if m.group(1) in ("−", "-") else 1.0
        out.append({"raw": m.group().strip(), "value": sign * float(body),
                    "decimals": len(frac), "sig": len(digits) if digits != "0" else len(frac) or 1,
                    "trailing": len(frac) - len(frac.rstrip("0")) if frac else 0,
                    "zero": not body.replace("0", "").replace(".", ""), "sci": bool(m.group(3)), "start": m.start(),
                    "end": m.end()})
    return out


class Findings:
    def __init__(self):
        self.items: list[dict] = []
        self._seen = set()

    def add(self, rule, severity, source, where, match, detail):
        key = (rule, source, where, match)
        if key in self._seen:
            return
        self._seen.add(key)
        self.items.append({"rule": rule, "severity": severity, "source": source, "where": where, "match": match,
                           "detail": detail})


def label_key(label: str) -> str:
    return re.sub(r"\\[ ,;:!]|\\q?quad|\s+", "", label)


def check_static(text: str, kind: str, role: str, source: str, where: str, cfg: dict, fd: Findings,
                 live: bool = False, fixed: dict | None = None) -> None:
    """Digits, trailing zeros, exact and signed zeros, minus, sci and unit spacing of one text. `fixed`: labels shown several
    times at one precision (one quantity in a legend or table), whose trailing zeros keep the precision aligned."""
    max_sig = cfg["max_sig"].get(role, 4)
    aligned = set()
    for m in LABELLED.finditer(text):
        if fixed and fixed.get(label_key(m.group(1))) == len(m.group(2).partition(".")[2]):
            aligned.add(m.end(2))
    for n in numbers_in(text, kind):
        if n["zero"] and n["raw"][:1] in "−-+" and (n["start"] == 0 or text[n["start"] - 1] in " =([{,:;\t\n"):
            fd.add("signed-zero", "error", source, where, n["raw"], "a zero with a sign (−0.00, +0.00) reads as a "
                   "small non-zero value: show 0.00 (fmt() and readout() never sign a zero)")
            continue
        if n["decimals"] == 0 and not n["sci"]:
            continue                                            # integers read fine
        if n["zero"] and not live:
            fd.add("exact-zero", "error" if n["decimals"] >= 3 else "warning", source, where, n["raw"],
                   "an exact zero shown with decimals: write 0, or 'exactly 0' (fmt(x, exact=True))")
            continue
        if n["sig"] > max_sig:
            sev = "error" if n["sig"] >= max_sig + cfg["error_extra_sig"] else "warning"
            fd.add("digits", sev, source, where, n["raw"], f"{n['sig']} significant digits; at most {max_sig} for "
                   f"{role} (fmt() rounds and drops trailing zeros)")
        elif n["trailing"] and not live and n["end"] not in aligned:
            sev = "error" if n["trailing"] >= cfg["trailing_zeros_error"] else "warning"
            fd.add("trailing-zero", sev, source, where, n["raw"], "trailing zero(s) after the point: "
                   f"{n['raw']} reads as {n['raw'].rstrip('0').rstrip('.')}")
        if n["sci"] and source == "screen":
            fd.add("sci", "warning", source, where, n["raw"], "e-notation on screen: write ×10⁻ⁿ (fmt() does)")
    if source == "screen" and kind == "text":
        for m in re.finditer(r"(?<![\w)\]’'])-(?=\d)", text):
            fd.add("minus", "warning", source, where, text[m.start():m.start() + 6].strip(),
                   "a hyphen before a number: use the minus sign − (U+2212; fmt() does)")
    if kind == "text":                    # in LaTeX, "2m" is a product (\frac{p^2}{2m}), not a unit
        units = "|".join(sorted((re.escape(u) for u in cfg["units"]), key=len, reverse=True))
        for m in re.finditer(rf"(?<![\w.])\d+(?:\.\d+)?({units})\b", text):
            fd.add("unit-space", "warning", source, where, m.group(), "put a space between the number and its unit")


def check_spoken(text: str, source: str, where: str, cfg: dict, fd: Findings) -> None:
    lim = cfg["narration_max_spoken_digits"]
    for m in SPOKEN.finditer(text):
        words = m.group(1).split()
        n_digits = len(words) + 1                               # the digit before "point" counts too
        trailing = 0
        for w in reversed(words):                               # "point five zero zero": two trailing zeros
            if w.lower() not in ("zero", "oh"):
                break
            trailing += 1
        if n_digits > lim or trailing:
            sev = "error" if n_digits >= lim + cfg["error_extra_sig"] or trailing >= 2 else "warning"
            fd.add("spoken", sev, source, where, "point " + m.group(1).strip(),
                   f"{n_digits} digits read out" + (f", {trailing} of them trailing zeros" if trailing else "")
                   + f": say at most {lim} significant digits, without trailing zeros")


def scene_order(run: Path | None) -> list[str]:
    if run is None:
        return []
    pp = run / "video" / "plan.json"
    return [s["class"] for s in json.loads(pp.read_text(encoding="utf-8")).get("scenes", [])] if pp.exists() else []


def check_layout(name: str, log: dict, cfg: dict, fd: Findings) -> dict:
    """On-screen numbers of one scene: static texts, live readouts over time, and the precision rules."""
    stats = {"text_items": 0, "live_items": 0, "samples": 0}
    by_label: dict[str, set] = {}
    label_where: dict[str, str] = {}
    seen: dict[str, list] = {}
    for item in log.get("timeline", []):
        if not item.get("axis") and not item.get("live"):
            for m in LABELLED.finditer(item.get("content", "")):
                seen.setdefault(label_key(m.group(1)), []).append(len(m.group(2).partition(".")[2]))
    fixed = {k: v[0] for k, v in seen.items() if len(v) >= 2 and len(set(v)) == 1 and v[0] > 0}
    for item in log.get("timeline", []):
        if item.get("axis"):
            continue
        stats["text_items"] += 1
        t0 = item["events"][0][0] if item.get("events") else 0.0
        where = f"{name} t={t0:.1f}s"
        if item.get("live"):
            stats["live_items"] += 1
            vals = item.get("values") or [[t0, item.get("content", "")]]
            stats["samples"] += len(vals)
            decs: dict[int, set] = {}
            for t, shown in vals:
                check_static(shown, "text", "readout", "screen", f"{name} t={t:.1f}s", cfg, fd, live=True)
                for k, n in enumerate(numbers_in(shown)):
                    decs.setdefault(k, set()).add(n["decimals"])
                for m in LABELLED.finditer(shown):
                    key = re.sub(r"\s+", "", m.group(1))
                    by_label.setdefault(key, set()).add(len(m.group(2).partition(".")[2]))
                    label_where.setdefault(key, f"{name} t={t:.1f}s")
            for k, ds in decs.items():
                if len(ds) > 1:
                    sample = " → ".join(dict.fromkeys(numbers_in(v)[k]["raw"] for _, v in vals
                                                      if len(numbers_in(v)) > k))
                    fd.add("precision", "error", "screen", where, sample[:60], "a live readout changes its number "
                           "of decimals while it updates: keep them fixed (readout(..., decimals=k))")
        else:
            text = item.get("content", "")
            check_static(text, item.get("kind", "text"), "screen", "screen", where, cfg, fd, fixed=fixed)
            if item.get("kind") == "text":
                for m in LABELLED.finditer(text):
                    key = re.sub(r"\s+", "", m.group(1))
                    by_label.setdefault(key, set()).add(len(m.group(2).partition(".")[2]))
                    label_where.setdefault(key, where)
    for key, ds in by_label.items():
        if len(ds) > 1 and max(ds) > 0:
            fd.add("precision", "error", "screen", label_where[key], key[:40], f"'{key} = ...' appears with "
                   f"{sorted(ds)} decimals in one scene: show one quantity at one precision")
    tol = cfg["compare_rel_tol"]
    for snap in log.get("snapshots", []):
        if not snap.get("settled"):
            continue
        nums = []
        for x in snap.get("texts", []):
            if x.get("axis") or x.get("opacity", 1) < 0.5:
                continue
            nums += [(x["id"], n, x.get("content", "")) for n in numbers_in(x.get("content", ""), x.get("kind", "text"))
                     if n["decimals"] > 0 and n["value"] != 0]
        for i, (ia, a, ca) in enumerate(nums):
            for ib, b, cb in nums[i + 1:]:
                if ia == ib or a["decimals"] == b["decimals"]:
                    continue
                if abs(a["value"] - b["value"]) <= tol * max(abs(a["value"]), abs(b["value"])):
                    fd.add("precision", "error", "screen", f"{name} t={snap['t']:.1f}s",
                           f"{a['raw']} / {b['raw']}", f"'{ca[:30]}' and '{cb[:30]}' are shown together and agree "
                           "but differ in decimals: give them the same precision")
    return stats


def srt_cues(path: Path) -> list[str]:
    out, cur = [], []
    for ln in path.read_text(encoding="utf-8").splitlines() + [""]:
        if not ln.strip():
            if cur:
                out.append(" ".join(cur))
            cur = []
        elif "-->" not in ln and not ln.strip().isdigit():
            cur.append(ln.strip())
    return out


def check_run(run: Path, stage: str, cfg: dict, fd: Findings) -> dict:
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    order = scene_order(run) or sorted(p.name[:-len(".layout.json")] for p in folder.glob("*.layout.json"))
    scenes = {}
    for name in order:
        lp = folder / f"{name}.layout.json"
        if not lp.exists():
            continue
        log_all = json.loads(lp.read_text(encoding="utf-8"))
        log = log_all["scenes"].get(name) or next(iter(log_all["scenes"].values()), {})
        scenes[name] = dict(check_layout(name, log, cfg, fd), layout_sha256=sha256_file(lp))
    for f in sorted((run / "video" / "scenes").glob("*.py")):
        if f.name in HELPERS:
            continue
        for i, (key, text) in enumerate(VS.blocks(f)):
            text = VS.spoken(text) if key else text        # the pacing markup ([pause 2.5]) is not a spoken number
            if text:
                where = f"{f.name}, block {i + 1}"
                check_spoken(text, "narration", where, cfg, fd)
                check_static(text, "text", "narration", "narration", where, cfg, fd)
    srts = sorted(folder.glob("*.srt")) + (sorted((run / "video" / "final").glob("*.srt")) if stage == "final" else [])
    for p in srts:
        for k, cue in enumerate(srt_cues(p)):
            check_spoken(cue, "captions", f"{p.name} cue {k + 1}", cfg, fd)
            check_static(cue, "text", "captions", "captions", f"{p.name} cue {k + 1}", cfg, fd)
    pp = run / "video" / "plan.json"
    if pp.exists():
        plan = json.loads(pp.read_text(encoding="utf-8"))
        for i, s in enumerate(plan.get("scenes", [])):
            if s.get("chapter"):
                check_static(s["chapter"], "text", "screen", "chapter", f"plan.json scenes[{i}]", cfg, fd)
        th = plan.get("thumbnail") or {}
        if th.get("text"):
            check_static(th["text"], "text", "screen", "thumbnail", "plan.json thumbnail", cfg, fd)
    return scenes


def write_report(out: Path, stage: str, fd: Findings, scenes: dict) -> dict:
    errors = sum(f["severity"] == "error" for f in fd.items)
    warnings = sum(f["severity"] == "warning" for f in fd.items)
    data = {"schema_version": 1, "tool": "check_numbers", "stage": stage, "checked_at": utc_now(),
            "passed": errors == 0, "summary": {"errors": errors, "warnings": warnings}, "scenes": scenes,
            "findings": fd.items}
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "check_numbers.json", data)
    md = [f"# Number format ({stage})", "", f"{errors} error(s), {warnings} warning(s); rules in config/video.json "
          "\"numbers\" (format numbers with fmt() in templates/manim/common.py).", ""]
    if fd.items:
        md += ["| Severity | Rule | Source | Where | Match | Detail |", "|---|---|---|---|---|---|"]
        md += [f"| {f['severity']} | {f['rule']} | {f['source']} | {f['where']} | {f['match'].replace('|', '/')} | "
               f"{f['detail'].replace('|', '/')} |" for f in sorted(fd.items, key=lambda f: f['severity'] != 'error')]
    (out / "check_numbers.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--layout", action="append", default=[])
    ap.add_argument("--srt", action="append", default=[])
    ap.add_argument("--text", action="append", default=[], help="narration text to check")
    a = ap.parse_args()
    cfg, fd = settings(), Findings()
    if a.run:
        run = resolve_run(a.run)
        scenes = check_run(run, a.stage, cfg, fd)
        data = write_report(run / "review" / "design" / a.stage, a.stage, fd, scenes)
        where = rel(run / "review" / "design" / a.stage / "check_numbers.md")
    elif a.layout or a.srt or a.text:
        scenes = {}
        for lp in a.layout:
            log_all = json.loads(Path(lp).read_text(encoding="utf-8"))
            for name, log in log_all.get("scenes", {}).items():
                scenes[name] = check_layout(name, log, cfg, fd)
        for p in a.srt:
            for k, cue in enumerate(srt_cues(Path(p))):
                check_spoken(cue, "captions", f"{Path(p).name} cue {k + 1}", cfg, fd)
                check_static(cue, "text", "captions", "captions", f"{Path(p).name} cue {k + 1}", cfg, fd)
        for i, t in enumerate(a.text):
            check_spoken(t, "narration", f"--text {i + 1}", cfg, fd)
            check_static(t, "text", "narration", "narration", f"--text {i + 1}", cfg, fd)
        data = {"summary": {"errors": sum(f["severity"] == "error" for f in fd.items),
                            "warnings": sum(f["severity"] == "warning" for f in fd.items)}}
        where = "(ad hoc)"
    else:
        ap.error("give a run, or --layout/--srt/--text")
    for f in fd.items:
        print(f"{f['severity'].upper():7} {f['source']} {f['where']}: {f['rule']} '{f['match']}' ({f['detail']})")
    errors = data["summary"]["errors"]
    print(f"check_numbers: {'FAIL' if errors else 'ok'} ({errors} error(s), {data['summary']['warnings']} warning(s)); "
          f"{where}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
