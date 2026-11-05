"""Unit tests for the original music and the mastering chain (tools/video/music.py, tools/video/assemble.py), the
music provenance stamp, the per-scene music modes, and the opening and packaging warnings of check_series.py."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))

import music as MU  # noqa: E402
import check_series as CS  # noqa: E402

HAS_FFMPEG = bool(shutil.which("ffmpeg"))


def segments(total=24.0):
    return [{"kind": "scene", "start": 0.0, "duration": 8.0, "role": "hook", "class": "Hook"},
            {"kind": "scene", "start": 8.0, "duration": 4.0, "role": "context", "class": "Ctx"},
            {"kind": "scene", "start": 12.0, "duration": 6.0, "role": "body", "class": "Body", "music": "off"},
            {"kind": "scene", "start": 18.0, "duration": total - 18.0, "role": "outro", "class": "Outro"}]


CHAPTERS = [{"start": 0.0}, {"start": 12.0}, {"start": 18.0}]


def voice(total=24.0, spans=((2.0, 6.0), (13.0, 15.0), (16.0, 17.5))):
    v = np.zeros(int(total * MU.SR))
    t = np.arange(len(v)) / MU.SR
    for a, b in spans:
        m = (t >= a) & (t < b)
        v[m] = 0.2 * np.sin(2 * np.pi * 180 * t[m])
    return v


class Modes(unittest.TestCase):
    def test_defaults_by_role_and_override(self):
        self.assertEqual(MU.scene_mode({"role": "hook"}), "bed")
        self.assertEqual(MU.scene_mode({"role": "context"}), "bed")
        self.assertEqual(MU.scene_mode({"role": "outro"}), "bed")
        self.assertEqual(MU.scene_mode({"role": "body"}), "low")
        self.assertEqual(MU.scene_mode({}), "low")
        self.assertEqual(MU.scene_mode({"role": "body", "music": "off"}), "off")
        self.assertEqual(MU.scene_mode({"role": "hook", "music": "nonsense"}), "low")

    def test_low_is_at_least_20_lu_under_the_voice(self):
        cfg = dict(MU.DEFAULTS)
        under = float(cfg["bed_under_voice_lu"]) + MU.mode_offset_db("low", cfg)
        self.assertLessEqual(under, -20.0)
        self.assertLess(MU.mode_offset_db("off", cfg), -60)

    def test_off_scene_is_silent_between_its_transitions(self):
        cfg = dict(MU.DEFAULTS)
        ev = MU.plan_events(segments(), CHAPTERS, 24.0, [], cfg)
        g = MU.mode_gain(int(24 * MU.SR), ev, cfg)
        self.assertLess(g[int(15.0 * MU.SR)], 1e-3)          # inside the "off" body scene
        self.assertAlmostEqual(g[int(12.0 * MU.SR)], 1.0, places=2)   # the transition swell at its cut
        self.assertAlmostEqual(g[int(4.0 * MU.SR)], 1.0, places=3)    # the hook's bed

    def test_a_planned_beat_in_an_off_scene_is_not_silent(self):
        """v4: a pause of off_beat_swell_s or more in a music-off scene gets the "low" bed, so a planned beat is never
        digital silence (episode 1 v3: 2.6 s of silence after the boxed descent inequality)."""
        cfg = dict(MU.DEFAULTS)
        gaps = MU.pauses(voice(spans=((2.0, 6.0), (13.0, 14.0), (16.5, 17.5))), MU.SR, 1.2)
        ev = MU.plan_events(segments(), CHAPTERS, 24.0, gaps, cfg)
        self.assertTrue(any(a < 15.2 < b for a, b in ev["off_beats"]), ev["off_beats"])
        g = MU.mode_gain(int(24 * MU.SR), ev, cfg)
        low = 10 ** (MU.mode_offset_db("low", cfg) / 20)
        self.assertGreater(g[int(15.25 * MU.SR)], 0.5 * low)        # the beat: the "low" level
        self.assertLess(g[int(13.5 * MU.SR)], 0.6 * low)             # under the words: still off (ramped edges)
        off = dict(cfg, off_beat_swell_s=0)
        ev0 = MU.plan_events(segments(), CHAPTERS, 24.0, gaps, off)
        self.assertEqual(ev0["off_beats"], [])
        self.assertLess(MU.mode_gain(int(24 * MU.SR), ev0, off)[int(15.25 * MU.SR)], 1e-3)

    def test_a_mode_change_inside_a_scene(self):
        """v5: plan.json music_from switches the bed inside a scene at a narration block (the outro's closing question
        under "low" music, after the bed of the card); assemble.py turns the words into a time."""
        cfg = dict(MU.DEFAULTS)
        segs = segments()
        segs[-1]["music_changes"] = [[21.0, "low"]]
        ev = MU.plan_events(segs, CHAPTERS, 24.0, [], cfg)
        self.assertEqual(ev["modes"][-2:], [[18.0, 21.0, "bed"], [21.0, 24.0, "low"]])
        g = MU.mode_gain(int(24 * MU.SR), ev, cfg)
        low = 10 ** (MU.mode_offset_db("low", cfg) / 20)
        self.assertAlmostEqual(g[int(19.5 * MU.SR)], 1.0, places=2)
        self.assertAlmostEqual(g[int(23.0 * MU.SR)], low, places=3)
        import assemble as A
        d = Path(tempfile.mkdtemp())
        try:
            log = d / "Outro.layout.json"
            log.write_text(json.dumps({"scenes": {"Outro": {"voiceovers": [
                {"start": 1.0, "duration": 3.0, "text": "One test."},
                {"start": 5.0, "duration": 2.0, "text": "Until then: why?"}]}}}))
            scene = {"class": "Outro", "music_from": [{"says": "until then", "mode": "low"}]}
            self.assertEqual(A.music_changes(scene, log, 100.0), [[105.0, "low"]])
            self.assertEqual(A.music_changes({"class": "Outro"}, log, 100.0), [])
        finally:
            shutil.rmtree(d)
        import plan as P
        msgs = [m for m in P.problems(Path(tempfile.gettempdir()), {"scenes": [
            {"file": "s.py", "class": "O", "chapter": "A", "music_from": [{"says": "x", "mode": "loud"}]}]})
            if "music_from" in m]
        self.assertTrue(msgs)

    def test_events(self):
        cfg = dict(MU.DEFAULTS)
        gaps = MU.pauses(voice(), MU.SR, 1.2)
        ev = MU.plan_events(segments(), CHAPTERS, 24.0, gaps, cfg)
        self.assertEqual([s["kind"] for s in ev["stings"]], ["hook_title", "outro"])
        self.assertEqual([s["t"] for s in ev["stings"]], [8.0, 18.0])   # the title beat after the hook; the outro
        self.assertEqual(ev["chapters"], [0.0, 12.0, 18.0])
        self.assertGreaterEqual(ev["intro_s"], 2.0)                    # the cold open swells until the first word
        for a, b in ev["swells"]:                                       # no swell inside the "off" scene
            self.assertFalse(12.0 <= (a + b) / 2 < 18.0, (a, b))
        times = MU.chord_times(ev, 12.0)
        for c in ev["chapters"]:
            self.assertIn(c, [round(x, 3) for x in times])              # a chord change on every chapter start


class Generator(unittest.TestCase):
    @unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
    def test_reproducible_and_stamped(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2, \
                tempfile.TemporaryDirectory() as d3:
            a = MU.build(Path(d1), "ep-slug", segments(), CHAPTERS, 24.0, voice())
            b = MU.build(Path(d2), "ep-slug", segments(), CHAPTERS, 24.0, voice())
            c = MU.build(Path(d3), "ep-slug", segments(), CHAPTERS, 24.0, voice(), seed=7)
            self.assertEqual(a["sha256"], b["sha256"])                 # same inputs, same file, bit for bit
            self.assertNotEqual(a["sha256"], c["sha256"])
            self.assertEqual(a["seed"], MU.seed_for("ep-slug"))
            self.assertEqual(a["generator"], MU.GENERATOR)
            self.assertEqual(MU.verify(Path(d1)), [])
            x, sr = MU.read_wav(Path(d1) / "music.wav")
            self.assertEqual(sr, MU.SR)
            self.assertAlmostEqual(x.shape[1] / sr, 24.0, places=2)
            self.assertLess(np.abs(x[:, int(23.95 * sr):]).max(), 0.02)   # faded out at the end
            # tampering is caught
            (Path(d1) / "music.wav").write_bytes(b"RIFF0000")
            self.assertTrue(any("differs" in e for e in MU.verify(Path(d1))))
            st = json.loads((Path(d2) / "music.json").read_text())
            st["generator"] = "someone else"
            (Path(d2) / "music.json").write_text(json.dumps(st))
            self.assertTrue(any("generator" in e for e in MU.verify(Path(d2))))
            self.assertTrue(MU.verify(Path(tempfile.gettempdir()) / "no-such-folder"))


class Ducking(unittest.TestCase):
    def test_duck_depth_lookahead_and_release(self):
        sr = 8000
        v = np.zeros(sr * 6)
        v[sr * 2:sr * 4] = 0.3 * np.sin(np.arange(sr * 2) * 0.3)
        g = MU.duck_gain(v, sr, 7.0, 60, 900, 150)
        db = 20 * np.log10(g)
        self.assertAlmostEqual(db[int(3.5 * sr)], -7.0, delta=0.2)     # full depth while the voice speaks
        self.assertLess(db[int(1.98 * sr)], -1.0)                       # already dipping before the first word
        self.assertGreater(db[int(1.7 * sr)], -0.5)                     # but not long before (look-ahead 150 ms)
        self.assertGreater(db[int(5.9 * sr)], -1.0)                     # mostly recovered (release time constant)
        self.assertLess(db[int(4.3 * sr)], -4.0)                        # the release is slow (900 ms)

    def test_pauses(self):
        gaps = MU.pauses(voice(), MU.SR, 1.2)
        self.assertEqual(gaps[0][0], 0.0)
        self.assertTrue(any(abs(a - 6.0) < 0.05 and abs(b - 13.0) < 0.05 for a, b in gaps), gaps)
        self.assertFalse(any(abs(a - 15.0) < 0.05 for a, b in gaps))   # 1.0 s is too short for a swell


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class Mastering(unittest.TestCase):
    """The whole audio chain of assemble.py on a 24 s clip: narration stem, music, two passes, the true-peak ceiling
    measured after AAC encoding."""

    def test_chain(self):
        import assemble
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            MU.write_wav(d / "v.wav", np.stack([voice(), voice()]) * 2.5)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x0f172a:s=320x180:r=15:d=24",
                            "-i", str(d / "v.wav"), "-c:v", "libx264", "-c:a", "aac", "-shortest", str(d / "j.mp4")],
                           check=True)
            final, build = d / "final", d / "build"
            final.mkdir()
            channel = {"video": {"loudness_lufs": -14}}
            audio = assemble.master_audio(d / "j.mp4", final / "x.mp4", build, final, "slug", segments(), CHAPTERS,
                                          24.0, channel)
            m = audio["measured"]
            self.assertLessEqual(m["true_peak_dbtp"], -1.0)
            self.assertLess(abs(m["integrated_lufs"] + 14.0), 1.0)
            self.assertTrue((final / "narration.wav").exists())
            if audio["music"]["used"]:
                self.assertEqual(MU.verify(final), [])
                self.assertEqual(audio["music"]["modes"][2][2], "off")
                self.assertLessEqual(audio["music"]["under_voice_max_db"], -12.0)   # nothing loud over the words


class OpeningAndPackaging(unittest.TestCase):
    CFG = dict(CS.DEFAULTS)

    def plan(self, **kw):
        p = {"title": "Why Does MPC Converge? A One-Step Proof", "search_term": "MPC",
             "scenes": [{"class": "Hook", "role": "hook"}, {"class": "Body", "role": "body"}],
             "thumbnail": {"scene": "Hook", "time": 5.0, "text": "Why MPC converges"}}
        p.update(kw)
        return p

    def test_good_packaging(self):
        w = CS.Warnings()
        CS.packaging(self.plan(), self.CFG, w)
        self.assertEqual(w.items, [])

    def test_packaging_warnings(self):
        w = CS.Warnings()
        CS.packaging(self.plan(title="Why Does Re-Planning Converge? The Remaining Action: a very long title indeed",
                               thumbnail={"scene": "Body", "time": 40, "text": "Why does it converge?"},
                               _series_title="The Remaining Action"), self.CFG, w)
        text = " ".join(x["detail"] for x in w.items)
        for part in ("characters", "search term", "series name", "words", "click match"):
            self.assertIn(part, text)

    def log(self, t0_paths, vo):
        snap = {"t": 0.0, "settled": False, "texts": [], "paths": t0_paths}
        return {"snapshots": [snap], "voiceovers": vo, "duration": 30.0, "timeline": []}

    def test_hook_checks(self):
        big = [{"bbox": [-5, -2, 2, 2], "stroke_opacity": 1, "fill_opacity": 0, "order": 1, "top": 0}]
        scenes = [{"class": "Hook", "role": "hook"}, {"class": "Ctx", "role": "context"}, {"class": "Body", "role": "body"}]
        good = {"Hook": self.log(big, [{"start": 2.0, "duration": 4.0, "text": "Plans, steps."},
                                       {"start": 7.0, "duration": 4.0, "text": "Why should it ever arrive?"}]),
                "Ctx": dict(self.log([], [{"start": 0.0, "duration": 4.0, "text": "Episode one of seven."}]),
                            duration=5.0), "Body": self.log([], [])}
        w = CS.Warnings()
        CS.hook_checks(scenes, good, {"Hook": 0.0, "Ctx": 30.0, "Body": 36.0}, {}, self.CFG, w)
        self.assertEqual(w.items, [])
        late = {"Hook": self.log([], [{"start": 0.1, "duration": 30.0, "text": "A long set-up, then: why?"}]),
                "Ctx": self.log([], []), "Body": self.log([], [])}
        w = CS.Warnings()
        CS.hook_checks(scenes, late, {"Hook": 0.0, "Ctx": 60.0, "Body": 76.0}, {}, self.CFG, w)
        text = " ".join(x["detail"] for x in w.items)
        for part in ("first frame", "question", "body starts"):
            self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
