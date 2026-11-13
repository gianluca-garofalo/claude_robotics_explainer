"""Fixture of tools/video/check_sync.py: a play of a news run (resampling) that warned as unanchored, in the context
it had there, where nearly every play runs until a bookmark: run_time=until(tr, ...)."""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


class Resample(RAScene):
    def construct(self):
        axes = Axes(x_range=[0, 40, 10], y_range=[0, 1, 0.5], x_length=8, y_length=3.5).shift(DOWN * 0.3)
        y_lbl = Text("guesses that count", font_size=24).next_to(axes, UP, buff=0.2).align_to(axes, LEFT)
        curve = axes.plot(lambda t: 0.95 ** t, color=AMBER)
        tag = Text("no resampling", font_size=24, color=AMBER).next_to(curve.get_end(), UP, buff=0.2)
        green = axes.plot(lambda t: 0.9 - 0.002 * t, color=BLUE)
        gtag = Text("resampling", font_size=24, color=BLUE).next_to(green.get_end(), UP, buff=0.2)
        half = DashedLine(axes.c2p(0, 0.5), axes.c2p(40, 0.5), color=MUTED)
        half_lbl = Text("half", font_size=24, color=MUTED).next_to(half, LEFT, buff=0.2)
        field = VGroup(*[Dot([0.7 * i - 4.2, 0.5 * j, 0], radius=0.06, color=MUTED)
                         for i in range(13) for j in range(-2, 3)])
        lost = VGroup(*[Dot([0.9 * k - 4.0, -2.4, 0], radius=0.08, color=AMBER) for k in range(9)])
        self.add(axes, y_lbl, curve, tag, green, gtag, half, half_lbl)
        with self.voiceover(text="Without it, <bookmark mark='w'/>the weight piles onto a few guesses, and the rest "
                                 "become <bookmark mark='scouts'/>scouts lost in the field.") as tr:
            self.play(curve.animate.set_stroke(width=8), run_time=until(tr, "w"))
            self.play(FadeOut(VGroup(axes, y_lbl, curve, tag, green, gtag, half, half_lbl)), FadeIn(field),
                      FadeIn(lost), run_time=until(tr, "scouts"))
            self.play(lost.animate.shift(DOWN * 0.3), run_time=max(tr.get_remaining_duration(), 0.6))
