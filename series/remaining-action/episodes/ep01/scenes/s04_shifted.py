"""Scene 4 (body, chapter "Why the bill falls"; v7): the tempting thought (re-planning with the best plan is enough)
and why it says nothing about tomorrow's bill; the main think prompt, held 4 s; then the answer, the old plan shifted
by one step: the rest of it still ends in the region and costs today's bill minus the step paid; it is one step
short, so one reference step is added inside the region; the one condition (the end cost falls along that step by at
least its cost) makes the extra step pay for itself; the best plan from the new point costs no more. The bars become
one line, then the descent, boxed and held 3 s (a still picture), restated in plain words, the window length never
used, and a one-sentence summary.

v7 against v6 (the pacing rules): the misconception and the think prompt open this chapter (v6: the end of Bill),
the prompt says "pause here if you like" and is held 4 s; the argument is read as slow blocks with a pause after each
step; the descent is held 3 s, still, then restated; the bonus, the slice and the stability names moved to the next
chapter, so each gets its own time.

Explainer: Section 3.2 (sec-descent), the proof with an explicit candidate (shift the path, extend it by one
reference step, use A2). Schematic picture and bar heights (no number is shown with them).
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_world import (REF_FRAC, BEST_NEXT, BILL, BODY_C, EQ_Y, PLAN_COSTS, PLAN_Q, PLAN_W, REF_COST, REF_W, X_AFTER, X_LABEL,
                        block, body_point, descent_line, level, make_meter, omega, plan_path, the_dot)

SLOT_Y, SLOT_X, SLOT = -1.95, -2.3, 0.42


def slots(colors):
    """The window as a row of slots, one per planned step: a colour fills a slot, None leaves it empty (dashed)."""
    row = VGroup()
    for c in colors:
        sq = Square(SLOT)
        if c is None:
            sq = DashedVMobject(sq, num_dashes=12).set_stroke(MUTED, width=4)
        else:
            sq.set_stroke(c, width=4).set_fill(c, opacity=0.85)
        row.add(sq)
    return row.arrange(RIGHT, buff=0.12).move_to([SLOT_X, SLOT_Y, 0])


def world():
    """The last frame of s03: the region (filled) with its label, the amber plan, the dot at its start, its tag q."""
    om = omega()
    om[0].set_fill(opacity=0.32)
    reg_lab = attach(Text("end region", font_size=28, color=qcolor("W")), om[0], direction=DOWN, buff=0.22)
    plan = plan_path(PLAN_Q)
    for seg in plan[0]:
        seg.set_stroke(qcolor("L_d"), width=6)
    plan[1][-1].set_color(qcolor("W"))
    return om, reg_lab, plan


class ShiftedPlan(RAScene):
    def construct(self):
        v = ValueTracker(BILL)
        om, reg_lab, plan = world()
        dot = the_dot(body_point(PLAN_Q[0], 0))
        q_lab = attach(MathTex("q", font_size=40), dot, direction=UP, buff=0.18)
        m = make_meter(v.get_value)
        self.carry_in(om, reg_lab, plan, m, dot, q_lab)             # the last frame of s03
        L = qcolor("L_d")
        p1 = body_point(PLAN_Q[1], 1)

        # the tempting thought, and why it says nothing about tomorrow's bill
        wander = dot.copy().set_opacity(0.55)                       # a ghost wanders; the controller stays put
        alt = plan_path([PLAN_Q[1], 0.6, 0.47, 0.36, 0.25], k0=1, color=MUTED, width=4, dashed=True)
        alt2 = plan_path([0.6, 0.5, 0.4, 0.3, 0.22], k0=2, color=MUTED, width=4, dashed=True)
        with self.voiceover(text="Here's a tempting thought. The controller plans again at every step, and every "
                                 "plan is the best it can find. <bookmark mark='r'/>Surely that's enough to get "
                                 "there?") as tr:
            self.play(wander.animate.move_to(p1), run_time=1.4)
            t1 = until(tr, "r", 2.4)
            self.play(Create(alt[0]), FadeIn(alt[1]), run_time=t1 / 3)
            self.play(wander.animate.move_to(body_point(0.6, 2)), alt[0][0].animate.set_stroke(opacity=0.3),
                      run_time=t1 / 3)
            self.play(Create(alt2[0]), FadeIn(alt2[1]), run_time=t1 / 3)
            self.wait_until_bookmark("r")
            self.play(FadeOut(alt), FadeOut(alt2), FadeOut(wander), run_time=max(tr.get_remaining_duration(), 1.0))
        t = ValueTracker(BILL)
        sc = m.bar_height / m.vmax
        ghost = always_redraw(lambda: DashedVMobject(Rectangle(
            width=0.7, height=max(t.get_value(), 0.01) * sc).move_to(
            [X_AFTER, level(0.0) + max(t.get_value(), 0.01) * sc / 2, 0]), num_dashes=24).set_stroke(INK, width=4))
        ask = Text("tomorrow?", font_size=28, color=INK).move_to([X_AFTER, level(0.6) + 0.35, 0])
        with self.voiceover(text="Not on its own. Today's best plan says nothing about how tomorrow's bill "
                                 "compares with today's. <bookmark mark='o'/>Each new plan could just push the hard "
                                 "part a little further out, again and again. [pause 1.8]") as tr:
            self.play(FadeIn(ghost), run_time=max(self.time_until_word("tomorrow's"), 0.6))
            self.play(FadeIn(ask), t.animate.set_value(BILL * 0.9), run_time=until(tr, "o", 1.0),   # v8: on its word
                      rate_func=smooth)
            self.wait_until_bookmark("o")
            rt = max(tr.get_remaining_duration(), 2.0)
            self.play(t.animate.set_value(BILL * 1.1), run_time=rt / 3, rate_func=smooth)
            self.play(t.animate.set_value(BILL * 0.85), run_time=rt / 3, rate_func=smooth)
            self.play(t.animate.set_value(BILL * 1.05), run_time=rt / 3, rate_func=smooth)

        # the main think prompt, held still for 4 s
        first = plan[0][0]
        today = DashedLine([X_AFTER - 0.45, level(BILL), 0], [m.frame.get_right()[0] + 0.1, level(BILL), 0],
                           color=MUTED, stroke_width=3, dash_length=0.1)
        minus = DashedLine([X_AFTER - 0.45, level(BILL - PLAN_COSTS[0]), 0],
                           [m.frame.get_right()[0] + 0.1, level(BILL - PLAN_COSTS[0]), 0], color=L,
                           stroke_width=4, dash_length=0.1)
        with self.voiceover(text="[slow] Here's the real question, then. <bookmark mark='ask'/>After one step, is "
                                 "there a plan from the new point that costs no more than today's bill, <bookmark "
                                 "mark='m2'/>minus the step we just paid? Pause here if you like. [pause 4]") as tr:
            self.play(FadeOut(ask), FadeOut(q_lab), run_time=0.6)
            t1 = until(tr, "m2", 2.0)
            self.play(dot.animate.move_to(p1), first.animate.set_stroke(opacity=0.3), Create(today), run_time=t1 / 2)
            self.play(t.animate.set_value(BILL - PLAN_COSTS[0]), run_time=t1 / 2)
            self.wait_until_bookmark("m2")
            self.play(ReplacementTransform(today.copy(), minus), run_time=max(min(tr.get_remaining_duration(), 2.0),
                                                                             0.8))
        ghost.clear_updaters()

        # the answer: what is left of today's plan, after the step it just took
        guide = DashedLine([X_AFTER - 0.5, level(BILL), 0], [m.frame.get_right()[0] + 0.1, level(BILL), 0],
                           color=MUTED, stroke_width=3, dash_length=0.1)
        paid = block(PLAN_COSTS[0], L)
        paid_lab = attach(Text("step paid", font_size=28, color=L), paid, direction=LEFT, buff=0.3)
        with self.voiceover(text="<bookmark mark='yes'/>The answer is yes, and it's hiding in today's plan. "
                                 "<bookmark mark='p'/>The controller has taken its first step, and it's paid for "
                                 "it.") as tr:
            self.play(FadeOut(VGroup(ghost, minus)), ReplacementTransform(today, guide), run_time=0.8)
            self.play(first.animate.set_stroke(opacity=1.0, width=9), run_time=max(until(tr, "p", 1.0) - 0.1, 0.8))
            self.wait_until_bookmark("p")
            self.play(TransformFromCopy(first, paid), FadeIn(paid_lab), first.animate.set_stroke(opacity=0.3, width=6),
                      run_time=max(tr.get_remaining_duration(), 1.0))

        # the rest of the old plan: today's bill minus the step paid (a step of the descent argument)
        rest, y = VGroup(), level(PLAN_COSTS[0])
        for c in PLAN_COSTS[1:]:
            b = block(c, L, bottom=y)
            rest.add(b)
            y += b.height
        wold = block(PLAN_W, qcolor("W"), bottom=y)
        rest_brace = Brace(VGroup(rest, wold), LEFT, buff=0.08, color=INK)     # v7 (FC-8): only the part above
        rest_lab = Text("rest of the\nold plan", font_size=28, color=INK, line_spacing=0.8)  # the step paid
        rest_lab.next_to(rest_brace, LEFT, buff=0.15)
        route = VMobject().set_points_as_corners([p1] + [d.get_center() for d in plan[1][1:]])
        walker = dot.copy().set_opacity(0.55)
        with self.voiceover(text="[slow] The rest of that old plan still starts right here, and it still ends in "
                                 "the region. <bookmark mark='c'/>It costs exactly today's bill, minus the step "
                                 "we've already paid. [pause 1.8]") as tr:
            self.play(MoveAlongPath(walker, route), run_time=max(until(tr, "c", 1.4) - 0.1, 1.2))
            self.wait_until_bookmark("c")
            rt = max(tr.get_remaining_duration() - 0.6, 1.2)
            self.play(*[TransformFromCopy(seg, b) for seg, b in zip(plan[0][1:], rest)],
                      TransformFromCopy(plan[1][-1], wold), FadeOut(walker), run_time=rt)
            self.play(GrowFromCenter(rest_brace), FadeIn(rest_lab), run_time=0.6)

        # one step short: the window always plans the same number of steps; add a reference step inside the region
        end = plan[1][-1].get_center()
        ref_end = BODY_C + REF_FRAC * (end - BODY_C)
        ref = Arrow(end, ref_end, buff=0.0, color=INK, stroke_width=8, max_tip_length_to_length_ratio=0.25)
        row = slots([L, L, L, None])
        win_lab = attach(Text("window", font_size=28, color=MUTED), row, direction=RIGHT, buff=0.3)
        full = slots([L, L, L, INK])
        ref_lab = attach(Text("reference step", font_size=28, color=INK), ref)
        ref_lab.move_to([-1.6, -1.3, 0])                 # under the arrow (v7, round 5)
        with self.voiceover(text="But it's one step short, and the window always plans that many steps. "
                                 "<bookmark mark='ref'/>So we add one more step at the end, a reference step that "
                                 "stays inside the region. [pause 1.6]") as tr:
            self.play(FadeOut(reg_lab), FadeOut(paid_lab),
                      *[TransformFromCopy(seg, sq) for seg, sq in zip(plan[0][1:], row[:3])],
                      Create(row[3]), FadeIn(win_lab, shift=UP * 0.1), run_time=max(until(tr, "ref", 1.6) - 0.1, 1.2))
            self.wait_until_bookmark("ref")
            self.play(GrowArrow(ref), om[0].animate.set_fill(opacity=0.38),
                      run_time=max(self.time_until_word("reference step"), 0.6))
            self.play(FadeIn(ref_lab), run_time=0.5)                # v8: the label on its words
            self.play(TransformFromCopy(ref, full[3]), FadeOut(row[3]), run_time=max(tr.get_remaining_duration(), 0.8))
            row.remove(row[3])
            row.add(full[3])

        # the one condition: along the reference step the end cost falls by at least its cost
        ref_cost = block(REF_COST, L, bottom=wold.get_bottom()[1])
        wnew = block(REF_W, qcolor("W"), bottom=wold.get_bottom()[1] + REF_COST * (m.bar_height / m.vmax))
        extra = block(REF_COST, L, x=X_AFTER - 1.0, bottom=wold.get_bottom()[1])
        test_lab = Text("the test", font_size=28, color=qcolor("W"))
        test_lab.move_to([X_LABEL - 0.3, level(BILL) + 0.5, 0])
        old_top = DashedLine([X_AFTER - 0.5, wold.get_top()[1], 0], [X_AFTER + 0.5, wold.get_top()[1], 0],
                             color=qcolor("W"), stroke_width=4, dash_length=0.08)
        spare = Line(wnew.get_top() + RIGHT * 0.5, [X_AFTER + 0.5, wold.get_top()[1], 0], color=qcolor("W"),
                     stroke_width=8)
        with self.voiceover(text="[slow] Here's the one condition we need. It's a test on the end region "
                                 "alone. <bookmark mark='t'/>From every point of the region, there must be a reference "
                                 "step that stays inside, and along it, the end cost has to fall by at least what that "
                                 "step costs. [pause 1.8]") as tr:
            self.play(FadeOut(VGroup(rest_lab, rest_brace)), FadeOut(VGroup(row, win_lab)),
                      TransformFromCopy(ref, extra),
                      run_time=max(until(tr, "t", 1.2) - 0.1, 1.0))
            self.wait_until_bookmark("t")
            self.play(FadeIn(test_lab), Create(old_top), run_time=0.8)
            self.play(ReplacementTransform(VGroup(wold, extra), VGroup(ref_cost, wnew)),
                      run_time=max(tr.get_remaining_duration(), 1.0))
        with self.voiceover(text="[slow] <bookmark mark='f'/>Then the extra step pays for itself. <bookmark "
                                 "mark='io'/>In other words, its cost comes out of the end cost it saves. "
                                 "[pause 1.8]") as tr:
            self.play(Create(spare), ref_cost.animate.shift(LEFT * 0.9),           # v8 (VD-1): the cost steps out to
                      run_time=max(until(tr, "io", 1.0) - 0.1, 1.0))           # the left, clear of the meter
            cost_lab = attach(Text("its cost", font_size=28, color=L), ref_cost.copy().shift(LEFT * 0.9),
                              direction=LEFT, buff=0.25)
            saved_lab = Text("saved", font_size=28, color=qcolor("W"))
            saved_lab.next_to(cost_lab, UP, buff=0.3).align_to(cost_lab, RIGHT)
            saved_lab = attach(saved_lab, spare)
            self.wait_until_bookmark("io")
            old_box = DashedVMobject(Rectangle(width=0.7, height=wold.height).move_to(wold), num_dashes=24)
            old_box.set_stroke(qcolor("W"), width=3)
            self.play(Create(old_box), run_time=max(self.time_until_word("its cost"), 0.4))
            self.wait_until_word("its cost")
            self.play(FadeIn(cost_lab), run_time=0.5)
            self.play(spare.animate.set_stroke(width=11), run_time=max(self.time_until_word("saves"), 0.4))
            self.wait_until_word("saves")
            self.play(FadeIn(saved_lab), spare.animate.set_stroke(width=8), run_time=0.5)
            rt = max(tr.get_remaining_duration(), 2.4)               # the return spans the hold: no dead air
            self.play(ref_cost.animate.shift(RIGHT * 0.9), FadeOut(old_box), FadeOut(VGroup(cost_lab, saved_lab)),
                      run_time=rt)

        # the best plan from the new point can only be cheaper: one blue block, what is left to pay from there
        best = block(BEST_NEXT, qcolor("V"), bottom=level(PLAN_COSTS[0]))
        best_lab = Text("left to pay,\nfrom here", font_size=28, color=qcolor("V"), line_spacing=0.8)
        best_lab.next_to(best, LEFT, buff=0.3)
        best_lab.shift(LEFT * max(0.0, best_lab.get_right()[0] - (X_AFTER - 0.5)))
        shifted_route = VMobject().set_points_as_corners([p1] + [d.get_center() for d in plan[1][1:]] + [ref_end])
        walker = dot.copy().set_opacity(0.55)
        with self.voiceover(text="[slow] From the new point, then, there's a plan. It costs no more than today's "
                                 "bill, minus the step. <bookmark mark='b'/>And the best plan from there can only be "
                                 "cheaper still. [pause 1.8]") as tr:
            self.play(FadeOut(VGroup(old_top, spare, test_lab)), run_time=0.5)
            self.play(MoveAlongPath(walker, shifted_route), run_time=max(until(tr, "b", 1.4) - 0.1, 1.2))
            self.wait_until_bookmark("b")
            self.play(ReplacementTransform(VGroup(rest, ref_cost, wnew), best), FadeIn(best_lab), FadeOut(walker),
                      run_time=max(tr.get_remaining_duration(), 1.2))

        # the bars become one line, then the descent, boxed and held still
        ineq = ceq(r"V_N(q)", r"\ \ge\ ", r"L_d(q,q^+)", r"+", r"V_N(q^+)", font_size=44).move_to([-2.4, EQ_Y, 0])
        with self.voiceover(text="[slow] <bookmark mark='ln'/>Now read the bars as one line. <bookmark mark='a'/>Today's bill "
                                 "<bookmark mark='l'/>covers the first step's cost, <bookmark mark='n'/>plus "
                                 "everything that's left to pay from the new point, q plus. [pause 2]") as tr:
            self.play(paid.animate.set_stroke(width=4), run_time=max(until(tr, "a", 0.6) - 0.05, 0.5))
            self.wait_until_bookmark("a")
            self.play(TransformFromCopy(m.frame, ineq[0]), FadeIn(ineq[1]), run_time=0.9)
            self.wait_until_bookmark("l")
            self.play(TransformFromCopy(paid, ineq[2]), FadeIn(ineq[3]), run_time=0.9)
            self.wait_until_bookmark("n")
            self.play(TransformFromCopy(best, ineq[4]), run_time=max(tr.get_remaining_duration(), 0.9))
        desc = descent_line(font_size=44)
        desc.move_to([-2.4, EQ_Y, 0])
        box = SurroundingRectangle(desc, color=INK, buff=0.22, corner_radius=0.1)
        with self.voiceover(text="[slow] Move the step's cost to the other side. <bookmark mark='desc'/>After one "
                                 "step, what's left to pay has dropped by at least what that step cost. "
                                 "[pause 3]") as tr:
            derive(self, ineq, desc, run_time=max(until(tr, "desc", 2.0) + 0.8, 2.4), beat_s=0)
            self.play(Create(box), v.animate.set_value(BEST_NEXT), run_time=max(tr.get_remaining_duration(), 1.0))

        # in plain words: the drop on the meter covers the step paid
        drop_x = m.frame.get_right()[0] + 0.25
        bracket = VGroup(Line([drop_x, level(BILL), 0], [drop_x, level(BEST_NEXT), 0]),
                         Line([drop_x - 0.12, level(BILL), 0], [drop_x, level(BILL), 0]),
                         Line([drop_x - 0.12, level(BEST_NEXT), 0], [drop_x, level(BEST_NEXT), 0])
                         ).set_stroke(qcolor("V"), width=5)
        with self.voiceover(text="<bookmark mark='rs'/>Put plainly, each step lowers the bill by at least "
                                 "its cost. [pause 1.8]") as tr:
            self.play(Create(bracket), FadeOut(best_lab), run_time=1.0)
            self.play(paid.animate.next_to(bracket, RIGHT, buff=0.12).align_to(bracket, UP),
                      best.animate.align_to(m.frame, DOWN), run_time=max(tr.get_remaining_duration() - 0.2, 1.0))

        # for every window length: the argument never used how many steps the window has
        row = slots([INK])
        win_lab = attach(Text("window", font_size=28, color=MUTED), row, direction=RIGHT, buff=0.3)
        with self.voiceover(text="And notice what the argument never used. It never asked how many steps the "
                                 "window has. <bookmark mark='h'/>Short window or long, it goes through the same way. "
                                 "[pause 1.8]") as tr:
            self.play(FadeIn(row), FadeIn(win_lab), run_time=max(until(tr, "h", 1.0) - 0.1, 1.0))
            self.wait_until_bookmark("h")
            long_row = slots([L] * 9 + [INK])
            self.play(Transform(row, long_row), win_lab.animate.next_to(long_row, RIGHT, buff=0.3),
                      run_time=max(tr.get_remaining_duration() * 0.6, 1.0))
            self.play(Transform(row, slots([L] * 2 + [INK])), win_lab.animate.next_to(slots([L] * 2 + [INK]), RIGHT,
                                                                                       buff=0.3),
                      run_time=max(tr.get_remaining_duration(), 0.8))
        with self.voiceover(text="<bookmark mark='sum2'/>That's the whole argument. The old plan, shifted one "
                                 "step and capped with a reference step, is why the bill can only fall. [pause 1.8]") as tr:
            walker = dot.copy().set_opacity(0.55)
            self.play(FadeOut(VGroup(row, win_lab)), run_time=0.6)
            self.play(MoveAlongPath(walker, shifted_route), ref.animate.set_color(qcolor("W")),
                      run_time=max(tr.get_remaining_duration() - 0.4, 1.2))
            self.play(FadeOut(walker), run_time=0.4)
        carry_over(self, om, plan, ref, dot, m, desc, box, paid, bracket, best)
