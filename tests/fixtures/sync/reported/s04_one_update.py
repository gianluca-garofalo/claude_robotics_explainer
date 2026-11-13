"""Fixture of tools/video/check_sync.py: plays of a news run (one particle filter update) that warned as unanchored,
in the context they had there, where nearly every play runs until a bookmark: run_time=until(tr, ...)."""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


class OneUpdate(RAScene):
    def construct(self):
        field = VGroup(*[Dot([0.7 * i - 4.2, 0.5 * j, 0], radius=0.06, color=MUTED)
                         for i in range(13) for j in range(-2, 3)])
        fresh = VGroup(*[Dot([0.8 * k - 3.6, 2.4, 0], radius=0.09, color=BLUE) for k in range(10)])
        picks = [fresh[k] for k in (1, 4, 5, 8, 9)]
        line = Line(LEFT * 4, RIGHT * 4).shift(DOWN * 1.2)
        ticks = VGroup(*[Line(UP * 0.12, DOWN * 0.12).move_to(line.point_from_proportion(k / 10)) for k in range(11)])
        axis_lbl = Text("distance to the reading", font_size=26).next_to(line, DOWN, buff=0.4)
        five = Text("5 of 10", font_size=30).next_to(line, UP, buff=0.3)
        bars_c = VGroup(*[Rectangle(width=0.5, height=0.3 * h, fill_opacity=0.8).set_stroke(width=0)
                          for h in (1, 3, 5, 3, 1)]).arrange(RIGHT, buff=0.15, aligned_edge=DOWN)
        bars_c.next_to(line, UP, buff=0)
        cost_lbl = Text("what the bad guesses cost", font_size=26).next_to(bars_c, UP, buff=0.3)
        self.add(field)
        with self.voiceover(text="Ten fresh guesses arrive. <bookmark mark='w'/>Each one is weighed against the new "
                                 "reading, and <bookmark mark='five'/>five of them land near it.") as tr:
            self.play(FadeIn(fresh, lag_ratio=0.1), run_time=until(tr, "w"))
            self.play(FadeOut(field), FadeOut(VGroup(*[p for p in fresh if p not in picks])),
                      Create(line), FadeIn(ticks), FadeIn(axis_lbl), run_time=until(tr, "five"))
            self.play(*[p.animate.move_to(line.get_center() + RIGHT * (k - 2) * 0.6) for k, p in enumerate(picks)],
                      FadeIn(five), run_time=max(tr.get_remaining_duration(), 0.6))
        with self.voiceover(text="The other five <bookmark mark='cost'/>cost something, and together "
                                 "<bookmark mark='half'/>half of the update goes to them.") as tr:
            self.play(five.animate.set_color(AMBER), run_time=until(tr, "cost"))
            self.wait_until_bookmark("cost")
            self.play(FadeOut(five), LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars_c], lag_ratio=0.15),
                      FadeIn(cost_lbl), run_time=until(tr, "half"))
            self.play(bars_c.animate.set_fill(opacity=0.5), run_time=max(tr.get_remaining_duration(), 0.6))
