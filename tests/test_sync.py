"""Unit tests for pictures on their words: RAScene.wait_until_word and time_until_word (templates/manim/common.py),
tools/video/check_sync.py and its report in tools/gate.py.

The fixture tests/fixtures/sync/ is a scene and its layout log from a silent draft render. The word timing tests need
manim-voiceover (this Python, the one next to $MANIM, or .venv); the render test also needs Manim and ffmpeg.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))
sys.path.insert(0, str(REPO / "templates" / "manim"))

import check_sync as CS  # noqa: E402
import gate  # noqa: E402
import voice  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "sync"
CFG = dict(CS.DEFAULTS)
HELPERS = ("common.py", "voice.py", "reading_model.py")


def voice_python():
    """A Python with manim-voiceover (this one, the one next to $MANIM, or .venv), or None."""
    cands = [sys.executable, str(REPO / ".venv" / "bin" / "python")]
    if os.environ.get("MANIM"):
        cands.insert(1, str(Path(os.environ["MANIM"]).parent / "python"))
    return next((c for c in cands if Path(c).exists() and subprocess.run(
        [c, "-c", "import manim_voiceover"], capture_output=True).returncode == 0), None)


def manim():
    m = os.environ.get("MANIM") or str(REPO / ".venv" / "bin" / "manim")
    return m if Path(m).exists() else shutil.which("manim")


VPY = voice_python()
HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def fixture_run(folder: Path, stage: str = "draft") -> Path:
    """A run with the fixture scene, its plan and its layout log of a silent draft (video/checks, or renders)."""
    run = folder / "run"
    (run / "video" / "scenes").mkdir(parents=True)
    shutil.copy(FIX / "plan.json", run / "video" / "plan.json")
    shutil.copy(FIX / "scenes" / "s01_robots.py", run / "video" / "scenes" / "s01_robots.py")
    logs = run / "video" / ("checks" if stage == "draft" else "renders")
    logs.mkdir(parents=True)
    shutil.copy(FIX / "Robots.layout.json", logs / "Robots.layout.json")
    return run


def by_rule(fd, rule):
    return [x for x in fd.items if x["rule"] == rule]


class Words(unittest.TestCase):
    def test_simple_stems(self):
        for a, b in (("robots", "robot"), ("legged", "legs"), ("circling", "circle"), ("costs", "costing"),
                     ("planned", "plans"), ("one", "1"), ("controller's", "controllers")):
            self.assertEqual(CS.stem(a), CS.stem(b), (a, b))
        self.assertNotEqual(CS.stem("cars"), CS.stem("cost"))

    def test_item_words(self):
        self.assertEqual(CS.item_words("text", "the Stage costs"), [(CS.stem("stage"), CS.stem("cost"))])
        self.assertEqual(CS.item_words("text", "0.42"), [("0", "42")])
        self.assertEqual(CS.item_words("math", r"V_N(q) = \min \text{stage cost} + \mathrm{d}t"),
                         [(CS.stem("stage"), CS.stem("cost"))])            # \mathrm{d} is a symbol, not a word
        self.assertEqual(CS.item_words("math", r"V_N(q)"), [])


def unanchored(source: str, extra: dict | None = None) -> list[dict]:
    d = Path(tempfile.mkdtemp())
    try:
        files = []
        for name, text in {"s.py": source, **(extra or {})}.items():
            (d / name).write_text(textwrap.dedent(text), encoding="utf-8")
            files.append(d / name)
        fd = CS.Findings()
        CS.unanchored(files, fd)
        return fd.items
    finally:
        shutil.rmtree(d)


class SourceRule(unittest.TestCase):
    """unanchored: one play() in a voiceover block showing several pictures off the words that name them."""

    def test_a_group_shown_at_the_blocks_start(self):
        found = unanchored('''
            class Hook(RAScene):
                def construct(self):
                    pics = VGroup(Square(), Circle(), Triangle())
                    with self.voiceover(text="It steers arms, legs and cars.") as tr:
                        self.play(LaggedStart(*[FadeIn(p) for p in pics], lag_ratio=0.3), run_time=1.2)
                        self.play(Create(Square()), FadeIn(Dot()), run_time=0.5)
        ''')
        self.assertEqual([(x["where"], x["line"]) for x in found], [("Hook", 6), ("Hook", 7)])
        self.assertTrue(all(x["severity"] == "warning" for x in found))
        self.assertIn("wait_until_word", found[0]["detail"])

    def test_each_picture_on_its_words(self):
        self.assertEqual(unanchored('''
            class Hook(RAScene):
                def construct(self):
                    arm, dog, car = Square(), Circle(), Triangle()
                    with self.voiceover(text="It steers arms, legs and cars.") as tr:
                        for pic, words in zip((arm, dog, car), ("arms", "legs", "cars")):
                            self.wait_until_word(words)
                            self.play(FadeIn(pic), run_time=0.3)
                        self.wait_until_bookmark("x")
                        t = until(tr, "y")
                        self.play(Create(arm), FadeIn(dog), run_time=t)
                    self.play(FadeIn(arm), FadeIn(car))
        '''), [])                                           # together on one word, or outside any block: fine

    def test_one_word_does_not_carry_a_stagger(self):
        found = unanchored('''
            class Hook(RAScene):
                def construct(self):
                    arm, dog, car = Square(), Circle(), Triangle()
                    with self.voiceover(text="It steers arms, legs and cars.") as tr:
                        self.wait_until_word("arms")
                        self.play(LaggedStart(FadeIn(arm), FadeIn(dog), GrowFromCenter(car)), run_time=1.5)
                        self.play(Create(arm), run_time=0.5)
                        self.play(FadeIn(dog), FadeIn(car))
        ''')
        self.assertEqual([x["line"] for x in found], [7, 9])   # after a play, the third is tied to no word

    def test_labels_and_parts_are_not_separate_pictures(self):
        found = unanchored('''
            from ep_world import tag

            class Body(RAScene):
                def construct(self):
                    bowl, alt = Circle(), VGroup(Line(), Dot())
                    lab = attach(Text("end cost", font_size=28), bowl)
                    head, lower = title_beat()
                    note = tag("the bowl").next_to(bowl, UP)
                    with self.voiceover(text="Here is the bowl and the end cost.") as tr:
                        self.play(Create(bowl), FadeIn(lab), FadeIn(note), FadeIn(head), Write(lower))
                        self.play(Create(alt[0]), FadeIn(alt[1]), bowl.animate.shift(UP))
                        self.play(LaggedStart(*[FadeIn(x) for x in VGroup(lab, note)]))
        ''', {"ep_world.py": '''
            def tag(text):
                t = Text(text, font_size=26)
                return t.scale(0.9)
        '''})
        self.assertEqual(found, [])

    def test_the_fixture_scene(self):
        fd = CS.Findings()
        CS.unanchored([FIX / "scenes" / "s01_robots.py"], fd)
        self.assertEqual([(x["rule"], x["where"], x["line"]) for x in fd.items], [("unanchored", "Robots", 20)])


class Early(unittest.TestCase):
    """early: a label or equation shown more than sync.lead_max_s before the narration says its words."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_draft(self):
        run = fixture_run(self.d)
        fd, stats = CS.check(run, "draft", CFG)
        early = by_rule(fd, "early")
        self.assertEqual([x["where"] for x in early], ["Robots"])
        self.assertIn("'stage cost'", early[0]["detail"])        # shown with the block's first words, said later
        self.assertIn("wait_until_word('stage cost')", early[0]["detail"])
        self.assertGreater(early[0]["t"], 8.0)
        self.assertEqual(stats["early"], 1)
        self.assertEqual(stats["spoken"], 2)        # "end cost" on its words; "schematic" never said; the opening
        self.assertEqual(stats["unanchored"], 1)    # frame's "a planner" skipped although said later
        self.assertEqual(set(stats["layout_sha256"]), {"Robots"})
        fd, stats = CS.check(run, "draft", dict(CFG, lead_max_s=5.0))
        self.assertEqual(by_rule(fd, "early"), [])

    def test_final_reads_the_narrations_word_timings(self):
        run = fixture_run(self.d, "final")
        fd, _ = CS.check(run, "final", CFG)
        self.assertEqual(len(by_rule(fd, "early")), 1)         # no narration manifest: the render's own timings
        log = json.loads((FIX / "Robots.layout.json").read_text())["scenes"]["Robots"]
        third = log["voiceovers"][2]
        text = third.get("raw") or third["text"]
        key = CS.VS.key(text)
        vdir = run / "video" / "voice"
        vdir.mkdir(parents=True)
        bounds = voice.paused_word_boundaries(text, 1.5, {})   # a fast take: "stage cost" by about 1 s
        (vdir / f"{key}.timings.json").write_text(json.dumps(bounds))
        (vdir / "manifest.json").write_text(json.dumps({"blocks": {key: {"text": text, "file": f"{key}.mp3"}}}))
        fd, _ = CS.check(run, "final", CFG)
        self.assertEqual(by_rule(fd, "early"), [])

    def test_cli_and_gate_report_without_blocking(self):
        run = fixture_run(self.d)
        r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_sync.py"), str(run), "--stage",
                            "draft"], capture_output=True, text=True, env=testenv.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = json.loads((run / "review" / "design" / "draft" / "check_sync.json").read_text())
        self.assertEqual(rep["summary"], {"errors": 0, "warnings": 2})
        self.assertTrue((run / "review" / "design" / "draft" / "check_sync.md").exists())
        g = gate.Gates()
        gate.video_checks(run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("sync"))
        self.assertTrue(row["ok"])
        self.assertIn("not blocking", row["detail"])
        self.assertNotIn("not run on the current", row["detail"])
        (run / "video" / "scenes" / "s01_robots.py").write_text("X = 1\n", encoding="utf-8")
        g = gate.Gates()
        gate.video_checks(run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("sync"))
        self.assertIn("not run on the current", row["detail"])

    def test_errors_block_the_gate_only_when_set(self):
        run = fixture_run(self.d)
        cfg = testenv.variant(self.d / "variant", {"video": {"sync": {"errors_block_gate": True}}})
        r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_sync.py"), str(run), "--stage",
                            "draft"], capture_output=True, text=True, env=testenv.env(cfg))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rep = json.loads((run / "review" / "design" / "draft" / "check_sync.json").read_text())
        self.assertEqual(rep["summary"], {"errors": 1, "warnings": 1})   # the early label; unanchored stays a warning
        with mock.patch.object(gate, "CONFIG", cfg):
            g = gate.Gates()
            gate.video_checks(run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("sync"))
        self.assertFalse(row["ok"])

    def test_scenes_mode_writes_nothing_without_out(self):
        scenes = self.d / "scenes"
        shutil.copytree(FIX / "scenes", scenes)
        r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_sync.py"), "--scenes", str(scenes)],
                           capture_output=True, text=True, env=testenv.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("s01_robots.py:20", r.stdout)
        self.assertEqual(sorted(p.name for p in scenes.iterdir()), ["s01_robots.py"])


WORD_TIMES = r'''
import importlib.machinery, json, sys, types
from pathlib import Path
import numpy as np
sys.path.insert(0, sys.argv[1])
out = Path(sys.argv[2])
mod = types.ModuleType("piper"); mod.__spec__ = importlib.machinery.ModuleSpec("piper", None)
class Chunk:
    def __init__(self, n): self.audio_int16_array = (np.sin(np.arange(n) / 9.0) * 8000).astype(np.int16)
class Voice:                                         # a stand-in for piper-tts: 0.1 s of tone per character
    config = types.SimpleNamespace(sample_rate=16000)
    @classmethod
    def load(cls, model, config_path=None): return cls()
    def synthesize(self, text, syn_config=None):
        yield Chunk(int(16000 * 0.1 * len(text) * (syn_config.kw.get("length_scale") or 1.0)))
class SynthesisConfig:
    def __init__(self, **kw): self.kw = kw
mod.PiperVoice, mod.SynthesisConfig = Voice, SynthesisConfig
sys.modules["piper"] = mod
import voice
from common import RAScene
from manim_voiceover.tracker import TimeInterpolator

def scene(data, start, now):
    interp = TimeInterpolator(data["word_boundaries"])
    tracker = types.SimpleNamespace(data=data, start_t=start, time_interpolator=interp)
    return types.SimpleNamespace(current_tracker=tracker, _now=lambda: now, _word_offset=RAScene._word_offset)

def at(data, word):
    return next(b["audio_offset"] / 1e7 for b in data["word_boundaries"] if b["text"] == word)

res = {}
text = "It <bookmark mark='a'/>steers robot arms, [pause 1] legged robots and cars. Cars again! [pause 0]"
silent = voice.SilentService(cache_dir=str(out))._wrap_generate_from_text(text)
s = scene(silent, 10.0, 10.0)
res["silent"] = [RAScene.time_until_word(s, "LEGGED robots"), at(silent, "legged"),
                 RAScene.time_until_word(s, "cars", occurrence=2), at(silent, "Cars"),
                 RAScene.time_until_word(s, "arms", lead=0.25), at(silent, "arms,") - 0.25,
                 RAScene.time_until_word(scene(silent, 10.0, 13.0), "steers")]
for phrase, n in (("trucks", 1), ("cars", 3), ("", 1)):
    try:
        RAScene.time_until_word(s, phrase, occurrence=n)
    except ValueError as exc:
        res.setdefault("errors", []).append(str(exc))
s.current_tracker._ra_held = True                    # the block has ended
try:
    RAScene.time_until_word(s, "cars")
except RuntimeError as exc:
    res["ended"] = str(exc)
model = out / "m.onnx"; model.write_bytes(b"x"); Path(str(model) + ".json").write_text("{}")
piper = voice.PiperService(model, voice="en_US-test-medium", sentence_pause_s=0.5, cache_dir=str(out))
ptext = "One two three. <bookmark mark='b'/>Four five six seven."
pd = piper._wrap_generate_from_text(ptext)
res["piper"] = [RAScene.time_until_word(scene(pd, 0.0, 0.0), "four"), at(pd, "Four"),
                RAScene.time_until_word(scene(pd, 0.0, 0.0), "six"), at(pd, "six")]
atext = "Azure says 0.42 here, then cars."
reported = [{"audio_offset": int(t * 1e7), "text": w, "duration_milliseconds": 300} for w, t in
            (("Azure", 0.1), ("says", 0.5), ("zero", 0.9), ("point", 1.2), ("four", 1.4), ("two", 1.6),
             ("here", 1.9), (",", 2.2), ("then", 2.4), ("cars", 2.8))]
ad = {"input_text": atext, "word_boundaries": voice.bookmark_safe(reported, atext, 3.5)}
res["azure"] = [RAScene.time_until_word(scene(ad, 5.0, 5.0), "Cars"),
                RAScene.time_until_word(scene(ad, 5.0, 5.0), "then cars")]
print(json.dumps(res))
'''


@unittest.skipUnless(VPY and HAVE_FFMPEG, "needs manim-voiceover (.venv or $MANIM) and ffmpeg")
class WordTimes(unittest.TestCase):
    """time_until_word on the word timings of the silent draft voice, Piper and Azure (a stand-in tracker)."""

    def test_services(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            r = subprocess.run([VPY, "-c", WORD_TIMES, str(REPO / "templates" / "manim"), str(tmp)],
                               capture_output=True, text=True, env=testenv.env())
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            res = json.loads(r.stdout.strip().splitlines()[-1])
            legged, legged_at, cars2, cars2_at, arms, arms_at, past = res["silent"]
            self.assertAlmostEqual(legged, legged_at, places=3)          # case and bookmarks ignored
            self.assertGreater(legged_at - arms_at, 1.0)                  # the [pause 1] in between
            self.assertAlmostEqual(cars2, cars2_at, places=3)             # the second "cars", capitalised
            self.assertAlmostEqual(arms, arms_at, places=3)               # lead
            self.assertEqual(past, 0.0)
            self.assertEqual(len(res["errors"]), 3)
            self.assertIn("trucks", res["errors"][0])
            self.assertIn("2 time(s)", res["errors"][1])
            self.assertIn("voiceover", res["ended"])
            four, four_at, six, six_at = res["piper"]
            self.assertAlmostEqual(four, four_at, places=3)               # the measured start of the second sentence
            self.assertAlmostEqual(six, six_at, places=3)
            cars, then_cars = res["azure"]
            self.assertAlmostEqual(cars, 2.8, places=3)                   # the time the service reported
            self.assertAlmostEqual(then_cars, 2.4, places=3)
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(manim() and HAVE_FFMPEG, "needs Manim with manim-voiceover ($MANIM or .venv) and ffmpeg")
class Rendered(unittest.TestCase):
    """The fixture scene rendered as a silent draft: each picture of block 2 appears on its word, the label "end cost"
    0.3 s before it, and check_sync.py finds in the new layout log what it finds in the fixture's."""

    def test_render(self):
        tmp = Path(tempfile.mkdtemp(prefix="sync-test-"))
        try:
            run = fixture_run(tmp)
            shutil.rmtree(run / "video" / "checks")
            for f in HELPERS:
                shutil.copy(REPO / "templates" / "manim" / f, run / "video" / "scenes" / f)
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(run), "--check"],
                               capture_output=True, text=True, env=testenv.env(MANIM=manim()), cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            log = json.loads((run / "video" / "checks" / "Robots.layout.json").read_text())["scenes"]["Robots"]
            frame = 1.0 / 15

            def said(block, word):
                v = log["voiceovers"][block]
                return v["start"] + next(e[1] for e in v["timings"] if e[0].strip(",.:").lower() == word)

            def fade_in_from(t):
                return min((p["start"] for p in log["plays"] if p["anims"] == ["FadeIn"] and p["start"] >= t - 0.5),
                           key=lambda s: abs(s - t))
            for word in ("robot", "legged", "cars"):
                self.assertAlmostEqual(fade_in_from(said(1, word)), said(1, word), delta=frame + 1e-3)
            self.assertAlmostEqual(fade_in_from(said(2, "end") - 0.3), said(2, "end") - 0.3, delta=frame + 1e-3)
            fresh, _ = CS.check(run, "draft", CFG)
            shutil.copy(FIX / "Robots.layout.json", run / "video" / "checks" / "Robots.layout.json")
            fixed, _ = CS.check(run, "draft", CFG)
            self.assertEqual([(x["rule"], x["where"]) for x in fresh.items],
                             [(x["rule"], x["where"]) for x in fixed.items])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
