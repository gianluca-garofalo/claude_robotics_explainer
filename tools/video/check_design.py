#!/usr/bin/env python3
"""Deterministic design checks of rendered scenes, from the layout log and the frames (Remaining Action house rules).

Usage:
  python3 tools/video/check_design.py runs/<run> --stage draft     # video/checks/<Class>_ql.mp4 + <Class>.layout.json
  python3 tools/video/check_design.py runs/<run> --stage final     # video/renders/<Class>.mp4 + layout, thumbnail
  python3 tools/video/check_design.py --layout X.layout.json [--video X.mp4] [--out DIR]   # one scene (tests, PoCs)

Checks, at the end of every animation ("settled" snapshots of tools/video/layout_probe.py) unless said otherwise:
  spacing       text closer than min_gap_warn (error below min_gap_error) to a text of another group, to an axis
                line beside it, or to any strong stroke (curve, arrow, plot line, outline: strong_stroke_width and
                strong_stroke_contrast; faint grid strokes are skipped). A label made with common.py attach() is
                exempt from its own object's strokes; the crossing rule (overlap) still applies to it
                (config/video.json "design")
  alignment     (warnings) three or more texts of one kind and size stacked in a column, or set in a row, whose left
                edges, centres or right edges (rows: centres or bottoms) are almost but not quite aligned: all within
                align_max but none within align_tol, or all but one aligned and the odd one off by less than
                align_outlier_max (common.py legend_table() aligns by construction)
  panels        (warnings) side-by-side panels (content separated by an empty vertical gutter of at least
                panel_gutter_min) whose content bottoms differ by more than panel_bottom_diff_warn while their centres
                differ by more than panel_centre_diff_warn (one side ends much higher), or a panel with a hole: an
                empty block inside its own box larger than panel_empty_warn of it; the outro is exempt
  overlap       text on text; text crossed by a strong stroke (curve, axis, arrow: width and contrast in config) or
                covered by a filled shape drawn after it. Thin, low-contrast strokes crossing text are warnings.
  safe-area     text outside the EBU R 95 action-safe area (error) or graphics-safe area (warning)
  glyph-size    cap height at 1080 lines and at a phone-sized picture (config phone_height_px)
  contrast      WCAG 2.x contrast of each text against what is behind it (background and filled shapes, with opacity)
  palette       semantic colours used together that collapse under protanopia, deuteranopia or tritanopia
                (Machado et al. 2009 simulation, CIEDE2000 difference), and colours outside the palette
  clutter       visible top-level elements and text items at once (the cells of one group on one line, a table row,
                count as one item)
  space         (warnings) how the graphics-safe area is used: content coverage, left/right and top/bottom balance,
                a large empty block while the content crowds one side, a small picture (config "space_*")
  motion        during animations, from the probe's 15 fps timeline: two opaque texts overlapping while something
                moves (warning, error when it lasts), and live readouts whose width changes as they update
  margins       non-background pixels in the action-safe margin of sampled frames (needs Pillow; warning)
  thumbnail     (final stage) the thumbnail text at 168 x 94 px: cap height, contrast, word count; nothing busy
                behind the title: no frame text under it, edge density and luminance spread (needs Pillow)
Frames at every settled time and every sample_interval_s are saved with a contact sheet for the video-design-reviewer.
Thresholds: config/video.json "design" and "palette". Writes <out>/check_design.json and .md (default
review/design/<stage>/); exit status 1 when there is an error. Pure Python except frames, margins and thumbnail.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import CONFIG, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402

CAP_PER_FONT = {"text": 0.010125, "math": 0.0070875}     # cap height (Manim units) per font-size unit, measured
MACHADO = {  # Machado, Oliveira and Fernandes (2009), severity 1.0, applied to linear RGB
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


# --------------------------------------------------------------------------- colour
def hex_rgb(h: str) -> tuple[float, float, float]:
    h = (h or "#000000").lstrip("#")[:6].ljust(6, "0")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def unlin(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(rgb) -> float:
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb1, rgb2) -> float:
    a, b = sorted((luminance(rgb1), luminance(rgb2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def blend(top, alpha: float, bottom):
    return tuple(alpha * t + (1 - alpha) * b for t, b in zip(top, bottom))


def simulate(rgb, kind: str):
    m = MACHADO[kind]
    v = [lin(c) for c in rgb]
    return tuple(unlin(sum(m[i][j] * v[j] for j in range(3))) for i in range(3))


def lab(rgb):
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def ciede2000(lab1, lab2) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cm = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    dLp, dCp = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    Lm, cmp_ = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hm = (h1p + h2p) / 2
    else:
        hm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    dtheta = 30 * math.exp(-(((hm - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cmp_ ** 7 / (cmp_ ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (Lm - 50) ** 2 / math.sqrt(20 + (Lm - 50) ** 2)
    sc, sh = 1 + 0.045 * cmp_, 1 + 0.015 * cmp_ * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dLp / sl) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dCp / sc) * (dHp / sh))


def cvd_distance(h1: str, h2: str) -> tuple[float, str]:
    """Smallest CIEDE2000 difference of two colours over normal vision and the three dichromacies."""
    c1, c2 = hex_rgb(h1), hex_rgb(h2)
    best = (ciede2000(lab(c1), lab(c2)), "normal")
    for kind in MACHADO:
        d = ciede2000(lab(simulate(c1, kind)), lab(simulate(c2, kind)))
        best = min(best, (d, kind))
    return best


# --------------------------------------------------------------------------- geometry
def inset(b, dx: float, dy_frac: float):
    h = b[3] - b[1]
    return [b[0] + dx, b[1] + dy_frac * h, b[2] - dx, b[3] - dy_frac * h]


def area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def box_gap(a, b) -> float:
    """Distance between two boxes [x0, y0, x1, y1] (0 when they touch or overlap)."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def seg_gap(p, q, box) -> tuple[float, float]:
    """(distance from the segment p-q to the box, where the box centre projects along p-q: 0..1 is beside it)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    vx, vy = q[0] - p[0], q[1] - p[1]
    n2 = vx * vx + vy * vy or 1e-12
    along = ((cx - p[0]) * vx + (cy - p[1]) * vy) / n2
    pts = [(p[0] + vx * k / 20, p[1] + vy * k / 20) for k in range(21)]
    def d(pt):
        dx = max(box[0] - pt[0], 0.0, pt[0] - box[2])
        dy = max(box[1] - pt[1], 0.0, pt[1] - box[3])
        return math.hypot(dx, dy)
    return min(d(pt) for pt in pts), along


def inter(a, b) -> float:
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def clip_len(p, q, box) -> float:
    """Length of segment pq inside the box (Liang-Barsky)."""
    x0, y0 = p
    dx, dy = q[0] - x0, q[1] - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if pp == 0:
            if qq < 0:
                return 0.0
            continue
        r = qq / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * math.hypot(dx, dy)


def path_len_inside(points, box) -> float:
    return sum(clip_len(points[i], points[i + 1], box) for i in range(len(points) - 1))


def _pt_box(pt, box) -> float:
    return math.hypot(max(box[0] - pt[0], 0.0, pt[0] - box[2]), max(box[1] - pt[1], 0.0, pt[1] - box[3]))


def _pt_seg(pt, p, q) -> float:
    vx, vy = q[0] - p[0], q[1] - p[1]
    n2 = vx * vx + vy * vy
    k = 0.0 if n2 == 0 else max(0.0, min(1.0, ((pt[0] - p[0]) * vx + (pt[1] - p[1]) * vy) / n2))
    return math.hypot(pt[0] - p[0] - k * vx, pt[1] - p[1] - k * vy)


def seg_box_gap(p, q, box) -> float:
    """Exact distance from the segment p-q to the box (0 when it touches or enters it)."""
    if clip_len(p, q, box) > 0 or _pt_box(p, box) == 0 or _pt_box(q, box) == 0:
        return 0.0
    corners = [(box[0], box[1]), (box[0], box[3]), (box[2], box[1]), (box[2], box[3])]
    return min([_pt_box(p, box), _pt_box(q, box)] + [_pt_seg(c, p, q) for c in corners])


def polyline_box_gap(points, box) -> float:
    if len(points) == 1:
        return _pt_box(points[0], box)
    return min(seg_box_gap(points[i], points[i + 1], box) for i in range(len(points) - 1))


def contains(outer, inner, tol: float = 0.0) -> bool:
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1] and outer[2] + tol >= inner[2]
            and outer[3] + tol >= inner[3])


def front(snap: dict, frame: dict, d: dict) -> tuple[list, list, list]:
    """(texts, paths, veils) of a snapshot, without what lies under a veil (a large, mostly opaque shape) or is
    faded below faded_opacity."""
    fw, fh = frame.get("width", 14.222), frame.get("height", 8.0)
    paths = snap.get("paths", [])
    veils = [p for p in paths if p["fill_opacity"] >= d["veil_opacity"] and area(p["bbox"]) >= d["veil_area"] * fw * fh]
    floor = max((v["order"] for v in veils), default=-1)
    texts = [x for x in snap.get("texts", []) if x["order"] > floor and x["opacity"] >= d["faded_opacity"]]
    return texts, [p for p in paths if p["order"] > floor and p not in veils], veils


def hidden(paths: list, lo: int, hi: int, box) -> bool:
    """True when an opaque filled shape drawn between drawing orders lo and hi covers the box: whatever was drawn
    at lo is hidden there (a card or panel over a curve), so it cannot clash with what is drawn at hi."""
    return any(lo < p["order"] < hi and p["fill_opacity"] >= 0.8 and contains(p["bbox"], box) for p in paths)


# --------------------------------------------------------------------------- space and motion
def largest_empty(grid: list[list[bool]]) -> int:
    """Cells of the largest all-empty rectangle (histogram method)."""
    if not grid:
        return 0
    cols, best = len(grid[0]), 0
    heights = [0] * cols
    for row in grid:
        heights = [h + 1 if not c else 0 for h, c in zip(heights, row)]
        stack: list[int] = []
        for i in range(cols + 1):
            h = heights[i] if i < cols else 0
            while stack and heights[stack[-1]] >= h:
                top = heights[stack.pop()]
                left = stack[-1] + 1 if stack else 0
                best = max(best, top * (i - left))
            stack.append(i)
    return best


def space_usage(texts: list, paths: list, gfx, d: dict) -> dict:
    """Content coverage of the graphics-safe area, centre of mass (-1..1), largest empty block and extent."""
    cols, rows = d.get("space_grid", [48, 27])
    w, h = gfx[2] - gfx[0], gfx[3] - gfx[1]
    boxes = [x["bbox"] for x in texts] + [p["bbox"] for p in paths
                                          if p["stroke_opacity"] >= 0.3 or p["fill_opacity"] >= 0.3]
    grid = [[False] * cols for _ in range(rows)]
    for b in boxes:
        x0, x1 = max(b[0], gfx[0]), min(b[2], gfx[2])
        y0, y1 = max(b[1], gfx[1]), min(b[3], gfx[3])
        if x1 <= x0 or y1 <= y0:
            continue
        c0, c1 = int((x0 - gfx[0]) / w * cols), min(cols - 1, int((x1 - gfx[0]) / w * cols - 1e-9))
        r0, r1 = int((gfx[3] - y1) / h * rows), min(rows - 1, int((gfx[3] - y0) / h * rows - 1e-9))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                grid[r][c] = True
    cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c]]
    if not cells:
        return {"coverage": 0.0}
    cx = sum(c + 0.5 for _, c in cells) / len(cells) / cols * 2 - 1
    cy = 1 - sum(r + 0.5 for r, _ in cells) / len(cells) / rows * 2
    rs, cs = [r for r, _ in cells], [c for _, c in cells]
    return {"coverage": round(len(cells) / (rows * cols), 3), "cx": round(cx, 2), "cy": round(cy, 2),
            "empty": round(largest_empty(grid) / (rows * cols), 3),
            "extent": [round((max(cs) - min(cs) + 1) / cols, 2), round((max(rs) - min(rs) + 1) / rows, 2)],
            "graphic": bool(paths)}


def space_findings(name: str, t: float, u: dict, d: dict, rep, role: str | None = None) -> None:
    if not u.get("coverage"):
        return
    if u["coverage"] < d.get("space_min_coverage_warn", 0.1) and not u.get("graphic"):
        return                           # a title or a line of text alone (a transition): nothing to balance
    bal = d.get("space_balance_warn", 0.35)
    for axis, v, sides in (("x", u["cx"], ("left", "right")), ("y", u["cy"], ("bottom", "top"))):
        if role == "outro" and axis == "x":
            continue                     # the outro keeps the right of the frame empty for the end screen
        if u["coverage"] < d.get("space_min_coverage_warn", 0.1):
            continue
        if abs(v) > bal:
            rep.add("space", "warning", name, t, f"the content sits in the {sides[v > 0]} part of the frame (centre "
                    f"of mass at {v:+.2f}, 0 = centred; limit {bal})", ("balance", axis, sides[v > 0]))
    if role != "outro" and u["empty"] >= d.get("space_empty_region_warn", 0.4) and \
            u["coverage"] >= d.get("space_empty_min_coverage", 0.15):
        rep.add("space", "warning", name, t, f"a large empty block ({100 * u['empty']:.0f} % of the safe area) while "
                f"the content crowds the rest: spread or enlarge it", ("empty",))
    if u.get("graphic") and u["coverage"] < d.get("space_min_coverage_warn", 0.1):
        rep.add("space", "warning", name, t, f"the picture covers {100 * u['coverage']:.0f} % of the safe area",
                ("sparse",))
    ext = d.get("space_min_extent_warn", 0.45)
    if u.get("graphic") and u["extent"][0] < ext and u["extent"][1] < ext:
        rep.add("space", "warning", name, t, f"the content spans only {100 * u['extent'][0]:.0f} % x "
                f"{100 * u['extent'][1]:.0f} % of the safe area: scale the picture up", ("small",))


def _components(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) >= 3]


def alignment_findings(name: str, t: float, texts: list, d: dict, rep) -> None:
    """Columns (texts stacked vertically) and rows (side by side, similar heights) of three or more settled texts whose
    edges are almost aligned: within align_max of each other but none within align_tol, or all but one aligned and
    the odd one off by less than align_outlier_max."""
    tol, mx, out = d.get("align_tol", 0.03), d.get("align_max", 0.4), d.get("align_outlier_max", 0.8)
    stack_gap, ratio = d.get("align_stack_gap", 0.6), d.get("align_row_height_ratio", 0.35)
    items = [x for x in texts if not x.get("axis") and not x.get("live")]
    b = [x["bbox"] for x in items]
    same = [(x["kind"], x.get("font_size")) for x in items]   # one family: legend entries, table rows, tags

    def overlap(a0, a1, b0, b1):
        return min(a1, b1) - max(a0, b0)
    col_edges, row_edges = [], []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if same[i] != same[j]:
                continue                                    # a heading over its items is hierarchy, not a column
            p, q = b[i], b[j]
            wmin, hmin = min(p[2] - p[0], q[2] - q[0]), min(p[3] - p[1], q[3] - q[1])
            vgap = max(p[1], q[1]) - min(p[3], q[3])            # > 0: one above the other
            hgap = max(p[0], q[0]) - min(p[2], q[2])            # > 0: side by side
            if vgap > 0 and vgap <= stack_gap and overlap(p[0], p[2], q[0], q[2]) >= 0.3 * wmin:
                col_edges.append((i, j))
            hmax = max(p[3] - p[1], q[3] - q[1])
            if hgap > 0 and hgap <= 2 * stack_gap and overlap(p[1], p[3], q[1], q[3]) >= 0.5 * hmin and \
                    hmax <= (1 + ratio) * hmin:
                row_edges.append((i, j))
    for kind, edges, measures in (
            ("column", col_edges, (("left edges", lambda r: r[0]), ("centres", lambda r: (r[0] + r[2]) / 2),
                                   ("right edges", lambda r: r[2]))),
            ("row", row_edges, (("centres", lambda r: (r[1] + r[3]) / 2), ("bottoms", lambda r: r[1])))):
        for group in _components(len(items), edges):
            if kind == "row":
                cy = [(b[i][1] + b[i][3]) / 2 for i in group]
                if max(cy) - min(cy) > max(b[i][3] - b[i][1] for i in group):
                    continue                                # a staircase, not one row
            vals = [[f(b[i]) for i in group] for _, f in measures]
            spreads = [max(v) - min(v) for v in vals]
            if min(spreads) <= tol:
                continue                                    # aligned on one of them
            names = [label(items[i]) for i in group]
            shown = ", ".join(repr(n) for n in names[:4])
            k = spreads.index(min(spreads))
            if spreads[k] < mx:
                rep.add("alignment", "warning", name, t, f"{len(group)} texts in a {kind} ({shown}) are almost "
                        f"aligned: their {measures[k][0]} differ by {spreads[k]:.2f} units (aligned within {tol}): "
                        "align them (legend_table())", ("near", kind) + tuple(sorted(items[i]["id"] for i in group)),
                        names)
                continue
            for (what, _), v in zip(measures, vals):
                for o in range(len(v)):
                    rest = v[:o] + v[o + 1:]
                    off = abs(v[o] - sorted(rest)[len(rest) // 2])
                    if max(rest) - min(rest) <= tol and tol < off < out:
                        rep.add("alignment", "warning", name, t, f"{len(group)} texts in a {kind}: the {what} of "
                                f"{len(rest)} align, '{names[o]}' is {off:.2f} units off: align it (legend_table())",
                                ("outlier", kind, what) + tuple(sorted(items[i]["id"] for i in group)), names)
                        break
                else:
                    continue
                break


def panel_findings(name: str, t: float, texts: list, paths: list, gfx, d: dict, rep, role: str | None = None) -> None:
    """Side-by-side panels: content separated by an empty vertical gutter. One side ending much higher than the other,
    or a panel that leaves a large block of its own area empty."""
    if role == "outro":
        return
    gutter, header = d.get("panel_gutter_min", 0.5), gfx[3] - d.get("panel_header_band", 0.9)
    boxes = [x["bbox"] + [False] for x in texts] + [p["bbox"] + [bool(p.get("axis"))] for p in paths
                                                    if p["stroke_opacity"] >= 0.3 or p["fill_opacity"] >= 0.3]
    boxes = [[max(b[0], gfx[0]), max(b[1], gfx[1]), min(b[2], gfx[2]), min(b[3], gfx[3]), b[4]] for b in boxes]
    boxes = [b for b in boxes if b[2] >= b[0] and b[3] >= b[1] and not (b[1] >= header and b[0] < 0 < b[2])]
    if not boxes:
        return
    groups: list[list] = []
    for b in sorted(boxes, key=lambda b: b[0]):
        if groups and b[0] < max(g[2] for g in groups[-1]) + gutter:
            groups[-1].append(b)
        else:
            groups.append([b])
    width = gfx[2] - gfx[0]
    panels = [g for g in groups if max(b[2] for b in g) - min(b[0] for b in g) >= d.get("panel_min_width", 0.15) * width]
    if len(panels) < 2:
        return
    ext = [(min(b[0] for b in g), min(b[1] for b in g), max(b[2] for b in g), max(b[3] for b in g)) for g in panels]
    for (a, ea), (bb, eb) in zip(zip(panels, ext), zip(panels[1:], ext[1:])):
        dbot, dcen = abs(ea[1] - eb[1]), abs((ea[1] + ea[3]) / 2 - (eb[1] + eb[3]) / 2)
        if dbot > d.get("panel_bottom_diff_warn", 1.0) and dcen > d.get("panel_centre_diff_warn", 0.6):
            hi = "left" if ea[1] > eb[1] else "right"
            rep.add("panels", "warning", name, t, f"side-by-side panels: the {hi} one ends {dbot:.2f} units higher "
                    f"(bottoms {ea[1]:.2f} and {eb[1]:.2f}, centres {dcen:.2f} apart): move its content down or spread "
                    f"it", ("balance", round(ea[0], 1), round(eb[0], 1)))
    cols, rows = d.get("space_grid", [48, 27])
    cw, rh = width / cols, (gfx[3] - gfx[1]) / rows
    for g, e in zip(panels, ext):
        if all(b[4] for b in g):
            continue                                        # an empty coordinate frame: the space rule's business
        y0, y1 = e[1], e[3]                                 # the panel's own box: holes inside it, not a short side
        if (y1 - y0) < 2 * rh:
            continue
        nc, nr = max(1, round((e[2] - e[0]) / cw)), max(1, round((y1 - y0) / rh))
        grid = [[False] * nc for _ in range(nr)]
        for b in g:
            c0, c1 = int((b[0] - e[0]) / (e[2] - e[0]) * nc), min(nc - 1, int((b[2] - e[0]) / (e[2] - e[0]) * nc - 1e-9))
            r0, r1 = int((y1 - b[3]) / (y1 - y0 or 1) * nr), min(nr - 1, int((y1 - b[1]) / (y1 - y0 or 1) * nr - 1e-9))
            for r in range(max(r0, 0), r1 + 1):
                for c in range(max(c0, 0), c1 + 1):
                    grid[r][c] = True
        frac = largest_empty(grid) / (nc * nr)
        if frac > d.get("panel_empty_warn", 0.35):
            rep.add("panels", "warning", name, t, f"the panel at x {e[0]:.1f} to {e[2]:.1f} leaves {100 * frac:.0f} % of "
                    f"its area empty in one block: fill or enlarge its content", ("empty", round(e[0], 1)))


def motion_checks(name: str, log: dict, d: dict, rep) -> dict:
    """Transient text overlaps and readout width changes, from the probe's timeline (state changes at up to 15 fps)."""
    items = [x for x in log.get("timeline", []) if not x.get("axis") and x.get("events")]
    times = sorted({ev[0] for x in items for ev in x["events"]})
    state: dict[int, list] = {}
    ptr = {x["id"]: 0 for x in items}
    by_id = {x["id"]: x for x in items}
    alpha_min = d.get("motion_min_opacity", 0.6)
    open_: dict[tuple, float] = {}
    spans: list[tuple] = []
    for t in times:
        changed = []
        for x in items:
            evs, k = x["events"], ptr[x["id"]]
            while k < len(evs) and evs[k][0] <= t + 1e-9:
                state[x["id"]] = evs[k]
                k += 1
                changed.append(x["id"])
            ptr[x["id"]] = k
        vis = {i: ev for i, ev in state.items() if ev[1] == 1 and ev[6] >= alpha_min}
        for pair in list(open_):
            a, b = pair
            if a not in vis or b not in vis or not _overlap(vis[a][2:6], vis[b][2:6]):
                spans.append((pair, open_.pop(pair), t))
        ids = sorted(vis)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if (a, b) not in open_ and (a in changed or b in changed) and _overlap(vis[a][2:6], vis[b][2:6]):
                    open_[(a, b)] = t
    end = log.get("duration", times[-1] if times else 0.0)
    spans += [(pair, t0, end) for pair, t0 in open_.items()]
    settled = [s_["t"] for s_ in log.get("snapshots", []) if s_.get("settled")]
    worst = 0.0
    for (a, b), t0, t1 in spans:
        if any(t0 - 1e-6 <= ts <= t1 + 1e-6 for ts in settled):
            continue                     # still overlapping when the animation ends: the settled check reports it
        dur = t1 - t0
        worst = max(worst, dur)
        if dur >= d.get("motion_overlap_warn_s", 0.25):
            sev = "error" if dur >= d.get("motion_overlap_error_s", 1.5) else "warning"
            rep.add("motion", sev, name, t0, f"'{label(by_id[a])}' and '{label(by_id[b])}' overlap for {dur:.2f} s "
                    "while things move", ("overlap",) + tuple(sorted((a, b))), [label(by_id[a]), label(by_id[b])])
    jitter = 0.0
    for x in items:
        if not x.get("live"):
            continue
        skeletons = {re.sub(r"[\d.,−+-]+", "#", v) for _, v in x.get("values", [])}
        if len(skeletons) > 1:
            continue                     # the text itself changes (a verdict), not just its numbers
        widths = [ev[4] - ev[2] for ev in x["events"] if ev[1] == 1]
        if len(widths) > 1:
            j = max(widths) - min(widths)
            jitter = max(jitter, j)
            if j > d.get("readout_width_jitter_warn", 0.12):
                rep.add("motion", "warning", name, x["events"][0][0], f"live readout '{label(x)}' changes width by "
                        f"{j:.2f} units while it updates: fixed decimals keep it steady (readout(..., decimals=k))",
                        ("jitter", x["id"]), [label(x)])
    return {"longest_transient_overlap_s": round(worst, 2), "max_readout_width_change": round(jitter, 3)}


def _overlap(a, b) -> bool:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w >= 0.04 and h >= 0.04


# --------------------------------------------------------------------------- checks on one scene
class Report:
    def __init__(self):
        self.findings: list[dict] = []
        self._seen: dict[tuple, dict] = {}

    def add(self, check: str, severity: str, scene: str, t: float, detail: str, key: tuple, items=()):
        k = (check, scene) + key
        if k in self._seen:
            self._seen[k]["count"] += 1
            return
        f = {"check": check, "severity": severity, "scene": scene, "t": round(t, 2), "detail": detail,
             "items": list(items), "count": 1}
        self._seen[k] = f
        self.findings.append(f)


def reading_items(texts: list) -> int:
    """Text items a viewer reads, counting the cells of one group that share a line (a table row split into cells,
    an equation built from parts) as one item, as if they were a single MathTex."""
    lines: list[tuple] = []
    for x in sorted(texts, key=lambda x: (x["top"], -x["bbox"][3])):
        b = x["bbox"]
        for k, (top, y0, y1) in enumerate(lines):
            if top == x["top"] and min(y1, b[3]) - max(y0, b[1]) >= 0.5 * min(y1 - y0, b[3] - b[1]):
                lines[k] = (top, min(y0, b[1]), max(y1, b[3]))
                break
        else:
            lines.append((x["top"], b[1], b[3]))
    return len(lines)


def label(item: dict) -> str:
    c = (item.get("content") or "").replace("\n", " ").strip()
    return (c[:48] + "...") if len(c) > 51 else c or f"#{item.get('id')}"


def scene_checks(name: str, log: dict, frame: dict, cfg: dict, palette: dict, rep: Report, role: str | None = None) -> dict:
    d = cfg
    fw, fh = frame.get("width", 14.222), frame.get("height", 8.0)
    bg = hex_rgb(frame.get("background", palette.get("background", "#0f172a")))
    px_per_unit = 1080.0 / fh
    phone_scale = d["phone_height_px"] / 1080.0
    act = [-fw / 2 * (1 - 2 * d["action_safe_inset"]), -fh / 2 * (1 - 2 * d["action_safe_inset"]),
           fw / 2 * (1 - 2 * d["action_safe_inset"]), fh / 2 * (1 - 2 * d["action_safe_inset"])]
    gfx = [-fw / 2 * (1 - 2 * d["graphics_safe_inset"]), -fh / 2 * (1 - 2 * d["graphics_safe_inset"]),
           fw / 2 * (1 - 2 * d["graphics_safe_inset"]), fh / 2 * (1 - 2 * d["graphics_safe_inset"])]
    semantic = {k.lower(): v for k, v in palette.get("semantic", {}).items()}
    neutral = {c.lower() for c in palette.get("neutral", []) + [palette.get("background", "#0f172a")]}
    used_semantic, off_palette, pairs = set(), set(), set()
    stats = {"settled_snapshots": 0, "max_elements": 0, "max_text_items": 0}
    for snap in log.get("snapshots", []):
        if not snap.get("settled"):
            continue
        stats["settled_snapshots"] += 1
        t = snap["t"]
        paths = snap.get("paths", [])
        front_t, front_p, _ = front(snap, frame, d)
        elements = len({x["top"] for x in front_t} | {p["top"] for p in front_p})
        reading = [x for x in front_t if not x.get("axis")]          # tick numbers belong to their axis
        usage = space_usage(front_t, front_p, gfx, d)
        space_findings(name, t, usage, d, rep, role)
        alignment_findings(name, t, front_t, d, rep)
        panel_findings(name, t, front_t, front_p, gfx, d, rep, role)
        if usage.get("coverage"):
            stats.setdefault("space_coverage", []).append(usage["coverage"])
        stats["max_elements"] = max(stats["max_elements"], elements)
        n_read = reading_items(reading)
        stats["max_text_items"] = max(stats["max_text_items"], n_read)
        if elements > d["max_elements_error"] or elements > d["max_elements_warn"]:
            sev = "error" if elements > d["max_elements_error"] else "warning"
            rep.add("clutter", sev, name, t, f"{elements} visible elements at once (limit {d['max_elements_warn']})",
                    ("elements",))
        if n_read > d["max_text_items_warn"]:
            sev = "error" if n_read > d["max_text_items_error"] else "warning"
            rep.add("clutter", sev, name, t, f"{n_read} text items at once, axis numbers not counted, the cells of "
                    f"one row counted once (limit {d['max_text_items_warn']})", ("texts",))
        colours_here = set()
        for p in front_p:
            for col, on in ((p["stroke_color"], p["stroke_opacity"] >= 0.5 and p["stroke_width"] >= 2),
                            (p["fill_color"], p["fill_opacity"] >= 0.5)):
                if on:
                    colours_here.add(col.lower())
        for x in front_t:
            colours_here.add(x["color"].lower())
        for col in colours_here:
            if col in semantic:
                used_semantic.add(col)
            elif col not in neutral and col != frame.get("background"):
                off_palette.add(col)
        chroma = sorted(c for c in colours_here if c not in neutral and c != frame.get("background"))
        pairs.update((a, b) for i, a in enumerate(chroma) for b in chroma[i + 1:])
        for i, x in enumerate(front_t):
            box = x["bbox"]
            ink = inset(box, 0.02, 0.12)
            # safe areas
            if not contains(act, box, 0.01):
                rep.add("safe-area", "error", name, t, f"'{label(x)}' reaches outside the action-safe area (EBU R 95)",
                        (x["id"],), [label(x)])
            elif not contains(gfx, box, 0.01):
                rep.add("safe-area", "warning", name, t, f"'{label(x)}' reaches outside the graphics-safe area",
                        (x["id"],), [label(x)])
            # glyph size
            cap = (x.get("font_size") or 0) * CAP_PER_FONT.get(x["kind"], CAP_PER_FONT["text"]) * px_per_unit
            if cap > 0:
                if cap < d["min_cap_px_1080_error"] or cap * phone_scale < d["min_cap_px_phone_error"]:
                    sev = "error"
                elif cap < d["min_cap_px_1080_warn"] or cap * phone_scale < d["min_cap_px_phone_warn"]:
                    sev = "warning"
                else:
                    sev = None
                if sev:
                    rep.add("glyph-size", sev, name, t, f"'{label(x)}': cap height {cap:.0f} px at 1080p, "
                            f"{cap * phone_scale:.1f} px on a {d['phone_height_px']} px phone picture", (x["id"],),
                            [label(x)])
            # contrast against what is behind (scene background, then filled shapes drawn before the text)
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            behind = bg
            for p in sorted(paths, key=lambda q: q["order"]):
                if p["order"] < x["order"] and p["fill_opacity"] > 0.05 and contains(p["bbox"], [cx, cy, cx, cy]):
                    behind = blend(hex_rgb(p["fill_color"]), p["fill_opacity"], behind)
            ratio = contrast(blend(hex_rgb(x["color"]), min(x["opacity"], 1.0), behind), behind)
            large = cap >= d["large_text_cap_px"]
            if ratio < d["contrast_error"] or (ratio < d["contrast_warn"] and not large):
                sev = "error" if ratio < d["contrast_error"] else "warning"
                rep.add("contrast", sev, name, t, f"'{label(x)}': contrast {ratio:.2f}:1 against its background",
                        (x["id"],), [label(x)])
            # text on text: glyph boxes (Manim boxes are tight to the ink) that touch by more than ~3 px
            tight = inset(box, 0.01, 0.0)
            for y in front_t[i + 1:]:
                other = inset(y["bbox"], 0.01, 0.0)
                w = min(tight[2], other[2]) - max(tight[0], other[0])
                hh = min(tight[3], other[3]) - max(tight[1], other[1])
                lo, hi = sorted((x["order"], y["order"]))
                if w >= 0.02 and hh >= 0.02 and not hidden(front_p, lo, hi, [max(tight[0], other[0]),
                                                                             max(tight[1], other[1]),
                                                                             min(tight[2], other[2]),
                                                                             min(tight[3], other[3])]):
                    rep.add("overlap", "error", name, t, f"'{label(x)}' overlaps '{label(y)}' "
                            f"({w:.2f} x {hh:.2f} units)", tuple(sorted((x["id"], y["id"]))), [label(x), label(y)])
                elif x["top"] != y["top"] and not (x.get("axis") and y.get("axis")):
                    gap = box_gap(x["bbox"], y["bbox"])     # items of one group (a paragraph, a legend) may sit close
                    if gap < d.get("min_gap_warn", 0.15):
                        sev = "error" if gap < d.get("min_gap_error", 0.05) else "warning"
                        rep.add("spacing", sev, name, t, f"'{label(x)}' and '{label(y)}' are {gap:.2f} units apart "
                                f"(at least {d.get('min_gap_warn', 0.15)})", ("gap",) + tuple(sorted((x["id"], y["id"]))),
                                [label(x), label(y)])
            # an axis line running beside the text (not at its tip, where axis labels belong)
            if not x.get("axis"):
                for p in front_p:
                    if p.get("axis") and len(p["points"]) == 2 and p["top"] != x["top"]:
                        gap, along = seg_gap(p["points"][0], p["points"][1], x["bbox"])
                        if 0.0 < gap < d.get("min_gap_warn", 0.15) and 0.0 <= along <= 1.0:
                            sev = "error" if gap < d.get("min_gap_error", 0.05) else "warning"
                            rep.add("spacing", sev, name, t, f"'{label(x)}' is {gap:.2f} units from an axis line "
                                    f"(at least {d.get('min_gap_warn', 0.15)})", ("axis-gap", x["id"], p["id"]),
                                    [label(x)])
            # strokes through the text, shapes on top of it
            h = max(ink[3] - ink[1], 1e-6)
            for p in front_p:
                if p.get("live") and p["top"] == x["top"]:
                    continue
                if (p["stroke_opacity"] >= 0.3 and p["stroke_width"] >= 0.5 and len(p["points"]) >= 2
                        and p["order"] < x["order"] and not hidden(front_p, p["order"], x["order"], ink)) or \
                        (p["stroke_opacity"] >= 0.3 and p["stroke_width"] >= 0.5 and len(p["points"]) >= 2
                         and p["order"] > x["order"]):
                    inside = path_len_inside(p["points"], ink)
                    if inside >= max(0.25 * h, 0.04):
                        strong = (p["stroke_width"] >= d["strong_stroke_width"] and
                                  contrast(hex_rgb(p["stroke_color"]), behind) >= d["strong_stroke_contrast"])
                        rep.add("overlap", "error" if strong else "warning", name, t,
                                f"'{label(x)}' is crossed by a {'strong' if strong else 'thin'} stroke "
                                f"(width {p['stroke_width']}, {p['stroke_color']}) over {inside:.2f} units",
                                (x["id"], "stroke" if not strong else p["id"]), [label(x)])
                if p["order"] > x["order"] and p["fill_opacity"] >= 0.5 and inter(ink, p["bbox"]) > 0.1 * area(ink):
                    rep.add("overlap", "error", name, t, f"'{label(x)}' is covered by a filled shape drawn after it "
                            f"({p['fill_color']}, opacity {p['fill_opacity']})", (x["id"], "covered", p["id"]),
                            [label(x)])
            # a strong stroke (curve, arrow, plot line, outline) running close to the text without crossing it
            if not x.get("axis"):
                gap_warn = d.get("min_gap_warn", 0.15)
                att = (x.get("attached_to") if x.get("attached") else False)
                near: dict[int, tuple[float, dict]] = {}       # per object (a dashed line is many paths): closest
                for p in front_p:
                    if p.get("axis") or p["top"] == x["top"] or len(p["points"]) < 2:
                        continue                         # axis lines: the axis-gap rule; one group: composed so
                    if att is None or (att and p["id"] in att):
                        continue                         # a label attached to this object (common.py attach())
                    if p["stroke_opacity"] < 0.3 or p["stroke_width"] < d["strong_stroke_width"] or \
                            contrast(hex_rgb(p["stroke_color"]), behind) < d["strong_stroke_contrast"]:
                        continue                         # faint grid strokes and hairlines
                    if box_gap(p["bbox"], box) >= gap_warn:
                        continue
                    lo, hi = sorted((p["order"], x["order"]))
                    if hidden(front_p, lo, hi, box) or path_len_inside(p["points"], ink) >= max(0.25 * h, 0.04):
                        continue                         # covered, or reported as a crossing (overlap)
                    gap = polyline_box_gap(p["points"], box)
                    if gap < gap_warn and (p["top"] not in near or gap < near[p["top"]][0]):
                        near[p["top"]] = (gap, p)
                for top_, (gap, p) in near.items():
                    sev = "error" if gap < d.get("min_gap_error", 0.05) else "warning"
                    rep.add("spacing", sev, name, t, f"'{label(x)}' is {gap:.2f} units from a line (width "
                            f"{p['stroke_width']}, {p['stroke_color']}; at least {gap_warn}): move it clear, or mark a "
                            "label that points at that object with attach()", ("stroke-gap", x["id"], top_), [label(x)])
    def role(c):
        return semantic[c].split(":")[0] if c in semantic else "off-palette"
    for a, b in sorted(pairs):
        dist, kind = cvd_distance(a, b)
        if dist < d["cvd_delta_e_warn"]:
            sev = "error" if dist < d["cvd_delta_e_error"] else "warning"
            rep.add("palette", sev, name, 0.0, f"{a} ({role(a)}) and {b} ({role(b)}) are used together but differ "
                    f"by only {dist:.1f} (CIEDE2000) for {kind}: label them or change one", (a, b))
    for col in sorted(off_palette):
        rep.add("palette", "warning", name, 0.0, f"colour {col} is not in the palette (config/video.json)", (col,))
    stats["semantic_colours"] = sorted(used_semantic)
    cov = stats.pop("space_coverage", [])
    stats["space"] = {"mean_coverage": round(sum(cov) / len(cov), 3) if cov else None,
                      "min_coverage": min(cov) if cov else None}
    stats["motion"] = motion_checks(name, log, d, rep)
    return stats


# --------------------------------------------------------------------------- frames (optional, Pillow)
def frame_times(log: dict, interval: float, cap: int) -> list[float]:
    dur = log.get("duration", 0.0)
    ts = sorted({round(s["t"], 2) for s in log.get("snapshots", []) if s.get("settled")} |
                {round(k * interval, 2) for k in range(1, int(dur // interval) + 1)})
    ts = [max(t - 0.05, 0.0) for t in ts if t <= dur]
    if len(ts) > cap:
        ts = [ts[round(i * (len(ts) - 1) / (cap - 1))] for i in range(cap)]
    return ts


def extract_frames(video: Path, times: list[float], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for t in times:
        f = out / f"t{t:07.2f}.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=960:-2", str(f)], capture_output=True)
        if r.returncode == 0 and f.exists():
            files.append(f)
    return files


def margin_and_sheet(name: str, frames: list[Path], bg_hex: str, d: dict, rep: Report, sheet: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    bg = tuple(int(c * 255) for c in hex_rgb(bg_hex))
    thumbs = []
    for f in frames:
        im = Image.open(f).convert("RGB")
        w, h = im.size
        mx, my = max(int(w * d["action_safe_inset"]), 1), max(int(h * d["action_safe_inset"]), 1)
        px = im.load()
        hits = 0
        for (x0, y0, x1, y1) in ((0, 0, w, my), (0, h - my, w, h), (0, 0, mx, h), (w - mx, 0, w, h)):
            for yy in range(y0, y1, 2):
                for xx in range(x0, x1, 2):
                    p = px[xx, yy]
                    if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 60:
                        hits += 1
        if hits > 12:
            t = float(f.stem[1:])
            rep.add("margins", "warning", name, t, f"drawn content in the outer {100 * d['action_safe_inset']:.1f} % "
                    f"margin of the frame ({hits} samples)", ("margin",))
        thumbs.append((f.stem[1:], im.resize((320, int(320 * h / w)))))
    if not thumbs:
        return
    cols = 4
    tw, th = thumbs[0][1].size
    rows = (len(thumbs) + cols - 1) // cols
    sheet_im = Image.new("RGB", (cols * tw, rows * (th + 18)), (8, 12, 24))
    draw = ImageDraw.Draw(sheet_im)
    for i, (stamp, im) in enumerate(thumbs):
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        sheet_im.paste(im, (x, y + 18))
        draw.text((x + 4, y + 3), f"{name}  t = {float(stamp):.2f} s", fill=(200, 210, 225))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet_im.save(sheet, "JPEG", quality=82)


def pixels(img) -> list:
    """Pixel values of a Pillow image (get_flattened_data where it exists: getdata is deprecated in Pillow 12)."""
    return list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())


def thumbnail_check(run: Path, d: dict, rep: Report, out: Path) -> dict | None:
    meta_p, img_p = run / "video" / "final" / "thumbnail.json", run / "video" / "final" / "thumbnail.jpg"
    if not (meta_p.exists() and img_p.exists()):
        return None
    try:
        from PIL import Image
    except ImportError:
        return {"skipped": "Pillow not installed"}
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    W, H = meta["size"]
    sw, sh = d["thumbnail_small"]
    im = Image.open(img_p).convert("RGB")
    small = im.resize((sw, sh), Image.LANCZOS)
    out.mkdir(parents=True, exist_ok=True)
    small.save(out / f"thumbnail_{sw}x{sh}.png")
    result = {"small": [sw, sh], "elements": []}
    for el in meta.get("elements", []):
        if el.get("decorative"):
            continue
        x0, y0, x1, y1 = el["bbox"]
        crop = im.crop((x0, y0, x1, y1)).resize((max(1, (x1 - x0) // 8), max(1, (y1 - y0) // 8)))
        lum = sorted(pixels(crop), key=lambda p: luminance(tuple(c / 255 for c in p)))
        median = tuple(c / 255 for c in lum[len(lum) // 4])        # darker quartile: the background behind the text
        ratio = contrast(hex_rgb(el["color"]), median)
        cap_small = el["font_px"] * 0.72 * sh / H
        result["elements"].append({"role": el["role"], "cap_px_small": round(cap_small, 1), "contrast": round(ratio, 2)})
        if cap_small < d["thumbnail_min_cap_px_warn"]:
            sev = "error" if cap_small < d["thumbnail_min_cap_px_error"] else "warning"
            rep.add("thumbnail", sev, "thumbnail", 0.0, f"{el['role']} text is {cap_small:.1f} px tall at {sw}x{sh}",
                    (el["role"], "size"))
        if ratio < d["contrast_warn"]:
            sev = "error" if ratio < d["contrast_error"] else "warning"
            rep.add("thumbnail", sev, "thumbnail", 0.0, f"{el['role']} text contrast {ratio:.2f}:1", (el["role"], "c"))
        n_words = len(str(el.get("text", "")).split())
        if el["role"] == "title" and n_words > d["thumbnail_max_words"]:
            rep.add("thumbnail", "warning", "thumbnail", 0.0, f"{n_words} words (at most {d['thumbnail_max_words']})",
                    ("words",))
        if el["role"] == "title":
            result["behind_title"] = thumbnail_behind_title(run, meta, im, el["bbox"], d, rep)
    return result


def thumbnail_behind_title(run: Path, meta: dict, im, title_box, d: dict, rep: Report) -> dict:
    """The area behind the thumbnail title must be calm: no frame text under it (from the scene's layout log at the
    thumbnail's time) and little texture left after the panel (edge density, luminance spread; config/video.json)."""
    from PIL import ImageFilter
    W, H = meta["size"]
    pad = 16
    x0, y0, x1, y1 = title_box
    box = (max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad))
    out = {"frame_texts": [], "edge_density": None, "luminance_std": None}
    fr = meta.get("frame") or {}
    lp = run / "video" / "renders" / f"{fr.get('scene', '')}.layout.json"
    if fr and lp.exists():
        log_all = json.loads(lp.read_text(encoding="utf-8"))
        fw, fh = log_all.get("frame", {}).get("width", 14.222), log_all.get("frame", {}).get("height", 8.0)
        log = next(iter(log_all.get("scenes", {}).values()), {})
        snaps = [x for x in log.get("snapshots", []) if x.get("t", 0) <= fr.get("scene_time", 0) + 1e-6]
        snap = snaps[-1] if snaps else None
        for x in (snap or {}).get("texts", []):
            if x.get("opacity", 1) < 0.3:
                continue
            bx = x["bbox"]
            px = ((bx[0] + fw / 2) / fw * W, (fh / 2 - bx[3]) / fh * H, (bx[2] + fw / 2) / fw * W, (fh / 2 - bx[1]) / fh * H)
            if px[0] < box[2] and px[2] > box[0] and px[1] < box[3] and px[3] > box[1]:
                out["frame_texts"].append(x.get("content", "")[:40])
        if out["frame_texts"]:
            rep.add("thumbnail", "error", "thumbnail", 0.0, f"frame text behind the title ({len(out['frame_texts'])}: "
                    f"'{out['frame_texts'][0]}'): choose a thumbnail time with nothing where the title goes",
                    ("behind", "text"))
    region = im.crop(box).convert("L")
    glyphs = region.point(lambda v: 255 if v > 150 else 0).filter(ImageFilter.MaxFilter(7))
    edges = region.filter(ImageFilter.FIND_EDGES)
    vals = [(e, g, v) for e, g, v in zip(pixels(edges), pixels(glyphs), pixels(region)) if not g]
    if vals:
        density = sum(e > 40 for e, _, _ in vals) / len(vals)
        lum = [v for _, _, v in vals]
        mean = sum(lum) / len(lum)
        std = (sum((v - mean) ** 2 for v in lum) / len(lum)) ** 0.5
        out.update(edge_density=round(density, 4), luminance_std=round(std, 1))
        if density > d.get("thumbnail_busy_max_edges", 0.04) or std > d.get("thumbnail_busy_max_std", 18):
            rep.add("thumbnail", "error", "thumbnail", 0.0, f"busy background behind the title (edge density "
                    f"{density:.3f}, luminance spread {std:.1f}; limits {d.get('thumbnail_busy_max_edges', 0.04)} and "
                    f"{d.get('thumbnail_busy_max_std', 18)}): choose a calmer frame or darken the panel",
                    ("behind", "busy"))
    return out


# --------------------------------------------------------------------------- driver
def load_config() -> tuple[dict, dict]:
    data = json.loads((CONFIG / "video.json").read_text(encoding="utf-8"))
    return data["design"], data.get("palette", {})


def scene_inputs(run: Path, stage: str) -> list[tuple[str, Path, Path]]:
    """(class, layout, video) for every scene of the plan (or every layout found)."""
    folder = run / "video" / ("checks" if stage == "draft" else "renders")
    names = []
    plan = run / "video" / "plan.json"
    if plan.exists():
        names = [s["class"] for s in json.loads(plan.read_text(encoding="utf-8")).get("scenes", [])]
    if not names:
        names = sorted(p.name[:-len(".layout.json")] for p in folder.glob("*.layout.json"))
    suffix = "_ql.mp4" if stage == "draft" else ".mp4"
    return [(n, folder / f"{n}.layout.json", folder / f"{n}{suffix}") for n in names if not n.startswith("_")]


def write_md(path: Path, data: dict) -> None:
    lines = [f"# Design check ({data['stage']})", "", f"{data['summary']['errors']} error(s), "
             f"{data['summary']['warnings']} warning(s); thresholds in config/video.json. Frames and contact sheets "
             "are next to this file.", "", "| Severity | Check | Scene | t (s) | Detail | Times |", "|---|---|---|---|---|---|"]
    for f in sorted(data["findings"], key=lambda f: (f["severity"] != "error", f["scene"], f["t"])):
        lines.append(f"| {f['severity']} | {f['check']} | {f['scene']} | {f['t']:.2f} | "
                     f"{f['detail'].replace('|', '/')} | {f['count']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?")
    ap.add_argument("--stage", choices=["draft", "final"], default="draft")
    ap.add_argument("--layout", help="one scene's layout log (instead of a run)")
    ap.add_argument("--video", help="that scene's video, for frames and margins")
    ap.add_argument("--out")
    ap.add_argument("--no-frames", action="store_true", help="skip frame extraction (layout checks only)")
    a = ap.parse_args()
    d, palette = load_config()
    rep = Report()
    if a.layout:
        run = None
        lp = Path(a.layout)
        log = json.loads(lp.read_text(encoding="utf-8"))
        inputs = [(n, lp, Path(a.video) if a.video else None) for n in log["scenes"]]
        out = Path(a.out) if a.out else lp.parent / "design"
    elif a.run:
        run = resolve_run(a.run)
        inputs = scene_inputs(run, a.stage)
        out = Path(a.out) if a.out else run / "review" / "design" / a.stage
    else:
        ap.error("give a run or --layout")
    if run is not None:                       # only this tool's own outputs: check_reading writes here too
        shutil.rmtree(out / "frames", ignore_errors=True)
        for old in list(out.glob("*-sheet.jpg")) + list(out.glob("thumbnail_*.png")):
            old.unlink()
    out.mkdir(parents=True, exist_ok=True)
    scenes, missing = {}, []
    roles = {}
    if run is not None and (run / "video" / "plan.json").exists():
        roles = {sc["class"]: sc.get("role") for sc in json.loads((run / "video" / "plan.json").read_text(
            encoding="utf-8")).get("scenes", [])}
    for name, lp, video in inputs:
        if not lp.exists():
            missing.append(name)
            rep.add("layout", "error", name, 0.0, f"no layout log {lp.name}: render with tools/render_video.sh, "
                    "which runs tools/video/layout_probe.py", ("missing",))
            continue
        log_all = json.loads(lp.read_text(encoding="utf-8"))
        log = log_all["scenes"].get(name) or next(iter(log_all["scenes"].values()))
        stats = scene_checks(name, log, log_all.get("frame", {}), d, palette, rep, roles.get(name))
        frames = []
        if video and video.exists() and not a.no_frames and shutil.which("ffmpeg"):
            frames = extract_frames(video, frame_times(log, d["sample_interval_s"], d["max_frames_per_scene"]),
                                    out / "frames" / name)
            margin_and_sheet(name, frames, log_all.get("frame", {}).get("background",
                                                                        palette.get("background", "#0f172a")), d, rep,
                             out / f"{name}-sheet.jpg")
        scenes[name] = dict(stats, layout=str(lp.name), layout_sha256=sha256_file(lp),
                            video=str(video.name) if video and video.exists() else None,
                            video_sha256=sha256_file(video) if video and video.exists() else None,
                            frames=[rel(f) if run else f.name for f in frames])
    thumb = thumbnail_check(run, d, rep, out) if run is not None and a.stage == "final" else None
    errors = sum(f["severity"] == "error" for f in rep.findings)
    warnings = sum(f["severity"] == "warning" for f in rep.findings)
    data = {"schema_version": 1, "tool": "check_design", "stage": a.stage, "checked_at": utc_now(),
            "passed": errors == 0, "summary": {"errors": errors, "warnings": warnings}, "scenes": scenes,
            "thumbnail": thumb, "findings": rep.findings}
    write_json(out / "check_design.json", data)
    write_md(out / "check_design.md", data)
    for f in rep.findings:
        if f["severity"] == "error":
            print(f"ERROR   {f['scene']} t={f['t']:.2f}s {f['check']}: {f['detail']}")
    print(f"check_design ({a.stage}): {'FAIL' if errors else 'ok'} ({errors} error(s), {warnings} warning(s)); "
          f"{rel(out / 'check_design.md') if run else out / 'check_design.md'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
