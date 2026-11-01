"""Narration for scenes (manim-voiceover): one setting picks the voice; word timings keep bookmarks working.

Copy next to the scenes (runs/<run>/video/scenes/voice.py); common.py re-exports speech_service().

The voice source is ONE setting, "voice.service" in config/channel.json. A run may override it: the pipeline's
`voice` input (it sets $VOICE_SERVICE), $VOICE_SERVICE, or `tools/render_video.sh ... --voice NAME`.

    piper     Piper, offline neural text to speech, no key: the voice of final renders. Needs the piper-tts package
              (requirements.txt) and the voice model named by "voice.piper.voice" in .cache/piper/ or
              $PIPER_MODEL_DIR: ./setup.sh downloads it (or python3 tools/video/piper_model.py fetch); the CI image
              has it. Without the model a final render stops and says so: there is no fallback voice.
    azure     Azure AI Speech neural voices; needs AZURE_SUBSCRIPTION_KEY and AZURE_SERVICE_REGION (CI secrets)
    recorded  audio prepared before rendering, one file per voiceover block in video/voice/: your own recordings
              (python3 tools/video/voice_script.py lists the blocks) or the narration tools/video/synthesize_voice.py
              made with Piper or Azure (CI renders this way, keyless)
    silent    silence sized from the word count: draft renders (render_video.sh --check) and tests

Pacing: a Piper block faster than reading.narration_wpm_target of config/video.json (150 words per minute, words
counted as the reading-time check counts them) is synthesized again, slower, so the synthetic voice keeps the house
pacing rule that tools/video/check_reading.py enforces on the final renders.

Draft renders use resolve(draft=True): always silent. Final renders use the setting as it is and fail fast, with
the fix, when it cannot work.

Word timings place <bookmark mark='x'/>. Azure reports where each word starts. Piper and recordings do not, so their
timings are ESTIMATED: Piper's sentence by sentence (each sentence is synthesized on its own, so sentence starts are
measured and only the words inside a sentence are spread by character position), recordings linearly over the
block. Every list goes through bookmark_safe(): offsets are
re-anchored on the block's own text (where manim-voiceover measures bookmark distances), increasing, and bracketed
by the start and the end of the audio, so a bookmark always resolves inside its block. Animations synced to a
bookmark of an estimated voice should tolerate a few tenths of a second.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

try:
    from manim_voiceover.helper import remove_bookmarks
    from manim_voiceover.services.base import SpeechService
    from manim_voiceover.tracker import AUDIO_OFFSET_RESOLUTION
except ImportError:  # resolve(), available() and the timing helpers work without it; the services need it
    AUDIO_OFFSET_RESOLUTION = 10_000_000

    def remove_bookmarks(text):
        return re.sub(r"<bookmark\s*mark\s*=['\"]\w*[\"']\s*/>", "", text)

    class SpeechService:  # placeholder that says what is missing when a service is created
        def __init__(self, *args, **kwargs):
            raise ImportError("manim-voiceover is not installed: pip install -r requirements.txt")

AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
SERVICES = ("piper", "azure", "recorded", "silent")   # the choices of voice.service
DEFAULT_PIPER_VOICE = "en_US-ljspeech-medium"
KEYS = {"azure": ("AZURE_SUBSCRIPTION_KEY", "AZURE_SERVICE_REGION")}
ESTIMATED = {"piper": "estimated sentence by sentence", "silent": "estimated (linear)",
             "azure": "reported by the service"}
PIPER_FIX = "run ./setup.sh (it downloads the voice model), or python3 tools/video/piper_model.py fetch"


def repo_root(start=None):
    """The folder that holds config/channel.json, searched upwards from start (or the working directory)."""
    if os.environ.get("CHANNEL_CONFIG"):
        return Path(os.environ["CHANNEL_CONFIG"]).resolve().parent.parent
    here = Path(start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        if (d / "config" / "channel.json").exists():
            return d
    return None


def channel_config(start=None):
    """config/channel.json of the repository (searched upwards), or $CHANNEL_CONFIG."""
    if os.environ.get("CHANNEL_CONFIG"):
        return json.loads(Path(os.environ["CHANNEL_CONFIG"]).read_text(encoding="utf-8"))
    root = repo_root(start)
    return json.loads((root / "config" / "channel.json").read_text(encoding="utf-8")) if root else {}


def block_key(text):
    """Stable id of a voiceover block: the first 10 hex digits of the SHA-1 of its words (bookmarks removed)."""
    words = " ".join(remove_bookmarks(text).split())
    return hashlib.sha1(words.encode("utf-8")).hexdigest()[:10]


def audio_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _write_wav(path, pcm16, rate):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm16)


_SPOKEN = re.compile(r"[\w'’-]+")   # how tools/video/layout_probe.py counts the words of a block


def spoken_words(text):
    """Words of a voiceover block as the reading-time check counts them (numbers such as 0.42 count twice)."""
    return len(_SPOKEN.findall(remove_bookmarks(text)))


def pacing_limit(start=None):
    """Words per minute a synthesized block should not exceed: reading.narration_wpm_target of config/video.json
    ($VIDEO_CONFIG, or found upwards from start), the target tools/video/check_reading.py measures against."""
    path = os.environ.get("VIDEO_CONFIG")
    if not path:
        root = repo_root(start)
        path = str(root / "config" / "video.json") if root else None
    try:
        return float(json.loads(Path(path).read_text(encoding="utf-8")).get("reading", {})
                     .get("narration_wpm_target", 150)) if path else 150.0
    except (OSError, ValueError):
        return 150.0


# ---------------------------------------------------------------------------------------------- word timings

_WORD = re.compile(r"\S+")


def _token(word):
    return re.sub(r"\W+", "", str(word)).lower()


def _boundary(offset, seconds, word):
    return {"audio_offset": int(round(seconds * AUDIO_OFFSET_RESOLUTION)), "text_offset": int(offset),
            "word_length": len(word), "text": word, "boundary_type": "Word"}


def bookmark_safe(bounds, text, duration):
    """Word timings that manim-voiceover can always interpolate, whatever produced them.

    Each boundary is matched by its word, in order, to the next words of remove_bookmarks(text) (the text in which
    bookmark distances are measured); boundaries that match nothing (punctuation, SSML escapes, a number spoken in
    parts) are dropped. Times never decrease and never pass the end of the audio. A boundary at offset 0 (time 0,
    unless the first word is there) and one at the end of the text (the end of the audio) bracket the list, so every
    bookmark distance lies inside the interpolation range.
    """
    raw = remove_bookmarks(text)
    words = [(m.start(), m.group(), _token(m.group())) for m in _WORD.finditer(raw)]
    end = max(float(duration), 0.0)
    out, cursor, last = [], 0, 0.0
    for b in bounds or []:
        tok = _token(b.get("text", ""))
        if not tok:
            continue
        hit = next((j for j in range(cursor, min(cursor + 4, len(words))) if words[j][2] == tok), None)
        if hit is None and cursor < len(words) and words[cursor][2] and (
                words[cursor][2].startswith(tok) or tok.startswith(words[cursor][2])):
            hit = cursor                                  # "Hamilton" of "Hamilton-Jacobi", "don" of "don't"
        if hit is None:
            continue
        t = min(max(float(b.get("audio_offset", 0)) / AUDIO_OFFSET_RESOLUTION, last), end)
        out.append(_boundary(words[hit][0], t, words[hit][1]))
        cursor, last = hit + 1, t
    if not out or out[0]["text_offset"] > 0:
        out.insert(0, _boundary(0, 0.0, words[0][1] if words else ""))
    out.append(_boundary(max(len(raw), out[-1]["text_offset"] + 1), end, "."))
    return out


def _spread(raw, a, b, t0, t1):
    """Boundaries for the words of raw[a:b], spread over [t0, t1] by their share of the spoken characters."""
    words = list(_WORD.finditer(raw, a, b))
    total = max(sum(len(m.group()) + 1 for m in words) - 1, 1)
    out, n = [], 0
    for m in words:
        out.append(_boundary(m.start(), t0 + (t1 - t0) * n / total, m.group()))
        n += len(m.group()) + 1
    return out


def linear_word_boundaries(text, duration):
    """Estimated timings for a whole block: each word starts at its share of the spoken characters."""
    raw = remove_bookmarks(text)
    return bookmark_safe(_spread(raw, 0, len(raw), 0.0, duration), text, duration)


def sentence_spans(raw):
    """(start, end) character spans of the sentences of raw: a sentence ends at . ! or ? (and closing quotes or
    brackets) followed by whitespace or the end, so decimals such as 0.42 stay whole."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?]+[\"')\]]*(?=\s|$)", raw):
        if raw[start:m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if raw[start:].strip():
        spans.append((start, len(raw)))
    return spans


def sentence_word_boundaries(text, spans, duration):
    """Estimated timings anchored on measured sentences: spans = [(char start, char end, t start, t end)] in the
    coordinates of remove_bookmarks(text); the words inside each sentence are spread by character position."""
    raw = remove_bookmarks(text)
    out = []
    for a, b, t0, t1 in spans:
        out += _spread(raw, a, b, t0, t1)
    return bookmark_safe(out, text, duration)


# ---------------------------------------------------------------------------------------------- services

class SilentService(SpeechService):
    """Offline draft narration: silence whose length follows the word count, with linear word timings."""

    def __init__(self, words_per_minute=150, **kwargs):
        self.words_per_minute = words_per_minute
        super().__init__(**kwargs)

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        cache_dir = cache_dir or self.cache_dir
        clean = " ".join(remove_bookmarks(text).split())
        data = {"input_text": clean, "service": "silent", "wpm": self.words_per_minute}
        cached = self.get_cached_result(data, cache_dir)
        if cached is not None:
            return cached
        duration = max(1.0, 60.0 * spoken_words(clean) / self.words_per_minute)
        name = str(path) if path else self.get_audio_basename(data) + ".mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                        "-t", f"{duration:.3f}", "-q:a", "9", str(Path(cache_dir) / name)], check=True)
        return {"input_text": text, "input_data": data, "original_audio": name,
                "word_boundaries": linear_word_boundaries(text, duration)}


def piper_settings(cfg):
    """voice.piper of config/channel.json with defaults; $PIPER_VOICE overrides the voice name."""
    p = dict(cfg.get("piper") or {})
    p["voice"] = os.environ.get("PIPER_VOICE") or p.get("voice") or DEFAULT_PIPER_VOICE
    return p


def piper_model(cfg=None, start=None):
    """(path of the voice model <voice>.onnx or None, the places searched). <voice>.onnx.json must sit next to it.

    Searched: $PIPER_MODEL (a file), $PIPER_MODEL_DIR/<voice>.onnx (the CI image), <repo>/.cache/piper/<voice>.onnx
    (./setup.sh, python3 tools/video/piper_model.py fetch).
    """
    voice = piper_settings(cfg if cfg is not None else channel_config(start).get("voice", {}))["voice"]
    places = []
    if os.environ.get("PIPER_MODEL"):
        places.append(Path(os.environ["PIPER_MODEL"]))
    if os.environ.get("PIPER_MODEL_DIR"):
        places.append(Path(os.environ["PIPER_MODEL_DIR"]) / f"{voice}.onnx")
    root = repo_root(start)
    if root is not None:
        places.append(root / ".cache" / "piper" / f"{voice}.onnx")
    found = next((p for p in places if p.is_file() and Path(f"{p}.json").is_file()), None)
    return found, places


class PiperService(SpeechService):
    """Piper: offline neural text to speech, no key. One WAV per block, synthesized sentence by sentence; word
    timings estimated within each measured sentence (see the module docstring)."""

    def __init__(self, model, voice=DEFAULT_PIPER_VOICE, length_scale=None, noise_scale=None, noise_w_scale=None,
                 speaker=None, sentence_pause_s=0.25, max_wpm=None, **kwargs):
        self.model = Path(model)
        self.voice_name = voice
        self.synthesis = {"length_scale": length_scale, "noise_scale": noise_scale, "noise_w_scale": noise_w_scale,
                          "speaker_id": speaker}
        self.sentence_pause_s = float(sentence_pause_s)
        self.max_wpm = max_wpm     # pacing: a block faster than this is synthesized again, slower (house rule)
        self._voice = None
        super().__init__(**kwargs)

    def _load(self):
        if self._voice is None:
            from piper import PiperVoice
            self._voice = PiperVoice.load(str(self.model), config_path=f"{self.model}.json")
        return self._voice

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        import numpy as np
        from piper import SynthesisConfig
        cache_dir = cache_dir or self.cache_dir
        raw = remove_bookmarks(text)
        settings = {k: v for k, v in self.synthesis.items() if v is not None}
        data = {"input_text": " ".join(raw.split()), "service": "piper", "voice": self.voice_name,
                "model_bytes": self.model.stat().st_size, "pause_s": self.sentence_pause_s, **settings}
        if self.max_wpm:
            data["max_wpm"] = self.max_wpm
        cached = self.get_cached_result(data, cache_dir)
        if cached is not None:
            return cached
        voice = self._load()
        rate = int(voice.config.sample_rate)
        gap = np.zeros(int(round(self.sentence_pause_s * rate)), dtype=np.int16)

        def synth(settings):
            syn = SynthesisConfig(**settings)
            parts, spans, t = [], [], 0.0
            for a, b in sentence_spans(raw):
                chunks = []
                for c in voice.synthesize(" ".join(raw[a:b].split()), syn_config=syn):
                    pcm = c.audio_int16_array
                    chunks.append(np.asarray(pcm() if callable(pcm) else pcm, dtype=np.int16).reshape(-1))
                pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
                if parts:
                    parts.append(gap)
                    t += len(gap) / rate
                spans.append((a, b, t, t + len(pcm) / rate))
                parts.append(pcm)
                t += len(pcm) / rate
            return (np.concatenate(parts) if parts else np.zeros(rate // 2, dtype=np.int16)), spans

        audio, spans = synth(settings)
        for _ in range(2):                                   # pacing: slow a block down to the house rate
            wpm = 60.0 * spoken_words(raw) / max(len(audio) / rate, 1e-6)
            if not self.max_wpm or wpm <= self.max_wpm:
                break
            settings = dict(settings, length_scale=(settings.get("length_scale") or 1.0) * wpm / self.max_wpm * 1.02)
            audio, spans = synth(settings)
        name = str(path) if path else self.get_audio_basename(data) + ".wav"
        _write_wav(Path(cache_dir) / name, audio.tobytes(), rate)
        return {"input_text": text, "input_data": data, "original_audio": name,
                "word_boundaries": sentence_word_boundaries(text, spans, len(audio) / rate)}


class RecordedService(SpeechService):
    """Audio prepared before rendering: video/voice/<block key>.(wav|mp3|m4a|flac|ogg), one file per voiceover block.

    Your own recordings, or the narration tools/video/synthesize_voice.py made (it also writes <key>.timings.json
    with the service's word timings, used instead of linear ones when present and re-anchored on the scene's text).
    Formats other than WAV and MP3 are converted to WAV, the two manim-voiceover can measure.
    """

    def __init__(self, voice_dir, **kwargs):
        self.voice_dir = Path(voice_dir)
        super().__init__(**kwargs)

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        cache_dir = cache_dir or self.cache_dir
        key = block_key(text)
        src = next((self.voice_dir / f"{key}{s}" for s in AUDIO_SUFFIXES if (self.voice_dir / f"{key}{s}").exists()),
                   None)
        if src is None:
            raise FileNotFoundError(f"no recording for voiceover block {key} in {self.voice_dir}: "
                                    f"{' '.join(remove_bookmarks(text).split())[:80]!r} "
                                    "(python3 tools/video/voice_script.py lists every block)")
        if src.suffix in (".wav", ".mp3"):
            name = f"recorded-{key}{src.suffix}"
            shutil.copyfile(src, Path(cache_dir) / name)
        else:
            name = f"recorded-{key}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", str(Path(cache_dir) / name)],
                           check=True)
        duration = audio_duration(Path(cache_dir) / name)
        timings = self.voice_dir / f"{key}.timings.json"
        bounds = json.loads(timings.read_text(encoding="utf-8")) if timings.exists() else None
        return {"input_text": text, "input_data": {"input_text": text, "service": "recorded", "key": key},
                "original_audio": name,
                "word_boundaries": bookmark_safe(bounds, text, duration) if bounds
                else linear_word_boundaries(text, duration)}


# ---------------------------------------------------------------------------------------------- choosing

def _need(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise RuntimeError(f"voice service needs {', '.join(missing)} in the environment (a CI secret, never a file "
                           "in the repository); piper needs no key")


def available(name, start=None):
    """(True, "") when the service can work here and now, else (False, the reason and the fix)."""
    name = (name or "").strip().lower()
    if name in ("silent", "recorded"):
        return True, ""
    if name == "piper":
        if importlib.util.find_spec("piper") is None:
            return False, f"the piper-tts package is not installed: {PIPER_FIX}"
        model, places = piper_model(start=start)
        if model is None:
            where = ", ".join(str(p) for p in places) or "nowhere: no config/channel.json above this folder"
            return False, f"the Piper voice model is not here (looked in {where}): {PIPER_FIX}"
        return True, ""
    if name in KEYS:
        missing = [k for k in KEYS[name] if not os.environ.get(k)]
        return (not missing), (f"needs {', '.join(missing)} in the environment" if missing else "")
    return False, f"unknown voice service {name!r} ({', '.join(SERVICES)})"


def resolve(name=None, draft=False, start=None):
    """(service, note). The voice is name, else $VOICE_SERVICE, else voice.service of config/channel.json.

    draft=True (render_video.sh --check): always silent (layout and reading-time checks need no voice).
    An unknown name raises ValueError, for drafts too.
    """
    cfg = channel_config(start).get("voice", {})
    name = (name or os.environ.get("VOICE_SERVICE") or cfg.get("service") or "piper").strip().lower()
    if name not in SERVICES:
        raise ValueError(f"unknown voice service {name!r} ({', '.join(SERVICES)})")
    if draft:
        return "silent", ("" if name == "silent" else "drafts are silent")
    return name, ""


def speech_service(scene_dir=None, name=None, cache_dir=None):
    """The speech service named by `name`, $VOICE_SERVICE or 'silent', configured from config/channel.json.

    cache_dir: where generated audio goes (default: manim-voiceover's, under the media folder of the render).
    """
    cfg = channel_config(scene_dir).get("voice", {})
    name = (name or os.environ.get("VOICE_SERVICE") or "silent").strip().lower()
    kw = {"cache_dir": str(cache_dir)} if cache_dir else {}
    if name == "silent":
        return SilentService(words_per_minute=cfg.get("draft_words_per_minute", 150), **kw)
    if name == "recorded":
        voice_dir = os.environ.get("VOICE_DIR") or Path(scene_dir or Path.cwd()) / ".." / "voice"
        return RecordedService(voice_dir, **kw)
    if name == "piper":
        ok, why = available("piper", scene_dir)
        if not ok:
            raise RuntimeError(f"voice service piper: {why}; no other voice is used in its place")
        p = piper_settings(cfg)
        return PiperService(piper_model(cfg, scene_dir)[0], voice=p["voice"], length_scale=p.get("length_scale"),
                            noise_scale=p.get("noise_scale"), noise_w_scale=p.get("noise_w_scale"),
                            speaker=p.get("speaker"), sentence_pause_s=p.get("sentence_pause_s", 0.25),
                            max_wpm=pacing_limit(scene_dir), **kw)
    if name == "azure":
        _need(*KEYS["azure"])
        from manim_voiceover.services.azure import AzureService
        return AzureService(voice=cfg.get("azure_voice", "en-US-AriaNeural"), **kw)
    raise ValueError(f"unknown voice service {name!r} ({', '.join(SERVICES)})")


def main(argv=None):
    """python3 voice.py resolve [NAME] [--draft]   prints the service a render uses (drafts: silent)
       python3 voice.py check NAME                 exit status 0 when NAME works here, 1 with the reason and the fix"""
    import argparse
    ap = argparse.ArgumentParser(description=main.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("name", nargs="?")
    r.add_argument("--draft", action="store_true")
    r.add_argument("--start", help="folder to search config/channel.json from (default: working directory)")
    c = sub.add_parser("check")
    c.add_argument("name")
    c.add_argument("--start")
    a = ap.parse_args(argv)
    if a.cmd == "resolve":
        try:
            name, note = resolve(a.name or None, a.draft, a.start)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if note:
            print(f"voice: {note}", file=sys.stderr)
        print(name)
        return 0
    ok, why = available(a.name, a.start)
    print(f"{a.name}: available" if ok else f"{a.name}: unavailable: {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
