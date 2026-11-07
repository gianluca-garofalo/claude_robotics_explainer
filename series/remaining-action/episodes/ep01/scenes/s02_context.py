"""Scene 2 (series context, as a title beat): the hook's last picture stays (the dot in the target, the drained meter);
the video's title replaces the question and an "Episode 1 of 8" lower third comes up over the one spoken series
sentence. Then the picture cuts to the body's start (the dot fades out and in at the plan's start: no rewind), the
target becomes the body's end region and the meter empties (its label alone from here: the body's bars are schematic
until the worked example); s03 starts from exactly this frame. v4: no "Back to the start" (FC-7), at most 6 s.

Series context from video/series_context.json (no explainer section); the meter's value is the hook's last
(ep01_numbers.LOOP), shown as a level only: v6 (VD-1) the readout is the label alone, as in the hook.
"""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403
from ep01_draw import DOT_R, FAST_TO, ep_meter, hook_point, hook_target, hook_trail
from ep01_numbers import LOOP
from ep01_world import PLAN_Q, body_point, omega, the_dot



class SeriesContext(RAScene):
    def construct(self):
        v = ValueTracker(LOOP[FAST_TO][1])
        target = hook_target()
        target[0].set_fill(opacity=0.45)
        m = ep_meter(v.get_value, show_value=False)          # v6 (VD-1, FC-6): schematic picture, label alone
        trail = hook_trail(LOOP, FAST_TO)
        dot = Dot(hook_point(LOOP[FAST_TO][0], FAST_TO), radius=DOT_R, color=INK)
        question = title("Why should it ever arrive?")
        self.carry_in(target, trail, m, dot, question)         # the hook's last frame, carried over
        head, lower = title_beat()
        om = omega()
        start = the_dot(body_point(PLAN_Q[0], 0))
        self.play(FadeOut(question), run_time=0.35)                # FC-6: the question leaves before the title comes
        with self.voiceover(text="Episode one of eight. The proof <bookmark mark='go'/> takes one step. [pause 0]") as tr:
            self.play(FadeIn(head), FadeIn(lower, shift=UP * 0.1), run_time=0.6)
            self.wait_until_bookmark("go")
            self.play(FadeOut(VGroup(head, lower)), FadeOut(trail),             # the label alone throughout
                      FadeOut(dot), FadeIn(start), Transform(target, om), v.animate.set_value(0.0),
                      run_time=max(min(tr.get_remaining_duration(), 1.2), 1.0))
        self.remove(dot)
