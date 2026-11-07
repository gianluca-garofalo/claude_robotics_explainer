"""Scene 9 (outro; v7): a silent callback of the hook, about 2.5 s: the hook's picture, small, on the left, the dot
steps along its path into the region while the meter (carried from the recap, label only) drains to the floor. The
picture then gives way to the takeaway card (no empty frame: the channel name comes in as the picture fades out, then
the card), said in one sentence: "One test, on one step" above the result. The teaser names what the next episode
does, with its title on screen ("Next: From Steps to Rates"); then the closing question, also on screen, with the
music down to "low" under it (plan.json music_from), and a held tail after the last word. Nothing at x > END_SCREEN_X.

v7 against v6: the next episode is "From Steps to Rates" (the eight-episode plan); the card shows this episode's
takeaway from series_context.json; the outro stays within 15-20 s.

Takeaway and teaser from video/series_context.json (no explainer section); the meter's level is the example's last
bill (ep01_numbers.LOOP), label only; the callback's path is the hook's (schematic, no number).
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
import ep01_numbers as E
from ep01_draw import DOT_R, ep_meter
from ep01_numbers import LOOP
from ep01_world import OUTRO_METER, outro_omega, outro_point


class Outro(RAScene):
    def construct(self):
        v0 = LOOP[4][1] * 0.15                               # where the recap left the meter (label only)
        v = ValueTracker(v0)
        m = ep_meter(v.get_value, show_value=False).move_to(OUTRO_METER)
        self.carry_in(m)                                             # the last frame of the recap

        # the silent callback of the hook: the dot steps into the region while the meter drains (about 2.5 s)
        om = outro_omega()
        n_steps = 12                                                 # q_12 lies inside the region
        pts = [outro_point(LOOP[k][0], k) for k in range(n_steps + 1)]
        dot = Dot(pts[0], radius=DOT_R * 0.8, color=INK)
        trail = VGroup()
        self.play(FadeIn(om), FadeIn(dot, scale=0.5), run_time=0.4)
        for k in range(n_steps):
            seg = Line(pts[k], pts[k + 1], color=INK, stroke_width=5)
            frac = (k + 1) / n_steps
            self.play(Create(seg), dot.animate.move_to(pts[k + 1]), v.animate.set_value(v0 * (1 - frac)),
                      run_time=0.13, rate_func=smooth)
            trail.add(seg)
            self.bring_to_front(dot)
        self.play(om[0].animate.set_fill(opacity=0.5), run_time=0.3)

        # the takeaway card: "One test, on one step" above the result (no empty frame on the way)
        ctx = series_context() or {}
        nxt = ((ctx.get("next") or {}).get("short_title")) or "the next episode"
        head = Text("One test, on one step", font_size=36, color=INK)
        first = ceq(r"V_1", r"\le", r"V_0", r"\ \Longrightarrow", font_size=40)
        first[2].set_color(qcolor("W"))                              # V_0 as in OneStepTest (FC-1)
        rows = VGroup(first,
                      ceq(r"V_N(q^+)", r"-", r"V_N(q)", r"\le", r"-", r"L_d(q,q^+)", font_size=40),
                      Text("for any window", font_size=28, color=INK))           # FC-9: N is never named
        rows.arrange(DOWN, buff=0.28)
        body = VGroup(head, rows).arrange(DOWN, buff=0.4)
        frame = RoundedRectangle(width=body.width + 0.8, height=body.height + 0.6, corner_radius=0.18, color=GRID,
                                 stroke_width=2).move_to(body)
        card = VGroup(frame, body)
        g = outro(card, next_title=nxt)
        g[0].shift(UP * 0.55)
        g[1].shift(UP * 0.55)
        ask = Text("Why does the textbook weight fail?", font_size=28, color=INK)
        ask.next_to(g[1], DOWN, buff=0.35).align_to(g[1], LEFT)
        m.freeze()
        self.play(FadeOut(VGroup(om, dot, trail, m)), FadeIn(g[-1]), FadeIn(g[0][0]), run_time=0.6)
        with self.voiceover(text="One test, on one step, and that's why it arrives. [pause 0.3]") as tr:
            self.play(FadeIn(g[0][1], lag_ratio=0.1), run_time=max(tr.get_remaining_duration(), 1.6))
        with self.voiceover(text="In the next episode, <bookmark mark='n'/>the step shrinks to zero. And a momentum "
                                 "shows up that nobody put in. [pause 0.3]") as tr:
            self.wait_until_bookmark("n")
            self.play(FadeIn(g[1], shift=UP * 0.1), run_time=max(min(tr.get_remaining_duration(), 1.2), 0.8))
        with self.voiceover(text="Until then, why does the textbook weight fail? [pause 1.6]") as tr:
            self.play(FadeIn(ask, shift=UP * 0.1), run_time=max(min(tr.duration, 1.2), 0.8))
