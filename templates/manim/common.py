"""Shared palette, helpers and the RAScene base class for every scene of a run.

Copy into runs/<run>/video/scenes/ with voice.py and reading_model.py. Colours have fixed meanings across the
Remaining Action series (config/video.json "palette"; state them in the run's video/README.md); the four semantic
colours stay distinguishable under protanopia, deuteranopia and tritanopia (tools/video/check_design.py checks it),
and outcomes are labelled in text too. Scenes derive from RAScene: narration (manim-voiceover) plus automatic reading
holds, so no text or equation leaves the screen before it can be read (templates/manim/reading_model.py).

House rule: the video is self-contained. Nothing on screen or in the narration names the explainer, code, files, data,
links or the description; no equation carries a label or tag ((13), (2), (★), "Eq. 3"; config/video.json
equation_numbers); to use an equation again, show it again or pin() it in a corner. tools/video/check_selfcontained.py
checks every render, the narration, the captions and the chapters. Numbers go through fmt() (config/video.json
"numbers", tools/video/check_numbers.py). A video opens with its hook: a full, moving picture from the first frame
(self.add() it before the first play()), a beat of motion and music, the first words by 3 s, the question by 15 s, no
channel card; then a short title beat (title_beat(), the "Episode n of N" lower third, at most about 6 s) and the
body by 45 s. It ends with outro() (takeaway_card() and the channel name; the right of the frame empty for end
screens); a series episode adds recap scenes with recap_tag() and recap_card() (tools/video/check_series.py). meter()
is the channel's signature object: the remaining action as a bar that drains, with a live readout. Choreography
(tools/video/check_engagement.py): keep the picture moving while the narration talks; derive equations with
derive() (TransformMatchingTex plus a highlight beat) on ceq() pieces coloured by quantity (config/video.json
"quantities"); end scenes with carry_over() instead of a fade to an empty frame; plan beat()s after the reveals;
show every inequality with the same budget_bars(). No persistent slide titles: the chapter list names the chapter.
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


def _palette(start):
    """The "palette" section of config/video.json ({} when absent)."""
    return _video_config(start).get("palette", {})


HERE = os.path.dirname(os.path.abspath(__file__))
_VIDEO = _video_config(HERE)
BG = _VIDEO.get("palette", {}).get("background", "#0f172a")   # config/video.json
INK = "#e2e8f0"         # main text
MUTED = "#94a3b8"       # axes, secondary text, captions
GRID = "#334155"        # grid lines, level sets
GREEN = "#2dd4bf"       # holds / stable / verified (teal-green: tells apart from RED for deuteranopes)
AMBER = "#fbbf24"       # contrast case / unstable / second option
BLUE = "#818cf8"        # reference case / first option (indigo: tells apart from GREEN for tritanopes)
RED = "#ef4444"         # failure / violation (always with a text label)
SAFE_X, SAFE_Y = 6.4, 3.6   # graphics-safe area (EBU R 95: 5 % margins), in Manim units from the centre

config.background_color = BG
from reading_model import MINUS, NUMBERS, fmt  # noqa: E402,F401  (number format house rule, pure Python)
Tex.set_default(color=INK)
MathTex.set_default(color=INK)
Text.set_default(color=INK, font="DejaVu Sans")


def _check_font(name="DejaVu Sans"):
    """Pango silently substitutes a missing font, which changes text widths and so the design checks: say so once."""
    try:
        import manimpango
        if name not in manimpango.list_fonts():
            print(f"warning: font '{name}' not found; Pango uses another font, so text widths and the layout checks "
                  "change (Linux: apt install fonts-dejavu-core; macOS: brew install --cask font-dejavu)",
                  file=sys.stderr)
    except Exception:                       # no ManimPango (a tool that only imports the palette): nothing to check
        pass


_check_font()

# MathTex needs LaTeX and dvisvgm. Without them, scenes fall back to Pango Text (set NO_LATEX=1 to force it).
HAS_LATEX = os.environ.get("NO_LATEX") != "1" and bool(shutil.which("latex")) and bool(shutil.which("dvisvgm"))


def eq(tex, plain=None, font_size=36, **kw):
    """A static equation: MathTex when LaTeX is available, else Text with the plain-text version."""
    if HAS_LATEX:
        return MathTex(tex, font_size=font_size, **kw)
    return Text(plain or tex, font_size=int(font_size * 0.75), **kw)


def caption(text, size=24):
    """Bottom caption inside the graphics-safe area. Font size >= 24 stays legible at 1080p."""
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
    """A smaller copy of an equation shown earlier, placed in a corner of the graphics-safe area: keep it in view while
    the narration uses it again, instead of asking the viewer to recall it (no equation labels or callbacks by number).
    The default scale keeps a 36-40 pt equation at 27-30 pt, above the 24 pt minimum."""
    c = mob.copy().scale(scale)
    x = SAFE_X - c.width / 2 if corner[0] > 0 else -SAFE_X + c.width / 2
    y = SAFE_Y - c.height / 2 if corner[1] > 0 else -SAFE_Y + c.height / 2
    return c.move_to([x, y, 0])


def swap_caption(scene, old, text, run_time=0.5):
    """Swap to a new caption: the old one fades out, then the new one in (Transform between different strings morphs
    glyphs illegibly; two texts faded on one spot at once overlap)."""
    new = caption(text)
    scene.play(Succession(FadeOut(old, shift=UP * 0.1, run_time=run_time / 2),
                          FadeIn(new, shift=UP * 0.1, run_time=run_time / 2)), run_time=run_time)
    return new


SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def sci_u(x, digits=1):
    """Unicode scientific notation for Pango Text, e.g. -2.7x10^-11 written with a real minus and superscripts."""
    m, e = f"{x:.{digits}e}".split("e")
    return f"{m.replace('-', chr(0x2212))}×10{str(int(e)).translate(SUP)}"


def always_redraw(func):
    """manim's always_redraw, keeping the text the mobject shows now (become() copies only the shape), so the layout
    probe logs what the viewer sees: live readouts are checked for format and width over time."""
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
    """A live number that changes every frame, in Pango Text (never a MathTex inside an updater: LaTeX would typeset
    every frame). readout("∫ L dt", lambda: paid, decimals=2) shows "∫ L dt = 1.04": the value goes through fmt() with
    fixed decimals (default numbers.readout_decimals), so the width stays steady and every readout of one quantity has
    the same precision; sign=True shows +0.14 and −1.50 (never −0.00). readout(lambda: "...") with a function returning
    the whole string still works: build its numbers with fmt(..., decimals=k). Position it with an updater after this
    one (m.move_to(...)), as before. zero_exact=True (the meter's readout, v5): an exact zero reads "0", never
    "0.000" (episode 1 v4, FC-11: an empty bar labelled "left to pay = 0.000")."""
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
    """Mark a label as belonging next to an object (a curve's name at its end, a dot's tag, a line's value): the
    text-stroke proximity rule of check_design.py does not count that object's strokes against the label (any stroke
    when target is True); the crossing rule still applies. With a target and a direction, also place the label next to
    it. Returns the label. Use it only for labels that point at their object; a label merely near a curve is a defect."""
    if direction is not None and target is not True:
        label.next_to(target, direction, buff=buff)
    label.ra_attached_to = target
    return label


class LegendTable(VGroup):
    """legend_table()'s result: a VGroup of rows (VGroups of cells) plus an invisible anchor. cells[i][j] is a cell,
    column(j) the cells of a column, place(mob, i, j) puts another mobject (a swapped label) in cell (i, j) with the
    column's alignment, wherever the table has moved."""

    def column(self, j):
        return VGroup(*[r[j] for r in self.cells if r[j] is not None])

    def place(self, mob, i, j):
        ox, oy = self._anchor.get_center()[:2]
        x0, w, a = ox + self._col_x[j], self._widths[j], self._aligns[j]
        x = x0 + mob.width / 2 if a == "l" else x0 + w - mob.width / 2 if a == "r" else x0 + w / 2
        return mob.move_to([x, oy + self._row_y[i], 0])


def legend_table(rows, aligns=None, col_gap=0.3, row_gap=0.22, min_widths=None):
    """Legends and blocks of readouts in fixed columns, aligned by construction (check_design.py warns about columns
    that are almost aligned). rows: lists of cells, each a Mobject (a Dot, a MathTex, a Text) or None; aligns: one
    letter per column, "l", "c" or "r" (default: "c" for a column of dots, "l" otherwise); col_gap: the space between
    columns; row_gap: the space between rows, at one pitch for the whole table; min_widths: {column: width} to reserve
    room for labels swapped in later with place(). The cells are moved, not copied; animate them through the rows or
    columns (FadeIn(VGroup(*[r[:3] for r in t.cells])), FadeIn(t.column(3))). Position the table like any VGroup."""
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
    """Load the npz exported by the run's code/ scripts. $SCENE_DATA overrides the path.
    Returns None when the file does not exist, so a scene can fall back to clearly labelled demo data."""
    path = os.environ.get("SCENE_DATA", os.path.join(here, "..", "data", default_name))
    return dict(np.load(path)) if os.path.exists(path) else None


# Narration and branding (voice.py sits next to this file)
from voice import block_end_pause, channel_config, speech_service, strip_markup  # noqa: E402,F401

CHANNEL = channel_config(os.path.dirname(os.path.abspath(__file__))).get("channel_name", "Remaining Action")


# Series beats and the outro (house rules: hook first, no channel card, a spoken series context over the builds-on
# frame, recaps of everything used, an outro with the takeaway card and the teaser; tools/video/check_series.py)
END_SCREEN_X = 1.4      # the outro keeps x > END_SCREEN_X (the right ~40 % of the frame) empty for end-screen elements


def series_context():
    """video/series_context.json of a series episode (written by tools/series.py start), or None (a news video)."""
    p = Path(HERE).parent / "series_context.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def takeaway_card(episode=None, tex=None, font_size=40, color=None):
    """An episode's takeaway card: its equations stacked in a rounded frame (the first one in `color` when given;
    by default all in ink: colours belong to quantities, config/video.json "quantities", so do not paint a result
    in a quantity's colour; mark the result with a shape, e.g. a box, if it needs emphasis). The same
    builder makes an episode's own card (outro) and the recap card of a later episode, from the same data
    (series_context.json "takeaways", or the recap's "card"), so the two match. episode: a key such as 2 or
    "mpc-mechanics:2" (default: this episode); tex: the equations themselves (news videos)."""
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
    """The card of the index-th recap of this episode (series_context.json "recaps": the recap's own card, or the
    takeaway equations of the episode it restates)."""
    rc = (series_context() or {}).get("recaps", [])[index]
    return takeaway_card(tex=rc["card"], font_size=font_size)


def recap_tag():
    """The small "Recap" tag in the upper-left corner, shown for the whole recap scene (viewers who know the episode
    it restates may skip; the recap also has its own chapter)."""
    t = Text("Recap", font_size=26, color=MUTED)
    bar = Line(ORIGIN, RIGHT * (t.width + 0.3), color=MUTED, stroke_width=2).next_to(t, DOWN, buff=0.1, aligned_edge=LEFT)
    g = VGroup(t, bar)
    return g.move_to([-SAFE_X + g.width / 2, SAFE_Y - g.height / 2, 0])


def builds_on(ctx=None):
    """The 4-6 s builds-on frame under the spoken series context: "Episode n of N", the series title, and the short
    titles of the episodes this one builds on (its must prerequisites). No map."""
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
    """The video's title from video/plan.json (the title beat shows it), or None."""
    p = Path(HERE).parent / "plan.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("title")
    except (OSError, ValueError):
        return None


def title_beat(title=None, ctx=None, size=40):
    """The short title beat right after the hook (about 4-6 s, over the picture the hook built, which stays): the
    video's title at the top of the safe area and a lower third with "Episode n of N", the series title and, when the
    episode builds on others, their short titles. Returns VGroup(head, lower); fade the hook's question out and head
    in, then FadeIn(lower). For a news video (no series context) the lower third is empty. Say the series sentence
    ("This is episode three of five ...") over it; there is no channel card and no separate series frame."""
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
    """meter()'s result: the frame, the live fill and the live readout. level(v) is the y of the fill's top at value v
    (to place a bracket or a cost segment beside the bar)."""

    def level(self, v):
        return self.frame.get_bottom()[1] + self.bar_height * max(0.0, min(v, self.vmax)) / self.vmax

    def _make_readout(self, show_value=True):
        label, value, decimals, font_size, buff = self._ro_args
        if show_value:
            ro = readout(label, value, decimals=decimals, font_size=font_size, zero_exact=True)
        else:                                   # a schematic picture: the meaning without a number
            ro = Text(label, font_size=font_size, color=INK)
        ro.next_to(self.frame, DOWN, buff=buff)
        ro.add_updater(lambda m: m.next_to(self.frame, DOWN, buff=buff))
        return ro

    def swap_readout(self, scene, show_value, run_time=0.5, *others):
        """Swap the readout (the old one fades out, then the new one fades in) between the live number (show_value=True: its value comes from code/ or a closed
        form) and the label alone (False: while the bar's level is schematic, no number is shown with it); `others`
        are animations played with the cross-fade."""
        new = self._make_readout(show_value)
        old = self.readout
        old.clear_updaters()
        self.remove(old)
        (scene.carry_in if hasattr(scene, "carry_in") else scene.add)(old)   # a live readout needs no reading hold
        # v4: the old text leaves before the new one arrives (a cross-fade on one spot reads "left toto pay": the
        # final-cut review of episode 1 v3, FC-6); `others` run over the whole run_time
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
    """The remaining-action meter, the channel's signature object (the series is named after it): a bar whose fill
    drains as the value falls, and under it a live readout("left to pay", value) through fmt(). value: a function
    (a ValueTracker's get_value) whose numbers come from code/ or a closed form, never typed by hand; vmax: the value
    of a full bar. Move the whole meter with move_to(); the fill and the readout follow its frame. Use it in the hook,
    the body where the argument is about what is left, the thumbnail frame and the outro. Marked ra_role="metaphor"
    for the checks, with ra_value() (the number the bar shows, readout or not) and ra_vmax, which layout_probe.py logs
    (v5): along the controller's path the bill only falls, so a refill (a new start, a shorter window, a scan of
    hypothetical points) is declared in plan.json (scenes[].metaphor_resets) and said in the narration, or shown
    on the bowl or a ghost meter instead. Call freeze() before fading it out."""
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
    m.ra_value, m.ra_vmax = (lambda: float(value())), vmax      # v5: logged by layout_probe.py, checked for refills
    return m


def outro(card, next_title=None):
    """The outro layout (15-20 s): the takeaway card and the channel name on the left, an optional "Next: ..." line,
    and the right of the frame (x > END_SCREEN_X) empty for YouTube's end-screen elements. Say the teaser ("In the
    next episode, ...") in the narration; the finale has none."""
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


# Choreography (the review against the 3Blue1Brown bar, 2026-11-04: transform, do not retype; colour bound to the
# quantity; carry objects across cuts; planned beats; one picture reused for every inequality)
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
    """An equation built from pieces (MathTex(*pieces)): every piece that starts with a quantity's symbol
    (config/video.json "quantities": V, L_d, W ...) takes that quantity's colour, everywhere in the video, so a
    quantity keeps one colour in pictures, bars and equations. Pieces are also the units TransformMatchingTex
    matches: write the pieces that stay the same in two lines identically, and derive() morphs only what changes.
    Without LaTeX, a plain Text fallback."""
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
    """One step of a derivation as a transform, in the manner of TransformMatchingTex: the pieces src and dst share
    (the same tex) glide to their new places, the pieces paired by key_map={"old piece": "new piece"} morph into
    each other (several old pieces may map to one new piece, and their glyph counts may differ), the rest fade out
    and in; then a highlight beat on what is new (or on the pieces given by index in `highlight`), so the eye lands
    where the change is. from_copy=True keeps src on screen. Position dst before calling. Returns dst."""
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
    """Seconds from now to a bookmark of the voiceover (at least `minimum`): give the animation before
    wait_until_bookmark() this run_time, so the picture keeps moving up to the word instead of waiting still."""
    try:
        return max(float(tracker.time_until_bookmark(mark)), minimum)
    except Exception:                              # no such bookmark, or a service without word timings
        return minimum


def pulse(scene, mob, seconds, period=1.6, scale=1.08, color=None, max_cycles=2):
    """Signal the object the narration is naming: at most `max_cycles` gentle Indicate cycles of about `period` each,
    then hold still for the rest of `seconds`. Emphasis is not motion: check_engagement.py counts narration over
    emphasis alone as a frozen picture (layout_probe.py logs every play), so do not pulse to fill time; animate what
    the narration says (move the dot, grow the bar, transform the equation) instead."""
    n = max(1, min(int(round(seconds / period)), max_cycles))
    each = min(period, seconds / n)
    for _ in range(n):
        scene.play(Indicate(mob, color=color or mob.get_color(), scale_factor=scale), run_time=each)
    if seconds - n * each > 0.05:
        scene.wait(seconds - n * each)


def carry_over(scene, *keep, run_time=0.6):
    """End a scene in the layout the next one starts from: fade out everything except `keep` (the dot, the region,
    the meter ...), which the next scene adds again at frame 0 with the same code. Replaces
    FadeOut(Group(*self.mobjects)), the fade to an empty frame (check_engagement.py warns about it)."""
    keep_ids = {id(x) for k in keep for x in k.get_family()}
    gone = [m for m in scene.mobjects if id(m) not in keep_ids]
    for m in gone:
        for x in m.get_family():
            x.clear_updaters()
    if gone:
        scene.play(*[FadeOut(m) for m in gone], run_time=run_time)
    return list(keep)


class Hold(Wait):
    """A planned hold of the picture (v7): a beat after a reveal, think time after a prompt, the pause after a
    narration block. It plays like Wait; layout_probe.py logs it as "Hold", so check_engagement.py exempts it from
    the frozen-picture warnings (a hold of up to 4 s, or 8 s with a restatement: rule P19) and
    check_pacing.py counts it as consolidation time."""

    def __init__(self, run_time=1.0, **kwargs):
        super().__init__(run_time=run_time, **kwargs)


def beat(scene, seconds=2.0, *mobs, push=1.0):
    """A planned pause right after a reveal: `seconds` without words, so the result can sink in. The music swells in
    it (give the scene "low" music: in a scene whose music is "off" a beat is digital silence, which
    check_engagement.py reports). With `push` > 1, the first of `mobs` grows slowly by that factor and settles back
    (a calm push-in, one smooth move); by default the picture holds still (a Hold): a beat needs no flashing. A pause
    longer than one Azure break (voice.azure.max_break_ms) is a beat between two narration blocks, never audio."""
    if mobs and push and push != 1.0:
        scene.play(mobs[0].animate.scale(push), rate_func=there_and_back, run_time=seconds)
    elif seconds > 0:
        scene.play(Hold(seconds))


class BudgetBars(VGroup):
    """budget_bars()'s result. before, after: VGroups of the stacked blocks (bottom first); guide: the dashed line at
    the top of the before stack, across to the after stack; level(v): the y of value v on the shared scale."""

    def level(self, v):
        return self.base_y + v * self.scale


def budget_bars(before, after, x_before, x_after, base_y=-1.9, scale=1.0, width=0.6, opacity=0.85, guide=True):
    """The budget picture of an inequality: a stack of blocks before a step against the stack after it, on one
    scale, so 'what is lost covers what is spent' is a comparison of heights. before, after: lists of (value,
    colour) pairs, bottom first (use qcolor() so each block has its quantity's colour); values from code/ or a
    closed form, or schematic heights when no number is shown. Reuse one picture for every inequality of an episode
    (the one-step test, the descent, the worked numbers)."""
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


# Reading holds (reading_model.py sits next to this file; constants in config/video.json "reading")
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
    """Remaining Action base scene: narration (manim-voiceover) plus automatic reading holds.

    Every text or equation is timed from the end of the animation that shows it. Before an animation removes or
    replaces it (FadeOut, Uncreate, Transform, ReplacementTransform, TransformMatchingTex, swap_caption, ...) or
    self.remove() takes it away, the scene waits until it has been on screen for reading_time(); while narration
    plays the time is longer. self.read(*mobjects) waits explicitly, for example before a cut. Live readouts (with
    updaters) are exempt. The speech service is set from config/channel.json; call set_speech_service to change it.
    """

    def setup(self):
        super().setup()
        self._shown, self._in_play = {}, False
        import inspect
        here = os.path.dirname(os.path.abspath(inspect.getfile(type(self))))
        self.set_speech_service(speech_service(here))
        self._block_end_s = float((channel_config(here).get("voice") or {}).get("block_end_pause_s", 0.75) or 0.0)

    def _add_voiceover_text(self, text, service_kwargs, subcaption=None, max_subcaption_len=70, subcaption_buff=0.1):
        """Captions never show the pacing markup ([pause S], [slow]): the subcaption is the spoken text."""
        if subcaption is None:
            subcaption = strip_markup(_remove_bookmarks(text))
        return super()._add_voiceover_text(text, service_kwargs, subcaption, max_subcaption_len, subcaption_buff)

    def wait_for_voiceover(self):
        """After a narration block, the picture holds for the block's pause (v7): its final "[pause S]", else
        voice.block_end_pause_s of config/channel.json; "[pause 0]" for none. A scene wait (a Hold), never audio: the
        voice drops a break at the end of its audio, and the narration is never padded."""
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
        """Add the objects carried over from the previous scene's last frame (carry_over() there): the first frame
        is the previous scene's last, and their texts count as already read, so nothing holds the picture still
        before the first animation."""
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
