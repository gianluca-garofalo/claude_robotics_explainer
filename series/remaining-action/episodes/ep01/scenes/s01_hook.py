"""Scene 1 (hook; v7: reused from v6 with the pacing markup): a controller plans, takes one step, throws the plan away, again and again, while a meter of what
is left to pay drains. Why should it arrive? It could circle forever. Watch the meter: every step lowers it by at
least what that step costs, so it must arrive.

Explainer: Section 1.1 (sec-idea); the meter's level follows the one-step-window scheme of the scalar example
(ep01_numbers.LOOP: V_1(q_k) and L_d(q_k, q_k+1), checked against code/logs/note__sec4_3_one_step_example.py.log).
The picture is schematic in direction; the dot's distance from the rest point is proportional to q_k. v5 (VD-2,
FC-8): no number is shown in the hook (a schematic picture carries none); the numbers are named first in the worked
example, on the bowl. The one refill (the cut back to the start) is said aloud and declared in plan.json.
Opening rule: a full, moving picture from the first frame (self.add before the first play), about two seconds of
motion and music before the first word, the question by about 12 s, then the stakes and the meter.
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_draw import (DOT_R, FAST_TO, HOOK_ANGLE0, HOOK_AXES, HOOK_C, HOOK_TURN, TRAIL_W, ep_meter, hook_fan,
                       hook_point, hook_target)
from ep01_numbers import LOOP



def pictograms():
    """Original line-art: a robot arm, a legged robot, a car (Manim primitives only)."""
    s = dict(color=INK, stroke_width=4)
    base = Rectangle(width=0.5, height=0.14, **s)
    sh, el, wr = np.array([0, 0.07, 0]), np.array([0.32, 0.62, 0]), np.array([0.78, 0.42, 0])
    arm = VGroup(base, Line(sh, el, **s), Line(el, wr, **s), Dot(sh, radius=0.06, color=INK),
                 Dot(el, radius=0.06, color=INK), Line(wr, wr + [0.16, 0.1, 0], **s),
                 Line(wr, wr + [0.16, -0.1, 0], **s))
    body = RoundedRectangle(width=1.0, height=0.32, corner_radius=0.08, **s)
    head = Square(side_length=0.22, **s).next_to(body, RIGHT, buff=0.04).shift(UP * 0.18)
    legs = VGroup(*[VGroup(Line([x, -0.16, 0], [x + 0.1, -0.4, 0], **s), Line([x + 0.1, -0.4, 0], [x, -0.64, 0], **s))
                    for x in (-0.38, -0.2, 0.2, 0.38)])
    dog = VGroup(body, head, legs)
    car_body = RoundedRectangle(width=1.2, height=0.3, corner_radius=0.08, **s)
    cabin = Polygon([-0.3, 0.15, 0], [-0.15, 0.4, 0], [0.25, 0.4, 0], [0.4, 0.15, 0], **s)
    wheels = VGroup(Circle(radius=0.13, **s).move_to([-0.35, -0.2, 0]), Circle(radius=0.13, **s).move_to([0.35, -0.2, 0]))
    car = VGroup(car_body, cabin, wheels)
    row = VGroup(arm, dog, car).arrange(RIGHT, buff=0.7, aligned_edge=DOWN)
    return row.move_to([-3.6, -2.75, 0])


class Hook(RAScene):
    def construct(self):
        v = ValueTracker(LOOP[0][1])
        target = hook_target()
        m = ep_meter(v.get_value, show_value=False)          # v4: the number appears when the narration names it
        dot = Dot(hook_point(LOOP[0][0], 0), radius=DOT_R, color=INK)
        trail, ghosts = VGroup(), VGroup()
        fan = hook_fan(LOOP, 0)
        self.add(ghosts, target, trail, fan, m, dot)        # the first frame is already the whole picture
        state = {"k": 0, "fan": fan}

        def step(rt, keep=True, bloom=True, drain=False):
            """One controller step: move along the chosen plan's first step, the meter drops to V_1 there, the plan
            is swept away (kept as a faint ghost) and the next fan of plans blooms."""
            k = state["k"]
            nxt = hook_point(LOOP[k + 1][0], k + 1)
            seg = Line(dot.get_center(), nxt, color=INK, stroke_width=TRAIL_W)
            meter_anim = [v.animate.set_value(LOOP[k + 1][1])] if drain else []   # v7 (VD-9): held until it is named
            self.play(Create(seg), dot.animate.move_to(nxt), *meter_anim, run_time=rt * 0.55)
            self.remove(seg)
            trail.add(seg)
            old = state["fan"]
            anims = [old.animate.set_stroke(color=MUTED, width=2.5, opacity=0.2)] if keep else [FadeOut(old)]
            new = hook_fan(LOOP, k + 1) if bloom and k + 2 < len(LOOP) else None
            if new is not None:
                anims.append(Create(new))
            self.play(*anims, run_time=rt * 0.45)
            if keep:
                self.remove(old)
                ghosts.add(old)
            self.bring_to_front(dot)
            state["k"], state["fan"] = k + 1, new if new is not None else VGroup()

        step(0.7)                                           # about 1.4 s of motion before the first word
        step(0.7)
        with self.voiceover(text="Here's a controller that plans a whole path, takes one step, and throws "
                                 "the rest away. Then it does it again. [pause 0.6]") as tr:
            for i in range(3):
                step(max(tr.get_remaining_duration() / (3 - i), 0.8))
        question = title("Why should it ever arrive?")
        with self.voiceover(text="If it keeps changing its mind, <bookmark mark='q'/> why should it ever "
                                 "arrive? [pause 0.7]") as tr:
            step(1.2)
            self.wait_until_bookmark("q")
            self.play(FadeIn(question, shift=DOWN * 0.1), run_time=0.6)
            step(max(tr.get_remaining_duration(), 0.8))
        pics = pictograms()
        with self.voiceover(text="It's model predictive control, and it steers robot arms, legged robots "
                                 "and cars. [pause 0.6]") as tr:
            step(max(self.time_until_word("robot arms"), 0.8))     # v8: each pictogram on its own words
            for p, words in zip(pics, ("robot arms", "legged robots", "cars")):
                self.wait_until_word(words)
                self.play(FadeIn(p, shift=UP * 0.1), run_time=0.4)
            step(max(tr.get_remaining_duration(), 0.8))

        # the stakes: nothing in the recipe rules out an orbit
        q = LOOP[state["k"]][0]
        orbit = DashedVMobject(Ellipse(width=2 * q * HOOK_AXES[0], height=2 * q * HOOK_AXES[1]).move_to(HOOK_C),
                               num_dashes=40).set_stroke(MUTED, width=5)
        a0 = np.radians(HOOK_ANGLE0 + HOOK_TURN * state["k"])
        ang = ValueTracker(a0)
        circler = always_redraw(lambda: Dot(HOOK_C + np.array([q * HOOK_AXES[0] * np.cos(ang.get_value()),
                                                               q * HOOK_AXES[1] * np.sin(ang.get_value()), 0]),
                                            radius=0.13, color=MUTED))
        worry = Text("circling forever?", font_size=28, color=INK).move_to([-4.3, -2.6, 0])
        with self.voiceover(text="Yet nothing rules out circling forever. [pause 0.6]") as tr:
            self.play(FadeOut(pics), FadeOut(state["fan"]), Create(orbit),
                      run_time=max(self.time_until_word("circling"), 0.6))
            self.wait_until_word("circling")                       # v8: the circling dot on its word
            self.play(FadeIn(circler), FadeIn(worry), run_time=0.4)
            self.play(ang.animate.set_value(a0 - 2 * np.pi), rate_func=linear,
                      run_time=max(tr.get_remaining_duration(), 1.0))

        # the answer: watch the meter. A cut back to the start, said aloud ("let's rewind"). v7 (VD-9): the meter held
        # its level through the first run, so the rewind needs no refill. v5 (VD-2, FC-8): the picture is schematic in
        # direction, so it carries no numbers: the meter shows its label alone, the step's cost is an amber block
        # beside the bar and the drop a bracket, both to the meter's scale.
        p0 = hook_point(LOOP[0][0], 0)
        with self.voiceover(text="So let's rewind. <bookmark mark='m'/> And this time, watch what's left "
                                 "to pay. [pause 0.7]") as tr:
            self.read(worry)
            self.play(FadeOut(VGroup(orbit, circler, worry)), FadeOut(ghosts), FadeOut(trail), FadeOut(dot),
                      run_time=0.8)
            dot.move_to(p0)
            self.play(FadeIn(dot, scale=0.5), run_time=max(until(tr, "m", 0.8), 0.8))
            trail, ghosts = VGroup(), VGroup()
            self.add(trail)
            state["k"], state["fan"] = 0, VGroup()
            self.wait_until_bookmark("m")
            self.play(Indicate(m.frame, scale_factor=1.06, color=BLUE), Indicate(m.readout, color=INK),
                      run_time=min(max(tr.get_remaining_duration(), 0.6), 1.0))      # the meter, named once

        scale = m.bar_height / m.vmax
        x_cost, x_drop = m.frame.get_left()[0] - 0.26, m.frame.get_right()[0] + 0.25
        with self.voiceover(text="Each step takes off at least what it costs, <bookmark mark='f'/> and a "
                                 "bill that keeps falling by real amounts can't fall forever, so the "
                                 "controller has to arrive. [pause 0]") as tr:   # v8: the sting's silence follows
            for k in range(4):
                old, new, ld = m.level(LOOP[k][1]), m.level(LOOP[k + 1][1]), LOOP[k][2]
                seg_cost = Rectangle(width=0.24, height=ld * scale, stroke_width=0, fill_color=AMBER,
                                     fill_opacity=0.9).move_to([x_cost, old - ld * scale / 2, 0])
                fan = hook_fan(LOOP, k)
                if k == 0:                                         # v8: the plan, then its cost on "costs"
                    self.play(Create(fan), run_time=max(self.time_until_word("costs"), 0.3))
                    self.wait_until_word("costs")
                else:
                    self.play(Create(fan), run_time=0.25)
                self.play(FadeIn(seg_cost), run_time=0.3)
                nxt = hook_point(LOOP[k + 1][0], k + 1)
                seg = Line(dot.get_center(), nxt, color=INK, stroke_width=TRAIL_W)
                self.play(Create(seg), dot.animate.move_to(nxt), v.animate.set_value(LOOP[k + 1][1]), run_time=0.6)
                self.remove(seg)
                trail.add(seg)
                bracket = VGroup(Line([x_drop, old, 0], [x_drop, new, 0]), Line([x_drop - 0.12, old, 0], [x_drop, old, 0]),
                                 Line([x_drop - 0.12, new, 0], [x_drop, new, 0])).set_stroke(qcolor("V"), width=5)
                self.play(Create(bracket), FadeOut(fan), run_time=0.45)
                self.play(FadeOut(VGroup(seg_cost, bracket)), run_time=0.3)
                self.bring_to_front(dot)
            self.wait_until_bookmark("f")
            fast = FAST_TO - 4
            rt = max(tr.get_remaining_duration() - 0.5, 1.2) / fast
            for k in range(4, FAST_TO):
                nxt = hook_point(LOOP[k + 1][0], k + 1)
                seg = Line(dot.get_center(), nxt, color=INK, stroke_width=TRAIL_W)
                self.play(Create(seg), dot.animate.move_to(nxt), v.animate.set_value(LOOP[k + 1][1]), run_time=rt,
                          rate_func=smooth)
                self.remove(seg)
                trail.add(seg)
                self.bring_to_front(dot)
            self.play(target[0].animate.set_fill(opacity=0.45), run_time=0.5)
