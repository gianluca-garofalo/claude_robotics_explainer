"""Unit tests for the spoken-script checks (tools/video/check_script.py) and their report in tools/gate.py."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))

import check_script as CS  # noqa: E402
import gate  # noqa: E402

TICK = 10_000_000

# a hook written for the page, and the same hook written for the ear
WRITTEN = ("This controller plans a whole path, takes one step, and throws the rest away. If it keeps changing its "
           "mind, why should it ever arrive? This is model predictive control, steering robot arms, legged robots and "
           "cars. Nothing in that recipe rules out circling forever. So let's start again from the same point, and "
           "watch one number: what is left to pay. Each step lowers it by at least what that step costs. A bill that "
           "keeps falling by real amounts cannot fall forever: the controller must arrive.")
SPOKEN = ("Here's a controller that plans a whole path, takes a single step, and then throws the rest of the plan "
          "away. Then it does it again. And again. So if it keeps changing its mind, why should it ever get anywhere? "
          "This is model predictive control, and it steers robot arms, legged robots, and cars. Yet nothing in that "
          "recipe stops it from going round in circles forever. So let's keep an eye on just one number: how much is "
          "left to pay. Every step brings it down by at least what that step costs. And a bill that keeps dropping "
          "by real amounts can't keep dropping forever, which means the controller has to arrive.")


def scene_file(cls, blocks):
    body = "\n".join(f"        with self.voiceover(text={b!r}):\n            pass" for b in blocks)
    return f"from common import *\n\nclass {cls}(RAScene):\n    def construct(self):\n{body}\n"


class Measures(unittest.TestCase):
    def test_owner_ab_is_separated(self):
        cfg = dict(CS.DEFAULTS)
        old, new = CS.measure(WRITTEN), CS.measure(SPOKEN)
        self.assertGreater(old["pause_punct_per_100"], cfg["pause_punct_per_100_warn"])
        self.assertLessEqual(new["pause_punct_per_100"], cfg["pause_punct_per_100_warn"])
        self.assertLess(old["contractions_per_100"], cfg["contractions_per_100_min"])
        self.assertGreaterEqual(new["contractions_per_100"], cfg["contractions_per_100_min"])
        self.assertLess(old["connectives_per_100"], cfg["connectives_per_100_min"])
        self.assertGreaterEqual(new["connectives_per_100"], cfg["connectives_per_100_min"])
        self.assertLess(old["sentence_spread"], cfg["sentence_spread_min"])
        self.assertGreaterEqual(new["sentence_spread"], cfg["sentence_spread_min"])

    def test_pause_punctuation(self):
        m = CS.measure("One idea: a colon; a semicolon (and brackets) — a dash. A ratio 3:2 is not a pause.")
        self.assertEqual(m["pause_punct"], 4)                 # ":" ";" "(" and the dash; not "3:2"

    def test_contractions_and_missed_ones(self):
        m = CS.measure("It's here, and we're done. It is not over. Let us see. That's it. Here it is.")
        self.assertEqual(m["contractions"], 3)
        # "It is not" is one place ("it isn't"); "Here it is." ends a sentence and does not contract
        self.assertEqual([u.lower() for u in m["uncontracted"]], ["it is", "let us"])
        self.assertEqual(CS.measure("The controller's plan.")["contractions"], 0)                 # a possessive

    def test_connectives(self):
        m = CS.measure("So it falls. And it keeps falling, which means it stops. Cats and dogs.")
        self.assertEqual(m["connectives"], 3)                 # "So", the opening "And", "which means"; not "and"

    def test_sentences_keep_decimals_and_ellipses(self):
        self.assertEqual(CS.sentences("It costs 0.42 here... Then less. Why?"), ["It costs 0.42 here...",
                                                                                 "Then less.", "Why?"])

    def test_short_runs(self):
        runs = CS.short_runs(["It stops.", "It waits.", "It goes.", "And then it arrives at the bottom of the bowl."],
                             8, 3)
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0]), 3)
        self.assertEqual(CS.short_runs(["It stops.", "It waits.", "A much longer sentence follows these two, "
                                        "doesn't it?"], 8, 3), [])

    def test_repeated_phrases_are_merged(self):
        out = CS.repeated_phrases([("A", "so let's start again from the same point and watch"),
                                   ("B", "now start again from the same point, with five steps")], 5)
        self.assertEqual(out, [("start again from the same point", ["A", "B"])])


class Run(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.run = self.d / "run"
        (self.run / "video" / "scenes").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.d)

    def make(self, scenes, resets=None):
        plan = {"scenes": []}
        for i, (cls, blocks) in enumerate(scenes):
            f = f"s{i + 1:02d}.py"
            (self.run / "video" / "scenes" / f).write_text(scene_file(cls, blocks), encoding="utf-8")
            plan["scenes"].append({"file": f, "class": cls, "role": "hook" if i == 0 else "body",
                                   **({"metaphor_resets": [{"says": resets[cls], "why": "-"}]}
                                      if resets and cls in resets else {})})
        (self.run / "video" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    def test_draft_findings(self):
        self.make([("Hook", [WRITTEN]), ("Body", ["It is amazing. Start again from the same point, with five steps. "
                                                  "It stops. It waits. It goes."])],
                  resets={"Hook": "start again from the same point", "Body": "start again from the same point"})
        fd, stats = CS.check(self.run, "draft", dict(CS.DEFAULTS))
        checks = {(x["check"], x["where"]) for x in fd.items if x["severity"] != "info"}
        self.assertIn(("rhythm", "Hook"), checks)               # a flat hook
        self.assertIn(("rhythm", "Body"), checks)               # three short sentences in a row
        self.assertIn(("hype", "Body"), checks)
        self.assertIn(("stock", "Hook"), checks)                # a stock phrase
        self.assertIn(("stock", "Body, Hook"), checks)          # the same reset words in two scenes
        self.assertIn(("pauses", "narration"), checks)
        self.assertEqual(set(stats["scene_sha256"]), {"s01.py", "s02.py"})

    def test_a_recap_may_repeat_a_result_word_for_word(self):
        result = "Shift the old plan by one step, and cap it with a reference step inside the region."
        self.make([("Hook", ["Why should a controller that keeps changing its mind ever arrive?"]),
                   ("Body", [result + " Then the bill can only fall."]),
                   ("Recap", ["What made the bill fall? " + result])])
        plan_p = self.run / "video" / "plan.json"
        plan = json.loads(plan_p.read_text())

        def repeated(plan):
            plan_p.write_text(json.dumps(plan))
            fd, _ = CS.check(self.run, "draft", dict(CS.DEFAULTS))
            return [x["where"] for x in fd.items if x["check"] == "stock" and "said in" in x["detail"]]
        self.assertEqual(repeated(plan), ["Body, Recap"])                  # a body scene repeating another
        self.assertEqual(repeated(dict(plan, ideas=[{"kind": "recap", "scene": "Recap", "says": "What made"}])), [])
        plan["scenes"][2].update(role="recap", recap_of=1)
        self.assertEqual(repeated(plan), [])                               # an earlier episode's recap

    def test_spoken_hook_passes(self):
        self.make([("Hook", [SPOKEN])])
        fd, _ = CS.check(self.run, "draft", dict(CS.DEFAULTS))
        self.assertEqual([x for x in fd.items if x["severity"] != "info"], [])

    def voice(self, text, bounds, seconds):
        vdir = self.run / "video" / "voice"
        vdir.mkdir(parents=True, exist_ok=True)
        key = CS.VS.key(text)
        (vdir / f"{key}.timings.json").write_text(json.dumps(bounds), encoding="utf-8")
        (vdir / "manifest.json").write_text(json.dumps({"service": "azure", "blocks": {
            key: {"text": text, "file": f"{key}.mp3", "seconds": seconds}}}), encoding="utf-8")

    def test_final_pace_and_mid_sentence_pauses_from_reported_durations(self):
        text = "Every step costs something, and the costs pile up. Then the plan ends."
        self.make([("Hook", [text])])
        t = [("Every", 0.0), ("step", 0.3), ("costs", 0.6), ("something,", 0.9), ("and", 2.4), ("the", 2.6),
             ("costs", 2.8), ("pile", 3.1), ("up.", 3.4), ("Then", 4.6), ("the", 4.9), ("plan", 5.1), ("ends.", 5.4)]
        self.voice(text, [{"audio_offset": int(s * TICK), "text": w, "duration_milliseconds": 250} for w, s in t], 6.0)
        fd, stats = CS.check(self.run, "final", dict(CS.DEFAULTS))
        mids = [x for x in fd.items if x["check"] == "mid pause"]
        self.assertEqual(len(mids), 1)                          # after "something," (1.25 s); not after "up."
        self.assertIn("something,", mids[0]["detail"])
        self.assertEqual(stats["audio"]["wpm"], 130)
        self.assertEqual(stats["audio"]["pause_method"], ["reported"])
        self.assertTrue(any(x["check"] == "pace" and x["where"] == "narration" for x in fd.items))

    def test_longest_pause_is_reported_and_planned_pauses_are_not_stumbles(self):
        text = "Every step costs something, [pause 1.5] and the costs pile up. Then the plan ends."
        self.make([("Hook", [text])])
        t = [("Every", 0.0), ("step", 0.3), ("costs", 0.6), ("something,", 0.9), ("and", 2.9), ("the", 3.1),
             ("costs", 3.3), ("pile", 3.6), ("up.", 3.9), ("Then", 5.1), ("the", 5.4), ("plan", 5.6), ("ends.", 6.1)]
        bounds = [{"audio_offset": int(s * TICK), "text": w, "duration_milliseconds": 250} for w, s in t]
        raw = " ".join(text.split())
        for b in bounds:                                   # bookmark_safe() offsets in the block's text
            b["text_offset"] = raw.index(b["text"], 0 if b is bounds[0] else bounds[bounds.index(b) - 1]["text_offset"] + 1)
        self.voice(raw, bounds, 6.5)
        fd, stats = CS.check(self.run, "final", dict(CS.DEFAULTS))
        self.assertEqual([x for x in fd.items if x["check"] == "mid pause"], [])   # the 1.75 s gap is planned
        self.assertAlmostEqual(stats["audio"]["longest_mid_pause_s"], 0.25, places=2)  # not 0.0: the true longest
        self.assertFalse([x for x in fd.items if x["check"] == "pace" and "no audio" in x["detail"]])   # key found
        self.assertFalse([x for x in fd.items if x["check"] == "pauses" and "[" in x["detail"]])        # no markup

    def test_a_fault_every_take_had_is_reported(self):
        text = "Every step costs something, and the costs pile up. Then the plan ends."
        self.make([("Hook", [text])])
        self.voice(text, [], 4.6)
        man_p = self.run / "video" / "voice" / "manifest.json"
        man = json.loads(man_p.read_text())
        next(iter(man["blocks"].values()))["fault"] = "a 0.27 s silence inside a phrase, after 'costs'"
        man_p.write_text(json.dumps(man))
        fd, _ = CS.check(self.run, "final", dict(CS.DEFAULTS))
        found = [x for x in fd.items if x["check"] == "voice"]
        self.assertEqual([(x["where"], x["severity"]) for x in found], [("Hook", "warning")])
        self.assertIn("inside a phrase", found[0]["detail"])

    def test_final_without_audio_says_so(self):
        self.make([("Hook", [SPOKEN])])
        fd, stats = CS.check(self.run, "final", dict(CS.DEFAULTS))
        self.assertNotIn("audio", stats)
        self.assertTrue(any(x["check"] == "pace" and "manifest" in x["detail"] for x in fd.items))

    def test_cli_writes_reports_and_the_gate_reports_them(self):
        self.make([("Hook", [WRITTEN])])
        r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_script.py"), str(self.run),
                            "--stage", "draft"], capture_output=True, text=True, env=testenv.env())
        self.assertEqual(r.returncode, 0, r.stderr)             # warnings only
        rep = json.loads((self.run / "review" / "design" / "draft" / "check_script.json").read_text())
        self.assertGreater(rep["summary"]["warnings"], 0)
        self.assertTrue((self.run / "review" / "design" / "draft" / "check_script.md").exists())
        g = gate.Gates()
        gate.video_checks(self.run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("spoken script"))
        self.assertTrue(row["ok"])                              # report only (script.errors_block_gate false)
        self.assertIn("not blocking", row["detail"])
        self.assertNotIn("not run on the current", row["detail"])
        (self.run / "video" / "scenes" / "s01.py").write_text(scene_file("Hook", [SPOKEN]), encoding="utf-8")
        g = gate.Gates()
        gate.video_checks(self.run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("spoken script"))
        self.assertIn("not run on the current scene files", row["detail"])


class SceneUrls(unittest.TestCase):
    def test_the_repository_helpers_are_not_scene_code(self):
        d = Path(tempfile.mkdtemp())
        try:
            scenes = d / "run" / "video" / "scenes"
            scenes.mkdir(parents=True)
            shutil.copyfile(REPO / "templates" / "manim" / "voice.py", scenes / "voice.py")   # SSML namespaces
            (scenes / "s01.py").write_text("X = 1\n", encoding="utf-8")
            self.assertEqual(gate.scene_urls(d / "run"), [])
            (scenes / "s01.py").write_text("IMG = 'https://example.com/a.png'\n", encoding="utf-8")
            (scenes / "voice.py").write_text((REPO / "templates" / "manim" / "voice.py").read_text() + "# edited\n")
            self.assertEqual(gate.scene_urls(d / "run"), ["s01.py: URL in scene code", "voice.py: URL in scene code"])
        finally:
            shutil.rmtree(d)

if __name__ == "__main__":
    unittest.main()
