"""Unit tests for the pacing markup and voice pace cap, the rules P1-P20 of check_pacing.py, the idea budget and the
plan.json idea declarations."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "templates" / "manim"))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))

import check_engagement as CE  # noqa: E402
import check_pacing as CP  # noqa: E402
import checks  # noqa: E402
import gate  # noqa: E402
import layout_probe as LP  # noqa: E402
import plan as P  # noqa: E402
import voice  # noqa: E402
import voice_script as VS  # noqa: E402

TICK = voice.AUDIO_OFFSET_RESOLUTION
CFG = CP.settings()


def rates(ssml: str) -> list[float]:
    return [float(e.get("rate").rstrip("%")) for e in ET.fromstring(ssml).iter("{http://www.w3.org/2001/10/synthesis}prosody")]


class Markup(unittest.TestCase):
    TEXT = ("[slow] Every step costs something. [pause 2.5] So the bill can only go down. Now <bookmark mark='x'/>"
            "let's check it on an example. [pause 1.5]")

    def test_markup_never_reaches_captions_word_counts_or_the_checks(self):
        spoken = voice.spoken_text(self.TEXT)
        self.assertNotIn("[", spoken)
        self.assertNotIn("bookmark", spoken)
        self.assertEqual(voice.spoken_words(self.TEXT), voice.spoken_words(spoken))
        self.assertEqual(VS.spoken(self.TEXT), spoken)
        self.assertEqual(LP.MARKUP.sub(" ", self.TEXT).split(), voice.MARKUP.sub(" ", self.TEXT).split())  # the probe
        masked = voice.mask_markup(self.TEXT)                    # offsets kept: bookmark distances do not move
        self.assertEqual(len(masked), len(self.TEXT))
        self.assertEqual(masked.index("<bookmark"), self.TEXT.index("<bookmark"))
        self.assertNotEqual(VS.key(self.TEXT), VS.key(spoken))   # a changed pause is new audio

    def test_blocks_by_class_reads_without_markup_unless_asked(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "s.py").write_text("class A(RAScene):\n    def construct(self):\n"
                                    f"        with self.voiceover(text={self.TEXT!r}):\n            pass\n")
            self.assertEqual(VS.blocks_by_class(d / "s.py")["A"], [voice.spoken_text(self.TEXT)])
            raw = VS.blocks_by_class(d / "s.py", markup=True)["A"][0]
            self.assertIn("[pause 2.5]", raw)
            self.assertEqual(VS.key(raw), next(VS.blocks(d / "s.py"))[0])
        finally:
            shutil.rmtree(d)

    def test_pauses_inside_are_breaks_and_at_the_end_holds(self):
        ssml = voice.azure_ssml(self.TEXT, "V", -15, 0.7, max_break_s=4)
        self.assertEqual(ssml.count("<break"), 1)
        self.assertIn('<break time="2500ms"/>', ssml)           # inside: a break
        self.assertNotIn("1500ms", ssml)                          # after the last word: no audio
        self.assertEqual(voice.block_end_pause(self.TEXT, 0.6), 1.5)
        self.assertEqual(voice.block_end_pause("No tag at the end.", 0.6), 0.6)
        self.assertEqual(voice.block_end_pause("Go straight on. [pause 0]", 0.6), 0.0)
        for tag in ("[pause", "[slow]", "bookmark"):
            self.assertNotIn(tag, ssml)

    def test_a_slow_block_is_read_whole_at_the_slow_rate_never_below_the_floor(self):
        self.assertTrue(voice.slow_block(self.TEXT))
        self.assertFalse(voice.slow_block(voice.spoken_text(self.TEXT)))
        self.assertEqual(rates(voice.azure_ssml(self.TEXT, "V", -15)), [-15.0])       # one run, the whole block
        self.assertGreaterEqual(min(rates(voice.azure_ssml(self.TEXT, "V", -35))), voice.RATE_FLOOR_PCT)
        a = voice.azure_settings({"azure": {"rate_pct": -8, "slow_rate_pct": -40}})
        self.assertEqual(a["slow_rate_pct"], voice.RATE_FLOOR_PCT)                    # the owner's floor
        a = voice.azure_settings({"azure": {"rate_pct": -8, "slow_rate_pct": -3}})
        self.assertEqual(a["slow_rate_pct"], -8.0)                                    # never faster than ordinary
        self.assertAlmostEqual(voice.slow_factor({"azure": {"rate_pct": -8, "slow_rate_pct": -15}}), 92 / 85)

    def test_a_pause_longer_than_one_break_must_end_the_block(self):
        long_inside = "One idea here. [pause 6] And the next one."
        self.assertTrue(voice.markup_problems(long_inside, 4.0))
        with self.assertRaises(ValueError):
            voice.azure_ssml(long_inside, "V", -8, max_break_s=4.0)
        self.assertEqual(voice.markup_problems("One idea here, then a long hold. [pause 6]", 4.0), [])
        self.assertTrue(voice.markup_problems("A [beat 2] tag.", 4.0))

    def test_slow_marks_a_whole_block_and_key_is_retired(self):
        self.assertEqual(voice.markup_problems("<bookmark mark='a'/>[slow] Read it slowly. [pause 2]", 4.0), [])
        self.assertTrue(voice.markup_problems("Not this one. [slow] This one.", 4.0))     # before the first word
        self.assertTrue(voice.markup_problems("[slow] [slow] Once is enough.", 4.0))
        retired = voice.markup_problems("Fast here. [key]Slow here.[/key]", 4.0)
        self.assertEqual(len(retired), 1)
        self.assertIn("[slow]", retired[0])                                          # the fix is named
        with self.assertRaises(ValueError):
            voice.azure_ssml("Fast here. [key]Slow here.[/key]", "V", -8)

    def test_silent_drafts_stretch_a_slow_block_as_the_voice_will(self):
        d = Path(tempfile.mkdtemp())
        svc = voice.SilentService.__new__(voice.SilentService)
        svc.words_per_minute, svc.ellipsis_pause_s, svc.slow_factor = 150, 0.7, 92 / 85
        svc.get_cached_result = lambda data, cache_dir: None
        svc.get_audio_basename = lambda data: "block"
        real = voice.subprocess.run
        voice.subprocess.run = lambda *a, **k: None                                  # no audio file needed here
        try:
            text = "Every step of the plan costs a little, and the bill keeps track of it. [pause 1] So it falls."
            plain = svc.generate_from_text(text, cache_dir=str(d))
            slow = svc.generate_from_text("[slow] " + text, cache_dir=str(d))
        finally:
            voice.subprocess.run = real
            shutil.rmtree(d)
        last = [r["word_boundaries"][-1]["audio_offset"] / TICK - 1.0 for r in (plain, slow)]   # the 1 s pause out
        self.assertAlmostEqual(last[1] / last[0], 92 / 85, places=2)

    def test_silent_drafts_keep_the_planned_pauses(self):
        text = "One two three four. [pause 2] Five six seven eight."
        plan = voice.pause_plan(text)
        self.assertEqual(plan, {4: 2.0})
        b = voice.paused_word_boundaries(text, 4.0, plan)
        start = {x["text"]: x["audio_offset"] / TICK for x in b}
        self.assertAlmostEqual(start["Five"] - start["four."], 2.0 + 4.0 * 6 / 41, places=2)
        self.assertAlmostEqual(b[-1]["audio_offset"] / TICK, 6.0, places=3)


def take(*words):
    """Word timings of a take: (text, start s, length s)."""
    return [{"audio_offset": int(t * TICK), "text": w, "duration_milliseconds": int(d * 1000)} for w, t, d in words]


class TakeCheck(unittest.TestCase):
    TEXT = "The bill drops by at least the step cost. [pause 3] In words, every step pays its way."

    def bounds(self, gap):
        w = [("The", 0.0), ("bill", 0.25), ("drops", 0.5), ("by", 0.8), ("at", 0.95), ("least", 1.1), ("the", 1.4),
             ("step", 1.55), ("cost.", 1.85)]
        after = [("In", 0), ("words,", 0.2), ("every", 0.6), ("step", 0.9), ("pays", 1.15), ("its", 1.4),
                 ("way.", 1.6)]
        end = 2.3
        return take(*[(x, t, 0.22) for x, t in w] + [(x, end + gap + t, 0.22) for x, t in after])

    def test_a_planned_pause_is_not_a_fault_and_an_unplanned_one_is(self):
        self.assertEqual(voice.voice_anomaly(self.bounds(3.1), self.TEXT, 2.3 + 3.1 + 1.9), "")
        plain = self.TEXT.replace(" [pause 3]", "")
        self.assertIn("gap before 'In'", voice.voice_anomaly(self.bounds(3.1), plain, 7.3))

    def test_a_word_without_a_match_keeps_the_pause_planned_before_it(self):
        b = self.bounds(3.1)
        k = next(i for i, x in enumerate(b) if x["text"] == "In")
        b.insert(k, dict(b[k], text="\u2014"))                  # a timing the text has no word for, after the pause
        self.assertEqual(voice.voice_anomaly(b, self.TEXT, 7.3), "")

    def test_a_lost_or_stretched_break_is_retaken(self):
        self.assertIn("planned 3 s pause", voice.voice_anomaly(self.bounds(0.4), self.TEXT, 4.6))
        self.assertIn("gap", voice.voice_anomaly(self.bounds(8.0), self.TEXT, 12.2))

    def test_the_pace_leaves_planned_pauses_out(self):
        text = "Before we go on, try this yourself and pause here if you like. [pause 4] Ready?"
        ws = [(w, 0.3 * k, 0.25) for k, w in enumerate(text.split()[:13])] + [("Ready?", 3.9 + 4.1, 0.4)]
        self.assertEqual(voice.voice_anomaly(take(*ws), text, 8.5, min_wpm=110), "")   # 14 words in 8.5 s


class FakeAzure:
    """A stand-in for the Speech SDK: speech of `per_word` seconds a word at prosody 0 %, slower in proportion at a
    negative rate, plus every <break> of the SSML; word timings to match."""

    def __init__(self, per_word):
        self.per_word, self.calls, self.duration = per_word, [], 0.0

    def synthesize(self, ssml, out):
        self.calls.append(ssml)
        Path(out).write_bytes(b"x")
        root = ET.fromstring(ssml)
        t, bounds = 0.0, []

        def walk(el, rate):
            nonlocal t
            tag = el.tag.split("}")[-1]
            if tag == "prosody":
                rate = float(el.get("rate").rstrip("%"))
            if tag == "break":
                t += float(el.get("time").rstrip("ms")) / 1000.0
            for w in (el.text or "").split():
                d = self.per_word / (1 + rate / 100.0)
                bounds.append({"audio_offset": int(t * TICK), "text": w, "duration_milliseconds": int(d * 900)})
                t += d
            for child in el:
                walk(child, rate)
                for w in (child.tail or "").split():
                    d = self.per_word / (1 + rate / 100.0)
                    bounds.append({"audio_offset": int(t * TICK), "text": w, "duration_milliseconds": int(d * 900)})
                    t += d
        walk(root, 0.0)
        self.duration = t + 0.05
        return bounds


class PaceCap(unittest.TestCase):
    """Rule P20: a block too fast for the house pace gets breaks at its sentence ends first, then a slower rate, never
    below the limit, then a rewrite flag; a slow block starts at the slow rate and is never slowed further."""

    def service(self, per_word):
        svc = voice.AzureSpeechService.__new__(voice.AzureSpeechService)
        svc.voice_name, svc.rate_pct, svc.ellipsis_pause_s, svc.style = "V", -8.0, 0.7, None
        svc.retries, svc.min_wpm, svc.max_wpm, svc.output_format = 1, 110, 160, "x"
        svc.cache_dir = None
        fake = FakeAzure(per_word)
        svc._synthesize = fake.synthesize
        svc.get_cached_result = lambda data, cache_dir: None
        svc.get_audio_basename = lambda data: "block"
        return svc, fake

    def run_block(self, per_word, text):
        tmp = Path(tempfile.mkdtemp())
        svc, fake = self.service(per_word)
        real = voice.audio_duration
        voice.audio_duration = lambda p: fake.duration
        try:
            return svc.generate_from_text(text, cache_dir=str(tmp)), fake
        finally:
            voice.audio_duration = real
            shutil.rmtree(tmp)

    TEXT = ("The plan ends in a region around the rest. Each step costs a little. "
            "So the bill keeps falling. And it never climbs back up.")

    def test_breaks_first(self):
        d, fake = self.run_block(0.31, self.TEXT)                 # a little too fast: breaks are enough
        self.assertEqual(d["input_data"]["pace"], "breaks")
        self.assertEqual(d["input_data"]["applied_rate_pct"], -8.0)
        self.assertNotIn("<break", fake.calls[0])
        self.assertIn("<break", fake.calls[1])

    def test_then_slower_then_rewrite_never_below_the_limits(self):
        d, fake = self.run_block(0.22, self.TEXT)                 # far too fast
        made = d["input_data"]
        self.assertEqual(made["pace"], "rewrite")
        self.assertEqual(made["applied_rate_pct"], -15.0)         # pace_min_rate_pct
        every = [r for ssml in fake.calls for r in rates(ssml)]
        self.assertGreaterEqual(min(every), voice.RATE_FLOOR_PCT)
        self.assertGreaterEqual(min(every), -15.0)                # never past the cap's slowest rate
        self.assertEqual(made["slowest_rate_pct"], -15.0)

    def test_a_slow_block_is_read_slowly_as_a_whole(self):
        plain, _ = self.run_block(0.34, self.TEXT)                # at -8 %: 162 words per minute, a little fast
        self.assertEqual(plain["input_data"]["pace"], "breaks")
        d, fake = self.run_block(0.34, "[slow] " + self.TEXT)     # the same words at -15 %: 150, within the cap
        made = d["input_data"]
        self.assertEqual((made["pace"], made["applied_rate_pct"], made["slow"], made["fault"]), ("ok", -15.0, True, ""))
        self.assertEqual(made["slow_rate_pct"], -15.0)
        self.assertEqual([rates(x) for x in fake.calls], [[-15.0]])   # one take, one run: the whole block
        self.assertGreater(made["speech_wpm"], 110)               # the take check's min_wpm still passes it
        self.assertNotIn("[slow]", fake.calls[0])

    def test_a_dense_slow_block_gets_breaks_then_a_rewrite_never_a_slower_rate(self):
        d, fake = self.run_block(0.22, "[slow] " + self.TEXT)
        made = d["input_data"]
        self.assertEqual((made["pace"], made["applied_rate_pct"]), ("rewrite", -15.0))
        self.assertEqual({r for x in fake.calls for r in rates(x)}, {-15.0})
        self.assertIn("<break", fake.calls[-1])


class Detectors(unittest.TestCase):
    def test_latex_symbols_and_relations(self):
        v_n = r"V_N(q) = \min \Big\{ \sum_{j=0}^{N-1}L_d(q_j,q_{j+1}) + W(q_N) \Big\}"
        syms = set(CP.latex_symbols(v_n))
        self.assertTrue({"V_N", "q", "L_d", "W", "q_N", "q_j"} <= syms)
        self.assertFalse(syms & {"m", "i", "n", "s", "u", "B", "g", "l", "e", "f", "t", "r", "h"})   # no command letters
        self.assertLessEqual(len(syms), 9)
        self.assertIn(r"\varphi_f", CP.latex_symbols(r"W(\varphi_f(q))"))
        self.assertEqual(CP.relations(r"\left( a \right)"), 0)    # \le is not \left
        self.assertEqual(CP.relations(r"V_1 \le V_0"), 1)
        self.assertEqual(CP.latex_symbols(r"V_0 = W \ \text{on}\ \Omega"), ["V_0", "W", r"\Omega"])

    def equations_of(self, contents):
        items = [{"scene": "B", "role": "body", "kind": "math", "content": c, "live": False, "t_on": t,
                  "t_done": t + 1.5, "values": [], "spans": [(t, t + 20)]} for t, c in contents]
        tl = {"items": items}
        labels = []
        return CP.equations(tl, 0.0, 1e9, CFG, labels), labels

    def test_equations_one_relation_rearrangements_and_labels(self):
        eqs, labels = self.equations_of([(10, "q"), (20, r"V_N(q^+) - V_N(q) \le -L_d(q,q^+)"), (30, "V_0 = W"),
                                         (40, r"V_N(q) - V_N(q^+) \ge L_d(q,q^+)")])
        self.assertEqual([x["content"] for x in labels], ["q"])  # a lone symbol is a label, not an equation
        by = {e["content"]: e for e in eqs}
        self.assertIn("V_0 = W", by)                              # one relation and a new symbol
        self.assertEqual(by[r"V_N(q) - V_N(q^+) \ge L_d(q,q^+)"]["weight"], CFG["rearrangement_weight"])
        self.assertEqual(by["V_0 = W"]["t_done"], 31.5)           # timed when it finishes writing

    def timeline(self, words, start=50.0):
        ws = [[w, 0.4 * k, 0.3] for k, w in enumerate(words.split())]
        return {"blocks": [{"scene": "B", "role": "body", "chapter": "c", "start": start, "end": start + 0.4 * len(ws),
                            "text": words, "raw": words, "slow": False, "bookmarks": {},
                            "words": [{"w": w, "t0": start + t, "d": d, "t1": start + t + d} for w, t, d in ws]}],
                "plan": {"glossary": ["one-step bill"]}, "items": []}

    def test_terms_hyphens_and_containment(self):
        tl = self.timeline("Think of it as a bill. Later the one-step bill sits under the end cost.")
        found = {x["term"] for x in CP.terms(tl, dict(CFG, glossary=["bill", "end cost"]))}
        self.assertTrue({"one step bill", "bill", "end cost"} <= found)

    def test_numbers(self):
        tl = self.timeline("The end cost there is zero point six, and checking one point settles every point.")
        nums = CP.numbers(tl)
        self.assertEqual([(n["text"], n["value"]) for n in nums], [("zero point six", 0.6)])
        tl["items"] = [{"kind": "text", "content": "end cost 0.6", "live": False, "values": [], "spans": [(0, 100)]}]
        self.assertTrue(CP.numbers_on_screen(tl, 0.6, nums[0]["t"]))
        self.assertFalse(CP.numbers_on_screen(tl, 0.24, nums[0]["t"]))

    def test_body_from_roles(self):
        tl = {"scenes": [{"role": "hook", "start": 0, "end": 30}, {"role": "context", "start": 30, "end": 36},
                         {"role": "body", "start": 36, "end": 300}, {"role": "outro", "start": 300, "end": 318}]}
        self.assertEqual(CP.body_bounds(tl), (36, 300))

    def test_stem_silences(self):
        d = Path(tempfile.mkdtemp())
        try:
            sr = 16000
            t = np.arange(int(sr * 6)) / sr
            x = 0.3 * np.sin(2 * np.pi * 220 * t)
            x[int(2.0 * sr):int(4.5 * sr)] = 0.0                     # 2.5 s of silence
            x[int(5.0 * sr):int(5.2 * sr)] = 0.0                     # 0.2 s: too short to count
            with wave.open(str(d / "n.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes((x * 32767).astype(np.int16).tobytes())
            sil = checks.silences(d / "n.wav", -30.0, 0.25, relative=True, bridge_s=0.1)
            self.assertEqual(len(sil), 1)
            self.assertAlmostEqual(sil[0][1] - sil[0][0], 2.5, delta=0.06)
        finally:
            shutil.rmtree(d)


def vo(start, text, wpm=150.0, plays=None):
    """A layout-log voiceover as layout_probe.py writes it for a silent draft (planned pauses in place)."""
    plan = voice.pause_plan(text, 0.7)
    speech = 60.0 * voice.spoken_words(text) / wpm
    b = [x for x in voice.paused_word_boundaries(text, speech, plan) if x["text"] != "."]
    seen = {}
    for x in b:
        seen[x["text_offset"]] = [x["text"], x["audio_offset"] / TICK, None]
    clean = voice.strip_markup(text)
    out = {"start": start, "duration": speech + sum(plan.values()), "text": clean,
           "words": voice.spoken_words(text), "timings": [seen[k] for k in sorted(seen)]}
    if clean != " ".join(text.split()):
        out["raw"] = " ".join(text.split())
    return out


def timed(start, text, wpm):
    """A voiceover with word lengths, as Azure reports them, at wpm while speaking."""
    v = vo(start, text, wpm)
    per = 60.0 / wpm
    v["timings"] = [[w, round(per * k, 3), round(per * 0.85, 3), k] for k, (w, _, _) in enumerate(v["timings"])]
    v["duration"] = round(per * len(v["timings"]) + 0.1, 3)
    return v


class Rules(unittest.TestCase):
    """check_pacing.py on synthetic drafts: a hook, a title beat, two body chapters and an outro."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.run = self.d / "run"
        (self.run / "video" / "checks").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.d)

    def make(self, body_blocks, ideas, holds=(), items=(), body_s=None, extra_plan=None, stage="draft"):
        """body_blocks: [(start, text)] of the first body scene, or ready voiceovers (dicts)."""
        vos = [b if isinstance(b, dict) else vo(*b) for b in body_blocks]
        logs = {"Hook": {"duration": 30.0, "voiceovers": [vo(1.0, "Why should a controller that keeps changing its "
                                                              "mind ever arrive?")]},
                "Context": {"duration": 6.0, "voiceovers": [vo(0.5, "Episode one of seven.")]},
                "Body": {"duration": body_s or max(v["start"] + v["duration"] + 8 for v in vos),
                         "voiceovers": vos,
                         "plays": [{"start": a, "end": b, "anims": ["Hold"]} for a, b in holds],
                         "timeline": list(items)},
                "Outro": {"duration": 18.0, "voiceovers": [vo(2.0, "One test, on one step.")]}}
        scenes = [{"file": "s.py", "class": c, "role": r, "chapter": ch} for c, r, ch in (
            ("Hook", "hook", "Opening"), ("Context", "context", "Opening"), ("Body", "body", "The bill"),
            ("Outro", "outro", "The end"))]
        plan = {"scenes": scenes, "ideas": ideas, **(extra_plan or {})}
        (self.run / "video" / "plan.json").write_text(json.dumps(plan))
        folder = self.run / "video" / ("checks" if stage == "draft" else "renders")
        folder.mkdir(parents=True, exist_ok=True)
        for cls, log in logs.items():
            (folder / f"{cls}.layout.json").write_text(json.dumps({"scenes": {cls: log}}))
        return CP.check(self.run, stage, CFG)

    STAR = "After one step, what's left to pay has dropped by at least what that step cost."

    def rules(self, fd, severity=None):
        return {x["rule"] for x in fd.items if severity is None or x["severity"] == severity}

    def test_p6_silence_after_a_starred_result(self):
        star = {"id": "descent", "kind": "star", "scene": "Body", "says": "what's left to pay has dropped"}
        fd, _ = self.make([(1.0, self.STAR + " So the controller arrives.")], [star])
        self.assertIn("P6", self.rules(fd, "error"))                       # the next sentence follows at once
        fd, stats = self.make([(1.0, self.STAR + " [pause 3] In words, every step pays its way.")],
                              [star, {"kind": "restatement", "of": "descent", "scene": "Body", "says": "In words"}])
        self.assertNotIn("P6", self.rules(fd))
        self.assertGreaterEqual(stats["ideas"][0]["silence_after_s"], 2.5)
        fd, _ = self.make([(1.0, self.STAR + " [pause 3]"), (10.0, "In words, every step pays its way.")],
                          [star], holds=[(6.4, 9.4)])                    # a hold of the picture after the block
        self.assertNotIn("P6", self.rules(fd, "error"))
        self.assertIn("P6", self.rules(fd, "warning"))                     # no restatement declared

    def test_p7_stretches_without_a_pause(self):
        long = " ".join(["Every step of the plan adds a small cost to the bill, and the bill keeps track."] * 16)
        fd, stats = self.make([(1.0, long)], [])
        self.assertIn("P7", self.rules(fd, "error"))
        self.assertGreater(stats["longest_stretch_s"], 90)
        parts = long.split(". ")
        broken = ". [pause 1.6] ".join(parts)
        fd, stats = self.make([(1.0, broken)], [])
        self.assertNotIn("P7", self.rules(fd))
        self.assertLess(stats["longest_stretch_s"], 45)

    def test_p3_claims_too_close(self):
        text = "The rest of the plan still ends in the region. The step we added stays inside it too."
        ideas = [{"id": "a", "kind": "claim", "scene": "Body", "says": "still ends in the region"},
                 {"id": "b", "kind": "claim", "scene": "Body", "says": "stays inside it too"}]
        fd, _ = self.make([(1.0, text)], ideas)
        self.assertTrue(any(x["rule"] == "P3" and "comes" in x["detail"] for x in fd.items))

    def test_p11_prompts(self):
        prompt = {"kind": "prompt", "main": True, "scene": "Body", "says": "what's the bill"}
        good = "Before we go on, what's the bill at a point outside? Pause here if you like. [pause 4]"
        fd, _ = self.make([(1.0, good), (12.0, "It's infinite, because no plan ends inside.")], [prompt],
                          holds=[(6.3, 10.3)])
        self.assertFalse([x for x in fd.items if x["rule"] == "P11" and "Body" in x["where"]])
        bad = "Before we go on, what's the bill at a point outside? It's infinite, because no plan ends inside."
        fd, _ = self.make([(1.0, bad)], [prompt])
        details = " ".join(x["detail"] for x in fd.items if x["rule"] == "P11")
        self.assertIn("goes on after the question", details)
        self.assertIn("pause here if you like", details)

    def test_p14_picture_first(self):
        text = "Every step costs something, and the end cost pays for the rest."
        idea = {"id": "end-cost", "kind": "concept", "scene": "Body", "says": "the end cost pays", "shows": "end cost"}

        def label(t):
            return {"kind": "text", "content": "end cost", "live": False, "events": [[t, 1, 0, 0, 1, 1, 1.0]]}
        fd, _ = self.make([(1.0, text)], [idea], items=[label(6.0)])     # words at about 2.6 s, label at 6 s
        self.assertIn("P14", self.rules(fd))
        fd, _ = self.make([(1.0, text)], [idea], items=[label(2.2)])
        self.assertNotIn("P14", self.rules(fd))

    def test_p10_rate_floor_is_an_error_at_the_final_stage(self):
        self.make([(1.0, "One block.")], [])
        voice_dir = self.run / "video" / "voice"
        voice_dir.mkdir(parents=True)
        (voice_dir / "manifest.json").write_text(json.dumps({"blocks": {
            "a": {"applied_rate_pct": -25.0, "slowest_rate_pct": -25.0},
            "b": {"applied_rate_pct": -17.0, "slowest_rate_pct": -17.0},
            "c": {"applied_rate_pct": -8.0, "slowest_rate_pct": -15.0, "pace": "rewrite"},
            "d": {"applied_rate_pct": -15.0, "slowest_rate_pct": -15.0, "slow": True, "slow_rate_pct": -15.0},
            "e": {"applied_rate_pct": -18.0, "slowest_rate_pct": -18.0, "slow": True, "slow_rate_pct": -18.0},
            "f": {"applied_rate_pct": -22.0, "slowest_rate_pct": -22.0, "slow": True, "slow_rate_pct": -22.0}}}))
        (self.run / "video" / "renders").mkdir()
        for f in (self.run / "video" / "checks").glob("*.json"):
            shutil.copy(f, self.run / "video" / "renders" / f.name)
        fd, _ = CP.check(self.run, "final", CFG)
        sev = {(x["rule"], x["where"]): x["severity"] for x in fd.items}
        self.assertEqual(sev[("P10", "block a")], "error")
        self.assertEqual(sev[("P10", "block b")], "warning")
        self.assertNotIn(("P10", "block c"), sev)
        self.assertEqual(sev[("P20", "block c")], "warning")
        self.assertNotIn(("P10", "block d"), sev)                          # a slow block at the slow rate
        self.assertNotIn(("P10", "block e"), sev)                          # at a slower slow rate, above the floor
        self.assertEqual(sev[("P10", "block f")], "error")                 # the floor holds for slow blocks too

    def test_p18_results_must_be_in_the_series_budget(self):
        (self.run / "episode.json").write_text(json.dumps({"ideas": [
            {"id": "descent", "kind": "star", "text": "x"}, {"id": "bill", "kind": "concept", "text": "y"}]}))
        ideas = [{"id": "descent", "kind": "star", "scene": "Body", "says": "what's left to pay"},
                 {"id": "recursion", "kind": "star", "scene": "Body", "says": "So the controller"}]
        fd, stats = self.make([(1.0, self.STAR + " So the controller arrives.")], ideas)
        details = [x["detail"] for x in fd.items if x["rule"] == "P18"]
        self.assertTrue(any("recursion" in d for d in details))
        self.assertEqual(stats["budget"]["from"], "the series plan")

    def test_undeclared_and_unplaced_ideas_are_reported(self):
        fd, _ = self.make([(1.0, "Then the bill is what's called a Lyapunov function. So it settles.")],
                          [{"id": "ghost", "kind": "claim", "scene": "Body", "says": "never said"}])
        self.assertTrue(any(x["rule"] == "ideas" and "ghost" in x["detail"] for x in fd.items))
        self.assertTrue(any(x["rule"] == "coverage" for x in fd.items))

    def test_p10_key_sentences_need_no_contrast_inside_a_slow_block(self):
        others = [timed(1.0 + 7.0 * k, "Every step of the plan costs a little more than the last one.", 160)
                  for k in range(5)]
        slow_others = [timed(60.0 + 7.0 * k, "[slow] Each of these steps is read slowly as a whole.", 140)
                       for k in range(6)]
        star = {"id": "descent", "kind": "star", "scene": "Body", "says": "the bill only falls"}
        line = "So the bill only falls by at least what each step costs."

        def key_findings(text, wpm):
            fd, stats = self.make(others + slow_others + [timed(40.0, text, wpm)], [star], stage="final")
            return [x for x in fd.items if x["rule"] == "P10" and "key sentence" in x["detail"]], stats
        rushed, stats = key_findings(line, 190)
        self.assertEqual(len(rushed), 1)                                   # faster than the ordinary sentences
        self.assertIn("[slow]", rushed[0]["detail"])                       # the fix: a slow block
        self.assertAlmostEqual(stats["speaking_wpm_median"], 160, delta=3)  # slow blocks do not lower the reference
        self.assertAlmostEqual(stats["speaking_wpm_slow_median"], 140, delta=3)
        self.assertEqual(key_findings(line, 150)[0], [])                   # slower than them: the contrast is right
        self.assertEqual(key_findings("[slow] " + line, 190)[0], [])       # inside a slow block: no contrast asked
        self.assertEqual(len(key_findings("[slow] " + line, 110)[0]), 1)   # but never dragged
        cal = stats["calibration"]["slow"]
        self.assertGreater(cal["share_of_body_narration"], 0.3)
        self.assertAlmostEqual(cal["extra_measured"], 160 / 140 - 1, delta=0.03)

    def test_p10_a_body_read_mostly_slow_loses_the_contrast(self):
        slow = "[slow] Each of these steps is read slowly, as a whole, because it carries the argument."
        plain = "Here the picture changes, and nothing new is argued."

        def share_warning(n_slow, n_plain):
            blocks = [(1.0 + 8.0 * k, slow if k < n_slow else plain) for k in range(n_slow + n_plain)]
            fd, stats = self.make(blocks, [])
            return [x for x in fd.items if x["rule"] == "P10" and "narration time" in x["detail"]], stats
        found, stats = share_warning(5, 1)
        self.assertGreater(stats["calibration"]["slow"]["share_of_body_narration"], 0.67)
        self.assertEqual(len(found), 1)
        found, stats = share_warning(3, 3)                                 # half of it: a normal episode
        self.assertEqual(found, [])
        self.assertGreater(stats["calibration"]["slow"]["share_of_body_narration"], 0.4)

    def test_p10_slow_blocks_belong_to_the_body(self):
        fd, _ = self.make([(1.0, "[slow] " + self.STAR)], [])
        self.assertFalse([x for x in fd.items if x["rule"] == "P10" and "([slow]) in the" in x["detail"]])
        (self.run / "video" / "checks" / "Hook.layout.json").write_text(json.dumps({"scenes": {"Hook": {
            "duration": 30.0, "voiceovers": [vo(1.0, "[slow] Why should a controller that keeps changing its mind "
                                                      "ever arrive?")]}}}))
        fd, _ = CP.check(self.run, "draft", CFG)
        self.assertTrue([x for x in fd.items if x["rule"] == "P10" and "in the hook" in x["detail"]])

    def test_p18_short_videos_are_calibration_long_ones_say_more(self):
        (self.run / "episode.json").write_text(json.dumps({"ideas": [
            {"id": "bill", "kind": "concept", "text": "x"}, {"id": "descent", "kind": "star", "text": "y"},
            {"id": "test", "kind": "star", "text": "z"}, {"id": "ex", "kind": "claim", "example": True, "text": "w"}]}))
        fd, stats = self.make([(1.0, "Every step costs something, and the bill keeps track.")], [])
        self.assertFalse([x for x in fd.items if x["rule"] == "P18" and "need" in x["detail"]])
        self.assertLess(stats["calibration"]["runtime_minus_budget_s"][0], -60)      # recorded, not a warning
        (self.run / "episode.json").write_text(json.dumps({"ideas": [{"id": "bill", "kind": "concept", "text": "x"}]}))
        fd, _ = self.make([(1.0, "Every step costs something, and the bill keeps track.")], [], body_s=600.0)
        self.assertTrue([x for x in fd.items if x["rule"] == "P18" and "more than it declares" in x["detail"]])

    def test_the_picture_holds_during_a_starred_results_silence(self):
        star = {"id": "descent", "kind": "star", "scene": "Body", "says": "what's left to pay has dropped"}
        label = {"kind": "text", "content": "a new label", "live": False, "events": [[7.6, 1, 0, 0, 1, 1, 1.0]]}
        fd, _ = self.make([(1.0, self.STAR + " [pause 3]"), (10.0, "In words, every step pays its way.")], [star],
                          holds=[(6.4, 9.4)], items=[label])
        self.assertTrue(any(x["rule"] == "P6" and "picture changes" in x["detail"] for x in fd.items))
        fd, _ = self.make([(1.0, self.STAR + " [pause 3]"), (10.0, "In words, every step pays its way.")], [star],
                          holds=[(6.4, 9.4)])
        self.assertFalse(any(x["rule"] == "P6" and "picture changes" in x["detail"] for x in fd.items))

    def test_discourse_so_is_not_a_claim(self):
        fd, _ = self.make([(1.0, "So far, every step has cost something. So here's the question we need.")], [])
        self.assertFalse([x for x in fd.items if x["rule"] == "coverage" and "undeclared claim" in x["detail"]])
        fd, _ = self.make([(1.0, "Each step costs something. So the bill can only go down.")], [])
        self.assertTrue([x for x in fd.items if x["rule"] == "coverage" and "undeclared claim" in x["detail"]])

    def test_p8_block_pauses_never_shorter_than_sentence_pauses(self):
        def block(start, gap):                       # two sentences with an ordinary (unplanned) pause between them
            words = "The plan ends in the region. Then the step is paid.".split()
            t, tim = 0.0, []
            for k, w in enumerate(words):
                tim.append([w, round(t, 3), 0.3, k])
                t += 0.35 + (gap if w.endswith(".") and k < len(words) - 1 else 0.0)
            return {"start": start, "duration": round(tim[-1][1] + 0.3, 3), "text": " ".join(words),
                    "words": len(words), "timings": tim}
        body = [block(1.0 + 5.4 * k, 1.2) for k in range(8)]               # blocks 0.4 s apart, sentences 1.2 s
        fd, stats = self.make(body, [], stage="final")
        self.assertGreater(stats["sentence_pause_median_s"], stats["block_pause_median_s"])
        self.assertTrue(any(x["rule"] == "P8" and "between sentences" in x["detail"] for x in fd.items))
        vdir = self.run / "video" / "voice"                                # the pace cap's breaks are not the rhythm
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "manifest.json").write_text(json.dumps({"blocks": {VS.key(body[0]["text"]): {"pace_break_s": 0.4}}}))
        fd, stats = self.make(body, [], stage="final")
        self.assertNotIn("sentence_pause_median_s", stats)

    def test_pretraining_counts_every_concept_event_in_the_segment(self):
        pre = [{"label": f"c{k}", "kind": "concept", "pretraining": True, "t": 10.0 + 10 * k, "t_end": 13.0 + 10 * k}
               for k in range(2)]
        fd = CP.Findings()
        seg = CP.pretraining({"items": []}, pre, [], [], fd, CFG, [(10.0, 1.0), (15.0, 1.0), (20.0, 1.0), (22.0, 1.0)])
        self.assertFalse(seg["valid"])
        self.assertTrue(seg["fails"][0].startswith("(a)"))                # four concept events in 60 s, not two

    def test_calibration_times_ideas_by_their_planned_role(self):
        (self.run / "episode.json").write_text(json.dumps({"ideas": [
            {"id": "descent", "kind": "star", "text": "x"},
            {"id": "stable", "kind": "claim", "follows": "descent", "text": "y"}]}))
        ideas = [{"id": "descent", "kind": "star", "scene": "Body", "says": "what's left to pay"},
                 {"id": "stable", "kind": "claim", "scene": "Body", "says": "So the controller"},
                 {"kind": "summary", "scene": "Body", "says": "That's the whole"}]
        _, stats = self.make([(1.0, self.STAR + " So the controller arrives. That's the whole argument.")], ideas)
        roles = stats["calibration"]["seconds_to_next_idea_by_role"]
        self.assertIn("star", roles)
        self.assertIn("consequence", roles)                               # from the series plan, not "key"

    def test_cli_and_gate_report_without_blocking(self):
        self.make([(1.0, self.STAR + " So the controller arrives.")],
                  [{"id": "descent", "kind": "star", "scene": "Body", "says": "what's left to pay"}])
        r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "check_pacing.py"), str(self.run),
                            "--stage", "draft"], capture_output=True, text=True, env=testenv.env())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)             # P6 is an error
        rep = json.loads((self.run / "review" / "design" / "draft" / "check_pacing.json").read_text())
        self.assertGreater(rep["summary"]["errors"], 0)
        g = gate.Gates()
        gate.video_checks(self.run, g, "draft")
        row = next(c for c in g.checks if c["name"].startswith("pacing"))
        self.assertTrue(row["ok"])                                         # pacing.errors_block_gate is false
        self.assertIn("not blocking", row["detail"])


class PlanIdeas(unittest.TestCase):
    def test_declarations(self):
        d = Path(tempfile.mkdtemp())
        try:
            run = d / "run"
            (run / "video" / "scenes").mkdir(parents=True)
            (run / "video" / "scenes" / "s.py").write_text(
                "class Body(RAScene):\n    def construct(self):\n"
                "        with self.voiceover(text=\"So <bookmark mark='star'/>the bill drops.\"):\n            pass\n")
            plan = {"scenes": [{"file": "s.py", "class": "Body"}]}
            ok = [{"id": "descent", "kind": "star", "scene": "Body", "bookmark": "star"},
                  {"kind": "restatement", "of": "descent", "scene": "Body", "says": "the bill drops"},
                  {"kind": "prompt", "main": True, "scene": "Body", "says": "So"}]
            self.assertEqual(P.idea_problems(run, dict(plan, ideas=ok), {"Body"}), [])
            bad = [{"id": "x", "kind": "theorem", "scene": "Body", "says": "a"},
                   {"id": "descent", "kind": "star", "scene": "Body", "bookmark": "nowhere"},
                   {"kind": "restatement", "scene": "Body", "says": "a"},
                   {"id": "c", "kind": "concept", "scene": "Body", "says": "a", "bookmark": "star"},
                   {"id": "d", "kind": "claim", "scene": "Elsewhere", "says": "a", "main": True}]
            found = P.idea_problems(run, dict(plan, ideas=bad), {"Body"})
            self.assertEqual(len(found), 6, found)
        finally:
            shutil.rmtree(d)

    def test_budget_of_a_standalone_run(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "video").mkdir()
            ideas = [{"id": "descent", "kind": "star", "scene": "Body", "says": "x"},
                     {"id": "step", "kind": "claim", "of": "descent", "scene": "Body", "says": "y"},
                     {"kind": "summary", "scene": "Body", "says": "z"}]
            (d / "video" / "plan.json").write_text(json.dumps({"scenes": [], "ideas": ideas}))
            r = subprocess.run([sys.executable, str(REPO / "tools" / "video" / "idea_budget.py"), str(d)],
                               capture_output=True, text=True, env=testenv.env())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("1 ideas"), r.stdout)       # the star; a step and a summary are not
            self.assertIn(" min", r.stdout)
        finally:
            shutil.rmtree(d)


class EngagementHolds(unittest.TestCase):
    """Rule P19: planned pauses and holds are consolidation time, not frozen narration or dead air."""

    def test_planned_pauses_are_not_narration(self):
        log = {"voiceovers": [vo(2.0, "The bill drops by at least the step. [pause 3] In words, each step pays.")]}
        pauses = CE.planned_pauses(log, 4.0)
        self.assertEqual(len(pauses), 1)
        self.assertAlmostEqual(pauses[0][1] - pauses[0][0], 3.0, places=2)
        self.assertEqual(CE.planned_pauses(log, 2.0), [])                  # longer than the exemption: not exempt
        self.assertEqual(CE.minus([(0.0, 10.0)], [(4.0, 7.0)]), [(0.0, 4.0), (7.0, 10.0)])
        self.assertEqual(CE.holds({"plays": [{"start": 1, "end": 3, "anims": ["Hold"]},
                                             {"start": 3, "end": 4, "anims": ["Indicate"]}]}), [(1.0, 3.0)])

    def test_pauses_stay_in_place_when_a_word_has_no_timing(self):
        log = {"voiceovers": [vo(2.0, "The bill drops by at least the step. [pause 3] In words, each step pays.")]}
        v = log["voiceovers"][0]
        v["timings"] = [e + [k] for k, e in enumerate(v["timings"])]   # with each word's index, as the probe logs
        full = CE.planned_pauses(log, 4.0)
        del v["timings"][2]                                            # the voice gave no timing for one word
        self.assertEqual(CE.planned_pauses(log, 4.0), full)

    def test_silence_before_assembly_counts_on_the_swells(self):
        d = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(CE.off_beat_fill_s(d, "final"), CE.off_beat_fill_s(d, "draft"))
        finally:
            shutil.rmtree(d)


def _manim():
    m = os.environ.get("MANIM") or str(REPO / ".venv" / "bin" / "manim")
    return m if Path(m).exists() else shutil.which("manim")


@unittest.skipUnless(_manim() and shutil.which("ffmpeg"), "needs Manim with manim-voiceover ($MANIM or .venv) and ffmpeg")
class RenderedHolds(unittest.TestCase):
    """A rendered draft: the pause after a block is a hold of the picture (no audio), the default one too; a slow block
    lasts as the voice will read it; captions and the layout log's text carry no markup; the log has the word timings
    and bookmark times check_pacing.py reads."""

    def test_render(self):
        tmp = Path(tempfile.mkdtemp(prefix="holds-test-"))
        try:
            scenes = tmp / "video" / "scenes"
            scenes.mkdir(parents=True)
            for f in ("common.py", "voice.py", "reading_model.py"):
                shutil.copy(REPO / "templates" / "manim" / f, scenes / f)
            (scenes / "t.py").write_text(
                "from manim import *\nfrom common import *\n\n"
                "class T(RAScene):\n    def construct(self):\n"
                "        d = Dot(radius=0.4, color=INK)\n"
                "        self.add(Square(5, color=INK, stroke_width=8), Text('holds', font_size=48).shift(2 * UP), d)\n"
                "        with self.voiceover(text=\"One two three four. [pause 2] <bookmark mark='b'/>Five six seven "
                "eight. [pause 1.5]\") as tr:\n"
                "            self.play(d.animate.shift(RIGHT), run_time=tr.duration)\n"
                "        with self.voiceover(text='[slow] Nine ten eleven twelve.') as tr:\n"
                "            self.play(d.animate.shift(LEFT), run_time=tr.duration)\n"
                "        beat(self, 2.0)\n", encoding="utf-8")
            env = dict(os.environ, MANIM=_manim(), VOICE_SERVICE="silent")
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(tmp), "--check", "--voice", "silent",
                                "--scene", "t.py:T"], capture_output=True, text=True, env=env, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            log = json.loads((tmp / "video" / "checks" / "T.layout.json").read_text())["scenes"]["T"]
            v1, v2 = log["voiceovers"]
            self.assertNotIn("[", v1["text"] + v2["text"])
            self.assertIn("[pause 2]", v1["raw"])
            words = {e[0]: e[1] for e in v1["timings"]}
            self.assertGreater(words["Five"] - words["four."], 2.0)          # the planned pause, in the draft too
            self.assertEqual([e[3] for e in v1["timings"]], list(range(8)))  # each word's index among the words
            self.assertIn("b", v1["bookmarks"])
            self.assertAlmostEqual(v2["start"] - (v1["start"] + v1["duration"]), 1.5, delta=0.05)   # its own hold
            cfg = json.loads((testenv.CONFIG / "channel.json").read_text())["voice"]
            self.assertAlmostEqual(v2["duration"], 60 * 4 / cfg.get("draft_words_per_minute", 150)
                                   * voice.slow_factor(cfg), delta=0.06)            # the slow block, stretched
            self.assertIn("[slow]", v2["raw"])
            holds = [p["end"] - p["start"] for p in log["plays"] if "Hold" in p["anims"]]
            self.assertEqual(len(holds), 3)                                  # 1.5 s, the default after block 2, beat
            self.assertAlmostEqual(sorted(holds)[-1], 2.0, delta=0.05)
            srt = (tmp / "video" / "checks" / "T_ql.srt").read_text()
            self.assertNotIn("[", srt)
            self.assertIn("Five six seven eight", srt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
