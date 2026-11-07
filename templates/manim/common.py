"""Palette, layout and choreography helpers and the RAScene base class (narration, reading holds) of every scene.

Usage: copy into runs/<run>/video/scenes/ with voice.py and reading_model.py; in a scene, from common import *
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from manim import *  # noqa: F401,F403


def _video_config(start):
    """config/video.json found upwards from `start` (or $VIDEO_CONFIG); {} when absent."""
    path = os.environ.get("VIDEO_CONFIG")
    if not path:
        here = Path(start).resolve()
        path = next((d / "config" / "video.json" for d in [here, *here.parents]
                     if (d / "config" / "video.json").exists()), None)
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return {}


HERE = os.path.dirname(os.path.abspath(__file__))
_VIDEO = _video_config(HERE)
BG = _VIDEO.get("palette", {}).get("background", "#0f172a")
INK = "#e2e8f0"         # main text
MUTED = "#94a3b8"       # axes, secondary text, captions
GRID = "#334155"        # grid lines, level sets
GREEN = "#2dd4bf"       # holds / stable / verified (teal: told apart from RED by deuteranopes)
AMBER = "#fbbf24"       # contrast case / unstable / second option
BLUE = "#818cf8"        # reference case / first option (indigo: told apart from GREEN by tritanopes)
RED = "#ef4444"         # failure / violation (always with a text label)
SAFE_X, SAFE_Y = 6.4, 3.6   # graphics-safe area (EBU R 95: 5 % margins), in Manim units from the centre

config.background_color = BG
from reading_model import MINUS, NUMBERS, fmt  # noqa: E402,F401
Tex.set_default(color=INK)
MathTex.set_default(color=INK)
Text.set_default(color=INK, font="DejaVu Sans")


def _check_font(name="DejaVu Sans"):
    """Warn once when the font is missing: Pango substitutes another, which changes text widths and the checks."""
    try:
        import manimpango
        if name not in manimpango.list_fonts():
            print(f"warning: font '{name}' not found; Pango uses another font, so text widths and the layout checks "
                  "change (Linux: apt install fonts-dejavu-core; macOS: brew install --cask font-dejavu)",
                  file=sys.stderr)
    except Exception:                       # no ManimPango (a tool that only imports the palette): nothing to check
        pass


_check_font()

HAS_LATEX = os.environ.get("NO_LATEX") != "1" and bool(shutil.which("latex")) and bool(shutil.which("dvisvgm"))


def eq(tex, plain=None, font_size=36, **kw):
    """A static equation: MathTex when LaTeX is available, else Text with the plain-text version."""
    if HAS_LATEX:
        return MathTex(tex, font_size=font_size, **kw)
    return Text(plain or tex, font_size=int(font_size * 0.75), **kw)


def caption(text, size=24):
    """Bottom caption inside the graphics-safe area."""
    c = Text(text, font_size=size, color=MUTED)
    if c.width > 2 * SAFE_X:
        c.scale_to_fit_width(2 * SAFE_X)
    return c.move_to([0, -SAFE_Y + c.height / 2 + 0.05, 0])


def title(text, size=34):
    """Scene title at the top of the graphics-safe area."""
    t = Text(text, font_size=size)
    if t.width > 2 * SAFE_X:
        t.scale_to_fit_width(2 * SAFE_X)
    return t.move_to([0, SAFE_Y - t.height / 2 - 0.05, 0])


def pin(mob, corner=UR, scale=0.75):
    """A smaller copy of an equation shown earlier, in a corner of the graphics-safe area, to keep it in view."""
    c = mob.copy().scale(scale)
    x = SAFE_X - c.width / 2 if corner[0] > 0 else -SAFE_X + c.width / 2
    y = SAFE_Y - c.height / 2 if corner[1] > 0 else -SAFE_Y + c.height / 2
    return c.move_to([x, y, 0])


def swap_caption(scene, old, text, run_time=0.5):
    """The old caption fades out, then the new one in (a Transform between strings morphs glyphs illegibly)."""
    new = caption(text)
    scene.play(Succession(FadeOut(old, shift=UP * 0.1, run_time=run_time / 2),
                          FadeIn(new, shift=UP * 0.1, run_time=run_time / 2)), run_time=run_time)
    return new


SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def sci_u(x, digits=1):
    """Scientific notation for Pango Text with a real minus and superscripts, e.g. −2.7×10⁻¹¹."""
    m, e = f"{x:.{digits}e}".split("e")
    return f"{m.replace('-', chr(0x2212))}×10{str(int(e)).translate(SUP)}"


def always_redraw(func):
    """manim's always_redraw that also keeps the text shown now (become() copies only the shape), for the layout log."""
    mob = func()

    def update(m):
        new = func()
        m.become(new)
        for attr in ("original_text", "text", "tex_string", "ra_live_text"):
            if hasattr(new, attr):
                try:
                    setattr(m, attr, getattr(new, attr))
                except (AttributeError, TypeError):
                    pass
    mob.add_updater(update)
    return mob


def readout(text_or_label, value=None, decimals=None, unit="", font_size=26, color=INK, sign=False, zero_exact=False,
            **kw):
    """A live number in Pango Text: readout("∫ L dt", lambda: paid, decimals=2) shows "∫ L dt = 1.04" through fmt()
    with fixed decimals; readout(lambda: "...") shows the string; zero_exact=True shows an exact zero as "0"."""
    if value is None:
        fn = text_or_label
    else:
        k = NUMBERS.get("readout_decimals", 2) if decimals is None else decimals
        def fn():
            x = float(value())
            shown = fmt(x, exact=True, unit=unit) if zero_exact and x == 0.0 else \
                fmt(x, decimals=k, unit=unit, sign=sign)
            if sign and shown[:1] not in ("+", MINUS):
                shown = "\u2007\u2009" + shown          # a zero keeps the sign's width (DejaVu Sans): no jump
            return f"{text_or_label} = {shown}"

    def make():
        shown = fn()
        m = Text(shown, font_size=font_size, color=color, **kw)
        m.ra_live_text = shown
        return m
    return always_redraw(make)


def attach(label, target=True, direction=None, buff=0.15):
    """Mark a label that names or points at `target` (any object when True), so check_design.py lets it sit close;
    with a direction, also place it next to the target. Returns the label."""
    if direction is not None and target is not True:
        label.next_to(target, direction, buff=buff)
    label.ra_attached_to = target
    return label


class LegendTable(VGroup):
    """legend_table()'s result: rows of cells (cells[i][j]), column(j), and place(mob, i, j) for a swapped-in cell."""

    def column(self, j):
        return VGroup(*[r[j] for r in self.cells if r[j] is not None])

    def place(self, mob, i, j):
        ox, oy = self._anchor.get_center()[:2]
        x0, w, a = ox + self._col_x[j], self._widths[j], self._aligns[j]
        x = x0 + mob.width / 2 if a == "l" else x0 + w - mob.width / 2 if a == "r" else x0 + w / 2
        return mob.move_to([x, oy + self._row_y[i], 0])


def legend_table(rows, aligns=None, col_gap=0.3, row_gap=0.22, min_widths=None):
    """Legends and readout blocks in fixed columns: rows of cells (Mobjects or None), aligns "l", "c" or "r" per column
    (default "c" for dots, else "l"), min_widths {column: width} reserved for cells placed later. Moves the cells."""
    rows = [list(r) for r in rows]
    ncol = max(len(r) for r in rows)
    rows = [r + [None] * (ncol - len(r)) for r in rows]
    if aligns is None:
        aligns = "".join("c" if all(isinstance(r[j], Dot) or r[j] is None for r in rows) else "l" for j in range(ncol))
    widths = [max([r[j].width for r in rows if r[j] is not None] + [(min_widths or {}).get(j, 0.0)])
              for j in range(ncol)]
    pitch = max(max([c.height for c in r if c is not None] + [0.0]) for r in rows) + row_gap
    col_x = [sum(widths[:j]) + j * col_gap for j in range(ncol)]
    row_y = [-i * pitch for i in range(len(rows))]
    anchor = VectorizedPoint(ORIGIN)
    table = LegendTable()
    table.cells, table._widths, table._aligns, table._col_x, table._row_y = rows, widths, aligns, col_x, row_y
    table._anchor = anchor
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            if c is not None:
                table.place(c, i, j)
    table.add(*[VGroup(*[c for c in r if c is not None]) for r in rows], anchor)
    return table


def load_data(default_name, here):
    """The arrays of ../data/<default_name> ($SCENE_DATA overrides the path), or None without the file."""
    path = os.environ.get("SCENE_DATA", os.path.join(here, "..", "data", default_name))
    return dict(np.load(path)) if os.path.exists(path) else None


from voice import block_end_pause, channel_config, speech_service, strip_markup  # noqa: E402,F401

CHANNEL = channel_config(os.path.dirname(os.path.abspath(__file__))).get("channel_name", "Remaining Action")
END_SCREEN_X = 1.4      # the outro keeps x > END_SCREEN_X (the right ~40 % of the frame) empty for end-screen elements


def series_context():
    """video/series_context.json of a series episode, or None (a news video)."""
    p = Path(HERE).parent / "series_context.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def takeaway_card(episode=None, tex=None, font_size=40, color=None):
    """An episode's takeaway equations stacked in a rounded frame, in ink (the first in `color` when given): episode
    a key such as 2 or "mpc-mechanics:2" of series_context.json "takeaways" (default this one), or tex the equations."""
    if tex is None:
        ctx = series_context() or {}
        key = str(episode if episode is not None else ctx.get("episode"))
        tex = ((ctx.get("takeaways") or {}).get(key) or {}).get("tex") or []
        if not tex:
            raise ValueError(f"no takeaway equations for episode {key} in series_context.json")
    rows = VGroup(*[eq(t, font_size=font_size, color=color if (i == 0 and color) else INK)
                    for i, t in enumerate(tex)])
    rows.arrange(DOWN, buff=0.4)
    frame = RoundedRectangle(width=rows.width + 0.8, height=rows.height + 0.7, corner_radius=0.18, color=GRID,
                             stroke_width=2).move_to(rows)
    return VGroup(frame, rows)


def recap_card(index=0, font_size=38):
    """The card of the index-th recap of series_context.json "recaps"."""
    rc = (series_context() or {}).get("recaps", [])[index]
    return takeaway_card(tex=rc["card"], font_size=font_size)


def recap_tag():
    """The small "Recap" tag in the upper-left corner, shown for the whole recap scene."""
    t = Text("Recap", font_size=26, color=MUTED)
    bar = Line(ORIGIN, RIGHT * (t.width + 0.3), color=MUTED, stroke_width=2).next_to(t, DOWN, buff=0.1, aligned_edge=LEFT)
    g = VGroup(t, bar)
    return g.move_to([-SAFE_X + g.width / 2, SAFE_Y - g.height / 2, 0])


def builds_on(ctx=None):
    """The builds-on frame: "Episode n of N", the series title and the short titles of the must prerequisites."""
    ctx = ctx or series_context()
    head = Text(f"Episode {ctx['episode']} of {ctx['episodes_total']}", font_size=44, weight=BOLD)
    sub = Text(ctx["series_title"], font_size=28, color=MUTED)
    rows = [Text(ctx["short_titles"].get(k, k), font_size=32, color=INK) for k in ctx["prerequisites"]["must"]]
    parts = [head, sub]
    if rows:
        parts += [Text("Builds on", font_size=26, color=MUTED), VGroup(*rows).arrange(DOWN, aligned_edge=LEFT,
                                                                                      buff=0.25)]
    g = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
    if rows:
        g[2].shift(DOWN * 0.25)
        g[3].shift(DOWN * 0.25 + RIGHT * 0.3)
    if g.width > 2 * SAFE_X - 1:
        g.scale_to_fit_width(2 * SAFE_X - 1)
    return g.move_to(ORIGIN)


def plan_title():
    """The title of video/plan.json, or None."""
    p = Path(HERE).parent / "plan.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("title")
    except (OSError, ValueError):
        return None


def title_beat(title=None, ctx=None, size=40):
    """VGroup(head, lower) of the title beat: the video's title at the top, and a lower third with "Episode n of N",
    the series title and what it builds on (empty for a news video)."""
    ctx = ctx if ctx is not None else series_context()
    head = Text(title or plan_title() or "", font_size=size, weight=BOLD)
    if head.width > 2 * SAFE_X:
        head.scale_to_fit_width(2 * SAFE_X)
    head.move_to([0, SAFE_Y - head.height / 2 - 0.05, 0])
    lines = []
    if ctx:
        lines += [Text(f"Episode {ctx['episode']} of {ctx['episodes_total']}", font_size=30, weight=BOLD),
                  Text(ctx["series_title"], font_size=24, color=MUTED)]
        must = (ctx.get("prerequisites") or {}).get("must", [])
        if must:
            lines += [Text("Builds on", font_size=24, color=MUTED)]
            lines += [Text(ctx["short_titles"].get(k, k), font_size=24, color=INK) for k in must]
    lower = VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.16) if lines else VGroup()
    if lines:
        if lower.width > 2 * SAFE_X - 0.6:
            lower.scale_to_fit_width(2 * SAFE_X - 0.6)
        bar = Line(ORIGIN, UP * lower.height, color=GREEN, stroke_width=4)
        lower.next_to(bar, RIGHT, buff=0.25)
        lower = VGroup(bar, lower)
        lower.move_to([-SAFE_X + lower.width / 2, -SAFE_Y + lower.height / 2 + 0.05, 0])
    return VGroup(head, lower)


class Meter(VGroup):
    """meter()'s result: frame, fill and readout; level(v) is the y of the fill's top at value v."""

    def level(self, v):
        return self.frame.get_bottom()[1] + self.bar_height * max(0.0, min(v, self.vmax)) / self.vmax

    def _make_readout(self, show_value=True):
        label, value, decimals, font_size, buff = self._ro_args
        if show_value:
            ro = readout(label, value, decimals=decimals, font_size=font_size, zero_exact=True)
        else:
            ro = Text(label, font_size=font_size, color=INK)
        ro.next_to(self.frame, DOWN, buff=buff)
        ro.add_updater(lambda m: m.next_to(self.frame, DOWN, buff=buff))
        return ro

    def swap_readout(self, scene, show_value, run_time=0.5, *others):
        """Swap the readout between the live number (show_value=True) and the label alone, the old one fading out
        before the new one fades in; `others` play along."""
        new = self._make_readout(show_value)
        old = self.readout
        old.clear_updaters()
        self.remove(old)
        (scene.carry_in if hasattr(scene, "carry_in") else scene.add)(old)   # a live readout needs no reading hold
        scene.play(Succession(FadeOut(old, run_time=run_time / 2), FadeIn(new, run_time=run_time / 2)), *others,
                   run_time=run_time)
        scene.remove(new)                         # FadeIn left it at the top level: keep one copy, inside the meter
        self.readout = new
        self.add(new)
        return self

    def freeze(self):
        """Stop the live fill and readout (call before FadeOut: a redrawn part would stay visible) and return self."""
        for part in (self.fill, self.readout):
            part.clear_updaters()
        return self


def meter(value, vmax, label="left to pay", height=4.0, width=0.6, decimals=3, color=BLUE, font_size=26,
          readout_buff=0.3, show_value=True):
    """The remaining-action meter: a bar that drains as value() falls (vmax fills it) over a live readout. Marked
    ra_role="metaphor" with ra_value and ra_vmax for the layout log; call freeze() before fading it out."""
    frame = Rectangle(width=width, height=height, color=MUTED, stroke_width=2)

    def make_fill():
        v = max(0.0, min(float(value()), vmax))
        h = max(height * v / vmax, 0.002)
        r = Rectangle(width=width - 0.1, height=h, stroke_width=0, fill_color=color, fill_opacity=0.9)
        return r.move_to(frame.get_bottom() + UP * (h / 2 + 0.0))
    fill = always_redraw(make_fill)
    m = Meter(frame, fill)
    m.frame, m.fill, m.bar_height, m.vmax = frame, fill, height, vmax
    m._ro_args = (label, value, decimals, font_size, readout_buff)
    m.readout = m._make_readout(show_value)
    m.add(m.readout)
    m.ra_role = "metaphor"
    m.ra_value, m.ra_vmax = (lambda: float(value())), vmax
    return m


def outro(card, next_title=None):
    """The outro: the card, an optional "Next: ..." line and the channel name on the left, x > END_SCREEN_X empty."""
    width = END_SCREEN_X + SAFE_X - 0.4
    if card.width > width:
        card.scale_to_fit_width(width)
    card.move_to([(-SAFE_X + END_SCREEN_X) / 2, 0.7, 0])
    parts = [card]
    if next_title:
        parts.append(Text(f"Next: {next_title}", font_size=28, color=MUTED).next_to(card, DOWN, buff=0.45))
    name = Text(CHANNEL, font_size=30, weight=BOLD, color=MUTED)
    name.move_to([-SAFE_X + name.width / 2, -SAFE_Y + name.height / 2 + 0.1, 0])
    parts.append(name)
    g = VGroup(*parts)
    for m in parts[1:-1]:
        m.align_to(card, LEFT)
    return g


_COLOR_NAMES = {"blue": BLUE, "amber": AMBER, "green": GREEN, "red": RED, "ink": INK, "muted": MUTED}
QUANTITIES = {k: v for k, v in (_VIDEO.get("quantities") or {}).items() if isinstance(v, dict)}
QCOLOR = {k: _COLOR_NAMES.get(str(v.get("color", "ink")).lower(), v.get("color", INK)) for k, v in QUANTITIES.items()}


def qcolor(name):
    """The fixed colour of a quantity (config/video.json "quantities", e.g. qcolor("V")), INK when unmapped."""
    return QCOLOR.get(name, INK)


def _piece_color(tex):
    t = tex.strip()
    for _ in range(3):                                   # leading relations and operators do not decide the colour
        t = re.sub(r"^(?:=|\\leq|\\geq|\\le|\\ge|<|>|\+|-|\\,|\\;|\\quad|\\qquad|\\ |\\!|\s)+", "", t)
    best = None
    for name, q in QUANTITIES.items():
        for pre in q.get("tex", []):
            if t.startswith(pre) and (best is None or len(pre) > best[1]):
                best = (name, len(pre))
    return QCOLOR[best[0]] if best else None


def ceq(*pieces, font_size=36, color_map=True, **kw):
    """MathTex(*pieces) with each piece that starts with a quantity's symbol (config/video.json "quantities") in its
    colour; the pieces are what derive() matches. Plain Text without LaTeX."""
    if not HAS_LATEX:
        return Text("".join(pieces), font_size=int(font_size * 0.75), **kw)
    m = MathTex(*pieces, font_size=font_size, **kw)
    if color_map:
        for sub, tex in zip(m.submobjects, pieces):
            c = _piece_color(tex)
            if c is not None:
                sub.set_color(c)
    return m


def derive(scene, src, dst, key_map=None, run_time=1.6, highlight=None, beat_s=0.8, from_copy=False):
    """One derivation step: shared pieces glide, pieces paired by key_map={"old": "new"} morph, the rest fade, then
    the new pieces (or those indexed in `highlight`) are indicated. from_copy=True keeps src. Returns dst."""
    key_map = key_map or {}
    sp, dp = list(src.submobjects), list(dst.submobjects)

    def tex(m):
        return getattr(m, "tex_string", None)
    used, pairs, new = set(), [], []
    for d in dp:
        i = next((i for i, x in enumerate(sp) if i not in used and tex(x) == tex(d)), None)
        if i is not None:
            used.add(i)
            pairs.append(([sp[i]], d))
        else:
            new.append(d)
    unmatched = []
    for d in new:
        ss = [i for i, x in enumerate(sp) if i not in used and key_map.get(tex(x)) == tex(d)]
        used.update(ss)
        if ss:
            pairs.append(([sp[i] for i in ss], d))
        else:
            unmatched.append(d)
    if hasattr(scene, "read") and not from_copy:
        scene.read(src)
    gone = [sp[i].copy() for i in range(len(sp)) if i not in used]
    anims = [ReplacementTransform(VGroup(*[x.copy() for x in ss]), d) for ss, d in pairs]
    anims += [FadeOut(x) for x in gone] + [FadeIn(d) for d in unmatched]
    if not from_copy:
        scene.remove(src, *sp)                    # its pieces may sit in the scene one by one (TransformFromCopy)
    scene.play(*anims, run_time=run_time)
    scene.remove(*dp, *gone)
    scene.add(dst)
    if highlight is None:
        old = {tex(x) for x in sp}
        targets = [x for x in dp if tex(x) not in old]
    else:
        targets = [dp[i] for i in highlight]
    if targets and beat_s > 0:
        scene.play(*[Indicate(x, color=x.get_color(), scale_factor=1.12) for x in targets], run_time=beat_s)
    return dst


def until(tracker, mark, minimum=0.6):
    """Seconds from now to a bookmark (at least `minimum`): the run_time that keeps moving up to the word."""
    try:
        return max(float(tracker.time_until_bookmark(mark)), minimum)
    except Exception:                              # no such bookmark, or a service without word timings
        return minimum


def pulse(scene, mob, seconds, period=1.6, scale=1.08, color=None, max_cycles=2):
    """At most `max_cycles` Indicate cycles of about `period` on the object being named, then a hold to `seconds`."""
    n = max(1, min(int(round(seconds / period)), max_cycles))
    each = min(period, seconds / n)
    for _ in range(n):
        scene.play(Indicate(mob, color=color or mob.get_color(), scale_factor=scale), run_time=each)
    if seconds - n * each > 0.05:
        scene.wait(seconds - n * each)


def carry_over(scene, *keep, run_time=0.6):
    """End a scene by fading out everything but `keep`, which the next scene adds again (carry_in) at frame 0."""
    keep_ids = {id(x) for k in keep for x in k.get_family()}
    gone = [m for m in scene.mobjects if id(m) not in keep_ids]
    for m in gone:
        for x in m.get_family():
            x.clear_updaters()
    if gone:
        scene.play(*[FadeOut(m) for m in gone], run_time=run_time)
    return list(keep)


class Hold(Wait):
    """A planned hold of the picture: a Wait that the layout log names "Hold", so the checks do not call it frozen."""

    def __init__(self, run_time=1.0, **kwargs):
        super().__init__(run_time=run_time, **kwargs)


def beat(scene, seconds=2.0, *mobs, push=1.0):
    """A pause of `seconds` without words after a reveal: a Hold, or with `push` > 1 a slow push-in on the first mob."""
    if mobs and push and push != 1.0:
        scene.play(mobs[0].animate.scale(push), rate_func=there_and_back, run_time=seconds)
    elif seconds > 0:
        scene.play(Hold(seconds))


class BudgetBars(VGroup):
    """budget_bars()'s result: before and after stacks, the dashed guide, and level(v), the y of value v."""

    def level(self, v):
        return self.base_y + v * self.scale


def budget_bars(before, after, x_before, x_after, base_y=-1.9, scale=1.0, width=0.6, opacity=0.85, guide=True):
    """The budget picture of an inequality: stacks of (value, colour) blocks, bottom first, before and after a step,
    on one scale."""
    def stack(items, x):
        g, y = VGroup(), base_y
        for v, c in items:
            h = max(v * scale, 0.002)
            g.add(Rectangle(width=width, height=h, stroke_width=2, stroke_color=c, fill_color=c,
                            fill_opacity=opacity).move_to([x, y + h / 2, 0]))
            y += h
        return g
    b, a = stack(before, x_before), stack(after, x_after)
    parts = [b, a]
    line = None
    if guide and before:
        top = base_y + sum(v for v, _ in before) * scale
        x0, x1 = sorted([x_before, x_after])
        line = DashedLine([x0 - width / 2, top, 0], [x1 + width / 2, top, 0], color=MUTED, stroke_width=2,
                          dash_length=0.1)
        parts.append(line)
    g = BudgetBars(*parts)
    g.before, g.after, g.guide, g.base_y, g.scale = b, a, line, base_y, scale
    return g


import reading_model as _RM  # noqa: E402
from manim_voiceover import VoiceoverScene  # noqa: E402
from manim_voiceover.helper import remove_bookmarks as _remove_bookmarks  # noqa: E402

READING = _RM.load(os.path.dirname(os.path.abspath(__file__)))
_TEXTS = (Text, MarkupText, Paragraph, SingleStringMathTex, DecimalNumber)


def text_items(mob):
    """The outermost Text, MathTex and number mobjects inside `mob` (or `mob` itself)."""
    if isinstance(mob, _TEXTS):
        return [mob]
    return [x for sm in mob.submobjects for x in text_items(sm)]


def _kind_content(m):
    if isinstance(m, DecimalNumber):
        return "math", str(m.number)
    if isinstance(m, SingleStringMathTex):
        return "math", m.tex_string
    return "text", getattr(m, "original_text", None) or getattr(m, "text", "")


def reading_time(mob, narrated=True):
    """Seconds `mob` (a text, an equation or a group of them) must stay visible to be read once."""
    return max((_RM.required_seconds(*_kind_content(m), narrated, READING) for m in text_items(mob)), default=0.0)


def _leaving(anims):
    """Mobjects whose current text an animation removes or replaces."""
    out = []
    for a in anims:
        if isinstance(a, AnimationGroup):
            out += _leaving(a.animations)
        elif isinstance(a, Animation) and (getattr(a, "remover", False) or isinstance(
                a, (Transform, FadeTransform, TransformMatchingShapes, TransformMatchingTex))):
            out.append(a.mobject)
    return out


class RAScene(VoiceoverScene):
    """The base scene: narration (manim-voiceover) and reading holds. Before a text or equation is removed or
    replaced, the scene waits until it has been on screen for its reading_time(); live readouts are exempt."""

    def setup(self):
        super().setup()
        self._shown, self._in_play = {}, False
        import inspect
        here = os.path.dirname(os.path.abspath(inspect.getfile(type(self))))
        self.set_speech_service(speech_service(here))
        self._block_end_s = float((channel_config(here).get("voice") or {}).get("block_end_pause_s", 0.75) or 0.0)

    def _add_voiceover_text(self, text, service_kwargs, subcaption=None, max_subcaption_len=70, subcaption_buff=0.1):
        """The caption is the spoken text, without the pacing markup."""
        if subcaption is None:
            subcaption = strip_markup(_remove_bookmarks(text))
        return super()._add_voiceover_text(text, service_kwargs, subcaption, max_subcaption_len, subcaption_buff)

    def wait_for_voiceover(self):
        """After a block, hold the picture (never the audio) for its final [pause S], else voice.block_end_pause_s."""
        super().wait_for_voiceover()
        tr = getattr(self, "current_tracker", None)
        if tr is None or getattr(tr, "_ra_held", False):
            return
        tr._ra_held = True
        hold = block_end_pause(tr.data.get("input_text", ""), self._block_end_s)
        if hold >= 1 / config["frame_rate"]:
            self.play(Hold(hold))

    def _now(self):
        return float(self.renderer.time)

    def _narrating(self):
        tr = getattr(self, "current_tracker", None)
        return tr is not None and tr.start_t <= self._now() < tr.end_t

    def _stamp(self):
        t = self._now()
        for top in self.mobjects:
            for m in text_items(top):
                if id(m) not in self._shown and not m.get_updaters():
                    self._shown[id(m)] = (m, t)

    def _due(self, mobs):
        t, wait = self._now(), 0.0
        for mob in mobs:
            for m in text_items(mob):
                rec = self._shown.get(id(m))
                if rec is not None and not m.get_updaters():
                    need = _RM.required_seconds(*_kind_content(m), self._narrating(), READING)
                    wait = max(wait, need - (t - rec[1]))
        return wait

    def read(self, *mobs):
        """Wait until every text in `mobs` (default: everything on screen) has been visible for its reading time."""
        wait = self._due(mobs or self.mobjects)
        if wait > 0.05:
            self.wait(wait)

    def add(self, *mobs):
        if not self._in_play:
            for m in mobs:
                if m.get_updaters():
                    m.update(0)       # place live readouts before they are first shown (and logged by the probe)
        super().add(*mobs)
        if not self._in_play:
            self._stamp()
        return self

    def carry_in(self, *mobs):
        """Add the objects carried over from the previous scene (carry_over()); their texts count as read."""
        self.add(*mobs)
        for m in mobs:
            for x in text_items(m):
                if id(x) in self._shown:
                    self._shown[id(x)] = (x, -1e9)
        return self

    def remove(self, *mobs):
        if not self._in_play:
            self.read(*mobs)
            for m in [x for mob in mobs for x in text_items(mob)]:
                self._shown.pop(id(m), None)
        return super().remove(*mobs)

    def play(self, *anims, **kwargs):
        leaving = _leaving(anims)
        if leaving and not self._in_play:
            self.read(*leaving)
        self._in_play = True
        try:
            super().play(*anims, **kwargs)
        finally:
            self._in_play = False
        for m in [x for mob in leaving for x in text_items(mob)]:
            self._shown.pop(id(m), None)              # gone, or now showing new content: its clock restarts
        self._stamp()
