#!/usr/bin/env python3
"""Render a Manim scene exactly as the manim command would, and log its layout and on-screen timeline.

Usage (tools/render_video.sh calls it with the Python that has Manim; everything after -- is the manim command line):
  .venv/bin/python tools/video/layout_probe.py --probe-out OUT.layout.json [--interval 1.0] -- -ql --media_dir M scene.py Class

It patches manim's Scene base class in this process only, so every scene is instrumented without changing its code
(the Remaining Action base class in templates/manim/common.py adds reading holds on top; it is not required here).
The JSON written to --probe-out holds, in scene seconds:
  snapshots   at the end of every play() and wait() ("settled") and every --interval seconds: each visible text item
              (Text, MarkupText, Paragraph, MathTex, Tex, DecimalNumber) with kind, content, bounding box, font size,
              colour, opacity, drawing order and top-level group; each visible path (curves, lines, shapes) as a
              subsampled polyline with stroke width, colours and opacities; the number of visible top-level elements
  timeline    every text item's visibility and position changes, sampled at up to --fps-max frames per second;
              for live items (readouts with updaters) also "values": [t, text shown] whenever the text changes
  voiceovers  start, duration and words of each manim-voiceover block; sections from next_section()
Coordinates are Manim units (frame 14.22 x 8, origin at the centre). tools/video/check_design.py and
tools/video/check_reading.py read this file; the gate never trusts a log it did not produce on a clean checkout.
"""
from __future__ import annotations

import atexit
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE: dict = {"scenes": {}, "frame": {}}
OUT: Path | None = None
INTERVAL, FPS_MAX = 1.0, 15.0
MAX_POINTS = 40


def _r(x: float, n: int = 3) -> float:
    return round(float(x), n)


class SceneLog:
    def __init__(self, name: str):
        self.name = name
        self.snapshots: list[dict] = []
        self.timeline: dict[int, dict] = {}
        self.voiceovers: list[dict] = []
        self.sections: list[dict] = []
        self.ids: dict[int, int] = {}
        self.keep: list = []                      # keep logged objects alive so id() stays unique
        self.last_sample = -1e9
        self.last_snapshot = -1e9
        self.end = 0.0

    def sid(self, m) -> int:
        k = id(m)
        if k not in self.ids:
            self.ids[k] = len(self.ids) + 1
            self.keep.append(m)
        return self.ids[k]

    def to_json(self) -> dict:
        return {"snapshots": self.snapshots, "timeline": list(self.timeline.values()), "voiceovers": self.voiceovers,
                "sections": self.sections, "duration": _r(self.end)}


def install() -> None:
    import numpy as np
    from manim import DL, UR, Scene, config
    from manim.mobject.graphing.coordinate_systems import CoordinateSystem
    from manim.mobject.graphing.number_line import NumberLine
    from manim.mobject.text.numbers import DecimalNumber
    from manim.mobject.text.tex_mobject import SingleStringMathTex
    from manim.mobject.text.text_mobject import MarkupText, Paragraph, Text
    from manim.mobject.types.vectorized_mobject import VMobject
    from manim.renderer.cairo_renderer import CairoRenderer
    from manim.utils.family import extract_mobject_family_members

    TEXT = (Text, MarkupText, Paragraph)
    MATH = (SingleStringMathTex, DecimalNumber)
    logs: dict[int, SceneLog] = {}

    def log_for(scene) -> SceneLog:
        lg = logs.get(id(scene))
        if lg is None:
            lg = logs[id(scene)] = SceneLog(type(scene).__name__)
            STATE["scenes"][lg.name] = lg
        return lg

    def now(scene) -> float:
        return float(getattr(scene.renderer, "time", 0.0))

    def alpha(m) -> float:
        best = 0.0
        for f in m.get_family():
            if not isinstance(f, VMobject) or not f.has_points():
                continue
            if len(f.fill_rgbas):
                best = max(best, float(np.max(f.fill_rgbas[:, 3])))
            if len(f.stroke_rgbas) and float(f.get_stroke_width() or 0) > 0:
                best = max(best, float(np.max(f.stroke_rgbas[:, 3])))
        return best

    def bbox(m) -> list[float]:
        x0, y0, _ = m.get_corner(DL)
        x1, y1, _ = m.get_corner(UR)
        return [_r(x0), _r(y0), _r(x1), _r(y1)]

    def colour(m) -> str:
        pts = [f for f in m.get_family() if isinstance(f, VMobject) and f.has_points()]
        try:
            return (pts[0] if pts else m).get_fill_color().to_hex().lower()[:7]
        except Exception:
            return "#ffffff"

    def content(m) -> str:
        live = getattr(m, "ra_live_text", None)          # common.py readout(): the string shown right now
        if isinstance(live, str) and live:
            return live
        if isinstance(m, DecimalNumber):                 # as displayed, not the full float
            try:
                return f"{float(m.number):.{int(getattr(m, 'num_decimal_places', 2))}f}"
            except (TypeError, ValueError):
                return str(getattr(m, "number", ""))
        if isinstance(m, Paragraph):
            return "\n".join(getattr(m, "lines_text", None) and [str(x) for x in m.lines_text.submobjects] or [])
        for attr in ("original_text", "tex_string", "text"):
            v = getattr(m, attr, None)
            if isinstance(v, str) and v:
                return v
        return ""

    def walk(scene):
        """Visible text items and paths in drawing order, with their top-level element index and live flag, and the
        attachment of each text (common.py attach(): a label that belongs next to an object; inherited from groups)."""
        order = {id(f): i for i, f in enumerate(extract_mobject_family_members(scene.mobjects, use_z_index=True))}
        texts, paths, attached = [], [], {}

        def go(m, top, live, axis, att):
            live = live or bool(m.get_updaters())
            axis = axis or isinstance(m, (NumberLine, CoordinateSystem))
            att = getattr(m, "ra_attached_to", None) or att
            if isinstance(m, TEXT + MATH):
                texts.append((m, top, live, axis))
                if att is not None:
                    attached[id(m)] = att
                return
            if isinstance(m, VMobject) and m.has_points():
                paths.append((m, top, live, axis))
            for sm in m.submobjects:
                go(sm, top, live, axis, att)

        for top, m in enumerate(scene.mobjects):
            go(m, top, False, False, None)
        return order, texts, paths, attached

    def attachment(lg, att) -> dict:
        """{"attached": True, "attached_to": [path ids] or None (any object)} for a text marked with attach()."""
        if att is None:
            return {}
        if att is True:
            return {"attached": True, "attached_to": None}
        targets = att if isinstance(att, (list, tuple)) else [att]
        ids = sorted({lg.sid(f) for t_ in targets for f in t_.get_family()
                      if isinstance(f, VMobject) and f.has_points()})
        return {"attached": True, "attached_to": ids}

    def text_record(lg, m, top, live, axis, order, att=None) -> dict | None:
        a = alpha(m)
        if a < 0.05:
            return None
        c = content(m)
        lines = len(getattr(m, "lines_text", [])) if isinstance(m, Paragraph) else c.count("\n") + 1
        return {"id": lg.sid(m), "kind": "math" if isinstance(m, MATH) else "text", "content": c[:300],
                "bbox": bbox(m), "font_size": _r(getattr(m, "font_size", 0) or 0, 1), "color": colour(m),
                "opacity": _r(a, 2), "order": order.get(id(m), 0), "top": top, "live": live, "axis": axis,
                "lines": max(lines, 1), **attachment(lg, att)}

    def path_record(lg, m, top, live, axis, order) -> dict | None:
        sw = float(m.get_stroke_width() or 0)
        so = float(np.max(m.stroke_rgbas[:, 3])) if len(m.stroke_rgbas) and sw > 0 else 0.0
        fo = float(np.max(m.fill_rgbas[:, 3])) if len(m.fill_rgbas) else 0.0
        if so < 0.05 and fo < 0.05:
            return None
        pts = np.asarray(m.get_anchors(), dtype=float).reshape(-1, 3)
        if len(pts) == 0:
            return None
        if len(pts) > MAX_POINTS:
            pts = pts[np.linspace(0, len(pts) - 1, MAX_POINTS).round().astype(int)]
        try:
            sc = m.get_stroke_color().to_hex().lower()[:7]
            fc = m.get_fill_color().to_hex().lower()[:7]
        except Exception:
            sc = fc = "#ffffff"
        return {"id": lg.sid(m), "order": order.get(id(m), 0), "top": top, "live": live, "axis": axis, "bbox": bbox(m),
                "stroke_width": _r(sw, 2), "stroke_opacity": _r(so, 2), "stroke_color": sc,
                "fill_opacity": _r(fo, 2), "fill_color": fc, "points": [[_r(p[0]), _r(p[1])] for p in pts]}

    def snapshot(scene, settled: bool, label: str) -> None:
        lg = log_for(scene)
        t = now(scene)
        order, texts, paths, attached = walk(scene)
        trs = [r for r in (text_record(lg, m, top, live, axis, order, attached.get(id(m)))
                           for m, top, live, axis in texts) if r]
        prs = [r for r in (path_record(lg, m, top, live, axis, order) for m, top, live, axis in paths) if r]
        visible_tops = sorted({r["top"] for r in trs} | {r["top"] for r in prs})
        lg.snapshots.append({"t": _r(t), "settled": settled, "label": label, "texts": trs, "paths": prs,
                             "elements": len(visible_tops)})
        lg.last_snapshot = t
        lg.end = max(lg.end, t)

    def sample(scene, force: bool = False) -> None:
        lg = log_for(scene)
        t = now(scene)
        if not force and t - lg.last_sample < 1.0 / FPS_MAX - 1e-9:
            return
        lg.last_sample = t
        lg.end = max(lg.end, t)
        order, texts, _, _ = walk(scene)
        seen = set()
        for m, top, live, axis in texts:
            a = alpha(m)
            k = lg.sid(m)
            seen.add(k)
            box = bbox(m)
            vis = a >= 0.2 and box[2] > -7.2 and box[0] < 7.2 and box[3] > -4.1 and box[1] < 4.1
            ent = lg.timeline.get(k)
            if ent is None:
                lines = len(getattr(m, "lines_text", [])) if isinstance(m, Paragraph) else content(m).count("\n") + 1
                ent = lg.timeline[k] = {"id": k, "kind": "math" if isinstance(m, MATH) else "text",
                                        "content": content(m)[:300], "font_size": _r(getattr(m, "font_size", 0) or 0, 1),
                                        "lines": max(lines, 1), "live": live, "axis": axis, "events": []}
            ent["live"] = ent["live"] or live
            if ent["live"] and vis:
                shown = content(m)[:300]
                vals = ent.setdefault("values", [])
                if not vals or vals[-1][1] != shown:
                    vals.append([_r(t), shown])
            ev = ent["events"]
            state = [_r(t), 1 if vis else 0, *[round(v, 2) for v in box], round(a, 1)]
            if not ev or ev[-1][1:] != state[1:]:
                ev.append(state)
        for k, ent in lg.timeline.items():               # removed from the scene: invisible from now on
            if k not in seen and ent["events"] and ent["events"][-1][1] == 1:
                ent["events"].append([_r(t), 0, *ent["events"][-1][2:6], 0.0])
        if t - lg.last_snapshot >= INTERVAL - 1e-9:
            snapshot(scene, False, "interval")

    orig_render = CairoRenderer.render
    orig_freeze = CairoRenderer.freeze_current_frame
    orig_play = Scene.play
    orig_section = Scene.next_section
    orig_scene_render = Scene.render

    def render(self, scene, time, moving_mobjects=None):
        sample(scene)
        return orig_render(self, scene, time, moving_mobjects)

    def freeze(self, duration):
        scene = getattr(self, "_probe_scene", None)
        if scene is not None:
            sample(scene, force=True)
        return orig_freeze(self, duration)

    def play(self, *args, **kwargs):
        self.renderer._probe_scene = self
        label = "wait" if args and all(type(a).__name__ == "Wait" for a in args) else "play"
        sample(self, force=True)
        result = orig_play(self, *args, **kwargs)
        sample(self, force=True)
        snapshot(self, True, label)
        return result

    def next_section(self, name: str = "unnamed", *a, **kw):
        log_for(self).sections.append({"name": name, "t": _r(now(self))})
        return orig_section(self, name, *a, **kw)

    def scene_render(self, *a, **kw):
        result = orig_scene_render(self, *a, **kw)
        sample(self, force=True)
        return result

    CairoRenderer.render = render
    CairoRenderer.freeze_current_frame = freeze
    Scene.play = play
    Scene.next_section = next_section
    Scene.render = scene_render

    try:
        from manim_voiceover import VoiceoverScene
        from manim_voiceover.helper import remove_bookmarks
        orig_vo = VoiceoverScene._add_voiceover_text

        def add_vo(self, text, *a, **kw):
            t0 = now(self)
            tracker = orig_vo(self, text, *a, **kw)
            clean = " ".join(remove_bookmarks(text).split())
            log_for(self).voiceovers.append({"start": _r(t0), "duration": _r(tracker.duration),
                                             "words": len(re.findall(r"[\w'’-]+", clean)), "text": clean[:500]})
            return tracker

        VoiceoverScene._add_voiceover_text = add_vo
    except ImportError:
        pass

    STATE["frame"] = {"width": float(config.frame_width), "height": float(config.frame_height)}
    STATE["config"] = config


def write() -> None:
    if OUT is None:
        return
    cfg = STATE.get("config")
    frame = dict(STATE["frame"])
    if cfg is not None:
        frame.update({"pixel_width": int(cfg.pixel_width), "pixel_height": int(cfg.pixel_height),
                      "fps": float(cfg.frame_rate), "background": str(cfg.background_color.to_hex()).lower()[:7]})
    data = {"schema_version": 1, "tool": "layout_probe", "frame": frame,
            "scenes": {name: lg.to_json() for name, lg in STATE["scenes"].items()}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    global OUT, INTERVAL, FPS_MAX
    argv = sys.argv[1:]
    if "--" not in argv or argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 2
    cut = argv.index("--")
    own, manim_args = argv[:cut], argv[cut + 1:]
    i = 0
    while i < len(own):
        if own[i] == "--probe-out":
            OUT = Path(own[i + 1]).resolve()
        elif own[i] == "--interval":
            INTERVAL = float(own[i + 1])
        elif own[i] == "--fps-max":
            FPS_MAX = float(own[i + 1])
        else:
            print(f"unknown option {own[i]}", file=sys.stderr)
            return 2
        i += 2
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]   # tools/video must not shadow scene imports
    install()
    atexit.register(write)
    from manim.__main__ import main as manim_main
    sys.argv = ["manim", *manim_args]
    try:
        manim_main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
