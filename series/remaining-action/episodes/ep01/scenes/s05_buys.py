"""Scene 5 (body, chapter "What the fall buys"; v7): two consequences of the descent, each with its own time. The
bonus first: from the new point the shifted plan always reaches the region, so the controller can always plan again.
Then the slice through the target: the bill drawn above every point is a bowl, the dot sits on it at the height the
meter shows, and a bill that only falls along the motion is named (Lyapunov function). Under two mild conditions
(every step away from the target costs something; the end cost fades to zero at the target without jumping) the dot
slides down the bowl and settles at the bottom, and that is named too (asymptotic stability): one new term per
sentence, each on its own object.

v7 against v6 (the pacing rules): this was the second half of v6's ShiftedPlan, 12-19 s between claims; now the
claims are 20 s or more apart with a pause after each, the two conditions are said in words instead of the labels
"no jumps" and "an edge", and each name has its own sentence.

Explainer: Sections 3.2 (recursive feasibility) and 3.3 (sec-asymptotic). Schematic: the bowl is V = V_SCHEM q^2 to
the meter's scale (ep01_world), no number is shown.
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_world import (REF_FRAC, BEST_NEXT, BILL, BODY_C, DESC_PIN, EQ_Y, OMEGA_B, PLAN_COSTS, PLAN_Q, REST, S04_QS, V_SCHEM, W_K,
                        at, axis_label, block, body_point, bowl, descent_line, end_bowl, level, make_meter,
                        meter_guide, omega, omega_interval, plan_path, q_axis, the_dot)


def region_label(iv):
    """The end region on the slice, named in words (as in the plane)."""
    return attach(Text("end region", font_size=28, color=qcolor("W")), iv[0], direction=DOWN, buff=0.3)


class WhatItBuys(RAScene):
    def construct(self):
        v = ValueTracker(BEST_NEXT)
        om = omega()
        om[0].set_fill(opacity=0.38)
        plan = plan_path(PLAN_Q)
        for seg in plan[0]:
            seg.set_stroke(qcolor("L_d"), width=6)
        plan[0][0].set_stroke(opacity=0.3)
        plan[1][-1].set_color(qcolor("W"))
        end = plan[1][-1].get_center()
        ref_end = BODY_C + REF_FRAC * (end - BODY_C)
        ref = Arrow(end, ref_end, buff=0.0, color=qcolor("W"), stroke_width=8, max_tip_length_to_length_ratio=0.25)
        p1 = body_point(PLAN_Q[1], 1)
        dot = the_dot(p1)
        m = make_meter(v.get_value)
        desc = descent_line(font_size=44).move_to([-2.4, EQ_Y, 0])
        box = SurroundingRectangle(desc, color=INK, buff=0.22, corner_radius=0.1)
        paid = block(PLAN_COSTS[0], qcolor("L_d"))
        drop_x = m.frame.get_right()[0] + 0.25
        bracket = VGroup(Line([drop_x, level(BILL), 0], [drop_x, level(BEST_NEXT), 0]),
                         Line([drop_x - 0.12, level(BILL), 0], [drop_x, level(BILL), 0]),
                         Line([drop_x - 0.12, level(BEST_NEXT), 0], [drop_x, level(BEST_NEXT), 0])
                         ).set_stroke(qcolor("V"), width=5)
        paid.next_to(bracket, RIGHT, buff=0.12).align_to(bracket, UP)
        best = block(BEST_NEXT, qcolor("V"))                                  # standing on the floor, as s04 left it
        self.carry_in(om, plan, ref, dot, m, desc, box, paid, bracket, best)  # the last frame of s04

        # the bonus: from the new point there is always a plan into the region
        shifted_route = VMobject().set_points_as_corners([p1] + [d.get_center() for d in plan[1][1:]] + [ref_end])
        walker = dot.copy().set_opacity(0.55)
        with self.voiceover(text="And there's a bonus here. <bookmark mark='feas'/>From the new point there's always a "
                                 "plan into the region, the shifted one, so the controller can always plan again. "
                                 "[pause 1.8]") as tr:
            self.play(FadeOut(VGroup(paid, bracket, best)), run_time=max(until(tr, "feas", 0.8) - 0.1, 0.6))
            self.wait_until_bookmark("feas")
            self.play(MoveAlongPath(walker, shifted_route), run_time=max(tr.get_remaining_duration() * 0.7, 1.5))
            self.play(om[0].animate.set_fill(opacity=0.5), run_time=max(tr.get_remaining_duration() - 0.3, 0.6))
            self.play(FadeOut(walker), om[0].animate.set_fill(opacity=0.38), run_time=0.3)

        # the slice through the target: the bill as a bowl over one coordinate
        axis = q_axis()
        q_lab = axis_label(axis)
        iv = omega_interval()
        tag = region_label(iv)
        vb = bowl(V_SCHEM, qcolor("V"))

        def on_bowl(q):
            return at(q, V_SCHEM * q * q)
        guide = always_redraw(lambda: meter_guide(dot.get_center(), m))
        with self.voiceover(text="Now let's slice the picture through the target. Above every point, draw what's "
                                 "left to pay from there. <bookmark mark='s'/>You get a bowl, and the dot sits on it "
                                 "at the height the meter shows.") as tr:
            t1 = until(tr, "s", 2.4)
            self.play(FadeOut(VGroup(plan, ref)), run_time=t1 * 0.25)
            self.play(om[0].animate.stretch_to_fit_height(0.08).stretch_to_fit_width(iv.width).move_to(REST),
                      om[1].animate.move_to(REST), Create(axis), FadeIn(q_lab),
                      dot.animate.move_to(at(S04_QS[0], 0)), run_time=t1 * 0.4)
            self.play(FadeOut(om), FadeIn(iv), FadeIn(tag), desc.animate.scale(0.75).move_to(DESC_PIN),
                      box.animate.scale(0.75).move_to(DESC_PIN), run_time=t1 * 0.35)
            self.wait_until_bookmark("s")
            rt = max(tr.get_remaining_duration(), 2.0)
            self.play(Create(vb), run_time=rt * 0.55)
            self.play(dot.animate.move_to(on_bowl(S04_QS[0])), run_time=rt * 0.25)
            self.add(guide)
            self.play(FadeIn(guide), run_time=rt * 0.2)

        # a bill that only falls along the motion: its name, on the bowl
        lyap = Text("Lyapunov function", font_size=28, color=qcolor("V"))
        lyap.move_to(at(-0.35, 0.47))
        lyap = attach(lyap, vb)
        with self.voiceover(text="<bookmark mark='ly'/>A Lyapunov function is a bill like this one, a bill that "
                                 "only falls along the motion. [pause 1.6]") as tr:
            self.play(FadeIn(lyap, shift=RIGHT * 0.2), vb.animate.set_stroke(width=8), run_time=1.2)
            self.play(dot.animate.move_to(on_bowl(S04_QS[1])), v.animate.set_value(V_SCHEM * S04_QS[1] ** 2),
                      vb.animate.set_stroke(width=6), run_time=max(tr.get_remaining_duration(), 1.0))

        # two mild conditions, then the dot settles at the bottom
        wb = end_bowl()
        away = dot.copy().set_opacity(0.55)
        tick = Line(UP * 0.0, UP * 0.5, color=qcolor("L_d"), stroke_width=10)
        slider = Dot(at(-OMEGA_B, W_K * OMEGA_B ** 2), radius=0.1, color=qcolor("W"))
        with self.voiceover(text="[slow] Two mild conditions finish the job. <bookmark mark='c1'/>Every step away "
                                 "from the target has to cost something, <bookmark mark='c2'/>and the end cost must "
                                 "fade away at the target, without jumps. <bookmark mark='stab'/>Then the dot slides "
                                 "down the bowl, step after step, and settles at the bottom. [pause 1.8]") as tr:
            self.play(FadeOut(lyap), run_time=max(until(tr, "c1", 0.5) - 0.05, 0.5))
            self.wait_until_bookmark("c1")
            t1 = until(tr, "c2", 1.5)
            tick.next_to(at(-0.55, 0), UP, buff=0.05)
            self.play(away.animate.move_to(at(-0.55, 0)), run_time=t1 * 0.5)
            self.play(GrowFromEdge(tick, DOWN), run_time=t1 * 0.3)
            self.play(FadeOut(VGroup(away, tick)), run_time=t1 * 0.2)
            self.wait_until_bookmark("c2")
            t2 = until(tr, "stab", 1.5)
            self.play(Create(wb), FadeIn(slider), run_time=t2 * 0.5)
            self.play(MoveAlongPath(slider, bowl(W_K, qcolor("W"), q0=-OMEGA_B, q1=0.0)), run_time=t2 * 0.45)
            self.play(FadeOut(slider), run_time=max(t2 * 0.05, 0.1))
            self.wait_until_bookmark("stab")
            rt = max(tr.get_remaining_duration(), 2.0) / (len(S04_QS) - 2)
            for q in S04_QS[2:]:
                self.play(dot.animate.move_to(on_bowl(q)), v.animate.set_value(V_SCHEM * q * q), run_time=rt)

        # settling like this: its name, at the bottom of the bowl
        stable = Text("asymptotic stability", font_size=28, color=INK)
        stable.move_to(at(0.0, 0.265))               # inside the bowl, above the end cost's tips, clear of both
        last = [-0.06, -0.035]
        with self.voiceover(text="<bookmark mark='as'/>Settling at the bottom like this is called asymptotic "
                                 "stability. [pause 1.8]") as tr:
            rt = max(tr.get_remaining_duration(), 1.6)
            self.play(FadeIn(stable, shift=DOWN * 0.15), dot.animate.move_to(on_bowl(last[0])),
                      v.animate.set_value(V_SCHEM * last[0] ** 2), run_time=rt / 2)
            self.play(dot.animate.move_to(on_bowl(last[1])), v.animate.set_value(V_SCHEM * last[1] ** 2),
                      run_time=rt / 2)
        guide.clear_updaters()
        self.play(FadeOut(guide), run_time=0.3)
        carry_over(self, axis, q_lab, iv, tag, vb, wb, dot, m, desc, box)
