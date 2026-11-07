#!/usr/bin/env python3
"""Engagement checks of a run's scenes: motion, cuts, animation vocabulary, narration, titles, beats, the metaphor.

Usage:
  python3 tools/video/check_engagement.py runs/<run> --stage draft|final [--no-video] [--out DIR]

Checks: motion, cuts, vocabulary, so what, narration, titles, beats, metaphor, emphasis, jargon, silence, thumbnail,
meter, blank, picture, outro (thresholds in config/video.json "engagement"; frame checks need ffmpeg and numpy).
Exit status 1 on an error.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file  # noqa: E402
import checks  # noqa: E402
import voice_script as VS  # noqa: E402

DEFAULTS = {
    "motion_fps": 4, "motion_size": [320, 180], "motion_pixel_delta": 6, "motion_min_pixels": 30,
    "frozen_narration_warn_s": 6.0, "frozen_narration_error_s": 12.0, "moving_share_warn": 0.5,
    "empty_cut_ink": 0.005, "ink_delta": 12, "empty_cut_share_warn": 0.25,
    "fade_ratio_warn": 5.0, "derivation_min_equations": 2,
    "notation_words_per_token": 25, "address_per_100_words": 1.0, "question_every_s": 120,
    "title_band_top": 2.9, "title_min_size": 30, "title_centre_max_x": 2.5, "title_max_s": 4.0,
    "beat_min_s": 1.5, "beats_min": 2, "dead_air_s": 1.2, "beat_min_moving": 0.5, "dead_air_max_moving": 0.25,
    "metaphor_body_share_min": 0.5, "errors_block_gate": False,
    "emphasis_counts_as_motion": False, "emphasis_share_warn": 0.2, "emphasis_per_min_warn": 4.0,
    "silence_off_max_s": 2.0, "jargon_new_per_block_warn": 2,
    "jargon": ["lyapunov", "asymptotically stable", "asymptotic stability", "terminal cost", "terminal set",
               "terminal region", "value function", "cost-to-go", "bellman", "principle of optimality", "recursive "
               "feasibility", "hamilton-jacobi", "lagrangian", "stage cost", "operator", "monotone", "riccati",
               "legendre", "momentum", "multiplier", "certificate", "invariant set", "receding horizon",
               "optimal control", "discretization", "convex", "gradient", "jacobian", "hessian", "eigenvalue"],
    "thumbnail_picture_bold_min": 0.08, "thumbnail_bold_delta": 40,
    "metaphor_rise_tol": 0.02, "metaphor_reset_margin_s": 2.0, "metaphor_static_min_share": 0.5,
    "blank_end_grace_s": 1.0, "outro_tail_min_s": 1.5,
    "hold_exempt_s": 4.0, "hold_exempt_restated_s": 8.0,
}
TRANSFORMS = {"Transform", "ReplacementTransform", "TransformMatchingTex", "TransformMatchingShapes",
              "TransformFromCopy", "FadeTransform", "FadeTransformPieces", "ClockwiseTransform",
              "CounterclockwiseTransform", "MoveToTarget", "derive"}
EQUATIONS = {"MathTex", "Tex", "eq", "ceq"}
EMPHASIS = {"Indicate", "Circumscribe", "Flash", "ShowPassingFlash", "ShowPassingFlashWithThinningStrokeWidth",
            "Wiggle", "FocusOn", "ApplyWave", "Blink", "pulse"}
COUNTED = TRANSFORMS | EQUATIONS | {"FadeIn", "FadeOut", "Write", "Create", "GrowArrow", "GrowFromEdge", "Indicate",
                                    "Circumscribe", "Brace", "BraceLabel", "ValueTracker", "readout", "meter",
                                    "carry_over", "beat", "budget_bars", "SurroundingRectangle", "LaggedStart"}
COUNTED |= EMPHASIS
# a lone letter is notation, but not the s of "it's" or the t of "can't" (spoken-script standard: contractions)
NOTATION = re.compile(r"(?<!['’])\b(?:(?![aAI]\b)[A-Za-z]|prime|primes|sub|subscript|superscript|hat|tilde|kappa|"
                      r"omega|phi|varphi|alpha|beta|gamma|delta|epsilon|theta|lambda|sigma|mu|nu|rho|tau|psi|xi|"
                      r"zeta)\b")
ADDRESS = re.compile(r"\b(?:you|your|yours|you're|you'll|you've|we|we're|we'll|we've|us|our|ours|let's)\b", re.I)
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def settings() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG / "video.json").get("engagement", {}))
    return cfg


Findings = partial(checks.Findings, "check", "severity", "where", "detail", "t")


# --------------------------------------------------------------------------- frames
def frames(video: Path, cfg: dict):
    """Grayscale frames (numpy uint8, n x h x w) at motion_fps, or None without ffmpeg, numpy or the file."""
    try:
        import numpy as np
    except ImportError:
        return None
    if not video.exists() or not shutil.which("ffmpeg"):
        return None
    w, h = cfg["motion_size"]
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"fps={cfg['motion_fps']},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True)
    if out.returncode != 0 or not out.stdout:
        return None
    return np.frombuffer(out.stdout, dtype=np.uint8).reshape(-1, h, w)


def motion_of(fr, cfg: dict) -> list[bool]:
    """moving[i] for the interval ending at frame i+1 (one entry per pair of consecutive frames)."""
    import numpy as np
    if fr is None or len(fr) < 2:
        return []
    d = np.abs(fr[1:].astype(np.int16) - fr[:-1].astype(np.int16)) > cfg["motion_pixel_delta"]
    return [bool(x) for x in (d.reshape(len(d), -1).sum(axis=1) > cfg["motion_min_pixels"])]


def ink(frame, cfg: dict) -> float:
    """Share of the picture that differs from its background (the most common grey level)."""
    import numpy as np
    bg = int(np.bincount(frame.ravel(), minlength=256).argmax())
    return float((np.abs(frame.astype(np.int16) - bg) > cfg["ink_delta"]).mean())


def frozen_stretches(moving: list[bool], dt: float) -> list[tuple[float, float]]:
    out, start = [], None
    for i, m in enumerate(moving + [True]):
        if not m and start is None:
            start = i
        elif m and start is not None:
            out.append((start * dt, i * dt))
            start = None
    return out


def overlap(a: tuple[float, float], spans: list[tuple[float, float]]) -> float:
    return sum(max(0.0, min(a[1], b[1]) - max(a[0], b[0])) for b in spans)


def moving_share(moving: list[bool], dt: float, t0: float, t1: float) -> float:
    i0, i1 = int(t0 / dt), max(int(t0 / dt) + 1, int(round(t1 / dt)))
    part = moving[i0:i1]
    return sum(part) / len(part) if part else 0.0


def emphasis_spans(log: dict) -> list[tuple[float, float]] | None:
    """(start, end) of the plays that only emphasise; None for a layout log without plays."""
    if "plays" not in log:
        return None
    return [(p["start"], p["end"]) for p in log["plays"]
            if p.get("anims") and all(a in EMPHASIS for a in p["anims"]) and p["end"] > p["start"]]


def mask_emphasis(moving: list[bool], spans_: list[tuple[float, float]], dt: float) -> list[bool]:
    """The moving intervals not wholly inside an emphasis-only play."""
    out = list(moving)
    for i in range(len(out)):
        a, b = i * dt, (i + 1) * dt
        if out[i] and any(s0 - 1e-6 <= a and b <= s1 + 1e-6 for s0, s1 in spans_):
            out[i] = False
    return out


def jargon_terms(text: str, terms: list[str]) -> list[str]:
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    return [t for t in terms if re.search(r"(?<![a-z])" + re.escape(t.lower()) + r"(?![a-z])", low)]


def thumbnail_bold(run: Path, cfg: dict) -> dict | None:
    """Share of the thumbnail's picture, outside its text, that stays bold at 168 x 94 (None without it or Pillow)."""
    img_p, meta_p = run / "video" / "final" / "thumbnail.jpg", run / "video" / "final" / "thumbnail.json"
    if not img_p.exists():
        return None
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    im = Image.open(img_p).convert("RGB")
    W, H = im.size
    sw, sh = 168, 94
    a = np.asarray(im.resize((sw, sh), Image.BOX), dtype=np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    bg_hex = (load_json(CONFIG / "video.json").get("palette", {}) or {}).get("background", "#0f172a").lstrip("#")
    bg = [int(bg_hex[i:i + 2], 16) for i in (0, 2, 4)]
    bg_lum = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    mask = np.ones((sh, sw), dtype=bool)
    for el in meta.get("elements", []):
        x0, y0, x1, y1 = el["bbox"]
        mask[int(y0 * sh / H):int(np.ceil(y1 * sh / H)), int(x0 * sw / W):int(np.ceil(x1 * sw / W))] = False
    bold = (np.abs(lum - bg_lum) > cfg["thumbnail_bold_delta"]) & mask
    return {"bold_share": round(float(bold.sum() / max(mask.sum(), 1)), 3)}


# --------------------------------------------------------------------------- scene code
def _name(node) -> str | None:
    f = node.func if isinstance(node, ast.Call) else None
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def vocabulary(path: Path, cls: str) -> dict:
    """Animation and equation calls of a scene class, fades of everything, boxes without a 'so what' after them."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None)
    counts: dict[str, int] = {}
    out = {"counts": counts, "fade_all": [], "boxes_without_after": [], "emphasis_loops": []}
    if node is None:
        return out
    for loop in [n for n in ast.walk(node) if isinstance(n, (ast.For, ast.While))]:
        if any(isinstance(c, ast.Call) and _name(c) in EMPHASIS for c in ast.walk(loop)):
            out["emphasis_loops"].append(loop.lineno)
    boxes, reveal, vo_lines = {}, {}, []
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr == "animate":
            counts[".animate"] = counts.get(".animate", 0) + 1
        if isinstance(n, ast.With):
            for it in n.items:
                if _name(it.context_expr) == "voiceover":
                    vo_lines.append(n.lineno)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and _name(n.value) == "SurroundingRectangle":
            for t in n.targets:
                if isinstance(t, ast.Name):
                    boxes[t.id] = n.lineno
        if not isinstance(n, ast.Call):
            continue
        name = _name(n)
        if name in COUNTED:
            counts[name] = counts.get(name, 0) + 1
        if name == "FadeOut" and "self.mobjects" in ast.unparse(n):
            out["fade_all"].append(n.lineno)
        if name in ("Create", "FadeIn", "Write", "DrawBorderThenFill", "GrowFromCenter"):
            for a in n.args:
                if isinstance(a, ast.Name) and a.id in boxes:
                    reveal[a.id] = max(reveal.get(a.id, 0), n.lineno)
    for b, line in reveal.items():
        if not any(v > line for v in vo_lines):
            out["boxes_without_after"].append(line)
    return out


# --------------------------------------------------------------------------- layout logs
def spans(log: dict) -> list[tuple[float, float]]:
    return [(v["start"], v["start"] + v.get("duration", 0.0)) for v in log.get("voiceovers", [])]


def planned_pauses(log: dict, cap: float) -> list[tuple[float, float]]:
    """(start, end) in scene seconds of each planned pause inside a narration block, up to cap seconds long."""
    out = []
    for v in log.get("voiceovers", []):
        raw, tim = v.get("raw"), v.get("timings") or []
        if not raw or not tim:
            continue
        start = {(e[3] if len(e) > 3 else k): float(e[1]) for k, e in enumerate(tim)}   # word index -> its start
        for n, sec in VS.VOICE.pause_plan(raw, 0.7).items():
            if n in start and 0 < sec <= cap:
                t1 = float(v["start"]) + start[n]
                out.append((max(float(v["start"]), t1 - sec), t1))
    return out


def minus(spans_: list[tuple[float, float]], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for a, b in spans_:
        cur = [(a, b)]
        for h0, h1 in holes:
            nxt = []
            for x, y in cur:
                if h1 <= x or h0 >= y:
                    nxt.append((x, y))
                    continue
                if x < h0:
                    nxt.append((x, h0))
                if h1 < y:
                    nxt.append((h1, y))
            cur = nxt
        out += cur
    return out


def holds(log: dict) -> list[tuple[float, float]]:
    """The planned holds of the picture (common.py Hold plays)."""
    return [(float(p["start"]), float(p["end"])) for p in log.get("plays") or [] if "Hold" in (p.get("anims") or [])]


def restates(scene: dict, block: dict | None, plan: dict) -> bool:
    """Whether a narration block says a plan.json restatement of this scene."""
    if not block:
        return False
    text = " ".join(str(block.get("text", "")).lower().split())
    for i in plan.get("ideas") or []:
        if not isinstance(i, dict) or i.get("kind") != "restatement" or i.get("scene") != scene.get("class"):
            continue
        if i.get("says") and " ".join(str(i["says"]).lower().split()) in text:
            return True
        if i.get("bookmark") and i["bookmark"] in (block.get("bookmarks") or {}):
            return True
    return False


def visible_time(item: dict, end: float) -> float:
    return sum(b - a for a, b in checks.intervals(item.get("events", []), end))


def titles(log: dict, cfg: dict) -> list[tuple[str, float]]:
    out = []
    for it in log.get("timeline", []):
        if it.get("kind") != "text" or it.get("live") or (it.get("font_size") or 0) < cfg["title_min_size"]:
            continue
        evs = [e for e in it.get("events", []) if e[1] == 1]
        if not evs:
            continue
        x0, y0, x1, y1 = evs[0][2:6]
        if y1 >= cfg["title_band_top"] and abs((x0 + x1) / 2) <= cfg["title_centre_max_x"]:
            out.append((it.get("content", ""), visible_time(it, log.get("duration", 0.0))))
    return out


def shows_label(log: dict, label: str) -> bool:
    return any((it.get("content") or "").strip().startswith(label) and any(e[1] == 1 for e in it.get("events", []))
               for it in log.get("timeline", []))


NUMBER = re.compile(r"=\s*(-?\d[\d,]*(?:\.\d+)?|-?\.\d+)")


def metaphor_track(log: dict, label: str | None) -> tuple[list[tuple[float, float]], float | None, float, str]:
    """(the metaphor's [(t, value)] while visible, its vmax, seconds visible, source: "probe", "readout" or "none")."""
    end = float(log.get("duration") or 0.0)
    best = None
    for ent in log.get("metaphor") or []:
        vis = ent.get("visible") or []
        spans_ = []
        for k, (t, on) in enumerate(vis):
            if on:
                t1 = vis[k + 1][0] if k + 1 < len(vis) else end
                spans_.append((float(t), float(t1)))
        shown = sum(b - a for a, b in spans_)
        vals = ent.get("values") or []
        track = []
        for k, (t, v) in enumerate(vals):              # a value holds until the next sample
            t_next = vals[k + 1][0] if k + 1 < len(vals) else end
            for a, b in spans_:
                if a - 1e-6 <= t < b or (t < a < t_next):
                    track.append((max(float(t), a), float(v)))
        track = sorted(set(track))
        if track and (best is None or shown > best[2]):
            best = (track, ent.get("vmax"), shown, "probe")
    if best:
        return best
    if label:                                   # a log without "metaphor": the readouts of the label, merged
        pts, shown = [], 0.0
        for it in log.get("timeline", []):
            own = []
            for t, text in it.get("values") or []:
                if str(text).strip().startswith(label):
                    m = NUMBER.search(str(text))
                    if m:
                        own.append((float(t), float(m.group(1).replace(",", ""))))
            if own:
                pts += own
                shown += visible_time(it, end)
        if pts:
            return sorted(pts), None, shown, "readout"
    return [], None, 0.0, "none"


def rises(track: list[tuple[float, float]], tol: float, gap_s: float = 1.5) -> list[tuple[float, float, float, float]]:
    """[(t0, t1, v0, v1)] where the value climbs by more than tol (a dip or a plateau over gap_s ends a climb)."""
    out, start, peak = [], None, None
    eps = tol / 10

    def close():
        if start is not None and peak[1] - start[1] > tol:
            out.append((start[0], peak[0], start[1], peak[1]))

    for (ta, va), (tb, vb) in zip(track, track[1:]):
        held = tb - ta > gap_s                   # samples come when the value changes: a long interval is a plateau
        if vb > va + 1e-9:
            if start is not None and (held or ta - peak[0] > gap_s or va < peak[1] - eps):
                close()
                start = None
            if start is None:
                start = (tb if held else ta, va)
            peak = (tb, vb)
        elif start is not None and (vb < peak[1] - eps or held):
            close()
            start = None
    close()
    return out


def phrase_time(block: dict, words: str) -> float | None:
    """When a narration block says words, from their position among its words (None when it does not)."""
    text = " ".join(str(block.get("text", "")).lower().split())
    k = text.find(" ".join(words.lower().split()))
    if k < 0:
        return None
    before, total = len(WORD.findall(text[:k])), max(len(WORD.findall(text)), 1)
    return float(block["start"]) + float(block.get("duration", 0.0)) * before / total


def declared(rise: tuple[float, float, float, float], resets: list, log: dict, margin: float) -> dict | None:
    """The plan.json reset whose words are said in a block overlapping the rise, no later than it begins."""
    for r in resets or []:
        says = str((r or {}).get("says") or "").strip().lower()
        if not says:
            continue
        for v in log.get("voiceovers", []):
            a, b = float(v["start"]), float(v["start"]) + float(v.get("duration", 0.0))
            if says not in " ".join(str(v.get("text", "")).lower().split()):
                continue
            t_said = phrase_time(v, says)
            if t_said is None:
                continue
            if a - margin <= rise[1] and rise[0] <= b + margin and rise[0] >= t_said - margin:
                return r
    return None


def reset_said_late(rise: tuple[float, float, float, float], resets: list, log: dict, margin: float) -> float | None:
    """For a rise no reset covers: how long after its start an overlapping block says the reset's words."""
    late = None
    for r in resets or []:
        says = str((r or {}).get("says") or "").strip().lower()
        for v in log.get("voiceovers", []) if says else []:
            a, b = float(v["start"]), float(v["start"]) + float(v.get("duration", 0.0))
            t_said = phrase_time(v, says)
            if t_said is not None and a - margin <= rise[1] and rise[0] <= b + margin and rise[0] < t_said - margin:
                late = t_said - rise[0] if late is None else min(late, t_said - rise[0])
    return late


DECIMAL = re.compile(r"\d[.,]\d")
DIGIT = re.compile(r"\d")


def numbers_on_schematic(log: dict) -> list[tuple[str, float]]:
    """[(text, first shown)] of live readouts with a digit and texts with a decimal: numbers on a schematic picture."""
    out = {}
    for it in log.get("timeline", []):
        if it.get("kind") != "text":
            continue
        shown = [str(v[1]) for v in it.get("values") or []] or [str(it.get("content", ""))]
        on = [e[0] for e in it.get("events", []) if e[1] == 1]
        if not on:
            continue
        for text in shown:
            if DECIMAL.search(text) or (it.get("live") and DIGIT.search(text)):
                out.setdefault(text, on[0])
    return sorted(out.items(), key=lambda x: x[1])


def blank_stretches(inks: list[float], dt: float, threshold: float, skip_end_s: float = 0.0) \
        -> list[tuple[float, float]]:
    """[(t0, t1)] of the frames between the first and the last (or the last skip_end_s) with ink under threshold."""
    n = len(inks)
    last = n - 1 - int(round(skip_end_s / dt)) if skip_end_s else n - 1
    out, start = [], None
    for i in range(1, max(last, 1)):
        if inks[i] < threshold:
            if start is None:
                start = i
        elif start is not None:
            out.append((start * dt, i * dt))
            start = None
    if start is not None:
        out.append((start * dt, max(last, 1) * dt))
    return out


def off_beat_fill_s(run: Path, stage: str) -> float:
    """The shortest pause of an "off" scene that music.py fills with a swell (0 when it does not)."""
    cfg = (load_json(CONFIG / "channel.json").get("music") or {})
    fill = float(cfg.get("off_beat_swell_s", 1.8) or 0.0)
    if not cfg.get("enabled", True):
        return 0.0
    if stage == "final":
        stamp = run / "video" / "final" / "music.json"
        if not stamp.exists():
            return fill                      # checked before assembly, which adds the swells
        if "off_beats" not in (json.loads(stamp.read_text(encoding="utf-8")).get("events") or {}):
            return 0.0
    return fill


def music_mode(scene: dict) -> str:
    if scene.get("music"):
        return scene["music"]
    modes = (load_json(CONFIG / "channel.json").get("music") or {}).get("modes_by_role", {})
    return modes.get(scene.get("role") or "body", "low")


# --------------------------------------------------------------------------- the check
def check(run: Path, stage: str, cfg: dict, use_video: bool = True) -> tuple[checks.Findings, dict]:
    fd = Findings()
    plan = json.loads((run / "video" / "plan.json").read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    dt = 1.0 / cfg["motion_fps"]
    stats = {"scenes": {}, "layout_sha256": {}, "frames": use_video}
    all_moving, frozen_narr, inks = [], [], []
    meter_tracks, undeclared_pictures = [], []
    words_total, tokens_total, address_total, questions, narr_s = 0, 0, 0, 0, 0.0
    fade_in, transforms, beats = 0, 0, 0
    narration, blocks_of = {}, {}
    for f in checks.scene_files(run):
        for c, blocks in VS.blocks_by_class(f).items():
            narration[c] = " ".join(b for b in blocks if b)
            blocks_of[c] = [b for b in blocks if b]
    seen_terms: set[str] = set()
    emph_narr_total, narr_total_s = 0.0, 0.0
    last = len(scenes) - 1
    fill_s = off_beat_fill_s(run, stage)
    for i, s in enumerate(scenes):
        cls, role = s["class"], s.get("role") or "body"
        log, lp = checks.scene_log(folder, cls)
        if lp is not None:
            stats["layout_sha256"][cls] = sha256_file(lp)
        st = {"role": role, "duration": round(log.get("duration", 0.0), 2)}
        stats["scenes"][cls] = st
        # vocabulary and so-what
        voc = vocabulary(run / "video" / "scenes" / s["file"], cls)
        c = voc["counts"]
        st["counts"] = dict(sorted(c.items()))
        tr = sum(v for k, v in c.items() if k in TRANSFORMS)
        eqs = sum(v for k, v in c.items() if k in EQUATIONS)
        fade_in += c.get("FadeIn", 0)
        transforms += tr
        if role in ("body", "recap") and eqs >= cfg["derivation_min_equations"] and tr == 0:
            fd.add("vocabulary", "warning", cls, f"{eqs} equations and no transform: derive by TransformMatchingTex, "
                   "TransformFromCopy or a brace (common.py derive()), not by writing each line afresh")
        for line in voc["emphasis_loops"]:
            fd.add("emphasis", "warning", cls, f"an emphasis animation inside a loop (line {line}): pulsing to keep "
                   "the picture moving is not motion; animate what the narration says")
        n_emph = sum(v for k, v in c.items() if k in EMPHASIS)
        minutes_scene = (log.get("duration") or 0.0) / 60
        if minutes_scene > 0.5 and n_emph > cfg["emphasis_per_min_warn"] * minutes_scene:
            fd.add("emphasis", "warning", cls, f"{n_emph} emphasis calls (Indicate, Circumscribe, pulse ...) in "
                   f"{minutes_scene * 60:.0f} s (at most {cfg['emphasis_per_min_warn']:g} per minute): emphasise "
                   "once, when the narration names the object")
        # jargon: new technical terms per narration block, in video order
        for k, b in enumerate(blocks_of.get(cls, [])):
            new_terms = [t for t in jargon_terms(b, cfg["jargon"]) if t not in seen_terms]
            seen_terms.update(new_terms)
            if len(new_terms) > cfg["jargon_new_per_block_warn"]:
                fd.add("jargon", "warning", cls, f"narration block {k + 1} introduces {len(new_terms)} new terms at "
                       f"once ({', '.join(new_terms)}): one new term at a time, each with its picture")
        if voc["fade_all"] and i != last:
            fd.add("vocabulary", "warning", cls, f"fades out everything (line {voc['fade_all'][0]}): end in the "
                   "layout the next scene starts from (common.py carry_over())")
        for line in voc["boxes_without_after"]:
            fd.add("so what", "warning", cls, f"a boxed result (line {line}) with no narration after it: say what it "
                   "buys the viewer")
        # narration
        text = narration.get(cls, "")
        words = len(WORD.findall(text))
        toks = NOTATION.findall(text)
        st["narration"] = {"words": words, "notation": len(toks), "address": len(ADDRESS.findall(text)),
                           "questions": text.count("?")}
        words_total += words
        tokens_total += len(toks)
        address_total += st["narration"]["address"]
        questions += text.count("?")
        sp_all = spans(log)
        narr_s += sum(b - a for a, b in sp_all)
        planned = planned_pauses(log, cfg["hold_exempt_s"])        # P19: planned pauses are not narration
        sp = minus(sp_all, planned) if planned else sp_all
        if planned:
            st["planned_pauses_s"] = round(sum(b - a for a, b in planned), 1)
        if words >= 50 and len(toks) * cfg["notation_words_per_token"] > words:
            fd.add("narration", "warning", cls, f"{len(toks)} spoken symbols in {words} words ({', '.join(sorted(set(toks))[:6])}"
                   f"): say meanings, let the coloured equation carry the symbols")
        # titles
        if role in ("body", "recap"):
            for content, shown in titles(log, cfg):
                if shown > cfg["title_max_s"]:
                    fd.add("titles", "warning", cls, f"slide title {content[:40]!r} on screen for {shown:.0f} s (at "
                           f"most {cfg['title_max_s']:.0f} s): the chapter list carries the title")
        # metaphor
        label = (plan.get("metaphor") or {}).get("label")
        if label and log:
            st["metaphor"] = shows_label(log, label)
            track, vmax, shown, source = metaphor_track(log, label)
            if track:
                meter_tracks.append((cls, role, s, log, track, vmax, shown, source, i))
        # what the picture claims: "faithful" (drawn to the scale of its numbers) or "schematic" (no numbers)
        pic = s.get("picture")
        if pic is None:
            undeclared_pictures.append(cls)
        elif pic == "schematic" and log:
            nums = numbers_on_schematic(log)
            if nums:
                st["numbers_on_schematic"] = [n for n, _ in nums][:5]
                fd.add("picture", "warning", cls, f"numbers on a schematic picture: {', '.join(repr(n) for n, _ in nums[:3])}"
                       f"{' ...' if len(nums) > 3 else ''} (first at {nums[0][1]:.1f} s): show the label without the "
                       "number (meter(..., show_value=False)), or draw the picture to scale and mark it \"faithful\"",
                       t=nums[0][1])
        # frames
        if not use_video:
            continue
        video = folder / (f"{cls}_ql.mp4" if stage == "draft" else f"{cls}.mp4")
        fr = frames(video, cfg)
        if fr is None:
            st["frames"] = "not read (no video, ffmpeg or numpy)"
            continue
        raw = motion_of(fr, cfg)
        emph = emphasis_spans(log)
        mv = raw if (emph is None or cfg["emphasis_counts_as_motion"]) else mask_emphasis(raw, emph, dt)
        all_moving += mv
        st["moving_share"] = round(sum(mv) / len(mv), 3) if mv else 0.0
        st["moving_share_raw"] = round(sum(raw) / len(raw), 3) if raw else 0.0
        if emph is None:
            st["emphasis"] = "not separated (layout log without plays: re-render with the current layout_probe.py)"
        else:
            narr_s_scene = sum(b - a for a, b in sp)
            e_narr = sum(overlap(e, sp) for e in emph)
            emph_narr_total += e_narr
            narr_total_s += narr_s_scene
            st["emphasis_narrated_share"] = round(e_narr / narr_s_scene, 3) if narr_s_scene else 0.0
            if narr_s_scene and e_narr > cfg["emphasis_share_warn"] * narr_s_scene:
                fd.add("emphasis", "warning", cls, f"the narration runs over emphasis alone for {e_narr:.0f} s of "
                       f"{narr_s_scene:.0f} s ({e_narr / narr_s_scene:.0%}, at most "
                       f"{cfg['emphasis_share_warn']:.0%}): show what is being said instead of pulsing")
        inks.append((cls, ink(fr[0], cfg), ink(fr[-1], cfg)))
        frame_inks = [ink(f_, cfg) for f_ in fr]
        for a, b in blank_stretches(frame_inks, dt, cfg["empty_cut_ink"],
                                    cfg["blank_end_grace_s"] if i == last else 0.0):
            st.setdefault("blank_inside", []).append([round(a, 2), round(b, 2)])
            fd.add("blank", "warning", cls, f"the picture is empty for {b - a:.2f} s at {a:.2f} s, inside the scene: "
                   "transform the last picture into the next one (or keep the metaphor on screen) instead of "
                   "clearing the frame", t=a)
        worst = 0.0
        for a, b in frozen_stretches(mv, dt):
            o = overlap((a, b), sp)
            worst = max(worst, o)
            if o > cfg["frozen_narration_warn_s"]:
                sev = "error" if o > cfg["frozen_narration_error_s"] else "warning"
                fd.add("motion", sev, cls, f"the picture is frozen for {b - a:.1f} s ({a:.1f}-{b:.1f} s) while the "
                       f"narration talks for {o:.1f} s of it (warn > {cfg['frozen_narration_warn_s']:.0f} s, error > "
                       f"{cfg['frozen_narration_error_s']:.0f} s): animate what is being said", t=a)
                frozen_narr.append(o)
        st["longest_frozen_narrated_s"] = round(worst, 2)
        # beats and dead air: gaps between narration blocks
        mode = music_mode(s)
        held = holds(log)
        vos = log.get("voiceovers", [])
        for k, ((a0, a1), (b0, _)) in enumerate(zip(sp_all, sp_all[1:])):
            gap = b0 - a1
            if gap < min(cfg["beat_min_s"], cfg["dead_air_s"]):
                continue
            share = moving_share(mv, dt, a1, b0)
            if role in ("body", "recap") and gap >= cfg["beat_min_s"] and (share >= cfg["beat_min_moving"]
                                                                          or mode != "off"):
                beats += 1
            hold = sum(overlap(h, [(a1, b0)]) for h in held)          # P19: a planned hold is not dead air
            cap = cfg["hold_exempt_restated_s"] if restates(s, vos[k + 1] if k + 1 < len(vos) else None, plan) \
                else cfg["hold_exempt_s"]
            exempt = hold >= 0.8 * gap and gap <= cap
            if gap >= cfg["silence_off_max_s"] and mode == "off" and not (fill_s and gap >= fill_s):
                fd.add("silence", "warning", cls, f"{gap:.1f} s of digital silence ({a1:.1f}-{b0:.1f} s): the "
                       "scene's music is off; give it \"low\" music or shorten the pause", t=a1)
            elif gap >= cfg["dead_air_s"] and share < cfg["dead_air_max_moving"] and mode == "off" and not exempt:
                fd.add("beats", "warning", cls, f"{gap:.1f} s of silence with a still picture and no music "
                       f"({a1:.1f}-{b0:.1f} s): dead air; move something or give the scene music", t=a1)
    # video-level
    if all_moving:
        share = sum(all_moving) / len(all_moving)
        stats["moving_share"] = round(share, 3)
        if share < cfg["moving_share_warn"]:
            fd.add("motion", "warning", "video", f"the picture moves in {share:.0%} of the runtime (at least "
                   f"{cfg['moving_share_warn']:.0%})")
        stats["frozen_narrated_over_warn"] = len(frozen_narr)
        stats["longest_frozen_narrated_s"] = round(max([0.0] + [v.get("longest_frozen_narrated_s", 0.0)
                                                                 for v in stats["scenes"].values()]), 2)
    if len(inks) > 1:
        empty = [f"{a[0]}|{b[0]}" for a, b in zip(inks, inks[1:])
                 if a[2] < cfg["empty_cut_ink"] or b[1] < cfg["empty_cut_ink"]]
        stats["cuts"] = {"total": len(inks) - 1, "through_empty": len(empty)}
        if len(empty) > cfg["empty_cut_share_warn"] * (len(inks) - 1):
            fd.add("cuts", "warning", "video", f"{len(empty)} of {len(inks) - 1} cuts pass through an empty frame "
                   f"({', '.join(empty[:4])}): carry the objects across the cut")
    if narr_total_s:
        stats["emphasis_narrated_share"] = round(emph_narr_total / narr_total_s, 3)
    if stage == "final":
        tb = thumbnail_bold(run, cfg)
        if tb is not None:
            stats["thumbnail"] = tb
            if tb["bold_share"] < cfg["thumbnail_picture_bold_min"]:
                fd.add("thumbnail", "warning", "thumbnail", f"the picture keeps {tb['bold_share']:.0%} bold pixels at "
                       f"168 x 94 (at least {cfg['thumbnail_picture_bold_min']:.0%}): thicker strokes, a bigger key "
                       "object, no small readouts in the frame")
    stats["fade_in"], stats["transforms"] = fade_in, transforms
    if fade_in > cfg["fade_ratio_warn"] * max(transforms, 1):
        fd.add("vocabulary", "warning", "video", f"FadeIn {fade_in} times against {transforms} transform(s) (at most "
               f"{cfg['fade_ratio_warn']:.0f} to 1): grow new content out of old content")
    stats["narration"] = {"words": words_total, "notation": tokens_total, "address": address_total,
                          "questions": questions, "seconds": round(narr_s, 1)}
    if words_total and tokens_total * cfg["notation_words_per_token"] > words_total:
        fd.add("narration", "warning", "video", f"{tokens_total} spoken symbols in {words_total} words (at most one "
               f"per {cfg['notation_words_per_token']})")
    if words_total and address_total * 100 < cfg["address_per_100_words"] * words_total:
        fd.add("narration", "warning", "video", f"'you / we' {address_total} times in {words_total} words (at least "
               f"{cfg['address_per_100_words']:g} per 100): talk to the viewer")
    minutes = narr_s or words_total / 150 * 60
    if minutes and questions < minutes / cfg["question_every_s"]:
        fd.add("narration", "warning", "video", f"{questions} question(s) in {minutes / 60:.1f} min of narration (one "
               f"per {cfg['question_every_s'] / 60:.0f} min or more)")
    if use_video and all_moving:
        stats["beats"] = beats
        if beats < cfg["beats_min"]:
            fd.add("beats", "warning", "video", f"{beats} planned beat(s) (a pause of {cfg['beat_min_s']} s or more "
                   f"with motion, after a reveal; at least {cfg['beats_min']}): common.py beat()")
    meta = plan.get("metaphor") or {}
    if not meta.get("label"):
        fd.add("metaphor", "warning", "video", "plan.json declares no \"metaphor\" {\"name\", \"label\"}: one central "
               "picture (the meter) carried through the video")
    else:
        flags = {c: v.get("metaphor") for c, v in stats["scenes"].items() if "metaphor" in v}
        roles = {s["class"]: s.get("role") or "body" for s in scenes}
        body = [c for c in flags if roles.get(c) == "body"]
        share = sum(bool(flags[c]) for c in body) / len(body) if body else 0.0
        stats["metaphor_body_share"] = round(share, 2)
        for r in ("hook", "outro"):
            for c in [c for c in flags if roles.get(c) == r and not flags[c]]:
                fd.add("metaphor", "warning", c, f"the {r} does not show the metaphor ({meta['label']!r})")
        if body and share < cfg["metaphor_body_share_min"]:
            fd.add("metaphor", "warning", "video", f"the metaphor ({meta['label']!r}) is on screen in {share:.0%} of "
                   f"the body scenes (at least {cfg['metaphor_body_share_min']:.0%})")
        meter_moves(fd, stats, meta, meter_tracks, cfg)
    outro_checks(fd, stats, scenes, folder, cfg)
    if undeclared_pictures:
        stats["pictures_undeclared"] = undeclared_pictures
        if any(s_.get("picture") for s_ in scenes):       # a plan that uses the field must use it everywhere
            fd.add("picture", "warning", "video", f"{len(undeclared_pictures)} scene(s) do not say whether their "
                   f"picture is \"faithful\" or \"schematic\" (plan.json scenes[].picture): "
                   f"{', '.join(undeclared_pictures[:6])}")
    return fd, stats


def meter_moves(fd: checks.Findings, stats: dict, meta: dict, tracks: list, cfg: dict) -> None:
    """Rises of the metaphor without a declared, spoken reset, and body scenes where it never changes."""
    direction = str(meta.get("direction", "down")).lower()
    n_rises, static = 0, []
    prev = None
    for cls, role, sc, log, track, vmax, shown, source, idx in tracks:
        top = float(vmax) if vmax else max(v for _, v in track)
        tol = max(cfg["metaphor_rise_tol"] * top, 1e-3)
        values = [v for _, v in track]
        if direction == "down":
            found = rises(track, tol)
            if prev is not None and prev[2] == idx - 1 and track[0][1] > prev[1] + tol:   # opens fuller than the
                found.insert(0, (0.0, track[0][0], prev[1], track[0][1]))                 # previous scene ended
            for r in found:
                cover = declared(r, sc.get("metaphor_resets"), log, cfg["metaphor_reset_margin_s"])
                if cover:
                    continue
                n_rises += 1
                at = "at the cut into the scene" if r[0] == 0.0 and r[1] == track[0][0] and prev is not None \
                    and r[2] == prev[1] else f"at {r[0]:.1f}-{r[1]:.1f} s"
                late = reset_said_late(r, sc.get("metaphor_resets"), log, cfg["metaphor_reset_margin_s"])
                if late is not None:
                    fd.add("meter", "warning", cls, f"the metaphor ({meta.get('label')!r}) rises from {r[2]:.3g} to "
                           f"{r[3]:.3g} {at}, {late:.1f} s before the narration announces it: refill on screen as "
                           "the words are said (or move the words before the refill)", t=r[0])
                    continue
                fd.add("meter", "warning", cls, f"the metaphor ({meta.get('label')!r}) rises from {r[2]:.3g} to "
                       f"{r[3]:.3g} {at} with no reset declared: along the path the bill only falls. Show the "
                       "hypothetical on the bowl or a ghost meter, or declare the reset in plan.json (scenes[]."
                       "metaphor_resets: {\"says\": words of the narration block that announces it, \"why\"}) and say "
                       "it", t=r[0])
        if role == "body" and log.get("duration") and source == "probe" \
                and shown >= cfg["metaphor_static_min_share"] * float(log["duration"]) \
                and max(values) - min(values) <= tol:
            static.append(cls)
            fd.add("meter", "warning", cls, f"the metaphor is on screen for {shown:.0f} s of "
                   f"{float(log['duration']):.0f} s and stays at {values[0]:.3g}: it reads as decoration; let it "
                   "follow the argument (fill as the bill is built, drain as steps are paid) or leave it out here")
        prev = (track[-1][0], track[-1][1], idx)
    stats["meter"] = {"rises_undeclared": n_rises, "static_scenes": static,
                      "sources": sorted({t[7] for t in tracks})}


def outro_checks(fd: checks.Findings, stats: dict, scenes: list, folder: Path, cfg: dict) -> None:
    """Time after the outro's last word, and its spoken question on screen."""
    if not scenes:
        return
    s = scenes[-1]
    if (s.get("role") or "outro") != "outro":
        return
    log, _ = checks.scene_log(folder, s["class"])
    vos = log.get("voiceovers") or []
    dur = float(log.get("duration") or 0.0)
    if not vos or not dur:
        return
    end = max(float(v["start"]) + float(v.get("duration", 0.0)) for v in vos)
    tail = dur - end
    stats["outro_tail_s"] = round(tail, 2)
    if tail < cfg["outro_tail_min_s"]:
        fd.add("outro", "warning", s["class"], f"the last word ends {tail:.1f} s before the end of the video (at least "
               f"{cfg['outro_tail_min_s']:.1f} s): hold the card with the music after the last sentence", t=end)
    asked = [v["text"] for v in vos if "?" in str(v.get("text", ""))]
    shown = any("?" in str(it.get("content", "")) and any(e[1] == 1 for e in it.get("events", []))
                for it in log.get("timeline", []))
    if asked and not shown:
        q = asked[-1][asked[-1].rfind(".", 0, asked[-1].find("?")) + 1:asked[-1].find("?") + 1].strip()
        fd.add("outro", "warning", s["class"], f"the outro asks {q!r} only aloud: put the question on screen (a short "
               "line on the card) so it stays when the voice stops")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--no-video", action="store_true", help="skip the frame-based checks")
    ap.add_argument("--out", help="output folder (default review/design/<stage>/)")
    a = ap.parse_args()
    run = resolve_run(a.run)
    cfg = settings()
    fd, s = check(run, a.stage, cfg, use_video=not a.no_video)
    n_err, n_warn = checks.summary(fd.items).values()
    out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    md = [f"# Engagement ({a.stage})", "", f"{n_err} error(s), {n_warn} warning(s); thresholds in "
          "config/video.json \"engagement\".", ""]
    if "moving_share" in s:
        md.append(f"- moving share of the runtime: {s['moving_share']:.0%}; longest frozen stretch under narration: "
                  f"{s['longest_frozen_narrated_s']:.1f} s; frozen stretches over the warning: "
                  f"{s['frozen_narrated_over_warn']}; cuts through an empty frame: "
                  f"{s.get('cuts', {}).get('through_empty', '-')}/{s.get('cuts', {}).get('total', '-')}; beats: "
                  f"{s.get('beats', '-')}")
    n = s["narration"]
    md.append(f"- FadeIn {s['fade_in']}, transforms {s['transforms']}; narration {n['words']} words, spoken symbols "
              f"{n['notation']}, you/we {n['address']}, questions {n['questions']}")
    if "metaphor_body_share" in s:
        md.append(f"- metaphor on screen in {s['metaphor_body_share']:.0%} of the body scenes")
    if "emphasis_narrated_share" in s:
        md.append(f"- narration over emphasis alone (Indicate, Circumscribe, pulse ...): "
                  f"{s['emphasis_narrated_share']:.0%} of the narrated time (counted as frozen for the motion budget)")
    if "thumbnail" in s:
        md.append(f"- thumbnail picture: {s['thumbnail']['bold_share']:.0%} bold pixels at 168 x 94")
    if "meter" in s:
        md.append(f"- metaphor value: {s['meter']['rises_undeclared']} undeclared rise(s); never changes in: "
                  f"{', '.join(s['meter']['static_scenes']) or 'none'} (from {', '.join(s['meter']['sources'])})")
    if "outro_tail_s" in s:
        md.append(f"- outro: {s['outro_tail_s']:.1f} s of picture after the last word")
    blanks = {c: v["blank_inside"] for c, v in s["scenes"].items() if v.get("blank_inside")}
    if blanks:
        md.append("- empty frames inside scenes: " + "; ".join(f"{c} at {', '.join(f'{a:.2f} s' for a, _ in v)}"
                                                              for c, v in blanks.items()))
    md += [""] + checks.md_table(
        ["Scene", "Role", "s", "moving (content / raw)", "longest frozen narrated (s)", "emphasis narrated",
         "transforms", "FadeIn", "symbols/words"],
        ([c, v["role"], v["duration"], f"{v.get('moving_share', '-')} / {v.get('moving_share_raw', '-')}",
          v.get("longest_frozen_narrated_s", "-"), v.get("emphasis_narrated_share", "-"),
          sum(x for k, x in v.get("counts", {}).items() if k in TRANSFORMS), v.get("counts", {}).get("FadeIn", 0),
          f"{v['narration']['notation']}/{v['narration']['words']}"] for c, v in s["scenes"].items()))
    if fd.items:
        md += [""] + checks.md_table(["Severity", "Check", "Where", "t (s)", "Detail"], (
            [x["severity"], x["check"], x["where"], "" if x["t"] is None else x["t"], x["detail"]] for x in fd.items))
    checks.write_report(out, "check_engagement", a.stage, fd.items, md, stats=s, layout_sha256=s.pop("layout_sha256"))
    for x in fd.items:
        print(f"{x['severity']} {x['check']} {x['where']}{'' if x['t'] is None else ' t=' + str(x['t']) + 's'}: "
              f"{x['detail']}")
    print(f"check_engagement ({a.stage}): {n_err} error(s), {n_warn} warning(s); {rel(out / 'check_engagement.md')}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
