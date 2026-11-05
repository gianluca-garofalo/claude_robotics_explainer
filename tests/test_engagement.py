"""Unit tests for the engagement checks (tools/video/check_engagement.py), the sting placement and the music-under-
voice measure (tools/video/music.py), the title-beat warnings of check_series.py and the choreography helpers'
pure parts (templates/manim/common.py is not imported: it needs Manim)."""
import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))

import check_engagement as CE  # noqa: E402
import check_series as CS  # noqa: E402
import layout_probe as LP  # noqa: E402
import music as MU  # noqa: E402

CFG = dict(CE.DEFAULTS)

SCENES = textwrap.dedent('''
    from common import *

    class Slide(RAScene):
        def construct(self):
            a = MathTex("V_N(q)")
            b = MathTex("V_N(q)", "=", "W")
            box = SurroundingRectangle(b)
            with self.voiceover(text="We write V of q, then q prime, then L d of q and q prime."):
                self.play(FadeIn(a), FadeIn(b))
                self.play(Create(box))
            self.play(FadeOut(Group(*self.mobjects)))

    class Moving(RAScene):
        def construct(self):
            a = ceq("V_N(q)", "=", "W(q)")
            b = ceq("V_N(q)", r"\\le", "W(q)")
            box = SurroundingRectangle(b)
            with self.voiceover(text="Watch what you pay."):
                derive(self, a, b)
                self.play(Create(box))
            with self.voiceover(text="So what does it buy you?"):
                self.play(b.animate.shift(UP))
            carry_over(self, b)

    class Last(RAScene):
        def construct(self):
            self.play(FadeOut(Group(*self.mobjects)))
''')


class Frames(unittest.TestCase):
    def test_motion_and_frozen_stretches(self):
        fr = np.zeros((41, 180, 320), dtype=np.uint8)
        for i in range(8):                       # 2 s of motion, then 8 s frozen
            fr[i + 1, 10:20, i * 10:i * 10 + 10] = 200
        mv = CE.motion_of(fr, CFG)
        self.assertEqual(len(mv), 40)
        self.assertTrue(all(mv[:8]))
        self.assertFalse(any(mv[10:]))
        st = CE.frozen_stretches(mv, 0.25)
        self.assertAlmostEqual(st[-1][1] - st[-1][0], 7.75, places=2)
        self.assertAlmostEqual(CE.overlap(st[-1], [(3.0, 9.0)]), 6.0, places=2)
        self.assertLess(CE.moving_share(mv, 0.25, 0.0, 10.0), 0.3)

    def test_ink(self):
        fr = np.full((180, 320), 22, dtype=np.uint8)
        self.assertEqual(CE.ink(fr, CFG), 0.0)
        fr[:18, :] = 200
        self.assertAlmostEqual(CE.ink(fr, CFG), 0.1, places=2)


class SceneCode(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "s.py").write_text(SCENES, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_vocabulary(self):
        slide = CE.vocabulary(self.d / "s.py", "Slide")
        self.assertEqual(slide["counts"].get("FadeIn"), 2)
        self.assertFalse(any(k in CE.TRANSFORMS for k in slide["counts"]))
        self.assertTrue(slide["fade_all"])
        self.assertTrue(slide["boxes_without_after"])            # a boxed result and nothing said after it
        moving = CE.vocabulary(self.d / "s.py", "Moving")
        self.assertEqual(moving["counts"].get("derive"), 1)
        self.assertEqual(moving["counts"].get("carry_over"), 1)
        self.assertFalse(moving["fade_all"])
        self.assertFalse(moving["boxes_without_after"])

    def test_narration_patterns(self):
        text = "We write V of q, then q prime, then L d of q and q prime. A bill you pay."
        toks = CE.NOTATION.findall(text)
        self.assertEqual(sorted(set(toks)), ["L", "V", "d", "prime", "q"])
        self.assertNotIn("A", toks)
        self.assertEqual(len(CE.ADDRESS.findall(text)), 2)

    def run_fixture(self, scenes_src, plan_scenes, logs, metaphor=None):
        run = self.d / "run"
        (run / "video" / "scenes").mkdir(parents=True)
        (run / "video" / "checks").mkdir(parents=True)
        (run / "video" / "scenes" / "s.py").write_text(scenes_src, encoding="utf-8")
        plan = {"scenes": plan_scenes}
        if metaphor:
            plan["metaphor"] = metaphor
        (run / "video" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        for cls, log in logs.items():
            (run / "video" / "checks" / f"{cls}.layout.json").write_text(json.dumps({"scenes": {cls: log}}))
        return CE.check(run, "draft", CFG, use_video=False)

    def test_check_without_frames(self):
        title = {"id": 1, "kind": "text", "content": "One test, on one step", "font_size": 34, "live": False,
                 "events": [[0.0, 1, -3, 3.1, 3, 3.5, 1.0]]}
        meter_lab = {"id": 2, "kind": "text", "content": "left to pay = 0.59", "font_size": 26, "live": True,
                     "events": [[0.0, 1, 3, -2.5, 6, -2.1, 1.0]]}
        logs = {"Slide": {"duration": 30.0, "timeline": [title], "voiceovers": [{"start": 0, "duration": 20}]},
                "Moving": {"duration": 20.0, "timeline": [meter_lab], "voiceovers": []},
                "Last": {"duration": 15.0, "timeline": [meter_lab], "voiceovers": []}}
        scenes = [{"file": "s.py", "class": "Slide", "role": "body"}, {"file": "s.py", "class": "Moving",
                                                                       "role": "body"},
                  {"file": "s.py", "class": "Last", "role": "outro"}]
        fd, stats = self.run_fixture(SCENES, scenes, logs, metaphor={"name": "meter", "label": "left to pay"})
        checks = {(x["check"], x["where"]) for x in fd.items}
        self.assertIn(("vocabulary", "Slide"), checks)            # equations, no transform; fade of everything
        self.assertIn(("so what", "Slide"), checks)
        self.assertIn(("titles", "Slide"), checks)                 # a slide title for 30 s
        self.assertNotIn(("vocabulary", "Moving"), checks)
        self.assertNotIn(("vocabulary", "Last"), checks)           # the last scene may fade out everything
        self.assertEqual(stats["metaphor_body_share"], 0.5)
        self.assertEqual(stats["transforms"], 1)
        self.assertFalse(any(x["severity"] == "error" for x in fd.items))


class EmphasisIsNotMotion(unittest.TestCase):
    """v4: pulsing to keep the picture moving does not satisfy the motion budget (the v3 review's FC-3: an 18 s
    stretch of looping borders around a static box passed as motion)."""

    def test_probe_names_leaf_animations(self):
        class _AnimationBuilder:
            pass

        class Indicate:
            pass

        class Wait:
            pass

        class LaggedStart:
            def __init__(self, *a):
                self.animations = list(a)
        names = LP.anim_names([LaggedStart(Indicate(), _AnimationBuilder()), Wait(), Indicate()])
        self.assertEqual(names, ["Indicate", "animate", "Indicate"])

    def test_emphasis_only_plays_count_as_frozen(self):
        log = {"plays": [{"start": 0.0, "end": 2.0, "anims": ["animate", "Indicate"]},
                         {"start": 2.0, "end": 8.0, "anims": ["Circumscribe"]},
                         {"start": 8.0, "end": 9.0, "anims": ["Indicate", "Indicate"]}]}
        spans = CE.emphasis_spans(log)
        self.assertEqual(spans, [(2.0, 8.0), (8.0, 9.0)])
        self.assertIsNone(CE.emphasis_spans({}))                       # an old log: nothing separated
        moving = [True] * 40                                           # 10 s at 4 fps, every interval moves
        content = CE.mask_emphasis(moving, spans, 0.25)
        self.assertTrue(all(content[:8]))                              # 0-2 s: a real move (".animate")
        self.assertFalse(any(content[8:36]))                           # 2-9 s: emphasis alone
        frozen = CE.frozen_stretches(content, 0.25)
        self.assertAlmostEqual(frozen[0][1] - frozen[0][0], 7.0, places=2)

    def test_emphasis_in_a_loop_is_flagged(self):
        src = textwrap.dedent('''
            from common import *

            class Fidget(RAScene):
                def construct(self):
                    box = Square()
                    with self.voiceover(text="Here is the result."):
                        for _ in range(4):
                            self.play(Circumscribe(box))
        ''')
        d = Path(tempfile.mkdtemp())
        try:
            (d / "f.py").write_text(src, encoding="utf-8")
            voc = CE.vocabulary(d / "f.py", "Fidget")
            self.assertEqual(len(voc["emphasis_loops"]), 1)
            self.assertEqual(voc["counts"].get("Circumscribe"), 1)
        finally:
            shutil.rmtree(d)


class JargonAndThumbnail(unittest.TestCase):
    def test_new_terms_per_block(self):
        block = ("With a continuous end cost and a bounded region, the remaining action is a Lyapunov function, and "
                 "the rest point is asymptotically stable: certified by the terminal cost and the terminal set.")
        terms = CE.jargon_terms(block, CFG["jargon"])
        self.assertEqual(set(terms) >= {"lyapunov", "asymptotically stable", "terminal cost", "terminal set"}, True)
        self.assertGreater(len(terms), CFG["jargon_new_per_block_warn"])
        self.assertEqual(CE.jargon_terms("a calm sentence with no terms", CFG["jargon"]), [])

    def test_thumbnail_picture_must_stay_bold(self):
        from PIL import Image, ImageDraw
        d = Path(tempfile.mkdtemp())
        try:
            fin = d / "video" / "final"
            fin.mkdir(parents=True)
            meta = {"size": [1280, 720], "elements": [{"role": "title", "text": "Why MPC converges", "font_px": 84,
                                                       "bbox": [64, 38, 1024, 120], "color": "#e2e8f0"}]}
            (fin / "thumbnail.json").write_text(json.dumps(meta), encoding="utf-8")
            shares = {}
            for kind, width in (("hairline", 3), ("bold", 40)):
                im = Image.new("RGB", (1280, 720), (15, 23, 42))
                dr = ImageDraw.Draw(im)
                dr.rectangle([64, 38, 1024, 120], fill=(226, 232, 240))           # the title: not counted
                dr.line([(80, 600), (500, 260), (900, 420), (1200, 300)], fill=(226, 232, 240), width=width)
                if kind == "bold":
                    dr.rectangle([1000, 250, 1120, 680], fill=(129, 140, 248))     # a thick meter bar
                im.save(fin / "thumbnail.jpg", quality=92)
                shares[kind] = CE.thumbnail_bold(d, CFG)["bold_share"]
            self.assertLess(shares["hairline"], CFG["thumbnail_picture_bold_min"])
            self.assertGreater(shares["bold"], CFG["thumbnail_picture_bold_min"])
        finally:
            shutil.rmtree(d)


class Stings(unittest.TestCase):
    def test_sting_waits_for_a_pause(self):
        cfg = dict(MU.DEFAULTS)
        # the narration speaks right from the segment start (8.0); the pause before it is short, a later one long
        gaps = [[0.0, 2.0], [7.5, 8.0], [10.0, 14.0]]
        self.assertEqual(MU.sting_slot(8.0, 16.0, gaps, cfg), 10.0)
        # a pause long enough before the speech: the sting ends just before the first word
        self.assertEqual(MU.sting_slot(8.0, 16.0, [[4.0, 8.4]], cfg), round(8.4 - 3.4, 3))
        # a pause that starts at the segment: the sting goes there
        self.assertEqual(MU.sting_slot(8.0, 16.0, [[7.9, 12.0]], cfg), 8.0)
        # only a shorter pause inside the segment: its start; nothing at all: no sting
        self.assertEqual(MU.sting_slot(8.0, 16.0, [[7.5, 8.0], [12.0, 14.0]], cfg), 12.0)
        self.assertIsNone(MU.sting_slot(8.0, 9.0, [], cfg))

    def test_under_voice(self):
        sr = 8000
        t = np.arange(sr * 4) / sr
        v = np.where((t > 1) & (t < 3), 0.3 * np.sin(2 * np.pi * 200 * t), 0.0)
        quiet = 0.3 * 10 ** (-20 / 20) * np.sin(2 * np.pi * 300 * t)
        self.assertLess(MU.under_voice(v, quiet, sr), -15)
        loud = quiet.copy()
        loud[int(1.5 * sr):int(2.0 * sr)] *= 10 ** (16 / 20)          # a sting over the words
        self.assertGreater(MU.under_voice(v, loud, sr), -12)
        self.assertIsNone(MU.under_voice(np.zeros(sr * 2), quiet[:sr * 2], sr))


class MeterMeansOneThing(unittest.TestCase):
    """v5: the metaphor's value is logged and must not refill unannounced; a meter that never moves is decoration;
    a frame inside a scene must not go blank; the outro leaves time after its last word and shows its question."""

    @staticmethod
    def probe_log(values, visible=((0.0, 1),), duration=40.0, voiceovers=(), vmax=0.6):
        return {"duration": duration, "timeline": [], "snapshots": [], "voiceovers": list(voiceovers),
                "metaphor": [{"id": 1, "vmax": vmax, "values": [list(v) for v in values],
                              "visible": [list(v) for v in visible]}]}

    def test_track_from_probe_and_from_readout(self):
        log = self.probe_log([(0.0, 0.5), (2.0, 0.4), (30.0, 0.3)], visible=[(0.0, 1), (10.0, 0), (25.0, 1)])
        track, vmax, shown, source = CE.metaphor_track(log, "left to pay")
        self.assertEqual(source, "probe")
        self.assertEqual(vmax, 0.6)
        self.assertAlmostEqual(shown, 25.0)                       # 0-10 s and 25-40 s
        self.assertEqual(track, [(0.0, 0.5), (2.0, 0.4), (25.0, 0.4), (30.0, 0.3)])   # 0.4 held into the second span
        old = {"duration": 20.0, "timeline": [{"id": 3, "kind": "text", "content": "left to pay = 0.586", "live": True,
                                                "events": [[0.0, 1, 3, -2, 5, -1.8, 1.0]],
                                                "values": [[0.0, "left to pay = 0.586"], [5.0, "left to pay = 0.12"],
                                                           [9.0, "left to pay = 1,234.5"]]}]}
        track, vmax, shown, source = CE.metaphor_track(old, "left to pay")
        self.assertEqual(source, "readout")
        self.assertIsNone(vmax)
        self.assertEqual(track, [(0.0, 0.586), (5.0, 0.12), (9.0, 1234.5)])
        self.assertEqual(CE.metaphor_track({"duration": 5.0, "timeline": []}, "left to pay")[3], "none")

    def test_rises_split_at_plateaus(self):
        # drains, refills over 4 s (a scan back to the start), holds, then climbs again much later
        track = [(0.0, 0.586), (1.0, 0.3), (2.0, 0.12), (2.5, 0.2), (3.5, 0.35), (4.5, 0.5), (5.5, 0.586),
                 (40.0, 0.59), (41.0, 0.6)]
        r = CE.rises(track, tol=0.012)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0][:2], (2.0, 5.5))
        self.assertAlmostEqual(r[0][3] - r[0][2], 0.466, places=3)
        self.assertEqual(r[1][0], 40.0)                          # the plateau 6-40 s ends the first rise
        self.assertEqual(CE.rises([(0.0, 0.5), (1.0, 0.505), (2.0, 0.4)], tol=0.012), [])   # a wobble is not a rise

    def run_meter(self, logs, scenes, metaphor):
        d = Path(tempfile.mkdtemp())
        try:
            run = d / "run"
            (run / "video" / "scenes").mkdir(parents=True)
            (run / "video" / "checks").mkdir(parents=True)
            (run / "video" / "scenes" / "s.py").write_text(SCENES, encoding="utf-8")
            (run / "video" / "plan.json").write_text(json.dumps({"scenes": scenes, "metaphor": metaphor}))
            for cls, log in logs.items():
                (run / "video" / "checks" / f"{cls}.layout.json").write_text(json.dumps({"scenes": {cls: log}}))
            return CE.check(run, "draft", CFG, use_video=False)
        finally:
            shutil.rmtree(d)

    def test_undeclared_refill_warns_and_a_spoken_reset_does_not(self):
        scan = self.probe_log([(0.0, 0.586), (3.0, 0.12), (5.0, 0.586), (8.0, 0.3)],
                              voiceovers=[{"start": 2.0, "duration": 6.0, "text": "Checking one point settles every "
                                                                                    "point. Back to the start."}])
        flat = self.probe_log([(0.0, 0.3)], duration=30.0)
        scenes = [{"file": "s.py", "class": "Moving", "role": "body"},
                  {"file": "s.py", "class": "Slide", "role": "body"}]
        meta = {"name": "meter", "label": "left to pay"}
        fd, stats = self.run_meter({"Moving": scan, "Slide": flat}, scenes, meta)
        meter = [x for x in fd.items if x["check"] == "meter"]
        self.assertEqual(stats["meter"]["rises_undeclared"], 1)
        self.assertTrue(any(x["where"] == "Moving" and "rises from 0.12 to 0.586" in x["detail"] for x in meter))
        self.assertTrue(any(x["where"] == "Slide" and "decoration" in x["detail"] for x in meter))   # never moves
        scenes[0]["metaphor_resets"] = [{"says": "back to the start", "why": "the scan was hypothetical"}]
        fd, stats = self.run_meter({"Moving": scan, "Slide": flat}, scenes, meta)
        self.assertEqual(stats["meter"]["rises_undeclared"], 0)
        scenes[0]["metaphor_resets"] = [{"says": "a fresh start", "why": "not in the narration"}]
        fd, stats = self.run_meter({"Moving": scan, "Slide": flat}, scenes, meta)
        self.assertEqual(stats["meter"]["rises_undeclared"], 1)  # declared but never said: still a warning
        fd, stats = self.run_meter({"Moving": scan, "Slide": flat}, scenes, dict(meta, direction="any"))
        self.assertEqual(stats["meter"]["rises_undeclared"], 0)

    def test_refill_across_a_cut(self):
        a = self.probe_log([(0.0, 0.5), (5.0, 0.04)])
        b = self.probe_log([(0.0, 0.586), (5.0, 0.3)])
        scenes = [{"file": "s.py", "class": "Moving", "role": "body"},
                  {"file": "s.py", "class": "Slide", "role": "body"}]
        fd, stats = self.run_meter({"Moving": a, "Slide": b}, scenes, {"name": "meter", "label": "left to pay"})
        self.assertTrue(any(x["check"] == "meter" and x["where"] == "Slide" and "cut into the scene" in x["detail"]
                            for x in fd.items))

    def test_blank_frames_inside_a_scene(self):
        inks = [0.05] * 10 + [0.0, 0.0] + [0.04] * 10 + [0.0]
        self.assertEqual(CE.blank_stretches(inks, 0.25, 0.005), [(2.5, 3.0)])     # the last frame is the cut's
        self.assertEqual(CE.blank_stretches([0.0] + [0.05] * 8 + [0.0] * 4, 0.25, 0.005, skip_end_s=1.0), [])

    def test_outro_tail_and_question(self):
        card = {"id": 1, "kind": "math", "content": "V_1 \\le V_0", "live": False,
                "events": [[0.0, 1, -5, 0, 0, 1, 1.0]]}
        outro = {"duration": 18.4, "timeline": [card], "snapshots": [],
                 "voiceovers": [{"start": 0.0, "duration": 6.0, "text": "One test, on one step."},
                                {"start": 13.0, "duration": 5.1, "text": "Until then: why does the textbook weight "
                                                                         "fail, by just one percent?"}]}
        scenes = [{"file": "s.py", "class": "Last", "role": "outro"}]
        fd, stats = self.run_meter({"Last": outro}, scenes, {"name": "meter", "label": "left to pay"})
        outro_f = [x["detail"] for x in fd.items if x["check"] == "outro"]
        self.assertAlmostEqual(stats["outro_tail_s"], 0.3, places=2)
        self.assertTrue(any("ends 0.3 s before the end" in t for t in outro_f))
        self.assertTrue(any("why does the textbook weight fail, by just one percent?" in t for t in outro_f))
        outro["duration"] = 21.0
        outro["timeline"].append({"id": 2, "kind": "text", "content": "Why does weight 1 fail?", "live": False,
                                  "events": [[14.0, 1, -5, -2, 0, -1.5, 1.0]]})
        fd, stats = self.run_meter({"Last": outro}, scenes, {"name": "meter", "label": "left to pay"})
        self.assertFalse([x for x in fd.items if x["check"] == "outro"])


class ResetTimingAndSchematic(unittest.TestCase):
    """v6: a declared refill counts when the meter refills while or after its words are said; a schematic picture
    shows no numbers."""

    def test_phrase_time_and_late_reset(self):
        block = {"start": 10.0, "duration": 10.0,
                 "text": "You get two more things from the same bookkeeping. Start again from the same point, with a "
                         "plan of five steps."}
        t = CE.phrase_time(block, "start again from the same point")
        self.assertAlmostEqual(t, 10.0 + 10.0 * 9 / 21, places=2)        # 9 words before them, 21 in all
        self.assertIsNone(CE.phrase_time(block, "let's build it"))
        log = {"voiceovers": [block]}
        resets = [{"says": "start again from the same point", "why": "a new plan from the same start"}]
        at_cut = (10.0, 10.5, 0.0, 0.552)                                # refilled at the cut, before the words
        self.assertIsNone(CE.declared(at_cut, resets, log, 2.0))
        self.assertAlmostEqual(CE.reset_said_late(at_cut, resets, log, 2.0), 4.3, places=1)
        as_said = (14.0, 15.0, 0.0, 0.552)                               # refilled as the words are said
        self.assertEqual(CE.declared(as_said, resets, log, 2.0), resets[0])
        self.assertIsNone(CE.reset_said_late(as_said, resets, log, 2.0))

    def test_numbers_on_a_schematic_picture(self):
        log = {"timeline": [
            {"kind": "text", "content": "left to pay = 0.039", "live": True, "events": [[0.0, 1, 0, 0, 1, 1, 1.0]],
             "values": [[0.0, "left to pay = 0.039"]]},
            {"kind": "text", "content": "Episode 1 of 7", "live": False, "events": [[0.5, 1, 0, 0, 1, 1, 1.0]]},
            {"kind": "math", "content": "V_1 \\le V_0", "live": False, "events": [[0.5, 1, 0, 0, 1, 1, 1.0]]},
            {"kind": "text", "content": "left to pay", "live": True, "events": [[1.0, 1, 0, 0, 1, 1, 1.0]],
             "values": [[1.0, "left to pay"]]},
            {"kind": "text", "content": "never shown 0.5", "live": False, "events": [[1.0, 0, 0, 0, 1, 1, 0.0]]}]}
        found = CE.numbers_on_schematic(log)
        self.assertEqual([n for n, _ in found], ["left to pay = 0.039"])

    def test_schematic_scene_warns_and_plan_must_be_consistent(self):
        d = Path(tempfile.mkdtemp())
        try:
            run = d / "run"
            (run / "video" / "scenes").mkdir(parents=True)
            (run / "video" / "checks").mkdir(parents=True)
            (run / "video" / "scenes" / "s.py").write_text(SCENES, encoding="utf-8")
            ro = {"id": 1, "kind": "text", "content": "left to pay = 0.039", "live": True,
                  "events": [[0.0, 1, 3, -2, 5, -1.8, 1.0]], "values": [[0.0, "left to pay = 0.039"]]}
            for cls in ("Moving", "Slide"):
                (run / "video" / "checks" / f"{cls}.layout.json").write_text(json.dumps(
                    {"scenes": {cls: {"duration": 6.0, "timeline": [ro], "voiceovers": [], "snapshots": []}}}))
            scenes = [{"file": "s.py", "class": "Moving", "role": "body", "picture": "schematic"},
                      {"file": "s.py", "class": "Slide", "role": "body"}]
            (run / "video" / "plan.json").write_text(json.dumps({"scenes": scenes}))
            fd, stats = CE.check(run, "draft", CFG, use_video=False)
            pic = [(x["where"], x["detail"]) for x in fd.items if x["check"] == "picture"]
            self.assertTrue(any(w == "Moving" and "0.039" in d_ for w, d_ in pic))
            self.assertTrue(any(w == "video" and "Slide" in d_ for w, d_ in pic))   # a plan that uses the field
            scenes[1]["picture"] = "faithful"
            (run / "video" / "plan.json").write_text(json.dumps({"scenes": scenes}))
            fd, stats = CE.check(run, "draft", CFG, use_video=False)
            self.assertEqual([x["where"] for x in fd.items if x["check"] == "picture"], ["Moving"])
            for s_ in scenes:
                s_.pop("picture")
            (run / "video" / "plan.json").write_text(json.dumps({"scenes": scenes}))
            fd, stats = CE.check(run, "draft", CFG, use_video=False)
            self.assertEqual([x for x in fd.items if x["check"] == "picture"], [])     # opt-in: no field, no check
        finally:
            shutil.rmtree(d)


class PlanFields(unittest.TestCase):
    def test_metaphor_direction_and_resets_are_validated(self):
        import plan as P
        d = Path(tempfile.mkdtemp())
        try:
            (d / "video" / "scenes").mkdir(parents=True)
            (d / "video" / "scenes" / "s.py").write_text(SCENES, encoding="utf-8")
            base = {"schema_version": 1, "title": "t", "summary": "s", "tags": [],
                    "thumbnail": {"scene": "Moving", "time": 1.0, "text": "x"},
                    "metaphor": {"name": "meter", "label": "left to pay"},
                    "scenes": [{"file": "s.py", "class": "Moving", "section": "sec-a", "chapter": "A", "role": "body",
                                "metaphor_resets": [{"says": "let's build it", "why": "the bill is built"}]}]}
            ok = [x for x in P.problems(d, base) if "metaphor" in x]
            self.assertEqual(ok, [])
            bad = json.loads(json.dumps(base))
            bad["scenes"][0]["metaphor_resets"] = [{"says": "", "why": "x"}]
            bad["metaphor"]["direction"] = "up"
            msgs = " ".join(x for x in P.problems(d, bad) if "metaphor" in x)
            self.assertIn("metaphor_resets", msgs)
            self.assertIn("direction", msgs)
            bad["scenes"][0]["picture"] = "diagram"
            self.assertTrue(any("picture" in x for x in P.problems(d, bad)))
            base["scenes"][0]["picture"] = "schematic"
            self.assertFalse(any("picture" in x for x in P.problems(d, base)))
        finally:
            shutil.rmtree(d)


class TitleBeat(unittest.TestCase):
    def test_long_silent_title_beat_warns(self):
        scenes = [{"class": "Hook", "role": "hook"}, {"class": "Ctx", "role": "context"}]
        hook = {"snapshots": [], "voiceovers": [{"start": 2.0, "duration": 4.0, "text": "Why?"}], "duration": 30.0}
        logs = {"Hook": hook, "Ctx": {"snapshots": [], "voiceovers": [{"start": 0.0, "duration": 3.0, "text": "x"}],
                                      "duration": 8.4}}
        w = CS.Warnings()
        CS.hook_checks(scenes, logs, {"Hook": 0.0, "Ctx": 30.0}, {}, dict(CS.DEFAULTS), w)
        text = " ".join(x["detail"] for x in w.items if x["check"] == "title beat")
        self.assertIn("lasts 8.4 s", text)
        self.assertIn("speech", text)
        logs["Ctx"] = {"snapshots": [], "voiceovers": [{"start": 0.0, "duration": 4.0, "text": "x"}], "duration": 5.5}
        w = CS.Warnings()
        CS.hook_checks(scenes, logs, {"Hook": 0.0, "Ctx": 30.0}, {}, dict(CS.DEFAULTS), w)
        self.assertFalse([x for x in w.items if x["check"] == "title beat"])


class CarriedText(unittest.TestCase):
    def test_text_carried_across_a_cut_is_credited(self):
        import check_reading as CR
        import reading_model as RM
        cfg = dict(RM.DEFAULTS)
        prev = {"duration": 10.0, "voiceovers": [], "snapshots": [],
                "timeline": [{"kind": "text", "content": "Why should it ever arrive?",
                              "events": [[2.0, 1, -3, 3, 3, 3.5, 1.0]]}]}
        nxt = {"duration": 6.0, "voiceovers": [], "snapshots": [],
               "timeline": [{"kind": "text", "content": "Why should it ever arrive?",
                             "events": [[0.0, 1, -3, 3, 3, 3.5, 1.0], [0.5, 0, -3, 3, 3, 3.5, 0.0]]}]}
        first, last = CR.edge_items(prev)
        self.assertAlmostEqual(last["Why should it ever arrive?"], 8.0)
        alone, carried = [], []
        CR.scene_reading("Next", nxt, cfg, alone, {})
        CR.scene_reading("Next", nxt, cfg, carried, {}, before=last)
        self.assertTrue([f for f in alone if f["check"] == "display-time"])
        self.assertFalse([f for f in carried if f["check"] == "display-time"])


if __name__ == "__main__":
    unittest.main()
