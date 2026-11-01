"""TEMPLATE: one idea, one narrated scene. Copy to runs/<run>/video/scenes/<name>.py (with common.py, voice.py and
reading_model.py), rename the class and list it in video/plan.json.

Explainer: ../../explainer.html, Section <n> (<section id>).        <- fill in (plan.json "section"; "chapter" is the
                                                                       viewer's title)
Data:      ../data/<file>.npz, written by ../../code/<script>.py.   <- fill in
Every number on screen is read from the data file or computed here from the explainer's equations; none is typed by
hand. Without a data file the scene runs on demo data and says so on screen (fine for the template check only).
Self-contained: those sources stay behind the scenes. Nothing on screen, in the narration or in the captions names
the explainer, code, files, data, links or the description, and no equation carries a label or tag such as (13),
(2) or (★), nor "Eq. 3" (config/video.json equation_numbers). To refer back to an equation, show it again (pin()
keeps it in a corner) or name it by its meaning. tools/video/check_selfcontained.py enforces this.
Narration: each `with self.voiceover(text=...)` block is spoken by the configured voice (Piper; silent in drafts
without its model) and becomes a caption; <bookmark mark='x'/> plus self.wait_until_bookmark('x') syncs an
animation to a word. The text must be a string literal (implicit concatenation of literals is fine; no f-strings, variables or conditionals): CI synthesizes the
voice from the parsed file without running it. Show live numbers on screen; say only numbers the explainer states.

RAScene holds every text and equation until it can be read (reading_model.py); self.read() waits explicitly.
Keep text inside the graphics-safe area: title() and caption() place it; tools/video/check_design.py checks overlaps,
safe areas, sizes, contrast and the palette on every draft render, tools/video/check_reading.py the reading times.

Draft check:  tools/render_video.sh runs/<run> --check        (-ql, silent, seconds)
Final render: tools/render_video.sh runs/<run> --quality h    (1080p60, configured voice)
"""
import os

import numpy as np
from manim import *  # noqa: F401,F403
from common import *  # noqa: F401,F403  (palette, RAScene, eq, title, caption, readout, load_data, speech_service)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = load_data("scene_data.npz", HERE)          # expects arrays t, x (rename to match your export)
DEMO = DATA is None
if DEMO:                                          # damped oscillator x = exp(-z w t) cos(w_d t), z = 0.15, w = 2
    t_ = np.linspace(0.0, 10.0, 401)
    z_, w_ = 0.15, 2.0
    DATA = {"t": t_, "x": np.exp(-z_ * w_ * t_) * np.cos(w_ * np.sqrt(1 - z_ ** 2) * t_)}
T, X = DATA["t"], DATA["x"]


class TemplateScene(RAScene):
    def construct(self):
        self.set_speech_service(speech_service(HERE))

        # 1. Title, then the one equation of the scene (copied from the explainer's $$...$$ source)
        head = title("One idea, one scene")
        law = eq(r"\ddot x + 2\zeta\omega\,\dot x + \omega^2 x = 0",
                 plain="x'' + 2 z w x' + w^2 x = 0", font_size=34).next_to(head, DOWN, buff=0.2)
        with self.voiceover(text="One idea per scene. <bookmark mark='law'/> Here is the equation that carries it."):
            self.play(FadeIn(head), run_time=0.8)
            self.wait_until_bookmark("law")
            self.play(Write(law), run_time=1.0)

        # 2. Axes and the data curve, then a tracker drives a dot and a live readout (Pango Text, not MathTex)
        ax = Axes(x_range=[0, float(T[-1]), 2], y_range=[-1.1, 1.1, 0.5], x_length=9.5, y_length=3.6, tips=False,
                  axis_config=dict(color=GRID, include_numbers=False)).shift(DOWN * 0.55)
        curve = ax.plot_line_graph(T, X, add_vertex_dots=False, line_color=BLUE, stroke_width=4)
        k = ValueTracker(0.0)

        def idx():
            return min(int(k.get_value()), len(T) - 1)

        dot = always_redraw(lambda: Dot(ax.c2p(T[idx()], X[idx()]), radius=0.08, color=AMBER))
        # numbers through fmt(): readout(label, value, decimals=k) keeps the width steady; sign=True for a signed value
        live_x = readout("x", lambda: X[idx()], decimals=2, sign=True, font_size=26, color=AMBER)
        live_x.add_updater(lambda m: m.move_to([SAFE_X - m.width / 2, 1.9, 0]))
        live_t = readout(lambda: f"t = {fmt(T[idx()], decimals=1):\u2007>4}", font_size=26, color=AMBER)  # steady width
        live_t.add_updater(lambda m: m.next_to(live_x, LEFT, buff=0.6))
        live = VGroup(live_x, live_t)                      # x first: t is placed next to it
        demo = [Text("demo data (template)", font_size=24, color=MUTED)] if DEMO else []
        for m in demo:
            m.move_to([-SAFE_X + m.width / 2, -SAFE_Y + m.height / 2, 0])
        with self.voiceover(text="This curve shows how the motion dies out. The dot follows it, and the numbers at the "
                                 "top follow the dot.") as tracker:
            self.play(Create(ax), Create(curve), *[FadeIn(m) for m in demo], run_time=min(2.0, tracker.duration / 2))
            self.add(dot, live)
            self.play(k.animate.set_value(len(T) - 1), run_time=max(tracker.get_remaining_duration(), 0.5),
                      rate_func=linear)

        # 3. End card: the takeaway, said again in the video's own words (no source, no link)
        card = VGroup(Text("Takeaway in one line", font_size=32, color=GREEN),
                      Text("and why it matters, in a few words", font_size=24, color=MUTED)
                      ).arrange(DOWN, buff=0.2)
        box = SurroundingRectangle(card, color=GREEN, buff=0.25, corner_radius=0.1, fill_color=BG, fill_opacity=0.95)
        with self.voiceover(text="The takeaway, in one line, and why it matters."):
            self.play(FadeIn(box), FadeIn(card), run_time=0.8)
        for m in (dot, live_x, live_t):
            m.clear_updaters()
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.5)
