"""Scene 8 (body, chapter "Recap"; v7): the end recap, about 25 s before the outro. The picture that taught the descent
comes back small on the left (the region, the plan, the dot), then the question the recap answers ("What made the
bill fall, step after step?"), on screen before it is said and held 2.5 s so the viewer can recall the answer first
(retrieval before restatement). Then the two starred results in the same plain words as their restatements, each
boxed as it comes: the descent, while the small picture replays the shifted plan and its reference step and the
meter falls step by step; then the one test behind it (the pinned test leaves its corner and is shown again under
the descent, an arrow from the test to the descent). The meter then moves to the outro's place.

v7, after the video design review (VD-7, VD-11): the picture of the argument is back beside the boxed results, and
the test no longer flies through the descent.

Explainer: Sections 3.2 (sec-descent) and 2.3 (sec-terminal); the results as shown in this video. No numbers.
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
import ep01_numbers as E
from ep01_world import (REF_FRAC, BODY_C, OUTRO_METER, PLAN_Q, Q_DRAW, W_K, at, axis_label, body_point, bowl, descent_line,
                        make_meter, omega, omega_interval, pinned_test, plan_path, q_axis, test_line, the_dot)

K1 = 0.5 * E.riccati(1)[1]
MINI = 0.7                                    # the copy of the plane, on the left (v7, FC-3: larger, lower)
MINI_AT = np.array([-4.0, -0.9, 0.0])


def region_label(iv):
    return attach(Text("end region", font_size=28, color=qcolor("W")), iv[0], direction=DOWN, buff=0.3)


class Recap(RAScene):
    def construct(self):
        v = ValueTracker(E.LOOP[4][1])
        axis = q_axis()
        q_lab = axis_label(axis)
        iv = omega_interval(Q_DRAW)
        iv[1].set_stroke(opacity=0.0)
        tag = region_label(iv)
        tag.next_to(at(-Q_DRAW, 0), DOWN, buff=0.3).shift(RIGHT * 1.0)
        wb = bowl(W_K, qcolor("W"))
        vb = bowl(K1, qcolor("V"))
        m = make_meter(v.get_value)
        test, tbox = pinned_test()
        here = the_dot(at(E.LOOP[4][0], E.LOOP[4][1]))
        self.carry_in(axis, q_lab, iv, tag, wb, vb, m, test, tbox, here)                   # the last frame of s07

        # the small picture of the argument comes back on the left, then the question (on screen before it is said)
        om = omega()
        om[0].set_fill(opacity=0.32)
        plan = plan_path(PLAN_Q)
        for seg in plan[0]:
            seg.set_stroke(qcolor("L_d"), width=6)
        plan[1][-1].set_color(qcolor("W"))
        dot = the_dot(body_point(PLAN_Q[0], 0))
        end = plan[1][-1].get_center()
        ref_end = BODY_C + REF_FRAC * (end - BODY_C)
        ref = Arrow(end, ref_end, buff=0.0, color=INK, stroke_width=8, max_tip_length_to_length_ratio=0.25)
        mini = VGroup(om, plan, dot)
        for x in (mini, ref):
            x.scale(MINI, about_point=BODY_C).shift(MINI_AT - BODY_C)
        ask = Text("What made the bill fall?", font_size=34, color=INK).move_to([0.7, 2.55, 0])
        self.play(FadeOut(VGroup(axis, q_lab, iv, tag, wb, vb, here)), run_time=0.8)
        self.play(FadeIn(mini), FadeIn(ask, shift=DOWN * 0.1), run_time=0.8)
        with self.voiceover(text="<bookmark mark='rc'/>What made the bill fall, step after step? [pause 2.5]") as tr:
            self.play(ask.animate.set_color(INK), run_time=max(tr.get_remaining_duration(), 0.5))

        # the descent, boxed first, while the small picture replays the shifted plan and the meter falls step by step
        desc = descent_line(font_size=36).move_to([0.7, 0.9, 0])
        dbox = SurroundingRectangle(desc, color=INK, buff=0.22, corner_radius=0.1)
        p1 = plan[1][0].get_center()
        with self.voiceover(text="Shift the old plan by one step, and cap it with a reference step at its end, "
                                 "inside the region. <bookmark mark='r1'/>Each time, the bill drops by at least what "
                                 "that step costs. [pause 1]") as tr:
            self.play(FadeIn(desc, shift=UP * 0.1), Create(dbox), run_time=1.2)
            t1 = until(tr, "r1", 2.0)
            self.play(dot.animate.move_to(p1), plan[0][0].animate.set_stroke(opacity=0.3), run_time=t1 * 0.4)
            self.play(LaggedStart(*[seg.animate.set_stroke(width=9) for seg in plan[0][1:]], lag_ratio=0.3),
                      run_time=t1 * 0.3)
            self.play(GrowArrow(ref), *[seg.animate.set_stroke(width=6) for seg in plan[0][1:]], run_time=t1 * 0.3)
            self.wait_until_bookmark("r1")
            rt = max(tr.get_remaining_duration(), 2.0) / 4
            for k in range(4):                              # the bill falls, step after step (label only)
                self.play(v.animate.set_value(E.LOOP[4][1] * (0.75 - 0.2 * k)), run_time=rt)

        # the one test behind it: shown again under the descent (it leaves its corner; nothing flies through)
        test2 = test_line(font_size=48).move_to([0.7, -1.5, 0])
        tbox2 = SurroundingRectangle(test2, color=INK, buff=0.3, corner_radius=0.1)
        implies = Arrow(tbox2.get_top(), dbox.get_bottom(), buff=0.12, color=INK, stroke_width=5,
                        max_tip_length_to_length_ratio=0.25)
        with self.voiceover(text="And behind it? One test, on a single step. <bookmark mark='r2'/>One step of "
                                 "planning never raises the bill. [pause 1.5]") as tr:
            self.play(FadeOut(VGroup(test, tbox)), FadeIn(test2, shift=UP * 0.1), Create(tbox2),
                      ref.animate.set_color(qcolor("W")), run_time=max(until(tr, "r2", 1.2), 1.2))
            self.wait_until_bookmark("r2")
            self.play(GrowArrow(implies), om[0].animate.set_fill(opacity=0.45), run_time=max(tr.get_remaining_duration(),
                                                                                            0.8))
        with self.voiceover(text="Together, they're the whole proof we needed. [pause 1.2]") as tr:
            self.play(VGroup(dbox, tbox2, implies).animate.set_stroke(width=6),
                      run_time=max(tr.get_remaining_duration() * 0.5, 0.6))
            self.play(VGroup(dbox, tbox2, implies).animate.set_stroke(width=4),
                      run_time=max(tr.get_remaining_duration(), 0.5))
        self.read(ask, desc, test2)
        m.freeze()
        self.play(FadeOut(VGroup(ask, desc, dbox, test2, tbox2, implies, mini, ref)), m.animate.move_to(OUTRO_METER),
                  run_time=0.8)
