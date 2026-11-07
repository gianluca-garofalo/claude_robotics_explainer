"""Scene 3 (body, chapter "What is left to pay"; v7): the roadmap, then the pretraining segment, five concepts, each
named on its own object as it is said and followed by a held pause: the window (a plan of a fixed number of steps;
only its first step is taken), the stage cost (each step's price, stacked as amber blocks), the end region (every
plan finishes inside it), the end cost (one last green block where a plan ends) and the remaining action (the
cheapest total over all plans, poured into the meter: its first fill, said aloud). Then a one-sentence summary and a
held pause, and only after it the line that combines them, V_N(q) = min[sum of stage costs + end cost], built from
the picture's pieces and held.

v7 against v6 (the pacing rules): the roadmap is new; the concepts come one at a time, about 20 s apart, each with
its label on its own object (pretraining exception of rule P4, conditions a-g); the candidate plans and their totals
show "the cheapest of all plans" instead of saying it; the equation is the short form (three new symbols, not
eight), after the summary; the misconception and the think prompt moved to the next chapter.

Explainer: Sections 1.1-1.3 and 2.1 (sec-idea, sec-problem, sec-steps, sec-window): the window problem (5).
Schematic picture: no number is shown with the bars (the meter shows its label alone).
"""
import numpy as np
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_draw import HOOK_ANGLE0
from ep01_world import (BILL, BODY_AXES, BODY_C, EQ_Y, PLAN_COSTS, PLAN_Q, PLAN_W, SCALE, X_AFTER, block,
                        body_point, level, make_meter, omega, plan_path, the_dot)

SLOT_Y, SLOT_X, SLOT = -1.95, -2.3, 0.42
CHIP_Y = 3.15
ALT_TOTALS = (0.56, 0.63)                 # the other two plans' totals (schematic heights, more than BILL)
ALT_X = (1.25, 2.2)


def slots(colors):
    """The window as a row of slots, one per planned step (None: an empty, dashed slot)."""
    row = VGroup()
    for c in colors:
        sq = Square(SLOT)
        if c is None:
            sq = DashedVMobject(sq, num_dashes=12).set_stroke(MUTED, width=4)
        else:
            sq.set_stroke(c, width=4).set_fill(c, opacity=0.85)
        row.add(sq)
    return row.arrange(RIGHT, buff=0.12).move_to([SLOT_X, SLOT_Y, 0])


def chip(text):
    t = Text(text, font_size=26, color=INK)
    frame = RoundedRectangle(width=t.width + 0.5, height=t.height + 0.32, corner_radius=0.12, color=MUTED,
                             stroke_width=2)
    return VGroup(frame, t.move_to(frame))


def alt_plan(qs, angles, width=5):
    """Another plan from the same start: points at sizes qs and angles (degrees) in the body's plane, dashed."""
    pts = [BODY_C + np.array([q * BODY_AXES[0] * np.cos(np.radians(a)), q * BODY_AXES[1] * np.sin(np.radians(a)), 0])
           for q, a in zip(qs, angles)]
    segs = VGroup(*[DashedLine(a, b, dash_length=0.12).set_stroke(MUTED, width=width) for a, b in zip(pts[:-1], pts[1:])])
    dots = VGroup(*[Dot(p, radius=0.08, color=MUTED) for p in pts[1:]])
    return VGroup(segs, dots)


class Bill(RAScene):
    def construct(self):
        v = ValueTracker(0.0)
        om = omega()
        dot = the_dot(body_point(PLAN_Q[0], 0))
        m = make_meter(v.get_value)
        self.carry_in(om, m, dot)                                   # the title beat's last frame

        # the roadmap: three moves, each chip comes up as it is named
        chips = VGroup(chip("the bill"), chip("why it falls"), chip("one test")).arrange(RIGHT, buff=0.5)
        chips.move_to([-0.6, CHIP_Y, 0])
        arrows = VGroup(*[Arrow(chips[i].get_right(), chips[i + 1].get_left(), buff=0.08, stroke_width=3,
                                color=MUTED, max_tip_length_to_length_ratio=0.3) for i in range(2)])
        track = DashedLine(chips.get_left() + DOWN * 0.5, chips.get_right() + DOWN * 0.5, dash_length=0.14)
        track.set_stroke(MUTED, width=3, opacity=0.7)               # the route the three chips sit on
        self.play(FadeIn(chips[0], shift=DOWN * 0.1), run_time=0.8)      # the picture first, then the words
        with self.voiceover(text="<bookmark mark='road'/>Here's the route we'll take. First, the bill, what the controller "
                                 "still has to pay. <bookmark mark='r2'/>Then why one step always lowers it. "
                                 "<bookmark mark='r3'/>And last, the one test behind it all, checked on an "
                                 "example. [pause 1.6]") as tr:
            t_r2 = max(until(tr, "r2", 1.6), 1.6)
            self.play(Create(track), run_time=t_r2 * 0.6)
            self.play(Indicate(m.frame, scale_factor=1.05, color=qcolor("V")), run_time=t_r2 * 0.4)
            self.wait_until_bookmark("r2")
            self.play(GrowArrow(arrows[0]), FadeIn(chips[1], shift=DOWN * 0.1), run_time=0.8)
            self.wait_until_bookmark("r3")
            self.play(GrowArrow(arrows[1]), FadeIn(chips[2], shift=DOWN * 0.1), run_time=0.8)

        # concept 1: the window (a plan of a fixed number of steps; only the first is taken)
        plan = plan_path(PLAN_Q)
        q_lab = attach(MathTex("q", font_size=40), dot, direction=UP, buff=0.18)
        L = qcolor("L_d")
        row = slots([None, None, None, None])
        filled = slots([INK, INK, INK, INK])
        win_lab = attach(Text("window", font_size=28, color=INK), row, direction=RIGHT, buff=0.3)
        with self.voiceover(text="[slow] From where it stands, the controller plans a few steps ahead. "
                                 "<bookmark mark='win'/>That's its window, and every plan it makes has the same "
                                 "number of steps. [pause 1.6]") as tr:
            self.play(FadeOut(VGroup(chips, arrows, track)), run_time=0.6)
            self.play(Create(plan[0], lag_ratio=1.0), FadeIn(plan[1], lag_ratio=0.5),
                      run_time=max(until(tr, "win", 1.5) - 0.3, 1.2))
            self.wait_until_bookmark("win")
            self.play(Create(row), FadeIn(win_lab), FadeIn(q_lab), run_time=1.0)
            rt = max(tr.get_remaining_duration() / 4, 0.4)
            for seg, sq, full in zip(plan[0], row, filled):
                self.play(TransformFromCopy(seg, full), FadeOut(sq), run_time=rt)
        row = filled
        p1 = body_point(PLAN_Q[1], 1)
        replan = VGroup(*[DashedLine(a, b, dash_length=0.1).set_stroke(MUTED, width=3) for a, b in zip(
            [p1, body_point(0.6, 2), body_point(0.45, 3)], [body_point(0.6, 2), body_point(0.45, 3),
                                                         body_point(0.27, 4)])])
        with self.voiceover(text="But it only ever takes the first of those steps. <bookmark mark='nx'/>Then it throws "
                                 "the rest away, and plans again from wherever it lands. [pause 1.6]") as tr:
            ghost = dot.copy().set_opacity(0.5)
            self.play(plan[0][0].animate.set_stroke(width=9), row[0].animate.set_fill(L, opacity=0.9).set_stroke(L),
                      run_time=1.0)
            self.play(MoveAlongPath(ghost, Line(dot.get_center(), p1)), run_time=max(until(tr, "nx", 1.0), 1.0))
            self.wait_until_bookmark("nx")
            self.play(VGroup(*plan[0][1:], *plan[1][1:]).animate.set_opacity(0.25), run_time=1.0)
            self.play(Create(replan, lag_ratio=1.0), run_time=max(tr.get_remaining_duration() - 0.6, 1.0))
            self.play(FadeOut(VGroup(ghost, replan)), VGroup(*plan[0][1:], *plan[1][1:]).animate.set_opacity(1.0),
                      plan[0][0].animate.set_stroke(width=5),
                      row[0].animate.set_fill(INK, opacity=0.85).set_stroke(INK), run_time=0.8)

        # concept 2: the stage cost (each step's price), and the costs piling up beside the meter
        rays = VGroup(*[DashedLine(om[1].get_center(), d.get_center(), dash_length=0.1).set_stroke(MUTED, 3)
                        for d in [dot, *plan[1]]])
        stage_lab = Text("stage cost", font_size=28, color=L)
        stage_lab.next_to(plan[0][1], UP, buff=0.25)
        stage_lab = attach(stage_lab, plan[0][1])
        with self.voiceover(text="[slow] Every step costs something. <bookmark mark='stage'/>That price is called "
                                 "the stage cost. [pause 1.2]") as tr:
            self.play(FadeOut(VGroup(row, win_lab)),
                      LaggedStart(*[seg.animate.set_stroke(L, width=6) for seg in plan[0]], lag_ratio=0.5),
                      run_time=max(until(tr, "stage", 1.0) - 0.1, 0.8))
            self.wait_until_bookmark("stage")
            self.play(FadeIn(stage_lab), plan[0][1].animate.set_stroke(width=9), run_time=1.0)
            self.play(plan[0][1].animate.set_stroke(width=6), run_time=max(tr.get_remaining_duration(), 0.5))
        with self.voiceover(text="You pay for how fast the step moves. And you pay for how far it is from the target. "
                                 "<bookmark mark='sp'/>Take a small step near the target. It costs very little. "
                                 "[pause 1.6]") as tr:
            t1 = until(tr, "sp", 2.0)
            self.play(LaggedStart(*[seg.animate.set_stroke(width=9) for seg in plan[0]], lag_ratio=0.4),
                      run_time=max(t1 * 0.4, 0.8))
            self.play(LaggedStart(*[seg.animate.set_stroke(width=6) for seg in plan[0]], lag_ratio=0.3),
                      LaggedStart(*[Create(r) for r in rays], lag_ratio=0.3), run_time=max(t1 * 0.6, 1.0))
            self.wait_until_bookmark("sp")
            self.play(plan[0][-1].animate.set_stroke(width=10), rays[-1].animate.set_stroke(width=5),
                      run_time=max(tr.get_remaining_duration() * 0.6, 0.8))
            self.play(plan[0][-1].animate.set_stroke(width=6), FadeOut(rays), run_time=max(tr.get_remaining_duration(),
                                                                                           0.5))
        blocks, y = VGroup(), level(0.0)
        for c in PLAN_COSTS:
            b = block(c, L, bottom=y)
            blocks.add(b)
            y += b.height
        with self.voiceover(text="<bookmark mark='pile'/>Step after step, those costs pile up, like charges on "
                                 "a bill. [pause 1.6]") as tr:
            rt = max((tr.get_remaining_duration() - 0.6) / len(blocks), 0.5)
            for seg, b in zip(plan[0], blocks):
                self.play(TransformFromCopy(seg, b), run_time=rt)
            self.play(stage_lab.animate.next_to(blocks, LEFT, buff=0.3), run_time=0.6)
        stage_lab.ra_attached_to = blocks

        # concept 3: the end region (every plan finishes inside it)
        reg_lab = attach(Text("end region", font_size=28, color=qcolor("W")), om[0], direction=DOWN, buff=0.22)
        alts = VGroup(alt_plan([1.0, 0.86, 0.66, 0.46, 0.24], [HOOK_ANGLE0, 128, 92, 52, 12]),
                      alt_plan([1.0, 0.8, 0.6, 0.42, 0.25], [HOOK_ANGLE0, 175, 200, 225, 245]))
        self.play(om[0].animate.set_stroke(width=7), run_time=0.9)                 # the picture first
        with self.voiceover(text="[slow] A plan can't stop just anywhere, though. <bookmark mark='reg'/>It has "
                                 "to finish inside the end region, a small region around the target. "
                                 "[pause 1.6]") as tr:
            self.play(om[0].animate.set_stroke(width=7), run_time=max(until(tr, "reg", 1.0) - 0.2, 0.8))
            self.wait_until_bookmark("reg")
            self.play(om[0].animate.set_fill(opacity=0.32).set_stroke(width=5), FadeIn(reg_lab), run_time=1.0)
            ghost = dot.copy().set_opacity(0.5)
            route = VMobject().set_points_as_corners([dot.get_center()] + [d.get_center() for d in plan[1]])
            self.play(MoveAlongPath(ghost, route), run_time=max(tr.get_remaining_duration() - 0.3, 1.0))
            self.play(FadeOut(ghost), run_time=0.3)
        with self.voiceover(text="<bookmark mark='cand'/>Here are a few other plans. The controller could pick "
                                 "any of them. <bookmark mark='c2'/>Each one has the same number of steps. And "
                                 "every one of them ends in there. [pause 1.6]") as tr:
            g1 = dot.copy().set_opacity(0.5)
            r1 = VMobject().set_points_as_corners([dot.get_center()] + [d.get_center() for d in alts[0][1]])
            self.play(Create(alts[0][0], lag_ratio=1.0), FadeIn(alts[0][1], lag_ratio=0.5), MoveAlongPath(g1, r1),
                      run_time=max(until(tr, "c2", 1.2), 1.2))
            self.remove(g1)
            self.wait_until_bookmark("c2")
            g2 = dot.copy().set_opacity(0.5)
            r2 = VMobject().set_points_as_corners([dot.get_center()] + [d.get_center() for d in alts[1][1]])
            self.play(Create(alts[1][0], lag_ratio=1.0), FadeIn(alts[1][1], lag_ratio=0.5), MoveAlongPath(g2, r2),
                      run_time=max(tr.get_remaining_duration() * 0.6, 1.2))
            self.remove(g2)
            self.play(LaggedStart(*[a[1][-1].animate.scale(1.6) for a in alts], plan[1][-1].animate.scale(1.6),
                                  lag_ratio=0.2), run_time=max(tr.get_remaining_duration() * 0.5, 0.6))
            self.play(LaggedStart(*[a[1][-1].animate.scale(1 / 1.6) for a in alts],
                                  plan[1][-1].animate.scale(1 / 1.6), lag_ratio=0.2),
                      run_time=max(tr.get_remaining_duration(), 0.5))

        # concept 4: the end cost (one last charge where a plan ends), then every plan's own total
        wb = block(PLAN_W, qcolor("W"), bottom=y)
        end_lab = attach(Text("end cost", font_size=28, color=qcolor("W")), wb, direction=LEFT, buff=0.3)
        end_dot = plan[1][-1]
        self.play(end_dot.animate.set_color(qcolor("W")).scale(1.5), run_time=0.9)  # the picture first
        with self.voiceover(text="[slow] Where a plan finishes, there's one last charge, for whatever is still "
                                 "left to do from there. <bookmark mark='end'/>That charge is the end cost. "
                                 "[pause 1.6]") as tr:
            self.play(TransformFromCopy(end_dot, wb), run_time=max(until(tr, "end", 1.2) - 0.2, 1.0))
            self.wait_until_bookmark("end")
            self.play(FadeIn(end_lab), wb.animate.set_stroke(width=6), run_time=1.0)
            self.play(end_dot.animate.scale(1 / 1.5), wb.animate.set_stroke(width=2),
                      run_time=max(tr.get_remaining_duration(), 0.5))
        totals = VGroup(*[DashedVMobject(Rectangle(width=0.6, height=t * SCALE).move_to(
            [x, level(0.0) + t * SCALE / 2, 0]), num_dashes=28).set_stroke(MUTED, width=3)
            for t, x in zip(ALT_TOTALS, ALT_X)])
        with self.voiceover(text="<bookmark mark='tot'/>Now add it all up. Every plan gets its own total, its own "
                                 "bill. [pause 2.5]") as tr:
            self.play(FadeOut(VGroup(stage_lab, end_lab)), run_time=0.5)
            rt = max((tr.get_remaining_duration() - 0.2) / 2, 0.8)
            for a, t in zip(alts, totals):
                self.play(TransformFromCopy(a[0], t), run_time=rt)

        # concept 5: the remaining action, the cheapest total, poured into the meter (its first fill, said aloud)
        bill = VGroup(blocks, wb)
        ra_lab = attach(Text("remaining action", font_size=28, color=qcolor("V")), m.frame, direction=UP, buff=0.25)
        best = SurroundingRectangle(bill, color=INK, buff=0.08, stroke_width=3)
        self.play(Create(best), run_time=1.0)                       # the picture first: the cheapest stack
        with self.voiceover(text="[slow] The cheapest of those totals has a name. <bookmark mark='ra'/>It's called "
                                 "the remaining action. [pause 1.2]") as tr:
            self.play(FadeOut(alts), FadeOut(totals), run_time=max(until(tr, "ra", 1.0) - 0.05, 0.8))
            self.wait_until_bookmark("ra")
            self.play(FadeIn(ra_lab), run_time=1.0)
        with self.voiceover(text="That total is what's left to pay from here. <bookmark mark='n'/>Now look at the "
                                 "meter. It shows exactly that total. [pause 1.6]") as tr:
            self.play(best.animate.set_stroke(width=5), run_time=max(until(tr, "n", 0.8), 0.8))
            self.wait_until_bookmark("n")                  # the bill pours into the meter as the words say so
            rt = max(tr.get_remaining_duration(), 1.6)
            self.play(v.animate.set_value(BILL), FadeOut(bill), FadeOut(best), run_time=rt * 0.7)
            self.play(Indicate(ra_lab, scale_factor=1.06, color=qcolor("V")), run_time=min(rt * 0.3, 0.8))

        # the summary (end of the pretraining segment), then the line that combines the concepts
        with self.voiceover(text="<bookmark mark='sum'/>In short, the bill is the cheapest plan's stage costs "
                                 "plus its end cost. [pause 2]") as tr:
            rt = max(tr.get_remaining_duration(), 2.0)
            self.play(LaggedStart(*[seg.animate.set_stroke(width=8) for seg in plan[0]],
                                  end_dot.animate.scale(1.4), lag_ratio=0.3), run_time=rt * 0.6)
            self.play(LaggedStart(*[seg.animate.set_stroke(width=6) for seg in plan[0]],
                                  end_dot.animate.scale(1 / 1.4), lag_ratio=0.2), run_time=rt * 0.4)
        vn = ceq(r"V_N(q)", r"=", r"\min", r"\Big[", r"\sum L_d", r"+", r"W", r"\Big]", font_size=44)
        vn.move_to([-1.6, EQ_Y + 0.05, 0])
        self.play(TransformFromCopy(m.frame, vn[0]), FadeIn(vn[1]), run_time=0.8)      # the picture first
        with self.voiceover(text="<bookmark mark='eq'/>In symbols, it's this. You add up the stage costs, "
                                 "<bookmark mark='w'/>add the end cost, <bookmark mark='mn'/>and take the cheapest "
                                 "plan. [pause 1.8]") as tr:
            self.play(TransformFromCopy(plan[0], vn[4]), run_time=max(until(tr, "w", 1.0), 1.0))
            self.wait_until_bookmark("w")
            self.play(FadeIn(vn[5]), TransformFromCopy(end_dot, vn[6]), run_time=max(until(tr, "mn", 0.8), 0.8))
            self.wait_until_bookmark("mn")
            self.play(FadeIn(vn[2]), FadeIn(vn[3]), FadeIn(vn[7]), run_time=max(tr.get_remaining_duration(), 0.8))
        self.read(vn)
        carry_over(self, om, dot, m, plan, q_lab, reg_lab)
