"""Scene 6 (body, chapter "One test, on one step"; v7): the one test, on one step, drawn on the slice and read as a
bill. The controller has arrived and its meter is empty, so the meter is set aside (said aloud) and the picture zooms
into the end region, with some axis outside it on both sides. A point of the region sits on the end-cost bowl; a
reference step stays inside; on the bowl, the fall of the end cost (green) against the step's cost (amber) stacked on
the end cost after the step: the cost fits under the old height. Read as a bill: with no steps left the bill is the
end cost inside the region (a legend, "no steps left") and, after a think prompt held 3.5 s, infinite outside (tall
walls). With one step to plan, the reference step is one plan the controller could pick, so the best one-step bill
sits under the end cost, and under infinity outside: V_1 <= V_0, boxed and held 3 s, restated. What is in it (no
window length), what that buys, the textbook names, a one-sentence summary; then the zoom out, the test pinned and
the controller's meter back, still empty.

v7 against v6 (the pacing rules): the meter is set aside without a ghost meter; the test is shown as bars on the bowl
and said in words (no A2 line and no chain of inequalities: one new equation, V_1 <= V_0, instead of four); the
outside of the region is a think prompt before the walls grow; the textbook names come once, at the end, one term
per sentence.

Explainer: Section 2.3 (sec-terminal): A1, A2 (8) and their reading (9) in the language of the recursion; Section 3.4
(sec-onestep) for "the certificate does not involve N". Schematic: the step is phi_f(q) = PHI q, its cost LD_S q^2
and the one-step bill V_SCHEM q^2 (shapes only; ep01_world); no number is shown.
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_world import (BASE_Y, DESC_PIN, OMEGA_B, SCALE, TEST_PIN, V_SCHEM, W_K, X0, XS, at, axis_label, bowl,
                        descent_line, end_bowl, make_meter, omega_interval, q_axis, test_line, the_dot, vbar)

PHI, LD_S = 0.7, 0.2            # schematic reference step q -> PHI q and its cost LD_S q^2 (the test holds)
Q_T = 0.45                      # the point the test is shown at
ZOOM = 1.6                      # the region's edges inside the frame, with axis outside them on both sides
ZOOM_V = 2.6                    # v7 (VD-3): heights zoomed more than widths, so the bowl and the test's bars fill the frame
XZ0 = X0 + 1.3                  # v7 (FC-2): the zoomed slice centred in the frame once the meter is set aside
VZ = (XZ0, BASE_Y, XS * ZOOM, SCALE * ZOOM_V)
Z_LIM = (-0.75, 0.72)           # the zoomed slice's q range (inside the frame)
EQ2 = np.array([2.5, 2.8, 0.0])   # the equation band, above the right wall, clear of the legend (FC-7)
WALL_TOP = 2.0                  # the walls of the bill with no steps left, outside the region


def W(q):
    return W_K * q * q


def zaxis():
    ax = Line(at(Z_LIM[0], 0, VZ), at(Z_LIM[1], 0, VZ), color=MUTED, stroke_width=4)
    return VGroup(ax, Dot(at(0, 0, VZ), radius=0.08, color=INK))


def walls():
    """The bill with no steps left, outside the region: a tall wall over each outside part of the axis, in the colour
    of V_0 (the end cost's: inside the region the same bill is the end cost; v7, FC-1)."""
    out = VGroup()
    for a, b in ((Z_LIM[0], -OMEGA_B), (OMEGA_B, Z_LIM[1])):
        x0, x1 = at(a, 0, VZ)[0], at(b, 0, VZ)[0]
        out.add(Rectangle(width=abs(x1 - x0), height=WALL_TOP - BASE_Y, stroke_width=5, stroke_color=qcolor("W"),
                          fill_color=qcolor("W"), fill_opacity=0.22).move_to([(x0 + x1) / 2, (WALL_TOP + BASE_Y) / 2, 0]))
    return out


def region_label(iv, text="end region"):
    return attach(Text(text, font_size=28, color=qcolor("W")), iv[0], direction=DOWN, buff=0.3)


class OneStepTest(RAScene):
    def construct(self):
        v = ValueTracker(V_SCHEM * 0.035 ** 2)
        axis = q_axis()
        q_lab = axis_label(axis)
        iv = omega_interval()
        tag = region_label(iv)
        vb = bowl(V_SCHEM, qcolor("V"))
        wb = end_bowl()
        dot = the_dot(at(-0.035, V_SCHEM * 0.035 ** 2))
        m = make_meter(v.get_value)
        desc = descent_line(font_size=44)
        box = SurroundingRectangle(desc, color=INK, buff=0.22, corner_radius=0.1)
        VGroup(desc, box).scale(0.75).move_to(DESC_PIN)
        self.carry_in(axis, q_lab, iv, tag, vb, wb, dot, m, desc, box)          # the last frame of s05

        # the meter is set aside, said aloud (the controller has arrived); zoom into the end region
        zax, ziv = zaxis(), omega_interval(view=VZ)
        zwb = bowl(W_K, qcolor("W"), VZ, -OMEGA_B, OMEGA_B, x_max=at(OMEGA_B, 0, VZ)[0] + 0.01)   # to the region's edge
        ztag = region_label(ziv)
        ztag.next_to(at(-OMEGA_B, 0, VZ), DOWN, buff=0.45).shift(RIGHT * 0.9)
        with self.voiceover(text="Everything now rests on that one test, at the end of the window. <bookmark "
                                 "mark='set'/>The controller has arrived, and its meter is empty. So let's set it "
                                 "aside, <bookmark mark='z'/>and zoom in on the end region.") as tr:
            self.play(Indicate(wb, color=qcolor("W"), scale_factor=1.04), run_time=max(until(tr, "set", 1.0) - 0.1,
                                                                                        0.8))
            self.wait_until_bookmark("set")
            t1 = until(tr, "z", 1.6)
            self.play(FadeOut(vb), dot.animate.move_to(at(-0.035, W(0.035))), run_time=t1 * 0.5)
            m.freeze()
            self.play(FadeOut(m), run_time=t1 * 0.5)
            self.wait_until_bookmark("z")
            self.play(Transform(axis, zax), FadeOut(q_lab), Transform(iv, ziv), Transform(wb, zwb),
                      Transform(tag, ztag), dot.animate.move_to(at(-0.035, W(0.035), VZ)),
                      FadeOut(VGroup(desc, box)), run_time=max(tr.get_remaining_duration(), 1.2))

        # the test on the bowl: a reference step from q stays inside; the end cost falls by at least its cost
        p, ph = Q_T, PHI * Q_T
        q_tag = attach(MathTex("q", font_size=40), axis[0], direction=DOWN, buff=0.3)
        q_tag.next_to(at(p, 0, VZ), DOWN, buff=0.3)
        tick = Line(at(p, 0, VZ) + DOWN * 0.15, at(p, 0, VZ) + UP * 0.15, color=INK, stroke_width=5)
        step = Arrow(at(p, 0, VZ) + UP * 0.32, at(ph, 0, VZ) + UP * 0.32, buff=0.0, color=INK, stroke_width=6,
                     max_tip_length_to_length_ratio=0.3)
        x_off = 0.42
        lvl = DashedLine(at(p, W(p), VZ), at(ph, W(p), VZ) + LEFT * (2 * x_off + 0.3), dash_length=0.1,
                         color=MUTED, stroke_width=3)
        fall = vbar(ph, W(ph), W(p), qcolor("W"), VZ, dx=-x_off, width=0.36)
        cost = vbar(ph, W(ph), W(ph) + LD_S * p * p, qcolor("L_d"), VZ, dx=-2 * x_off, width=0.36)
        down = bowl(W_K, qcolor("W"), VZ, ph, p).reverse_direction()
        with self.voiceover(text="[slow] Pick a point in the region. <bookmark mark='g'/>The test asks for a "
                                 "reference step from there that stays inside, <bookmark mark='b'/>and along that "
                                 "step, the end cost must drop by at least the step's own cost. [pause 1.8]") as tr:
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, -0.035, p)), Create(tick), FadeIn(q_tag),
                      run_time=max(until(tr, "g", 1.0), 1.0))
            self.wait_until_bookmark("g")
            self.play(GrowArrow(step), MoveAlongPath(dot, down), run_time=max(until(tr, "b", 1.2), 1.2))
            self.wait_until_bookmark("b")
            t1 = tr.get_remaining_duration()
            self.play(dot.animate.move_to(at(p, W(p), VZ)), Create(lvl), run_time=max(t1 * 0.25, 0.6))
            self.play(MoveAlongPath(dot, down), Create(fall), run_time=max(t1 * 0.35, 0.8))
            self.play(GrowFromEdge(cost, DOWN), run_time=max(t1 * 0.4, 0.8))

        # read as a bill: with no steps left, the end cost inside the region (a legend names the curve)
        none_row = [VGroup(Line(LEFT * 0.3, RIGHT * 0.3, stroke_width=7, color=qcolor("W")),
                           Square(0.22, stroke_color=qcolor("W"), stroke_width=3, fill_color=qcolor("W"),
                                  fill_opacity=0.22)).arrange(RIGHT, buff=0.12),
                    Text("no steps left = end cost", font_size=28, color=INK)]
        one_row = [Line(LEFT * 0.3, RIGHT * 0.3, stroke_width=7, color=qcolor("V")).set_x(0),
                   Text("one step left", font_size=28, color=INK)]
        legend = legend_table([none_row, one_row], aligns="ll", col_gap=0.3, row_gap=0.28)
        legend.move_to([-6.2 + legend.width / 2, 3.0, 0])
        none_square = none_row[0][1]
        none_square.set_opacity(0.0)                       # the wall sample comes with the walls
        with self.voiceover(text="[slow] Now read the same test as a bill. Say there are no steps left. <bookmark "
                                 "mark='v0'/>Then take a point of the region. The bill there is just its end cost. [pause 1.2]") as tr:
            self.play(FadeOut(VGroup(lvl, fall, cost)), run_time=max(until(tr, "v0", 0.8) - 0.1, 0.6))
            self.wait_until_bookmark("v0")
            self.play(FadeIn(none_row[0][0]), FadeIn(none_row[1]), wb.animate.set_stroke(width=9), run_time=1.0)
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, -0.5, p).reverse_direction()),
                      run_time=max(tr.get_remaining_duration() * 0.6, 1.0))
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, -0.5, p)), wb.animate.set_stroke(width=6),
                      run_time=max(tr.get_remaining_duration(), 0.8))
        outside = VGroup(*[Line(at(a, 0, VZ), at(b, 0, VZ), color=INK, stroke_width=7)
                           for a, b in ((Z_LIM[0], -OMEGA_B), (OMEGA_B, Z_LIM[1]))])
        probe = Dot(at(-0.62, 0, VZ), radius=0.12, color=INK).set_opacity(0.6)
        with self.voiceover(text="[slow] And now take a point outside the region. <bookmark mark='ask2'/>With no "
                                 "steps left, what's the bill there? [pause 3.8]") as tr:
            self.play(Create(outside), FadeIn(probe), run_time=1.2)
            rt = max(tr.get_remaining_duration() - 0.6, 1.2)
            self.play(probe.animate.move_to(at(-0.72, 0, VZ)), run_time=rt * 0.5)
            self.play(probe.animate.move_to(at(-0.62, 0, VZ)), run_time=rt * 0.5)
            self.play(probe.animate.move_to(at(-0.66, 0, VZ)), run_time=0.6)
        wl = walls()
        infs = VGroup(*[Text("∞", font_size=48, color=INK).move_to(          # FC-7: clear of the one-step curve
            w.get_center() + UP * 0.7 + (RIGHT if w.get_x() > XZ0 else LEFT) * 0.16) for w in wl])
        with self.voiceover(text="But outside, no plan can end in the region at all. <bookmark mark='x'/>The bill out "
                                 "there is infinite. [pause 1.8]") as tr:
            self.play(FadeOut(outside), FadeOut(probe), run_time=max(until(tr, "x", 0.8) - 0.1, 0.6))
            self.wait_until_bookmark("x")
            rt = max(tr.get_remaining_duration(), 1.6)
            self.play(*[GrowFromEdge(w, DOWN) for w in wl], none_square.animate.set_opacity(1.0).set_fill(opacity=0.22),
                      run_time=rt * 0.7)
            self.play(FadeIn(infs, shift=UP * 0.15), run_time=rt * 0.3)

        # with one step to plan: the reference step is one plan; the best one-step bill sits under the end cost
        v1_pt = Dot(radius=0.14, color=qcolor("V"))
        plan_lvl = W(ph) + LD_S * p * p
        start = at(ph, plan_lvl, VZ) + LEFT * 2 * x_off
        fall_right = at(ph, plan_lvl, VZ)[0] - x_off + 0.2           # just right of the green bar
        carry = DashedLine([fall_right, at(ph, plan_lvl, VZ)[1], 0], at(p, plan_lvl, VZ), dash_length=0.1,
                           color=MUTED, stroke_width=3)
        lvl2 = DashedLine(at(p, W(p), VZ), [fall_right, at(p, W(p), VZ)[1], 0], dash_length=0.1, color=MUTED,
                          stroke_width=3)
        fall = vbar(ph, W(ph), W(p), qcolor("W"), VZ, dx=-x_off, width=0.36)
        cost = vbar(ph, W(ph), W(ph) + LD_S * p * p, qcolor("L_d"), VZ, dx=-2 * x_off, width=0.36)
        with self.voiceover(text="[slow] Now give the controller a single step. <bookmark mark='osb'/>The one-step "
                                 "bill is the lowest bill it can reach with that step. [pause 1.2]") as tr:
            self.play(dot.animate.move_to(at(p, W(p), VZ)), FadeIn(one_row[0]), FadeIn(one_row[1]), run_time=1.0)
            self.play(FadeIn(fall), GrowFromEdge(cost, DOWN), run_time=max(tr.get_remaining_duration(), 0.8))
        with self.voiceover(text="[slow] The reference step is one plan it could pick, and the test says that plan "
                                 "costs no more than the end cost. <bookmark mark='lo'/>The best one-step bill can "
                                 "only be lower still. [pause 1.8]") as tr:
            v1_pt.move_to(start)
            t1 = until(tr, "lo", 1.6)
            self.play(Create(lvl2), run_time=t1 * 0.5)                 # the end cost at q, beside the green bar
            self.add(v1_pt)
            self.play(Create(carry), v1_pt.animate.move_to(at(p, plan_lvl, VZ)), run_time=max(t1 * 0.5 - 0.1, 0.6))
            self.wait_until_bookmark("lo")
            drop_seg = Line(at(p, plan_lvl, VZ), at(p, V_SCHEM * p * p, VZ), color=qcolor("V"), stroke_width=6)
            self.play(v1_pt.animate.move_to(at(p, V_SCHEM * p * p, VZ)), Create(drop_seg),
                      run_time=max(tr.get_remaining_duration(), 1.0))
        v1 = bowl(V_SCHEM, qcolor("V"), VZ, Z_LIM[0], Z_LIM[1], top=0.2, width=7, x_max=at(Z_LIM[1], 0, VZ)[0])
        sweep = DashedLine(at(Z_LIM[0], 0, VZ), [at(Z_LIM[0], 0, VZ)[0], WALL_TOP, 0], dash_length=0.1,
                           color=MUTED, stroke_width=3)
        test = test_line().move_to(EQ2)
        tbox = SurroundingRectangle(test, color=INK, buff=0.3, corner_radius=0.1)
        with self.voiceover(text="[slow] That's true at every point, inside the region and out. <bookmark "
                                 "mark='t'/>With one step to plan, the bill is never higher than with none. "
                                 "[pause 3]") as tr:
            self.add(sweep)
            t1 = until(tr, "t", 2.0)
            self.play(Create(v1), sweep.animate.move_to([at(Z_LIM[1], 0, VZ)[0], sweep.get_y(), 0]),
                      FadeOut(VGroup(v1_pt, carry, lvl2, fall, cost, drop_seg)), rate_func=linear,
                      run_time=max(t1 - 1.2, 1.2))
            self.remove(sweep)
            self.play(FadeIn(test[0], shift=RIGHT * 0.2), FadeIn(test[1]), FadeIn(test[2], shift=RIGHT * 0.2),
                      Indicate(one_row[1], color=qcolor("V"), scale_factor=1.05),
                      Indicate(none_row[1], color=qcolor("W"), scale_factor=1.05), run_time=2.0)
            self.play(Create(tbox), run_time=max(tr.get_remaining_duration(), 0.8))

        # in plain words; what is in it (no window length) and what that buys
        with self.voiceover(text="<bookmark mark='rs2'/>In plain words, one step of planning never raises the bill. "
                                 "[pause 2.4]") as tr:
            self.play(dot.animate.move_to(at(ph, W(ph), VZ)), run_time=max(tr.get_remaining_duration() * 0.5, 0.8))
            self.play(dot.animate.move_to(at(p, W(p), VZ)), run_time=max(tr.get_remaining_duration(), 0.8))
        with self.voiceover(text="It also works the other way round. <bookmark mark='cv'/>When the best one-step bill "
                                 "is no higher than the end cost, its best step is a reference step that passes the "
                                 "test. [pause 1.8]") as tr:                # v7 (final-cut round 2, FC-1): the converse
            q_best = 0.6 * p                                          # where the best single step lands
            best = Arrow(at(p, 0, VZ) + UP * 0.72, at(q_best, 0, VZ) + UP * 0.72, buff=0.0, color=qcolor("V"),
                         stroke_width=6, max_tip_length_to_length_ratio=0.3)
            land = Dot(at(q_best, W(q_best), VZ), radius=0.1, color=qcolor("V"))
            self.play(GrowArrow(best), run_time=max(until(tr, "cv", 1.0) - 0.1, 0.8))
            self.wait_until_bookmark("cv")
            rt = max(tr.get_remaining_duration(), 2.4)
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, q_best, p).reverse_direction()), FadeIn(land),
                      run_time=rt * 0.4)
            self.play(best.animate.set_color(INK), step.animate.set_stroke(width=9), run_time=rt * 0.3)
            self.play(FadeOut(VGroup(best, land)), dot.animate.move_to(at(p, W(p), VZ)),
                      step.animate.set_stroke(width=6), run_time=rt * 0.3)
        with self.voiceover(text="[slow] Before we go on, take one more look at the test. <bookmark mark='ask3'/>What's "
                                 "in it, and what's missing? [pause 4.4]") as tr:
            self.play(FadeOut(VGroup(tick, q_tag)), run_time=0.6)
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, ph, p)), run_time=max(until(tr, "ask3", 1.0), 1.0))
            self.play(MoveAlongPath(dot, bowl(W_K, qcolor("W"), VZ, ph, p).reverse_direction()),
                      run_time=max(min(tr.get_remaining_duration(), 2.0), 0.8))
        def win_row(n):
            return VGroup(*[Square(0.34).set_stroke(INK, width=3) for _ in range(n)]).arrange(RIGHT, buff=0.1) \
                .move_to([-3.2, -3.05, 0])
        gone = win_row(6)
        win_tag = Text("window", font_size=28, color=INK).next_to(gone, RIGHT, buff=0.3)
        with self.voiceover(text="The answer is the window. <bookmark mark='wf'/>There's the end cost, the region and a "
                                 "single step, but no window length at all. [pause 1.8]") as tr:
            self.play(LaggedStart(*[FadeIn(sq) for sq in gone], lag_ratio=0.2), FadeIn(win_tag),
                      run_time=max(until(tr, "wf", 0.8), 0.8))
            self.wait_until_bookmark("wf")
            rt = max(tr.get_remaining_duration() / 4, 0.6)
            self.play(wb.animate.set_stroke(width=10), run_time=rt)
            self.play(wb.animate.set_stroke(width=6), iv[0].animate.set_stroke(width=20), run_time=rt)
            self.play(iv[0].animate.set_stroke(width=14), step.animate.set_stroke(width=9), run_time=rt)
            self.play(FadeOut(VGroup(gone, win_tag), shift=DOWN * 0.3), run_time=rt)
        with self.voiceover(text="You can check it once, before the controller ever runs, and pick the window "
                                 "for computing time, not for safety. <bookmark mark='nxt'/>What a longer window "
                                 "does buy is a story for the next episode. [pause 1.8]") as tr:
            row = win_row(3)
            tag_w = Text("window", font_size=28, color=INK).next_to(row, RIGHT, buff=0.3)
            t0 = max(until(tr, "nxt", 1.2), 1.2)
            self.play(step.animate.set_stroke(width=6), FadeIn(row), FadeIn(tag_w), run_time=t0 * 0.25)
            for n in (6, 2, 4):                                        # any length: chosen for computing time
                new = win_row(n)
                self.play(Transform(row, new), tag_w.animate.next_to(new, RIGHT, buff=0.3), run_time=t0 * 0.25)
            self.wait_until_bookmark("nxt")
            longer = win_row(8)
            self.play(Transform(row, longer), tag_w.animate.next_to(longer, RIGHT, buff=0.3),
                      run_time=max(tr.get_remaining_duration() * 0.6, 0.8))
            self.play(FadeOut(VGroup(row, tag_w)), run_time=max(tr.get_remaining_duration(), 0.4))
        tc = Text("terminal cost", font_size=28, color=qcolor("W"))
        tc.move_to(at(0.06, 0.135, VZ))
        tc = attach(tc, wb)
        ts = region_label(iv, "terminal set")
        ts.move_to(ztag).shift(RIGHT * (ts.width - ztag.width) / 2)
        with self.voiceover(text="<bookmark mark='tn'/>The end cost is called the terminal cost. <bookmark "
                                 "mark='tn2'/>The region, the terminal set. [pause 1.2]") as tr:
            self.play(FadeIn(tc, shift=UP * 0.1), run_time=0.5)
            self.play(wb.animate.set_stroke(width=9), run_time=max(until(tr, "tn2", 1.0) - 0.1, 0.5))
            self.wait_until_bookmark("tn2")
            self.play(Succession(FadeOut(tag, run_time=0.4), FadeIn(ts, run_time=0.6)), wb.animate.set_stroke(width=6),
                      run_time=max(tr.get_remaining_duration(), 1.0))

        # the summary; zoom out, the test pinned, the controller's meter back (still empty)
        with self.voiceover(text="<bookmark mark='sum4'/>So a single test, on one step, is all it takes to certify "
                                 "the controller. [pause 1.8]") as tr:
            self.play(FadeOut(VGroup(tc, ts, wl, infs, v1, legend)), run_time=0.8)
            back_iv = omega_interval()
            self.play(Transform(axis, q_axis()), Transform(iv, back_iv), Transform(wb, end_bowl()),
                      FadeOut(step), dot.animate.move_to(at(ph, W(ph))),
                      VGroup(test, tbox).animate.scale(0.6).move_to(TEST_PIN),
                      run_time=max(tr.get_remaining_duration() - 0.2, 1.2))
        m2 = make_meter(v.get_value)                         # the controller's meter again: still empty
        tag2 = region_label(iv)
        q_lab2 = axis_label(axis)
        self.play(FadeIn(q_lab2), FadeIn(m2), FadeIn(tag2), run_time=1.0)
        carry_over(self, axis, q_lab2, iv, tag2, wb, dot, m2, test, tbox)
