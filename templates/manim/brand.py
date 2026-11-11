"""The channel's brand: the RA monogram, one trajectory that writes R and A while its receding window slides ahead of
it and lands as the A's crossbar; the wordmark; the lockups; the logo sting that opens the title beat.

Usage: next to common.py; in a scene, from brand import logo, logo_sting
"""
import numpy as np
from manim import *  # noqa: F401,F403

from common import BG, CHANNEL, GREEN, GRID, INK, MUTED

STROKE = 0.14                       # stroke width per unit of cap height
NOTES = (0.15, 0.40, 0.65, 0.90)    # the bells of tools/video/music.py sting(): 0.15 s, then one every 0.25 s
STING_S = 2.5                       # the logo sting; the bells ring on to the end of music.py's sting
VARIANT = "trajectory"              # "trajectory": one stroke; "pair": two letters; "frame": an open window


def _fillet(way, radii, step=0.004):
    """Points along the polyline `way`, inner corner i rounded by an arc of radius radii[i] (0: sharp); fillets that
    would overlap on a segment share it."""
    P = np.asarray(way, float)
    n = len(P)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    u = np.diff(P, axis=0) / seg[:, None]
    th = [np.arccos(np.clip(-u[c - 1] @ u[c], -1.0, 1.0)) for c in range(1, n - 1)]
    tan = [r / np.tan(t / 2) if r > 0 and 1e-6 < t < np.pi - 1e-6 else 0.0 for r, t in zip(radii, th)]
    for k in range(n - 1):                          # segment k runs from corner k to corner k + 1
        ia, ib = (k - 1 if k >= 1 else None), (k if k <= n - 3 else None)
        need = sum(tan[i] for i in (ia, ib) if i is not None)
        if need > seg[k]:
            for i in (ia, ib):
                if i is not None:
                    tan[i] *= seg[k] / need
    out = [P[0]]
    for c in range(1, n - 1):
        t = tan[c - 1]
        if t <= 0:
            out.append(P[c])
            continue
        r = t * np.tan(th[c - 1] / 2)
        back, ahead = -u[c - 1], u[c]
        cen = P[c] + (back + ahead) / np.linalg.norm(back + ahead) * r / np.sin(th[c - 1] / 2)
        a0, a1 = (np.arctan2(*(P[c] + d * t - cen)[::-1]) for d in (back, ahead))
        sweep = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
        ang = a0 + sweep * np.linspace(0.0, 1.0, max(4, int(abs(sweep) * r / step)) + 1)
        out.extend(cen + r * np.column_stack([np.cos(ang), np.sin(ang)]))
    out.append(P[-1])
    return np.array(out)


def _arclength(pts):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])


def _along(pts, cum, s):
    """The points at arc lengths s of the polyline pts (cum: its arc length at each point)."""
    return np.column_stack([np.interp(s, cum, pts[:, j]) for j in range(pts.shape[1])])


def _resample(pts, n):
    cum = _arclength(pts)
    return _along(pts, cum, np.linspace(0.0, cum[-1], n))


def _geometry(variant):
    """In units of cap height from the foot of the R's stem: the strokes' centre lines, the window's two ends, and the
    corners the sting passes on the bells (the stem's top, the bowl's return, the A's foot)."""
    yj, xr, d, yc, ov = 0.48, 0.48, 0.34, 0.33, 0.04    # bowl's return and reach, A's half-width, crossbar, overhang
    rb = (1 - yj) / 2
    r_way, r_rad = [(0, 0), (0, 1), (xr, 1), (xr, yj), (0, yj)], [0.10, rb, rb, 0.0]
    if variant == "pair":
        x0 = 0.70
        strokes = [_fillet(r_way + [(0.45, 0)], r_rad), _fillet([(x0, 0), (x0 + d, 1), (x0 + 2 * d, 0)], [0.0])]
    else:
        x0 = 0.53
        strokes = [_fillet(r_way + [(x0, 0), (x0 + d, 1), (x0 + 2 * d, 0)], r_rad + [0.05, 0.05])]
    ends = np.array([(x0 + d * yc - ov, yc), (x0 + d * (2 - yc) + ov, yc)])
    return strokes, ends, np.array([(0, 1), (0, yj), (x0, 0)], float)


def _line(pts, width, color=INK):
    """A round-capped polyline through pts, (n, 2) or (n, 3)."""
    pts = np.asarray(pts, float)
    if pts.shape[1] == 2:
        pts = np.column_stack([pts, np.zeros(len(pts))])
    m = VMobject(stroke_color=color, stroke_width=width, joint_type=LineJointType.ROUND)
    m.set_points_as_corners(pts)
    return m.set_cap_style(CapStyleType.ROUND)


def monogram(size=1.0, variant=VARIANT, plate=False):
    """The RA monogram, cap height `size` in scene units, centred at the origin: parts .letters (ink) and .window
    (green); plate=True sets it on a rounded square of the background colour, for small sizes and light backgrounds.
    Resize with scale(k, scale_stroke=True)."""
    strokes, (a, b), _ = _geometry(variant)
    w = STROKE * size * 100                          # a stroke width of 1 is 0.01 scene units
    letters = VGroup(*[_line(_resample(s, 600) * size, w) for s in strokes])
    if variant == "frame":
        h = 0.085 * size
        window = RoundedRectangle(width=(b[0] - a[0]) * size + h, height=2 * h, corner_radius=h, stroke_width=0.55 * w,
                                  stroke_color=GREEN, fill_color=BG, fill_opacity=1)
        window.move_to([*((a + b) / 2 * size), 0])
    else:
        window = _line(np.linspace(a, b, 24) * size, w, GREEN)
    anchors = VGroup(VectorizedPoint(ORIGIN), VectorizedPoint(RIGHT * size))   # the unit frame the sting draws in
    mark = VGroup(letters, window, anchors)
    mark.letters, mark.window, mark.anchors, mark.variant, mark.plate = letters, window, anchors, variant, None
    mark.shift(-letters.get_center())
    if plate:
        side = letters.width + (STROKE + 0.5) * size
        mark.plate = RoundedRectangle(width=side, height=side, corner_radius=0.22 * side, fill_color=BG, fill_opacity=1,
                                      stroke_color=GRID, stroke_width=3.5 * size)
        mark.add_to_back(mark.plate)
    return mark


def wordmark(font_size=36, color=INK):
    """The channel's name in the scenes' font."""
    return Text(CHANNEL, font_size=font_size, weight=BOLD, color=color)


def logo(size=1.0, word=True, stacked=False, variant=VARIANT, plate=False, font_size=None, color=INK):
    """The lockup, centred at the origin: the monogram (cap height `size`) with the wordmark to its right, its capitals
    0.42 of the monogram's on its middle, or centred below it (stacked, 0.2); parts .mark and .word (None without)."""
    mark = monogram(size, variant, plate)
    g = VGroup(mark)
    g.mark, g.word = mark, None
    if word:
        g.word = wordmark(font_size or round(size * (20 if stacked else 41.5)), color)
        if stacked:
            g.word.next_to(mark, DOWN, buff=0.38 * size)
        else:
            g.word.next_to(mark, RIGHT, buff=0.42 * size)
            g.word.shift(UP * (mark.letters.get_center()[1] - g.word[0].get_center()[1]))    # capitals on the middle
        g.add(g.word)
    return g.move_to(ORIGIN)


def _ease(u, k=0.6):
    """Smoothstep blended with linear: the speed at both ends is 1 - k of the mean."""
    u = np.clip(u, 0.0, 1.0)
    return k * u * u * (3 - 2 * u) + (1 - k) * u


def _ramp(t, t0, t1):
    """0 before t0, 1 after t1, smooth in between."""
    return float(smooth(np.clip((t - t0) / (t1 - t0), 0.0, 1.0)))


def _fader(mob):
    """A function o -> the stroke and fill opacities of mob's family at o times their present values."""
    fam = [(m, m.get_stroke_opacity(), m.get_fill_opacity()) for m in mob.family_members_with_points()]

    def fade(o):
        for m, so, fo in fam:
            m.set_stroke(opacity=so * o, family=False)
            m.set_fill(opacity=fo * o, family=False)
    return fade


class LogoSting(Animation):
    """The logo sting on music.py's motif (STING_S seconds): the trajectory draws in four steps that end on the bells,
    its window riding ahead; the window lands as the A's crossbar, the letters resolve from muted to ink and the
    wordmark fades in. `lockup` is logo()'s, already placed; it is hidden until the sting plays."""

    DRAW_END, OPEN_S, LAND_S, SETTLE_S, RESOLVE, WORD = 1.25, 0.15, 0.3, 0.1, (1.2, 1.5), (1.2, 1.6)

    def __init__(self, lockup, **kwargs):
        super().__init__(lockup, run_time=STING_S, rate_func=linear, introducer=True, **kwargs)
        mark = lockup.mark
        o, x = (p.get_center() for p in mark.anchors)
        k = float(np.linalg.norm(x - o))             # scene units per unit of cap height

        def placed(p):
            return o + k * np.column_stack([p, np.zeros(len(p))])
        strokes, ends, corners = _geometry(mark.variant)
        route = np.vstack(strokes)                   # a pen-up move joins two strokes
        cum = _arclength(route)
        starts = np.cumsum([0] + [len(s) for s in strokes])
        self.spans = [(cum[i], cum[j - 1]) for i, j in zip(starts[:-1], starts[1:])]
        self.route, self.cum, self.total = placed(route), cum, cum[-1]
        knots, lo = [], 0
        for c in corners:                            # in order: the stem passes the bowl's return too
            lo += int(np.argmin(np.linalg.norm(route[lo:] - c, axis=1)))
            knots.append(cum[lo])
        self.T, self.S = [*NOTES, self.DRAW_END], [0.0, *knots, self.total]
        self.win = float(np.linalg.norm(ends[1] - ends[0]))
        self.bar = np.linspace(*placed(ends), 24)
        grid = np.linspace(NOTES[1], self.DRAW_END, 400)
        self.t_land = next((t for t in grid if self.tip(t) + self.win >= self.total), self.DRAW_END)
        self.band = _line(self.bar, STROKE * k * 100, GREEN)
        self.dot, self.dot_r = Dot(color=INK), 0.68 * STROKE * k
        self.full = [s.copy() for s in mark.letters]
        self.window_fade, self.band_fade = _fader(mark.window), _fader(self.band)
        self.word = lockup.word
        if self.word is not None:
            self.word_at, self.word_fade, self.word_rise = self.word.get_center(), _fader(self.word), 0.12 * k
        lockup.add(self.band, self.dot)
        self.interpolate_mobject(0.0)

    def tip(self, t):
        """Arc length of the trajectory's tip at time t."""
        T, S = self.T, self.S
        if t <= T[0]:
            return 0.0
        for j in range(len(T) - 1):
            if t < T[j + 1]:
                return S[j] + _ease((t - T[j]) / (T[j + 1] - T[j])) * (S[j + 1] - S[j])
        return self.total

    def interpolate_mobject(self, alpha):
        t = alpha * STING_S
        s = self.tip(t)
        ink = interpolate_color(ManimColor(MUTED), ManimColor(INK), _ramp(t, *self.RESOLVE))
        for vm, full, (a, b) in zip(self.mobject.mark.letters, self.full, self.spans):
            f = float(np.clip((s - a) / (b - a), 0.0, 1.0))
            vm.pointwise_become_partial(full, 0.0, f)
            vm.set_stroke(color=ink, opacity=1.0 if f > 0 else 0.0)
        grow = _ramp(t, NOTES[1], NOTES[1] + self.OPEN_S)              # the window opens ahead of the tip
        landed = self.t_land + self.LAND_S
        settle = _ramp(t, landed, landed + self.SETTLE_S)               # the band hands over to the window
        if grow > 0:
            s0 = min(s, self.total - self.win)
            ride = _along(self.route, self.cum, np.linspace(s0, s0 + self.win * grow, 24))
            land = _ramp(t, self.t_land, landed)
            self.band.set_points_as_corners((1 - land) * ride + land * self.bar)
        self.band_fade((1 - settle) if grow > 0 else 0.0)
        self.window_fade(settle)
        pop = _ramp(t, NOTES[0] - 0.1, NOTES[0]) * (1 - _ramp(t, self.DRAW_END, self.DRAW_END + 0.15))
        self.dot.become(Dot(_along(self.route, self.cum, [s])[0], radius=max(self.dot_r * pop, 1e-4), color=INK,
                            fill_opacity=1.0 if pop > 0 else 0.0))
        if self.word is not None:
            e = _ramp(t, *self.WORD)
            self.word.move_to(self.word_at + DOWN * self.word_rise * (1 - e))
            self.word_fade(e)

    def clean_up_from_scene(self, scene):
        super().clean_up_from_scene(scene)
        self.mobject.remove(self.band, self.dot)


def logo_sting(scene, at=ORIGIN, size=1.8, stacked=True, variant=VARIANT):
    """Play the logo sting (STING_S seconds) at `at` and return the lockup, left on screen in its final state. It opens
    the title beat, right after the hook; its steps land on music.py's hook_title bells when they start with it."""
    lockup = logo(size, stacked=stacked, variant=variant).move_to(at)
    sting = LogoSting(lockup)
    scene.add(lockup)
    scene.play(sting)
    return lockup
