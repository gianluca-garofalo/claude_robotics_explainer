"""Fixture of tools/video/check_sync.py and RAScene.wait_until_word: pictures and labels against the words that name
them. Block 1 shows three pictures at once before their words (the pictogram case), block 2 each on its words; in
block 3 "stage cost" comes early, "end cost" on its words and "schematic" is never said."""
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403


def icons(y):
    """Three stand-in pictures in a row: a square, a circle and a triangle."""
    row = VGroup(Square(0.9), Circle(0.45), Triangle().scale(0.5)).set_stroke(INK, 4)
    return row.arrange(RIGHT, buff=1.0).move_to([0, y, 0])


class Robots(RAScene):
    def construct(self):
        dot = Dot(color=INK, radius=0.15).move_to([-5, -3, 0])
        self.add(dot, Text("a planner", font_size=30).move_to([-4.2, 3.1, 0]))      # the opening frame
        first, second = icons(1.2), icons(-1.2)
        with self.voiceover(text="It steers robot arms, legged robots and cars, this planner. [pause 0]") as tr:
            self.play(LaggedStart(*[FadeIn(p) for p in first], lag_ratio=0.3), run_time=1.0)
            self.play(dot.animate.shift(RIGHT * 2), run_time=tr.get_remaining_duration())
        with self.voiceover(text="Again: robot arms, [pause 0.8] legged robots, and cars. [pause 0]") as tr:
            for pic, words in zip(second, ("robot arms", "legged robots", "cars")):
                self.wait_until_word(words)
                self.play(FadeIn(pic), run_time=0.3)
            self.play(dot.animate.shift(RIGHT * 2), run_time=max(tr.get_remaining_duration(), 0.2))
        self.play(FadeOut(VGroup(first, second)), run_time=0.5)
        stage = Text("stage cost", font_size=28).move_to([3.6, 2.6, 0])
        end = Text("end cost", font_size=28).move_to([3.6, 1.6, 0])
        never = Text("schematic", font_size=26, color=MUTED).move_to([-3.6, 1.6, 0])
        with self.voiceover(text="Every step has a price. That price is called the stage cost. And the plan's last "
                                 "point pays the end cost. [pause 0]") as tr:
            self.play(FadeIn(stage), FadeIn(never), dot.animate.shift(RIGHT * 2), run_time=0.6)
            self.wait_until_word("end cost", lead=0.3)
            self.play(FadeIn(end), run_time=0.5)
            self.play(dot.animate.shift(RIGHT * 2), run_time=max(tr.get_remaining_duration(), 0.2))
        self.read()
