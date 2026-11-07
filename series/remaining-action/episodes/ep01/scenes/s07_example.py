"""Scene 7 (body, chapter "One example, step by step"; v7): the test with numbers, on one coordinate. The scalar
example with no limits (the end region is the whole line) and the shortest window (one step): the end cost
W = 1.2 * 1/2 q^2 and the one-step bill V_1(q) drawn as bowls over the q axis, to the meter's scale (the dot on V_1
sits at the height the meter shows). The test at q = 1 (0.6 against 0.59: it passes); both bills grow with q
squared, so one point settles every point (a ghost point slides along with its two bars and a fixed ratio); then the
controller runs four logged steps from q = 1: the first one said with its numbers, the next three silent, the drop
(blue) beside the step's cost (amber) at every step, and the bill's level said at the end. Then the textbook end
cost (weight 1, the same convention) fails the test by a hair (its two bars at the start, and the scan's ratio
readout at 1.01 against the scan's 0.98: shown, not said; v7, FC-4), and a
one-sentence summary.

v7 against v6 (the pacing rules): six spoken numbers instead of seventeen (at most three in any 20 s, each on screen
as it is said: readouts at two decimals); the parameters on screen and said in words; three steps run silently;
the "region as large as we like" clause is gone (the example has no limits from the start); a pause after each
claim and a summary at the end.

Explainer: Sections 3.4 (sec-onestep, the one-step window) and 6.4 (sec-numeric, case B). Numbers: ep01_numbers.py
(closed forms of the example) checked against code/logs/note__sec4_3_one_step_example.py.log ('rect 1.2': the four
closed-loop steps; 'rect 1.0': the textbook weight).
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
import ep01_numbers as E
from ep01_world import (Q_DRAW, V_SCHEM, W_K, at, axis_label, bowl, end_bowl, make_meter, meter_guide,
                        omega_interval, pinned_test, q_axis, the_dot, vbar)

K1 = 0.5 * E.riccati(1)[1]           # V_1(q) = K1 q^2, the one-step bill of the example
assert abs(W_K - E.C * 0.5) < 1e-12  # the drawn end cost is the example's
PHI, Q_T = 0.7, 0.45                 # where s06 left the dot: the reference step's end from its test point


def v1(q):
    return K1 * q * q


def region_label(iv):
    return attach(Text("end region", font_size=28, color=qcolor("W")), iv[0], direction=DOWN, buff=0.3)


class Example(RAScene):
    def construct(self):
        q_in = PHI * Q_T
        v = ValueTracker(V_SCHEM * 0.035 ** 2)
        axis = q_axis()
        q_lab = axis_label(axis)
        iv = omega_interval()
        tag = region_label(iv)
        wb = end_bowl()
        dot = the_dot(at(q_in, W_K * q_in * q_in))
        m = make_meter(v.get_value)
        test, tbox = pinned_test()
        self.carry_in(axis, q_lab, iv, tag, wb, dot, m, test, tbox)             # the last frame of s06

        # the example: one coordinate, each step pays for its speed and its distance; no limits: the whole line

        one = Line(at(E.Q0, 0) + DOWN * 0.15, at(E.Q0, 0) + UP * 0.15, color=INK, stroke_width=5)
        one_lab = attach(Text(fmt(E.Q0), font_size=28), one, direction=UP, buff=0.15)
        with self.voiceover(text="Now it's time for numbers, on the simplest example there is. <bookmark mark='c'/>There's "
                                 "one coordinate, and every step pays for its speed and for its distance from the "
                                 "target, both with weight one. [pause 1.2]") as tr:
            self.play(dot.animate.move_to(at(0.0, 0.0)), run_time=max(until(tr, "c", 1.0) - 0.1, 1.0))
            self.wait_until_bookmark("c")
            self.play(Create(one), FadeIn(one_lab), run_time=1.0)
            self.play(dot.animate.move_to(at(E.Q0, 0)), run_time=max(tr.get_remaining_duration() * 0.5, 1.0))
            self.play(dot.animate.move_to(at(0.35, 0)), run_time=max(tr.get_remaining_duration(), 0.8))
        big = omega_interval(Q_DRAW)
        big[1].set_stroke(opacity=0.0)               # the whole drawn line: no end tick beside the "1"
        big_tag = region_label(big)
        big_tag.next_to(at(-Q_DRAW, 0), DOWN, buff=0.3).shift(RIGHT * 1.0)
        with self.voiceover(text="<bookmark mark='reg2'/>Nothing limits the steps here. And the end region is the "
                                 "whole line. [pause 1.2]") as tr:
            self.play(Transform(iv, big), Transform(tag, big_tag), run_time=max(tr.get_remaining_duration(), 1.2))

        # the end cost, weight 1.2; a guess first, then the test at the start: 0.6 against 0.59
        wq = Text(f"end cost weight {fmt(E.C)}", font_size=28, color=qcolor("W")).move_to([0.9, -3.05, 0])
        w_full = bowl(W_K, qcolor("W"))
        with self.voiceover(text="<bookmark mark='w'/>The end cost is the usual quadratic, scaled up by a weight "
                                 "of one point two. [pause 1.2]") as tr:
            self.play(FadeIn(wq, shift=UP * 0.1), run_time=1.0)
            self.play(Transform(wb, w_full), run_time=max(tr.get_remaining_duration(), 1.2))
        with self.voiceover(text="[slow] Before we compute anything, make a guess. <bookmark mark='ask4'/>With a "
                                 "single step to plan, will this end cost pass the test? [pause 3.8]") as tr:
            self.play(Indicate(VGroup(test, tbox), color=INK, scale_factor=1.08), run_time=max(until(tr, "ask4", 1.0),
                                                                                                 1.0))
            self.play(dot.animate.move_to(at(E.Q0, 0)), run_time=max(tr.get_remaining_duration() - 0.2, 1.0))
        vb = bowl(K1, qcolor("V"))
        w_lab = readout("end cost", lambda: E.W_Q0, decimals=2, color=qcolor("W"), font_size=28)
        w_lab.add_updater(lambda r: r.move_to(at(E.Q0, E.W_Q0) + LEFT * 2.35 + UP * 0.05))
        guide = always_redraw(lambda: meter_guide(dot.get_center(), m))
        with self.voiceover(text="Take the shortest window, a single step, and put the controller at one. "
                                 "<bookmark mark='ex'/>The end cost there is zero point six, and the best one-step "
                                 "bill is about zero point five nine, <bookmark mark='lw'/>lower, so the test "
                                 "passes. [pause 2.8]") as tr:
            self.play(dot.animate.move_to(at(E.Q0, E.W_Q0)), run_time=max(until(tr, "ex", 1.0) - 0.9, 1.0))
            self.play(FadeIn(w_lab), run_time=0.8)
            self.wait_until_bookmark("ex")
            t1 = until(tr, "lw", 1.6)
            self.play(Create(vb), dot.animate.move_to(at(E.Q0, E.V1_Q0)), v.animate.set_value(E.V1_Q0),
                      run_time=max(t1 * 0.35, 0.8))
            m.swap_readout(self, True, max(t1 * 0.2, 0.4))
            self.wait_until_bookmark("lw")
            self.play(Indicate(VGroup(test, tbox), color=INK, scale_factor=1.08), run_time=max(
                tr.get_remaining_duration(), 0.8))
        self.add(guide)
        self.play(FadeIn(guide), run_time=1.0)

        # the controller runs: four logged steps; drop (blue) beside cost (amber), drawn to scale on the bowl.
        # The two readouts change together, in the frame the step's two bars appear.
        c = ValueTracker(E.LOOP[0][2])
        d = ValueTracker(-E.LOOP[0][3])
        cost_ro = readout("this step", c.get_value, decimals=2, color=qcolor("L_d"), font_size=28)
        drop_ro = readout("drop", d.get_value, decimals=2, color=qcolor("V"), font_size=28)
        x_ro = -2.9
        cost_ro.add_updater(lambda r: r.shift([x_ro - r.get_left()[0], 2.45 - r.get_y(), 0]))
        drop_ro.add_updater(lambda r: r.shift([x_ro - r.get_left()[0], 1.85 - r.get_y(), 0]))
        trail = VGroup()
        self.add(trail)

        def one_step(k, rt, extra=()):
            q0, v0, cst, dv = E.LOOP[k]
            q1 = E.LOOP[k + 1][0]
            path = bowl(K1, qcolor("V"), q0=q1, q1=q0).reverse_direction()
            self.play(MoveAlongPath(dot, path), v.animate.set_value(v0 + dv), run_time=rt * 0.55)
            c.set_value(cst)                                   # both readouts, at once, with the two bars
            d.set_value(-dv)
            old = DashedLine(at(q0, v0), at(q1, v0) + LEFT * 0.9, dash_length=0.1, color=MUTED, stroke_width=3)
            drop = vbar(q1, v0 + dv, v0, qcolor("V"), dx=-0.35)        # inside the bowl, left of the dot
            cost = vbar(q1, v0 + dv, v0 + dv + cst, qcolor("L_d"), dx=-0.7)
            base = DashedLine(at(q1, v0 + dv), at(q1, v0 + dv) + LEFT * 0.9, dash_length=0.1, color=MUTED,
                              stroke_width=3)
            self.play(Create(old), Create(base), Create(drop), GrowFromEdge(cost, DOWN), *extra, run_time=rt * 0.45)
            trail.add(Dot(at(q1, 0), radius=0.07, color=INK))
            return VGroup(old, base, drop, cost)

        self.play(FadeOut(w_lab), run_time=0.6)                                 # the picture first
        with self.voiceover(text="Now let's run the controller, one step at a time. <bookmark mark='s'/>The first step costs about zero "
                                 "point one one, and the bill drops by about zero point one two. <bookmark "
                                 "mark='k'/>The drop covers the cost. [pause 1.8]") as tr:
            self.play(dot.animate.scale(1.25), run_time=max(until(tr, "s", 0.6) - 0.05, 0.5))
            self.play(dot.animate.scale(1 / 1.25), run_time=0.3)
            self.wait_until_bookmark("s")
            self.play(FadeIn(cost_ro), FadeIn(drop_ro), run_time=0.5)     # v7 (round 5): the numbers first
            marks = one_step(0, max(until(tr, "k", 2.0), 2.0))
            self.wait_until_bookmark("k")
            self.play(FadeIn(trail[-1], scale=0.5), marks[2].animate.set_stroke(width=5),
                      run_time=max(tr.get_remaining_duration(), 0.8))
        for r in (cost_ro, drop_ro):                           # v7 (FC-5): at two decimals the second step would
            r.clear_updaters()                                 # read 0.09 against 0.09; the bars show drop > cost
        self.play(FadeOut(marks), FadeOut(VGroup(cost_ro, drop_ro)), run_time=0.4)
        marks = one_step(1, 2.6)
        for k in (2, 3):                                       # three more steps, silent: the picture says it
            self.play(FadeOut(marks), run_time=0.3)
            marks = one_step(k, 2.6)
        # the whole run on the meter: the total drop (blue bracket) against the four step costs stacked (amber)
        sc = m.bar_height / m.vmax
        top = m.level(E.LOOP[0][1])
        bot = m.level(E.LOOP[4][1])
        bx = m.frame.get_right()[0] + 0.25
        bracket = VGroup(Line([bx, top, 0], [bx, bot, 0]), Line([bx - 0.12, top, 0], [bx, top, 0]),
                         Line([bx - 0.12, bot, 0], [bx, bot, 0])).set_stroke(qcolor("V"), width=5)
        costs, y = VGroup(), top
        for k in range(4):
            h = E.LOOP[k][2] * sc
            costs.add(Rectangle(width=0.3, height=h, stroke_width=2, stroke_color=qcolor("L_d"),
                                fill_color=qcolor("L_d"), fill_opacity=0.85).move_to([bx + 0.4, y - h / 2, 0]))
            y -= h
        with self.voiceover(text="<bookmark mark='dd'/>At every step, the bill fell by more than that step cost. "
                                 "Now it's down to about zero point two four. [pause 1.8]") as tr:
            self.play(FadeIn(trail[-1], scale=0.5), Create(bracket), run_time=1.0)
            self.play(LaggedStart(*[GrowFromEdge(b, UP) for b in costs], lag_ratio=0.6),
                      run_time=max(tr.get_remaining_duration() - 0.2, 1.2))

        # why one point settles every point: a ghost point slides along the bowls; the ratio never changes
        qt = ValueTracker(E.Q0)
        ghost = always_redraw(lambda: Dot(at(qt.get_value(), v1(qt.get_value())), radius=0.12, color=INK)
                              .set_opacity(0.5))
        bars = always_redraw(lambda: VGroup(
            vbar(qt.get_value(), 0.0, W_K * qt.get_value() ** 2, qcolor("W"), dx=0.09, width=0.14),
            vbar(qt.get_value(), 0.0, v1(qt.get_value()), qcolor("V"), dx=-0.09, width=0.14)))
        ratio = readout("one-step bill \u00f7 end cost", lambda: v1(qt.get_value()) / (W_K * qt.get_value() ** 2),
                        decimals=2, font_size=28)
        ratio.add_updater(lambda r: r.shift([-4.5 - r.get_left()[0], 2.15 - r.get_y(), 0]))   # clear of the tall bars at 1
        with self.voiceover(text="[slow] Why does it pass at every point, and not only at one? <bookmark "
                                 "mark='ra'/>Both bills grow with the square of the distance, so their ratio never "
                                 "changes, and passing at one point means passing everywhere. [pause 2.2]") as tr:
            t0 = until(tr, "ra", 1.2)
            self.play(FadeOut(VGroup(marks, bracket, costs, one, one_lab)), run_time=min(t0 * 0.4, 1.0))  # bars at 1
            self.play(FadeIn(ghost), FadeIn(bars), FadeIn(ratio), run_time=max(t0 * 0.6 - 0.1, 0.6))
            self.wait_until_bookmark("ra")
            t1 = max(tr.get_remaining_duration(), 2.0)
            self.play(qt.animate.set_value(0.45), run_time=t1 * 0.4)
            self.play(qt.animate.set_value(-0.8), run_time=t1 * 0.35)
            self.play(qt.animate.set_value(0.85), run_time=t1 * 0.25)
        for x in (ghost, bars, ratio):
            x.clear_updaters()
        self.play(FadeOut(VGroup(ghost, bars, ratio)), run_time=0.6)

        # the tease: the textbook end cost (weight 1, the same convention) fails the test by a hair
        tb = bowl(E.W_TEXTBOOK, qcolor("W"))                      # weight 1: W = 1/2 q^2 (W_TEXTBOOK at q = 1)
        vtb = bowl(E.V1_TEXTBOOK, qcolor("V"))                    # its one-step bill (V1_TEXTBOOK at q = 1)
        tw = Text("textbook weight 1", font_size=28, color=qcolor("W")).move_to([-1.9, 3.05, 0])
        p_v = Dot(at(E.Q0, E.V1_TEXTBOOK), radius=0.1, color=qcolor("V"))
        cross = VGroup(Line(UL, DR), Line(UR, DL)).scale(0.16).set_stroke(RED, width=6)
        fails = Text("fails", font_size=28, color=RED)
        tag_f = VGroup(cross, fails).arrange(RIGHT, buff=0.15).next_to(tw, RIGHT, buff=0.6)
        guide.clear_updaters()
        m.swap_readout(self, False, 0.7, FadeOut(guide), FadeOut(dot), FadeOut(trail), FadeOut(wq))   # FC-1, round 4
        self.play(FadeIn(tw), Transform(wb, tb), Transform(vb, vtb), run_time=2.8)    # the picture first
        with self.voiceover(text="What about the plain textbook end cost, with weight one? <bookmark mark='tb'/>It "
                                 "fails this test, by a hair. [pause 1.8]") as tr:
            self.play(wb.animate.set_stroke(width=9), run_time=max(until(tr, "tb", 1.0) - 0.1, 0.8))
            self.wait_until_bookmark("tb")
            self.play(FadeIn(tag_f), FadeIn(p_v, scale=0.5), run_time=0.5)
            self.play(wb.animate.set_stroke(width=6), run_time=max(tr.get_remaining_duration(), 0.8))
        # v7 (FC-4): the two bills at the start as bars to scale, and the same ratio readout as the scan's, now above 1
        tb_bars = VGroup(vbar(E.Q0, 0.0, E.W_TEXTBOOK, qcolor("W"), dx=0.09, width=0.14),
                         vbar(E.Q0, 0.0, E.V1_TEXTBOOK, qcolor("V"), dx=-0.09, width=0.14))
        tb_ratio = readout("one-step bill \u00f7 end cost", lambda: E.V1_TEXTBOOK / E.W_TEXTBOOK, decimals=2,
                           font_size=28)
        tb_ratio.add_updater(lambda r: r.shift([-4.5 - r.get_left()[0], 2.15 - r.get_y(), 0]))
        with self.voiceover(text="At the start, its one-step bill comes out just above its end cost. <bookmark "
                                 "mark='why'/>Why? That's a story for a later episode. [pause 1.8]") as tr:
            rt = max(until(tr, "why", 2.0), 2.0)
            self.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in tb_bars], lag_ratio=0.4), run_time=rt * 0.55)
            self.play(FadeIn(tb_ratio), run_time=rt * 0.45)
            self.wait_until_bookmark("why")
            self.play(p_v.animate.scale(1.3), run_time=max(tr.get_remaining_duration() * 0.5, 0.5))
            self.play(p_v.animate.scale(1 / 1.3), run_time=max(tr.get_remaining_duration(), 0.5))
        self.read()

        # back to weight 1.2: the summary; the controller where its four steps left it, the meter keeps that bill
        q4, v4 = E.LOOP[4][0], E.LOOP[4][1]
        here = the_dot(at(q4, v4))
        with self.voiceover(text="<bookmark mark='sum5'/>So with weight one point two, one check at one point is "
                                 "enough to certify the controller, for every window length. [pause 1.8]") as tr:
            tb_ratio.clear_updaters()
            self.play(FadeOut(VGroup(tw, p_v, tag_f, tb_bars, tb_ratio)), Transform(wb, bowl(W_K, qcolor("W"))),
                      Transform(vb, bowl(K1, qcolor("V"))), FadeIn(wq), run_time=1.2)
            self.play(FadeIn(here, scale=0.5), Indicate(VGroup(test, tbox), color=INK, scale_factor=1.08),
                      run_time=max(tr.get_remaining_duration(), 1.0))
        self.play(FadeOut(wq), run_time=0.6)                                  # the numbers ended before the aside
        carry_over(self, axis, q_lab, iv, tag, wb, vb, m, test, tbox, here)
