"""Drawing helpers shared by the scenes of episode 1 (no scene class: render_video.sh skips this file).

The state-plane pictures are schematic (no computed numbers are shown with them): a path that contracts towards the
rest point by a fixed similarity per step, the way an optimal path of a quadratic problem does.
"""
import numpy as np
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


def spiral(start, centre, n, scale=0.62, turn=-18.0):
    """n+1 points: start, then each one the previous one scaled by `scale` and turned by `turn` degrees about centre."""
    c = np.array(centre, dtype=float)
    a = np.radians(turn)
    rot = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    pts = [np.array(start, dtype=float)]
    for _ in range(n):
        pts.append(c + scale * rot @ (pts[-1] - c))
    return pts


def region(centre, radius=0.85, color=GREEN):
    """The terminal region: a disc with a soft fill and the rest point in its middle."""
    disc = Circle(radius=radius, color=color, stroke_width=3, fill_color=color, fill_opacity=0.12).move_to(centre)
    rest = Dot(centre, radius=0.06, color=INK)
    return VGroup(disc, rest)


def path_mob(pts, color=BLUE, width=3, dashed=True, dot_radius=0.06):
    """Segments joining the points, with a small dot at each point after the first."""
    segs = VGroup()
    for a, b in zip(pts[:-1], pts[1:]):
        ln = Line(a, b, color=color, stroke_width=width)
        segs.add(DashedLine(a, b, color=color, stroke_width=width, dash_length=0.12) if dashed else ln)
    dots = VGroup(*[Dot(p, radius=dot_radius, color=color) for p in pts[1:]])
    return VGroup(segs, dots)


# --------------------------------------------------------------------------- the hook's world (s01_hook, s02_context)
# The dot's distance from the rest point is proportional to q_k of the scalar example (ep01_numbers.LOOP: the
# one-step-window scheme from q = 1), drawn on an ellipse turned by HOOK_TURN degrees per step; the target is the
# level q = HOOK_TARGET_Q. Schematic in direction, faithful in size: the meter beside it shows V_1(q_k) itself.
HOOK_C = np.array([-1.0, -0.4, 0.0])
HOOK_AXES = (5.0, 2.75)
HOOK_ANGLE0, HOOK_TURN = 155.0, -32.0
HOOK_TARGET_Q = 0.3
METER_AT = np.array([4.55, 0.1, 0.0])
METER_VMAX = 0.6
METER_W, METER_FONT = 0.9, 28     # v4: a wider bar and a larger readout (bold at thumbnail size)
TRAIL_W, PLAN_W_STROKE, DOT_R = 7, 5, 0.15   # v4: bold strokes and a big dot (the thumbnail is the hook's frame)


def ep_meter(value, show_value=True, decimals=2):
    """The episode's meter, the same in every scene: wide, at METER_AT, label alone unless show_value. v7: two
    decimals when it shows its value (the worked example says "about zero point five nine" and shows 0.59)."""
    return meter(value, METER_VMAX, width=METER_W, font_size=METER_FONT, show_value=show_value,
                 decimals=decimals).move_to(METER_AT)
FAST_TO = 12            # the hook's replay ends at step 12, inside the target (s02 starts from there)


def hook_point(q, k):
    """The dot after k steps, at size q."""
    a = np.radians(HOOK_ANGLE0 + HOOK_TURN * k)
    return HOOK_C + np.array([q * HOOK_AXES[0] * np.cos(a), q * HOOK_AXES[1] * np.sin(a), 0.0])


def hook_target():
    """The target: the level set q = HOOK_TARGET_Q, softly filled, with the rest point."""
    e = Ellipse(width=2 * HOOK_TARGET_Q * HOOK_AXES[0], height=2 * HOOK_TARGET_Q * HOOK_AXES[1], color=GREEN,
                stroke_width=5, fill_color=GREEN, fill_opacity=0.3).move_to(HOOK_C)
    return VGroup(e, Dot(HOOK_C, radius=0.08, color=INK))


def hook_plan(q, k, first, bend, color=BLUE, width=PLAN_W_STROKE, opacity=1.0, n=4, shrink=0.62):
    """A plan from the dot at step k: it starts with `first` (the step the controller will take) and then believes in
    its own, more sharply bending, path to the rest point (bend degrees per step)."""
    a0 = np.radians(HOOK_ANGLE0 + HOOK_TURN * k)
    pts = [hook_point(q, k), first]
    qq = np.linalg.norm(((first - HOOK_C)[:2]) / np.array(HOOK_AXES))
    a = np.arctan2((first - HOOK_C)[1] / HOOK_AXES[1], (first - HOOK_C)[0] / HOOK_AXES[0])
    for _ in range(n - 1):
        qq *= shrink
        a += np.radians(bend)
        pts.append(HOOK_C + np.array([qq * HOOK_AXES[0] * np.cos(a), qq * HOOK_AXES[1] * np.sin(a), 0.0]))
    segs = VGroup(*[DashedLine(p0, p1, color=color, stroke_width=width, dash_length=0.12, stroke_opacity=opacity)
                    for p0, p1 in zip(pts[:-1], pts[1:])])
    del a0
    return segs


def hook_fan(loop, k):
    """Three candidate plans from step k: the chosen one (blue, its first step is the step taken) and two faint
    alternatives."""
    q, qn = loop[k][0], loop[k][0] * loop[k + 1][0] / loop[k][0] if k + 1 < len(loop) else loop[k][0] * 0.9
    nxt = hook_point(qn, k + 1)
    chosen = hook_plan(q, k, nxt, -34.0)
    alts = VGroup(*[hook_plan(q, k, hook_point(qn * f, k + 1 + d), b, color=MUTED, width=4, opacity=0.55)
                    for f, d, b in ((1.08, -0.3, -20.0), (0.9, 0.35, -50.0))])
    return VGroup(alts, chosen)


def hook_trail(loop, k_end, width=TRAIL_W):
    """The steps actually taken, from step 0 to step k_end."""
    return VGroup(*[Line(hook_point(loop[i][0], i), hook_point(loop[i + 1][0], i + 1), color=INK, stroke_width=width)
                    for i in range(k_end)])


def ghost_meter(value, vmax, label, color=GREEN):
    """v5: a dashed ghost of the meter, in the meter's place, for a hypothetical point (a test point, a scan): it is
    not the controller's bill, so it is not marked as the metaphor (the real meter, which only falls along the path,
    is set aside while the ghost is shown, and the narration says why). Label alone, no number (schematic)."""
    g = meter(value, vmax, label=label, width=METER_W, font_size=METER_FONT, color=color,
              show_value=False).move_to(METER_AT)
    g.ra_role = "ghost"
    g.ra_value = None
    g.frame.set_stroke(opacity=0.0)
    dashed = DashedVMobject(g.frame.copy().set_stroke(MUTED, width=3, opacity=1.0), num_dashes=40)
    g.add(dashed)
    return g
