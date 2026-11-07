"""The body's one world (no scene class: render_video.sh skips this file): the state plane with the controller's dot
and the end region Omega on the left, the remaining-action meter on the right (where the hook put it), and the
budget bars between them. Every body scene starts from the layout the previous one ended in (common.py carry_over()),
so these builders are shared.

The plane is schematic in direction: a point after k steps at size q sits at angle HOOK_ANGLE0 + BODY_TURN * k on an
ellipse of half-axes q * BODY_AXES around BODY_C (the hook's geometry, scaled down). In the schematic chapters the
bars' heights are schematic too (PLAN_COSTS ...) and no number is shown with them: the meter shows its label alone.

v4 (final-cut review of v3, FC-1): from the end of s04 on, the picture is the slice through the rest point, one
coordinate q on an axis with the bills drawn above it as bowls, to the meter's scale (see "the slice" below). The
worked example (s06) and the window comparison (s07) are drawn only there, with their logged numbers.
"""
import numpy as np
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_draw import DOT_R, HOOK_ANGLE0, HOOK_TURN, METER_AT, METER_VMAX, ep_meter

BODY_C = np.array([-2.3, -0.3, 0.0])     # v4: the plane centred in the frame (v3 sat in its top 60 %: FC-9)
BODY_AXES = (3.7, 2.05)
OMEGA_Q = 0.3                     # the drawn end region: the level q = OMEGA_Q (schematic)
BASE_Y = ep_meter(lambda: 0.0, show_value=False).frame.get_bottom()[1]   # every bar stands
# on the meter's bottom (the meter is centred with its readout, as the hook placed it)
SCALE = 4.0 / METER_VMAX          # units of height per unit of value (the meter's own scale)
X_AFTER = 3.2                     # the "after" stack of the budget bars, left of the meter
X_LABEL = 2.35                    # labels of the blocks, left of the after stack
EQ_Y = -2.85                      # the equation band under the world

# A schematic plan of four steps from q = 1 into Omega, and its bill (heights only; no number is shown with them)
PLAN_Q = [1.0, 0.74, 0.55, 0.41, 0.28]
PLAN_COSTS = [0.14, 0.09, 0.06, 0.04]          # the step costs, amber
PLAN_W = 0.15                                  # the end cost where the plan ends, green
BILL = sum(PLAN_COSTS) + PLAN_W                # the remaining action at the start (the meter's level)
REF_COST, REF_W = 0.045, 0.06                  # the reference step at the plan's end: cost, end cost after it
                                               # (v7, final-cut round 5: a visible saving, 0.045 against 0.09)
BEST_NEXT = 0.27                               # the best bill from the next point (at most the shifted plan's 0.295)
REF_FRAC = 0.2                                 # the reference step runs from the plan's end to this fraction of the
                                               # way to the target (v7, round 5: long enough to read as a step)


BODY_TURN = -50.0                 # degrees per step in the body's plane (the hook turns by HOOK_TURN): a plan of four
#                                   steps sweeps around the region and fills the picture


def body_point(q, k):
    a = np.radians(HOOK_ANGLE0 + BODY_TURN * k)
    return BODY_C + np.array([q * BODY_AXES[0] * np.cos(a), q * BODY_AXES[1] * np.sin(a), 0.0])


def omega(fill=0.14, q=OMEGA_Q):
    """The end region: the level set q = OMEGA_Q, softly filled, with the rest point."""
    e = Ellipse(width=2 * q * BODY_AXES[0], height=2 * q * BODY_AXES[1], color=qcolor("W"), stroke_width=5,
                fill_color=qcolor("W"), fill_opacity=fill).move_to(BODY_C)
    return VGroup(e, Dot(BODY_C, radius=0.07, color=INK))


def omega_label(om):
    return attach(MathTex(r"\Omega", font_size=40, color=qcolor("W")), om[0], direction=DOWN, buff=0.15)


def the_dot(p):
    return Dot(p, radius=DOT_R, color=INK)


def plan_path(qs, k0=0, color=INK, width=5, dashed=False, opacity=1.0):
    """The segments of a plan through sizes qs, starting at step index k0, with a small dot at each point."""
    pts = [body_point(q, k0 + i) for i, q in enumerate(qs)]
    segs = VGroup()
    for a, b in zip(pts[:-1], pts[1:]):
        ln = DashedLine(a, b, dash_length=0.12) if dashed else Line(a, b)
        segs.add(ln.set_stroke(color, width=width, opacity=opacity))
    dots = VGroup(*[Dot(p, radius=0.08, color=color).set_opacity(opacity) for p in pts[1:]])
    return VGroup(segs, dots)


def make_meter(value, show_value=False):
    """The meter where the hook left it; in the body its level is schematic (label only) unless show_value."""
    return ep_meter(value, show_value=show_value)


def block(v, color, x=X_AFTER, bottom=BASE_Y, width=0.7, opacity=0.85):
    h = max(v * SCALE, 0.002)
    return Rectangle(width=width, height=h, stroke_width=2, stroke_color=color, fill_color=color,
                     fill_opacity=opacity).move_to([x, bottom + h / 2, 0])


def stack(values_colors, x=X_AFTER, bottom=BASE_Y, width=0.7, opacity=0.85):
    g, y = VGroup(), bottom
    for v, c in values_colors:
        b = block(v, c, x=x, bottom=y, width=width, opacity=opacity)
        g.add(b)
        y += v * SCALE
    return g


def level(v):
    return BASE_Y + v * SCALE


def world_start():
    """The layout every body scene can start from: Omega, the dot at the plan's start, the meter (label only)."""
    om = omega()
    return om, the_dot(body_point(PLAN_Q[0], 0))


DESC_PIN = np.array([0.9, 3.15, 0.0])           # the descent inequality, pinned at the top after s04
TEST_PIN = np.array([-4.9, 3.15, 0.0])          # the one-step test, pinned at the top after s05


def descent_line(font_size=44):
    return ceq(r"V_N(q^+)", r"-", r"V_N(q)", r"\ \le\ ", r"-", r"L_d(q,q^+)", font_size=font_size)


def pinned_descent():
    """The boxed descent inequality as s04 leaves it: scaled to 0.75 and pinned at DESC_PIN."""
    d = descent_line()
    box = SurroundingRectangle(d, color=INK, buff=0.22, corner_radius=0.1)
    return d.scale(0.75).move_to(DESC_PIN), box.scale(0.75).move_to(DESC_PIN)


def test_line(font_size=54):
    """V_1 <= V_0. v7 (FC-1): V_0, the bill with no steps left, is the end cost inside the region (infinite outside),
    so it takes the end cost's colour, as its curve and walls do in OneStepTest; V_1 keeps the bill's."""
    t = ceq(r"V_1", r"\ \le\ ", r"V_0", font_size=font_size)
    t[2].set_color(qcolor("W"))
    return t


def pinned_test():
    """The boxed one-step test as s05 leaves it, pinned at TEST_PIN (scaled to 0.6)."""
    t = test_line()
    box = SurroundingRectangle(t, color=INK, buff=0.3, corner_radius=0.1)
    return t.scale(0.6).move_to(TEST_PIN), box.scale(0.6).move_to(TEST_PIN)


# --------------------------------------------------------------------------- the slice: one coordinate (v4, FC-1)
# From the end of s04 on, the picture is the slice through the rest point: the state q on a horizontal axis (the
# rest point in the middle, the end region Omega an interval of it), and above each q its bill, drawn to the meter's
# own scale (the axis is the meter's floor, BASE_Y, and one unit of value is SCALE high), so the dot on a bowl sits
# exactly at the height the meter shows. A view (x0, y0, xs, vs) maps (q, value) to the frame; s05 zooms by using a
# view twice as large (ZOOM). The schematic bowl of s04/s05 is V = V_SCHEM q^2 (no number is shown with it); the end
# cost is the example's W = 1.2 * 1/2 q^2 = 0.6 q^2 throughout; s06 draws the example's V_1 with its logged numbers.
X0 = -1.2                 # the rest point's x
XS = 4.0                  # frame units per unit of q
Q_DRAW = 1.05             # the slice is drawn for |q| <= Q_DRAW
V_TOP = 0.62              # bowls are cut at this value (the meter is full at 0.6)
V_SCHEM = 0.45            # the schematic bill of s04/s05, V = V_SCHEM q^2, under the end cost inside the region
W_K = 0.6                 # the end cost, W = W_K q^2 (the example's 1.2 * 1/2)
OMEGA_B = 0.55            # the schematic end region of s04/s05: |q| <= OMEGA_B
VIEW = (X0, BASE_Y, XS, SCALE)
ZOOM = 2.0
VIEW_Z = (X0, BASE_Y, XS * ZOOM, SCALE * ZOOM)
REST = np.array([X0, BASE_Y, 0.0])


def at(q, val=0.0, view=VIEW):
    x0, y0, xs, vs = view
    return np.array([x0 + xs * q, y0 + vs * val, 0.0])


def q_axis(view=VIEW, q_lim=Q_DRAW + 0.12):
    """The state axis of the slice, with the rest point; label q at its right end (s06 adds ticks)."""
    ax = Line(at(-q_lim, 0, view), at(q_lim, 0, view), color=MUTED, stroke_width=4)
    rest = Dot(at(0, 0, view), radius=0.08, color=INK)
    return VGroup(ax, rest)


def axis_label(axis):
    return attach(MathTex("q", font_size=40, color=INK), axis[0], direction=RIGHT, buff=0.2)


def bowl(k, color, view=VIEW, q0=-Q_DRAW, q1=Q_DRAW, top=V_TOP, width=6, x_max=3.5, x_min=-6.2):
    """The graph of k q^2 over [q0, q1], cut where it leaves the picture (value above top, x beyond the limits)."""
    x0, y0, xs, vs = view
    qmax = min(np.sqrt(top / k), (x_max - x0) / xs, q1)
    qmin = max(-np.sqrt(top / k), (x_min - x0) / xs, q0)
    qs = np.linspace(qmin, qmax, 121)
    c = VMobject().set_points_smoothly([at(q, k * q * q, view) for q in qs])
    return c.set_stroke(color, width=width)


def omega_interval(b=OMEGA_B, view=VIEW):
    """The end region on the slice: the interval |q| <= b, a thick green bar on the axis with an edge mark at each
    end (the region is bounded: it has an edge)."""
    bar = Line(at(-b, 0, view), at(b, 0, view), color=qcolor("W"), stroke_width=14)
    edges = VGroup(*[Line(at(s * b, 0, view) + DOWN * 0.22, at(s * b, 0, view) + UP * 0.22, color=qcolor("W"),
                          stroke_width=6) for s in (-1, 1)])
    return VGroup(bar, edges)


def omega_tag(iv):
    return attach(MathTex(r"\Omega", font_size=40, color=qcolor("W")), iv[0], direction=DOWN, buff=0.3)


def end_bowl(b=OMEGA_B, view=VIEW, width=6):
    """The end cost over the region: W = W_K q^2 on |q| <= b."""
    return bowl(W_K, qcolor("W"), view, -b, b, width=width)


def vseg(q, v_lo, v_hi, color, view=VIEW, dx=0.0, width=8):
    """A vertical segment above q from value v_lo to v_hi (a drop or a cost drawn to scale), shifted by dx."""
    return Line(at(q, v_lo, view) + RIGHT * dx, at(q, v_hi, view) + RIGHT * dx, color=color, stroke_width=width)


def vbar(q, v_lo, v_hi, color, view=VIEW, dx=0.0, width=0.28):
    """A thin filled bar above q from value v_lo to v_hi (a fall or a cost drawn to scale, like the budget bars)."""
    lo, hi = at(q, v_lo, view) + RIGHT * dx, at(q, v_hi, view) + RIGHT * dx
    h = max(hi[1] - lo[1], 0.01)
    return Rectangle(width=width, height=h, stroke_width=2, stroke_color=color, fill_color=color,
                     fill_opacity=0.85).move_to((lo + hi) / 2)


def level_guide(q_from, q_to, val, view=VIEW):
    """A dashed horizontal line at height val between q_from and q_to (where a bill was, carried over to a new q)."""
    return DashedLine(at(q_from, val, view), at(q_to, val, view), dash_length=0.1, color=MUTED, stroke_width=3)


def meter_guide(p, m, color=None):
    """A dashed line from a point of a bowl to the meter: the same height, the same number. color: the quantity the
    meter shows (default V, blue; v6, VD-12: green for the ghost meter of the end cost)."""
    if p[1] < BASE_Y + 0.35:                       # near the floor the guide would run along the axis: none
        return VMobject().set_stroke(width=0, opacity=0)   # v5: invisible (an empty path at the origin read as a line)
    return DashedLine(p, [m.frame.get_left()[0] - 0.08, p[1], 0], dash_length=0.1, color=color or qcolor("V"),
                      stroke_width=3, stroke_opacity=0.7)


S04_QS = [-0.816, -0.588, -0.423, -0.305, -0.219, -0.158, -0.114]   # the dot's slide down the schematic bowl (s04)


# the outro's compact world: everything left of the end-screen area (x < END_SCREEN_X)
OUTRO_C, OUTRO_AXES = np.array([-3.4, 1.0, 0.0]), (2.0, 1.1)
OUTRO_METER = np.array([0.1, 0.1, 0.0])


def outro_point(q, k):
    a = np.radians(HOOK_ANGLE0 + HOOK_TURN * k)
    return OUTRO_C + np.array([q * OUTRO_AXES[0] * np.cos(a), q * OUTRO_AXES[1] * np.sin(a), 0.0])


def outro_omega():
    e = Ellipse(width=2 * OMEGA_Q * OUTRO_AXES[0], height=2 * OMEGA_Q * OUTRO_AXES[1], color=qcolor("W"),
                stroke_width=5, fill_color=qcolor("W"), fill_opacity=0.28).move_to(OUTRO_C)
    return VGroup(e, Dot(OUTRO_C, radius=0.07, color=INK))
