"""Unit tests for the narration voices (templates/manim/voice.py, tools/video/synthesize_voice.py, piper_model.py).

The timing helpers and the voice choice run everywhere. The speech services need manim-voiceover: those tests run in
this interpreter when it has it, else in the Python next to $MANIM or in .venv, and are skipped when there is none.
"""
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import testenv  # noqa: E402
testenv.activate()                  # fixture config and sources, before any tool is imported
sys.path.insert(0, str(REPO / "templates" / "manim"))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "video"))

import voice  # noqa: E402
import metadata  # noqa: E402
import piper_model  # noqa: E402

TICK = voice.AUDIO_OFFSET_RESOLUTION
CHOICE_ENV = ("VOICE_SERVICE", "PIPER_MODEL", "PIPER_MODEL_DIR", "PIPER_VOICE", "CHANNEL_CONFIG",
              "AZURE_SUBSCRIPTION_KEY", "AZURE_SERVICE_REGION", "AZURE_VOICE")


def voice_python():
    """A Python with manim-voiceover (this one, the one next to $MANIM, or .venv), or None."""
    cands = [sys.executable]
    if os.environ.get("MANIM"):
        cands.append(str(Path(os.environ["MANIM"]).parent / "python"))
    cands.append(str(REPO / ".venv" / "bin" / "python"))
    for c in cands:
        if Path(c).exists() and subprocess.run([c, "-c", "import manim_voiceover"], capture_output=True).returncode == 0:
            return c
    return None


VPY = voice_python()
HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def times(bounds):
    return [(b["text_offset"], b["audio_offset"] / TICK) for b in bounds]


def interpolate(bounds, distance):
    """What manim-voiceover's TimeInterpolator does (interp1d without extrapolation), as numpy."""
    import numpy as np
    x = [b["text_offset"] for b in bounds]
    y = [b["audio_offset"] / TICK for b in bounds]
    if not x[0] <= distance <= x[-1]:
        raise ValueError(f"{distance} outside [{x[0]}, {x[-1]}]")
    return float(np.interp(distance, x, y))


class BookmarkSafe(unittest.TestCase):
    TEXT = "The hilltop <bookmark mark='top'/> is where the value is highest. Then <bookmark mark='fall'/>it falls."

    def test_brackets_every_bookmark_distance(self):
        raw = voice.remove_bookmarks(self.TEXT)
        b = voice.linear_word_boundaries(self.TEXT, 6.0)
        self.assertEqual(times(b)[0], (0, 0.0))
        self.assertEqual(times(b)[-1], (len(raw), 6.0))
        for d in (0, 5, len(raw) // 2, len(raw)):
            interpolate(b, d)                                   # never outside the range

    def test_offsets_are_in_the_text_bookmark_distances_use(self):
        raw = voice.remove_bookmarks(self.TEXT)
        b = voice.linear_word_boundaries(self.TEXT, 6.0)
        for x in b[1:-1]:
            self.assertEqual(raw[x["text_offset"]:x["text_offset"] + len(x["text"])], x["text"])
        offs = [x["text_offset"] for x in b]
        self.assertEqual(offs, sorted(set(offs)))

    def test_reanchors_timings_of_the_normalised_text(self):
        # timings made for the whitespace-normalised text (as synthesize_voice stores them) fit the scene's text
        clean = " ".join(voice.remove_bookmarks(self.TEXT).split())
        made = voice.linear_word_boundaries(clean, 6.0)
        safe = voice.bookmark_safe(made, self.TEXT, 6.0)
        raw = voice.remove_bookmarks(self.TEXT)
        words = [x["text"] for x in safe[:-1]]         # the first word sits at offset 0: no extra start boundary
        self.assertEqual(words, raw.split())
        self.assertEqual(safe[-1]["text_offset"], len(raw))

    def test_drops_unmatched_and_clips_times(self):
        bounds = [{"text": "The", "audio_offset": 0}, {"text": "&amp;", "audio_offset": 1 * TICK},
                  {"text": "hilltop", "audio_offset": 9 * TICK}, {"text": "is", "audio_offset": 2 * TICK}]
        safe = voice.bookmark_safe(bounds, self.TEXT, 5.0)
        ts = [t for _, t in times(safe)]
        self.assertEqual(ts, sorted(ts))
        self.assertLessEqual(max(ts), 5.0)
        self.assertNotIn("&amp;", [x["text"] for x in safe])

    def test_partial_tokens_match_the_next_word(self):
        safe = voice.bookmark_safe([{"text": "Hamilton", "audio_offset": 0}, {"text": "Jacobi", "audio_offset": TICK},
                                    {"text": "condition", "audio_offset": 2 * TICK}], "Hamilton-Jacobi condition", 3)
        self.assertEqual([x["text"] for x in safe], ["Hamilton-Jacobi", "condition", "."])

    def test_empty_text_still_interpolates(self):
        b = voice.bookmark_safe([], "<bookmark mark='a'/>", 1.0)
        interpolate(b, 0)
        self.assertLess(b[0]["text_offset"], b[-1]["text_offset"])


class Sentences(unittest.TestCase):
    def test_spans(self):
        raw = "The gain is 0.42 at the top. Does it fall? Yes! (It does.) and then"
        spans = voice.sentence_spans(raw)
        self.assertEqual([raw[a:b].strip() for a, b in spans],
                         ["The gain is 0.42 at the top.", "Does it fall?", "Yes!", "(It does.)", "and then"])

    def test_pauses_follow_the_ending(self):
        """v4: a question and a deliberate ellipsis get longer pauses than a statement (less uniform delivery)."""
        raw = "Does it fall? It does... Then it stops\u2026 Next one. A 0.42 value."
        spans = voice.sentence_spans(raw)
        self.assertEqual(len(spans), 5)                                   # the ellipsis character ends a sentence
        question, dots, char, statement, number = [voice.pause_after(raw[a:b], 0.25) for a, b in spans]
        self.assertEqual((statement, number), (0.25, 0.25))                # a statement: the base pause
        self.assertGreater(question, 0.25)
        self.assertGreater(dots, 0.25)
        self.assertEqual(char, dots)                                      # "..." and the ellipsis character alike
        self.assertEqual(voice.pause_after("Why?", 0.25, question=0.6), 0.6)
        self.assertEqual(voice.pause_after("(Really...)", 0.25, ellipsis=1.0), 1.0)

    def test_sentence_starts_are_kept(self):
        text = "First sentence here. Second one."
        raw = voice.remove_bookmarks(text)
        (a1, b1), (a2, b2) = voice.sentence_spans(raw)
        b = voice.sentence_word_boundaries(text, [(a1, b1, 0.1, 1.5), (a2, b2, 1.9, 3.0)], 3.2)
        starts = {x["text"]: x["audio_offset"] / TICK for x in b}
        self.assertAlmostEqual(starts["First"], 0.1)
        self.assertAlmostEqual(starts["Second"], 1.9)
        self.assertAlmostEqual(b[-1]["audio_offset"] / TICK, 3.2)


class Choice(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "config").mkdir()
        self.cfg = self.tmp / "config" / "channel.json"
        self.cfg.write_text(json.dumps({"voice": {"service": "piper", "piper": {"voice": "en_US-test-medium"}}}))
        self.env = {k: os.environ.pop(k) for k in CHOICE_ENV if k in os.environ}   # hermetic: no keys of this shell
        os.environ["CHANNEL_CONFIG"] = str(self.cfg)
        self.saved_piper = sys.modules.pop("piper", None)

    def tearDown(self):
        for k in CHOICE_ENV:
            os.environ.pop(k, None)
        os.environ.update(self.env)
        sys.modules.pop("piper", None)
        if self.saved_piper is not None:
            sys.modules["piper"] = self.saved_piper
        shutil.rmtree(self.tmp)

    def fake_piper(self):
        mod = types.ModuleType("piper")
        mod.__spec__ = importlib.machinery.ModuleSpec("piper", None)
        sys.modules["piper"] = mod

    def model(self):
        d = self.tmp / ".cache" / "piper"
        d.mkdir(parents=True)
        (d / "en_US-test-medium.onnx").write_bytes(b"onnx")
        (d / "en_US-test-medium.onnx.json").write_text("{}")
        return d / "en_US-test-medium.onnx"

    def test_final_uses_the_setting(self):
        self.assertEqual(voice.resolve(), ("piper", ""))
        os.environ["VOICE_SERVICE"] = "azure"
        self.assertEqual(voice.resolve(), ("azure", ""))
        self.assertEqual(voice.resolve("recorded"), ("recorded", ""))

    def test_drafts_are_silent(self):
        for name in ("piper", "azure", "recorded", None):
            self.assertEqual(voice.resolve(name, draft=True), ("silent", "drafts are silent"), name)
        self.assertEqual(voice.resolve("silent", draft=True), ("silent", ""))

    def test_drafts_are_silent_even_with_the_piper_model(self):
        self.fake_piper()
        m = self.model()
        self.assertEqual(voice.piper_model()[0], m)
        self.assertEqual(voice.available("piper"), (True, ""))
        self.assertEqual(voice.resolve(draft=True), ("silent", "drafts are silent"))
        self.assertEqual(voice.resolve(), ("piper", ""))

    def test_piper_without_its_model_fails_with_the_fix_and_no_other_voice(self):
        self.fake_piper()
        ok, why = voice.available("piper")
        self.assertFalse(ok)
        self.assertIn("./setup.sh", why)
        self.assertIn("piper_model.py fetch", why)
        with self.assertRaises(RuntimeError) as cm:
            voice.speech_service(name="piper")
        self.assertIn("./setup.sh", str(cm.exception))
        self.assertIn("no other voice is used in its place", str(cm.exception))

    def test_model_search_order(self):
        self.model()
        other = self.tmp / "img"
        other.mkdir()
        (other / "en_US-test-medium.onnx").write_bytes(b"x")
        (other / "en_US-test-medium.onnx.json").write_text("{}")
        os.environ["PIPER_MODEL_DIR"] = str(other)
        self.assertEqual(voice.piper_model()[0], other / "en_US-test-medium.onnx")
        (other / "en_US-test-medium.onnx.json").unlink()      # a model without its config does not count
        self.assertEqual(voice.piper_model()[0].parent.name, "piper")

    def test_piper_without_package(self):
        sys.modules["piper"] = None                     # not importable here, whatever this machine has installed
        self.model()
        ok, why = voice.available("piper")
        self.assertFalse(ok)
        self.assertIn("piper-tts", why)

    def test_unknown_service(self):
        self.assertFalse(voice.available("nope")[0])
        with self.assertRaises(ValueError):
            voice.speech_service(name="nope")
        for draft in (False, True):
            with self.assertRaises(ValueError):
                voice.resolve("nope", draft=draft)

    def test_removed_voices_are_refused(self):
        for gone in ("espeak", "gtts", "openai", "elevenlabs"):
            ok, why = voice.available(gone)
            self.assertFalse(ok, gone)
            self.assertIn("unknown voice service", why)
            with self.assertRaises(ValueError):
                voice.speech_service(name=gone)

    def test_keyed_services_name_their_keys(self):
        ok, why = voice.available("azure")
        self.assertFalse(ok)
        self.assertIn("AZURE_SUBSCRIPTION_KEY", why)

    def test_azure_without_its_package_says_so(self):
        os.environ.update(AZURE_SUBSCRIPTION_KEY="dummy", AZURE_SERVICE_REGION="westeurope")
        real = voice._has_module
        voice._has_module = lambda name: False
        try:
            ok, why = voice.available("azure")
        finally:
            voice._has_module = real
        self.assertFalse(ok)
        self.assertIn("azure-cognitiveservices-speech", why)

    def test_azure_settings_and_ssml(self):
        a = voice.azure_settings({"azure_voice": "en-US-SamuelMultilingualNeural", "azure": {"ellipsis_pause_s": 0.5}})
        self.assertEqual(a["voice"], "en-US-SamuelMultilingualNeural")
        ssml = voice.azure_ssml("It does it again... And <bookmark mark='a'/>again & again?", a["voice"], -8,
                                a["ellipsis_pause_s"])
        self.assertIn('<voice name="en-US-SamuelMultilingualNeural">', ssml)
        self.assertIn('<break time="500ms"/>', ssml)            # only the planned beat becomes a break
        self.assertEqual(ssml.count("<break"), 1)
        self.assertIn('<prosody rate="-8%">', ssml)
        self.assertIn("again &amp; again?", ssml)
        self.assertNotIn("bookmark", ssml)

    def test_hd_voice_name_with_a_colon(self):
        hd = "en-US-Steffan:DragonHDLatestNeural"
        a = voice.azure_settings({"azure_voice": hd})
        self.assertEqual((a["voice"], a["retries"], a["min_wpm"]), (hd, 3, 110))
        self.assertIn(f'<voice name="{hd}">', voice.azure_ssml("Hello there.", hd))
        self.assertEqual(voice.DEFAULT_AZURE_VOICE, hd)
        floor = voice.azure_settings({"azure": {"min_rate_pct": -35, "slow_rate_pct": -40}})       # the owner's rule
        self.assertGreaterEqual(min(floor["min_rate_pct"], floor["slow_rate_pct"]), voice.RATE_FLOOR_PCT)
        self.assertNotIn("silence", json.dumps(voice.azure_ssml("One... two.", hd, -8)))

    def test_voice_anomaly(self):
        def take(*words):          # (text, start s, length s)
            return [{"audio_offset": int(t * TICK), "text": w, "duration_milliseconds": int(d * 1000)}
                    for w, t, d in words]
        text = "The robot plans a short path ahead. Then it moves one step... and it plans again."
        good = take(("The", 0.0, 0.2), ("robot", 0.2, 0.3), ("plans", 0.5, 0.3), ("a", 0.8, 0.1),
                    ("short", 0.9, 0.3), ("path", 1.2, 0.3), ("ahead.", 1.5, 0.5), ("Then", 2.4, 0.2),
                    ("it", 2.6, 0.1), ("moves", 2.7, 0.3), ("one", 3.0, 0.3), ("step...", 3.3, 0.5),
                    ("and", 5.3, 0.2), ("it", 5.5, 0.1), ("plans", 5.6, 0.3), ("again.", 5.9, 0.5))
        self.assertEqual(voice.voice_anomaly(good, text, 6.5), "")          # 1.5 s after a planned beat is fine
        stretched = [dict(b) for b in good]
        stretched[7]["audio_offset"] += 3 * TICK                              # 3 s more before "Then"
        self.assertIn("gap before 'Then'", voice.voice_anomaly(stretched, text, 9.5))
        long_word = [dict(b) for b in good]
        long_word[4]["duration_milliseconds"] = 2500
        self.assertIn("'short'", voice.voice_anomaly(long_word, text, 6.5))
        self.assertIn("after the last word", voice.voice_anomaly(good, text, 9.0))
        self.assertEqual(voice.voice_anomaly([], text, 1.0), "no word timings")

    def test_a_faulty_take_is_synthesized_again(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            svc = voice.AzureSpeechService.__new__(voice.AzureSpeechService)
            svc.voice_name, svc.rate_pct, svc.ellipsis_pause_s, svc.style = "en-US-Steffan:DragonHDLatestNeural", -8, 0.7, None
            svc.retries, svc.min_wpm, svc.max_wpm, svc.min_rate_pct = 3, 110, 160, -20
            calls = []

            def fake(ssml, out):
                calls.append(ssml)
                Path(out).write_bytes(b"x")
                gap = 4.0 if len(calls) == 1 else 0.3                         # the first take stretches a pause
                return [{"audio_offset": 0, "text": "Hello", "duration_milliseconds": 400},
                        {"audio_offset": int((0.4 + gap) * TICK), "text": "there.", "duration_milliseconds": 400}]
            svc._synthesize = fake
            real = voice.audio_duration
            voice.audio_duration = lambda p: 1.2 if len(calls) > 1 else 4.9
            try:
                ssml, bounds, duration, takes, fault = svc._take("Hello there.", -8, tmp / "a.mp3")
            finally:
                voice.audio_duration = real
            self.assertEqual((takes, fault, len(calls)), (2, "", 2))
            self.assertEqual(calls[0], calls[1])                              # the same SSML: no cut, no splice
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["a.mp3"])
        finally:
            shutil.rmtree(tmp)

    def test_proxy_settings(self):
        self.assertEqual(voice.proxy_settings({"HTTPS_PROXY": "http://user:pw@127.0.0.1:3128"}),
                         ("127.0.0.1", 3128, "user", "pw"))
        self.assertIsNone(voice.proxy_settings({}))

    def test_durations_survive_bookmark_safe(self):
        out = voice.bookmark_safe([{"audio_offset": 0, "text": "Hello", "duration_milliseconds": 300},
                                   {"audio_offset": 5 * TICK, "text": "there", "duration_milliseconds": 250}],
                                  "Hello there", 1.0)
        self.assertEqual([b.get("duration_milliseconds") for b in out[:2]], [300, 250])

    def test_cli(self):
        cli = [sys.executable, str(REPO / "templates" / "manim" / "voice.py")]
        r = subprocess.run(cli + ["resolve", "azure", "--draft"], capture_output=True, text=True, env=os.environ)
        self.assertEqual(r.stdout.strip(), "silent")
        self.assertIn("drafts are silent", r.stderr)
        r = subprocess.run(cli + ["check", "piper"], capture_output=True, text=True, env=os.environ)
        self.assertEqual(r.returncode, 1)                  # no model under this channel config's folder
        self.assertIn("./setup.sh", r.stdout)


class FinalRenderNeedsItsVoice(unittest.TestCase):
    """render_video.sh: a final render whose voice cannot work here stops before rendering, with the fix."""

    def test_final_render_without_the_piper_model_stops(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "config").mkdir()
            (tmp / "config" / "channel.json").write_text(json.dumps({"voice": {"service": "piper", "piper": {
                "voice": "en_US-missing-medium"}}}))
            run = tmp / "2026-10-31-x"
            (run / "video" / "scenes").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in ("VOICE_SERVICE", "PIPER_MODEL", "PIPER_MODEL_DIR",
                                                                    "PIPER_VOICE")}
            env.update(CHANNEL_CONFIG=str(tmp / "config" / "channel.json"), MANIM="/bin/sh",
                       MANIM_PYTHON=sys.executable, PYTHON=sys.executable)
            r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(run), "--quality", "l"],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("./setup.sh", r.stderr)
            self.assertIn("nothing was rendered", r.stderr)
            self.assertFalse((run / "video" / "renders").exists())
            for mode in (["--quality", "l"], ["--check"]):          # an unknown voice: refused, drafts too
                r = subprocess.run(["bash", str(REPO / "tools" / "render_video.sh"), str(run), *mode, "--voice",
                                    "espeak"], capture_output=True, text=True, env=env)
                self.assertNotEqual(r.returncode, 0, mode)
                self.assertIn("unknown voice service 'espeak'", r.stderr)
        finally:
            shutil.rmtree(tmp)


class PiperModelTool(unittest.TestCase):
    def test_urls(self):
        files = piper_model.files_of("en_US-ljspeech-medium", "main")
        self.assertEqual(files["en_US-ljspeech-medium.onnx"].split("?")[0],
                         "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/"
                         "en_US-ljspeech-medium.onnx")
        self.assertTrue(files["en_US-ljspeech-medium.MODEL_CARD"].split("?")[0].endswith("/medium/MODEL_CARD"))

    def test_rejects_bad_names(self):
        for bad in ("ljspeech", "en_US-ljspeech", "../x-y-medium", "en_US-a-b-ultra"):
            with self.assertRaises(SystemExit):
                piper_model.files_of(bad, "main")

    def test_network_refusal_names_the_hosts(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            def refuse(*a, **k):
                raise piper_model.FetchError("huggingface.co: Tunnel connection failed: 403 Forbidden", network=True)
            saved = piper_model.download
            piper_model.download = refuse
            import contextlib
            import io
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = piper_model.fetch(types.SimpleNamespace(voice="en_US-ljspeech-medium", dest=str(tmp),
                                                             force=False))
            self.assertEqual(rc, 2)
            self.assertIn("huggingface.co", err.getvalue())
            self.assertIn("hf.co", err.getvalue())
            self.assertIn("by hand", err.getvalue())
            self.assertNotIn("espeak", err.getvalue().lower())
            self.assertEqual(list(tmp.iterdir()), [])
        finally:
            piper_model.download = saved
            shutil.rmtree(tmp)


class SyntheticFlag(unittest.TestCase):
    def test_from_the_manifest(self):
        ch = {"youtube": {"contains_synthetic_media": "auto"}, "voice": {"service": "recorded"}}
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "video" / "voice").mkdir(parents=True)
            man = tmp / "video" / "voice" / "manifest.json"
            man.write_text(json.dumps({"blocks": {"a": {"source": "kept"}, "b": {"source": "kept"}}}))
            self.assertFalse(metadata.synthetic_flag(ch, tmp))
            man.write_text(json.dumps({"blocks": {"a": {"source": "kept"}, "b": {"source": "piper"}}}))
            self.assertTrue(metadata.synthetic_flag(ch, tmp))
            man.write_text(json.dumps({"blocks": {"a": {"source": "azure"}}}))
            self.assertTrue(metadata.synthetic_flag(ch, tmp))
        finally:
            shutil.rmtree(tmp)


STAND_IN_PIPER = '''"""Stand-in for piper-tts in the tests: a tone of 0.06 s per character, one chunk per call."""
import types

import numpy as np


class _Chunk:
    def __init__(self, n):
        self.audio_int16_array = (np.sin(np.arange(n) / 9.0) * 8000).astype(np.int16)


class SynthesisConfig:
    def __init__(self, **kw):
        self.kw = kw


class PiperVoice:
    config = types.SimpleNamespace(sample_rate=16000)

    @classmethod
    def load(cls, model, config_path=None):
        return cls()

    def synthesize(self, text, syn_config=None):
        scale = (syn_config.kw.get("length_scale") if syn_config else None) or 1.0
        yield _Chunk(int(16000 * 0.06 * len(text) * scale))
'''


SERVICE_SCRIPT = r'''
import json, sys, types, importlib.machinery, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, sys.argv[1])
out = Path(sys.argv[2])
# a stand-in for piper-tts: 1 s of tone per 10 characters, one chunk per call
mod = types.ModuleType("piper"); mod.__spec__ = importlib.machinery.ModuleSpec("piper", None)
class Chunk:
    def __init__(self, n): self.audio_int16_array = (np.sin(np.arange(n) / 9.0) * 8000).astype(np.int16)
class Voice:
    config = types.SimpleNamespace(sample_rate=16000)
    calls = []
    per_char = 0.1                                   # seconds of audio per character at length_scale 1
    @classmethod
    def load(cls, model, config_path=None): return cls()
    def synthesize(self, text, syn_config=None):
        Voice.calls.append(text)
        yield Chunk(int(16000 * Voice.per_char * len(text) * (syn_config.kw.get("length_scale") or 1.0)))
class SynthesisConfig:
    def __init__(self, **kw): self.kw = kw
mod.PiperVoice, mod.SynthesisConfig = Voice, SynthesisConfig
sys.modules["piper"] = mod
import voice
from manim_voiceover.tracker import TimeInterpolator
model = out / "m.onnx"; model.write_bytes(b"x"); Path(str(model) + ".json").write_text("{}")
svc = voice.PiperService(model, voice="en_US-test-medium", sentence_pause_s=0.5, cache_dir=str(out))
text = "One two three. <bookmark mark='b'/>Four five six seven."
data = svc._wrap_generate_from_text(text)          # as VoiceoverScene calls it: writes the cache entry
again = svc._wrap_generate_from_text(text)         # found in the cache: no second synthesis
with wave.open(str(out / data["original_audio"])) as w:
    dur = w.getnframes() / w.getframerate()
ti = TimeInterpolator(data["word_boundaries"])
starts = {b["text"]: b["audio_offset"] / 1e7 for b in data["word_boundaries"]}
res = {"calls": list(Voice.calls), "duration": dur, "four": starts["Four"], "end": data["word_boundaries"][-1]["audio_offset"] / 1e7,
       "bookmark": ti.interpolate(len("One two three. ")), "cached": again["original_audio"] == data["original_audio"]}
Voice.per_char = 0.02                              # a fast voice: about 500 words per minute
fast = voice.PiperService(model, voice="en_US-test-medium", sentence_pause_s=0.0, max_wpm=150, cache_dir=str(out))
words = "Every frame reads it, so nothing on screen is typed by hand."
fd = fast.generate_from_text(words, cache_dir=str(out))
with wave.open(str(out / fd["original_audio"])) as w:
    res["paced_wpm"] = 60 * voice.spoken_words(words) / (w.getnframes() / w.getframerate())
print(json.dumps(res))
'''


@unittest.skipUnless(VPY and HAVE_FFMPEG, "needs manim-voiceover (.venv or $MANIM) and ffmpeg")
class Services(unittest.TestCase):
    def test_piper_sentences_pauses_cache_and_bookmarks(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            r = subprocess.run([VPY, "-c", SERVICE_SCRIPT, str(REPO / "templates" / "manim"), str(tmp)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            res = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertEqual(res["calls"], ["One two three.", "Four five six seven."])   # one call per sentence
            first = 0.1 * len("One two three.")
            self.assertAlmostEqual(res["four"], first + 0.5, places=3)                  # measured sentence start
            self.assertAlmostEqual(res["duration"], first + 0.5 + 0.1 * len("Four five six seven."), places=3)
            self.assertAlmostEqual(res["end"], res["duration"], places=3)
            self.assertAlmostEqual(res["bookmark"], res["four"], delta=0.05)              # bookmark before "Four"
            self.assertTrue(res["cached"])
            self.assertLessEqual(res["paced_wpm"], 150.5)                                 # slowed to the house rate
            self.assertGreater(res["paced_wpm"], 120)
        finally:
            shutil.rmtree(tmp)

    def test_recorded_converts_formats_and_reanchors(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            vdir, cache = tmp / "voice", tmp / "cache"
            vdir.mkdir()
            cache.mkdir()
            text = "A <bookmark mark='x'/> hilltop holds."
            key = voice.block_key(text)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=2", "-ac", "1",
                            str(vdir / f"{key}.flac")], check=True)
            clean = " ".join(voice.remove_bookmarks(text).split())
            (vdir / f"{key}.timings.json").write_text(json.dumps(voice.linear_word_boundaries(clean, 2.0)))
            script = ("import sys, json; sys.path.insert(0, sys.argv[1]); import voice; "
                      "d = voice.RecordedService(sys.argv[2], cache_dir=sys.argv[3]).generate_from_text(sys.argv[4]); "
                      "print(json.dumps(d))")
            r = subprocess.run([VPY, "-c", script, str(REPO / "templates" / "manim"), str(vdir), str(cache), text],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            d = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertTrue(d["original_audio"].endswith(".wav"))                      # flac -> wav
            raw = voice.remove_bookmarks(text)
            self.assertEqual(d["word_boundaries"][-1]["text_offset"], len(raw))
            hill = next(b for b in d["word_boundaries"] if b["text"] == "hilltop")
            self.assertEqual(raw[hill["text_offset"]:hill["text_offset"] + 7], "hilltop")
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(VPY and HAVE_FFMPEG, "needs manim-voiceover (.venv or $MANIM) and ffmpeg")
class Synthesize(unittest.TestCase):
    """synthesize_voice.py keeps recordings, keeps its own audio and replaces audio made by another service."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "2026-10-31-x"
        scenes = self.run_dir / "video" / "scenes"
        scenes.mkdir(parents=True)
        (scenes / "a.py").write_text(
            "class A(RAScene):\n    def construct(self):\n"
            "        with self.voiceover(text=\"First block here.\"):\n            pass\n"
            "        with self.voiceover(text=\"Second block.\"):\n            pass\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def synth(self, service, env=None):
        r = subprocess.run([VPY, str(REPO / "tools" / "video" / "synthesize_voice.py"), str(self.run_dir),
                            "--service", service], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        return json.loads((self.run_dir / "video" / "voice" / "manifest.json").read_text()), r

    def stand_in_piper(self):
        """An environment with a stand-in piper package (tone instead of speech) and a stand-in voice model."""
        pkg = self.tmp / "standin" / "piper"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(STAND_IN_PIPER, encoding="utf-8")
        model = self.tmp / "standin" / "en_US-standin-medium.onnx"
        model.write_bytes(b"x")
        Path(f"{model}.json").write_text("{}")
        return dict(os.environ, PYTHONPATH=str(self.tmp / "standin"), PIPER_MODEL=str(model))

    def test_sources_carry_over_and_service_change_resynthesizes(self):
        m, _ = self.synth("silent")
        self.assertEqual(m["sources"], {"silent": 2})
        self.assertNotIn("stopgap", m)
        m, _ = self.synth("silent")                     # second run: same service, files kept with their source
        self.assertEqual(m["sources"], {"silent": 2})
        m, r = self.synth("piper", env=self.stand_in_piper())   # another service: every block is made again
        self.assertEqual(m["sources"], {"piper": 2})
        self.assertEqual(m["service"], "piper")
        self.assertEqual(m["timings"], "estimated sentence by sentence")
        files = sorted(p.name for p in (self.run_dir / "video" / "voice").iterdir())
        self.assertEqual(sum(f.endswith(".mp3") for f in files), 0)    # the silent mp3s were replaced by wavs
        self.assertEqual(sum(f.endswith(".wav") for f in files), 2)

    def test_unavailable_service_is_a_clean_error(self):
        env = dict(os.environ, PIPER_VOICE="en_US-missing-medium")      # no such model anywhere
        r = subprocess.run([VPY, str(REPO / "tools" / "video" / "synthesize_voice.py"), str(self.run_dir),
                            "--service", "piper"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: voice service piper", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_recordings_are_never_replaced(self):
        import hashlib
        vdir = self.run_dir / "video" / "voice"
        vdir.mkdir(parents=True)
        key = hashlib.sha1(b"First block here.").hexdigest()[:10]
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=200:d=1", str(vdir / f"{key}.wav")],
                       check=True)
        m, _ = self.synth("silent")
        self.assertEqual(m["blocks"][key]["source"], "kept")
        m, _ = self.synth("silent")
        self.assertEqual(m["blocks"][key]["source"], "kept")
        self.assertEqual(m["sources"], {"kept": 1, "silent": 1})


if __name__ == "__main__":
    unittest.main()
