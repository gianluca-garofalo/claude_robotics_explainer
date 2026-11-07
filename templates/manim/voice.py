"""Narration for scenes (manim-voiceover): the speech service voice.service names, word timings for bookmarks.

Usage (it sits next to the scenes, runs/<run>/video/scenes/voice.py; common.py re-exports speech_service()):
  python3 voice.py resolve [NAME] [--draft] [--start DIR]   # the service a render uses (drafts: silent)
  python3 voice.py check NAME [--start DIR]                 # exit status 0 when NAME works here, else 1 and the fix
"""
import bisect
import hashlib
import importlib.util
import json
import math
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
except ImportError:  # the tools use the timing and markup helpers without manim-voiceover; only services need it
    AUDIO_OFFSET_RESOLUTION = 10_000_000

    def remove_bookmarks(text):
        return re.sub(r"<bookmark\s*mark\s*=['\"]\w*[\"']\s*/>", "", text)

    class SpeechService:  # placeholder that says what is missing when a service is created
        def __init__(self, *args, **kwargs):
            raise ImportError("manim-voiceover is not installed: pip install -r requirements.txt")

AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
SERVICES = ("piper", "azure", "recorded", "silent")   # the choices of voice.service
DEFAULT_PIPER_VOICE = "en_US-ljspeech-medium"
DEFAULT_AZURE_VOICE = "en-US-Steffan:DragonHDLatestNeural"
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


# audio_duration and _write_wav repeat tools/video/media.py: this file runs from a run's scene folder, without tools/
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
    """Words of a block as the reading-time check counts them (0.42 is two words; the markup is none)."""
    return len(_SPOKEN.findall(strip_markup(remove_bookmarks(text))))


def pacing_limit(start=None):
    """reading.narration_wpm_target of config/video.json: the words per minute a synthesized block stays under."""
    path = os.environ.get("VIDEO_CONFIG")
    if not path:
        root = repo_root(start)
        path = str(root / "config" / "video.json") if root else None
    try:
        return float(json.loads(Path(path).read_text(encoding="utf-8")).get("reading", {})
                     .get("narration_wpm_target", 150)) if path else 150.0
    except (OSError, ValueError):
        return 150.0


RATE_FLOOR_PCT = -20.0      # no block is ever read slower: below it the voice drags words
PAUSE_TAG = re.compile(r"\[pause\s+(\d+(?:\.\d+)?)\s*s?\]", re.I)
MARKUP = re.compile(r"\[(?:pause\s+\d+(?:\.\d+)?\s*s?|slow)\]", re.I)
_SLOW_TAG = re.compile(r"\[slow\]", re.I)
_RETIRED_KEY = re.compile(r"\[/?key\]", re.I)
_ANY_TAG = re.compile(r"\[[^\[\]\n]{0,40}\]")
_ELLIPSIS_END = ("...", "…")
_SENTENCE_END = (".", "!", "?")
_WORD = re.compile(r"\S+")


def strip_markup(text):
    """The text without the pacing markup ([pause S], [slow]), as captions show it."""
    return " ".join(MARKUP.sub(" ", str(text)).split())


def mask_markup(text):
    """The markup replaced by spaces of the same length, so character offsets (bookmark distances) stay."""
    return MARKUP.sub(lambda m: " " * len(m.group()), str(text))


def spoken_text(text):
    return strip_markup(remove_bookmarks(text))


def _word_starts(raw):
    return [m.start() for m in _WORD.finditer(mask_markup(raw))]


def planned_pauses(text):
    """[(spoken words before the tag, seconds, "inside" a break or "end" a hold after the block)] of [pause S]."""
    raw = remove_bookmarks(text)
    starts = _word_starts(raw)
    out = []
    for m in PAUSE_TAG.finditer(raw):
        n = bisect.bisect_left(starts, m.start())
        out.append((n, float(m.group(1)), "end" if n >= len(starts) else "inside"))
    return out


def block_end_pause(text, default=0.0):
    """Seconds the picture holds after a block: its final [pause S] tags ([pause 0]: none), else default."""
    ends = [s for _, s, where in planned_pauses(text) if where == "end"]
    return float(sum(ends)) if ends else float(default)


def pause_plan(text, ellipsis_s=0.0, pace_break_s=0.0):
    """{n: seconds} of the breaks after the first n spoken words: [pause S] tags, untagged ellipses (ellipsis_s) and,
    with pace_break_s, the other sentence ends; none after the last word."""
    raw = remove_bookmarks(text)
    words = [m.group() for m in _WORD.finditer(mask_markup(raw))]
    plan = {}
    for n, s, where in planned_pauses(text):
        if where == "inside":
            plan[n] = plan.get(n, 0.0) + s
    for i, w in enumerate(words[:-1]):
        end = w.rstrip("\"')]")
        if i + 1 in plan:
            continue
        if end.endswith(_ELLIPSIS_END):
            if ellipsis_s:
                plan[i + 1] = float(ellipsis_s)
        elif pace_break_s and end.endswith(_SENTENCE_END):
            plan[i + 1] = float(pace_break_s)
    return plan


def with_text(cached, text):
    """A cache hit with this call's text: the cache key leaves bookmarks out, but manim-voiceover places them from
    "input_text", so the cached entry's old text would put a moved bookmark where it was (or miss it)."""
    return dict(cached, input_text=text)


def slow_block(text):
    return bool(_SLOW_TAG.search(remove_bookmarks(str(text))))


def slow_factor(cfg):
    """How much longer a [slow] block lasts at the Azure rates: (100 + rate_pct) / (100 + slow_rate_pct)."""
    a = azure_settings(cfg)
    return (100.0 + a["rate_pct"]) / (100.0 + a["slow_rate_pct"])


def markup_problems(text, max_break_s=None):
    """Why a block's pacing markup cannot be voiced as written, each with the fix ([] when it can)."""
    raw = remove_bookmarks(text)
    out = []
    if _RETIRED_KEY.search(raw):
        out.append("[key] is retired: read a key sentence in a slow block, "
                   "[slow] before the first word of its derivation's block or of a block of its own")
    out += [f"unknown tag {m.group()!r} (the markup is [pause S] and [slow])"
            for m in _ANY_TAG.finditer(raw) if not (MARKUP.fullmatch(m.group()) or _RETIRED_KEY.fullmatch(m.group()))]
    starts = _word_starts(raw)
    slow = [bisect.bisect_left(starts, m.start()) for m in _SLOW_TAG.finditer(raw)]
    if len(slow) > 1:
        out.append("one [slow] per block (it marks the whole block)")
    if any(n > 0 for n in slow):
        out.append("[slow] marks a whole block: put it before the first word")
    for n, s, where in planned_pauses(text):
        if n == 0:
            out.append(f"[pause {s:g}] before the first word: hold the picture before the block instead (beat())")
        elif where == "inside" and s <= 0:
            out.append("[pause 0] belongs after the last word (no hold after the block)")
        elif where == "inside" and max_break_s and s > float(max_break_s) + 1e-9:
            out.append(f"[pause {s:g}] is longer than one break ({float(max_break_s):g} s): end the block there; a "
                       "[pause S] after the last word holds the picture for any length")
    return out


def _token(word):
    return re.sub(r"\W+", "", str(word)).lower()


def _boundary(offset, seconds, word, duration_ms=None):
    b = {"audio_offset": int(round(seconds * AUDIO_OFFSET_RESOLUTION)), "text_offset": int(offset),
         "word_length": len(word), "text": word, "boundary_type": "Word"}
    if duration_ms is not None:
        b["duration_milliseconds"] = int(duration_ms)
    return b


def _match_words(bounds, raw):
    """(the words of raw as (offset, word, token), [(boundary, index of the word it matches)]), matched in order;
    boundaries that match no word (punctuation, SSML escapes, a number spoken in parts) are left out."""
    words = [(m.start(), m.group(), _token(m.group())) for m in _WORD.finditer(mask_markup(raw))]
    hits, cursor = [], 0
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
        hits.append((b, hit))
        cursor = hit + 1
    return words, hits


def bookmark_safe(bounds, text, duration):
    """Word timings re-anchored on remove_bookmarks(text), never decreasing, bracketed by the start and the end of the
    text and the audio, so manim-voiceover can interpolate every bookmark."""
    raw = remove_bookmarks(text)
    words, hits = _match_words(bounds, raw)
    end = max(float(duration), 0.0)
    out, last = [], 0.0
    for b, hit in hits:
        t = min(max(float(b.get("audio_offset", 0)) / AUDIO_OFFSET_RESOLUTION, last), end)
        out.append(_boundary(words[hit][0], t, words[hit][1], b.get("duration_milliseconds")))
        last = t
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
    """Estimated timings: each word starts at its share of the spoken characters."""
    return paused_word_boundaries(text, duration, {})


def paused_word_boundaries(text, speech_s, plan):
    """Estimated timings over speech_s seconds of speech, the words after each pause of plan (pause_plan()) later."""
    raw = mask_markup(remove_bookmarks(text))
    words = list(_WORD.finditer(raw))
    total = max(sum(len(m.group()) + 1 for m in words) - 1, 1)
    out, n, shift = [], 0, 0.0
    for i, m in enumerate(words):
        shift += float(plan.get(i, 0.0))
        out.append(_boundary(m.start(), speech_s * n / total + shift, m.group()))
        n += len(m.group()) + 1
    return bookmark_safe(out, text, speech_s + sum(float(v) for v in plan.values()))


def sentence_spans(raw):
    """(start, end) character spans of the sentences of raw; a decimal such as 0.42 ends none."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?\u2026]+[\"')\]]*(?=\s|$)", raw):
        if raw[start:m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if raw[start:].strip():
        spans.append((start, len(raw)))
    return spans


def pause_after(sentence, base, question=None, ellipsis=None):
    """Silence after a sentence: an ellipsis 2.8 x base, a question 1.8 x base (unless given), else base."""
    end = sentence.rstrip().rstrip("\"')]")
    if end.endswith("...") or end.endswith("\u2026"):
        return float(ellipsis) if ellipsis is not None else 2.8 * base
    if end.endswith("?"):
        return float(question) if question is not None else 1.8 * base
    return base


def _break(seconds):
    return f'<break time="{int(round(float(seconds) * 1000))}ms"/>'


def azure_ssml(text, voice, rate_pct=0, ellipsis_pause_s=0.7, style=None, lang="en-US", pace_break_s=0.0,
               max_break_s=None):
    """SSML of one block: the pauses of pause_plan() as <break>s, the whole block at rate_pct (never below
    RATE_FLOOR_PCT); ValueError when its markup cannot be voiced."""
    from xml.sax.saxutils import escape
    raw = " ".join(remove_bookmarks(text).split())
    problems = markup_problems(raw, max_break_s)
    if problems:
        raise ValueError(f"narration markup: {problems[0]} in {strip_markup(raw)[:70]!r}")
    rate = max(RATE_FLOOR_PCT, float(rate_pct or 0))
    words = [m.group() for m in _WORD.finditer(mask_markup(raw))]
    plan = pause_plan(raw, ellipsis_pause_s, pace_break_s)
    parts = []
    for i, w in enumerate(words):
        core = w[:-3] if w.endswith("...") else w[:-1] if w.endswith("\u2026") else w
        if core:
            parts.append(escape(core))
        if i + 1 in plan and plan[i + 1] > 0:
            parts.append(_break(plan[i + 1]))
    body = " ".join(parts)
    if round(rate):
        body = f'<prosody rate="{rate:+.0f}%">{body}</prosody>'
    if style:
        body = f'<mstts:express-as style="{escape(style)}">{body}</mstts:express-as>'
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" '
            f'xml:lang="{lang}"><voice name="{escape(voice)}">{body}</voice></speak>')


def proxy_settings(env=None):
    """(host, port, user, password) of $HTTPS_PROXY, for the Speech SDK, which does not read it; else None."""
    from urllib.parse import urlparse
    env = os.environ if env is None else env
    url = env.get("HTTPS_PROXY") or env.get("https_proxy")
    if not url:
        return None
    u = urlparse(url if "://" in url else f"http://{url}")
    if not u.hostname:
        return None
    return u.hostname, int(u.port or 80), u.username or "", u.password or ""


def pause_report(bounds, text, duration, plan):
    """[{"after": word, "planned_s", "measured_s"}] of each planned pause, measured between the words' timings."""
    words = [b for b in bounds or [] if b.get("duration_milliseconds") is not None]
    toks, hits = _match_words(words, remove_bookmarks(text))
    at = {hit: b for b, hit in hits}
    out = []
    for n, s in sorted(plan.items()):
        before = next((at[j] for j in range(n - 1, -1, -1) if j in at), None)
        after = next((at[j] for j in range(n, len(toks)) if j in at), None)
        gap = None
        if before is not None and after is not None:
            gap = round(after["audio_offset"] / AUDIO_OFFSET_RESOLUTION
                        - (before["audio_offset"] / AUDIO_OFFSET_RESOLUTION + before["duration_milliseconds"] / 1000.0),
                        3)
        out.append({"after": toks[n - 1][1] if 0 < n <= len(toks) else "", "planned_s": round(float(s), 3),
                    "measured_s": gap})
    return out


def voice_anomaly(bounds, text, duration, ellipsis_pause_s=0.7, max_gap_s=1.3, max_word_s=1.6, max_tail_s=1.5,
                  min_wpm=110, pace_break_s=0.0, verify_min_s=1.0, verify_tol_s=0.35):
    """Why a synthesized take does not sound like speech ("" when it does): a stretched or lost pause, an over-long
    word or tail, or a pace under min_wpm, judged from its word timings and the pauses planned in text."""
    words = [b for b in bounds or [] if b.get("duration_milliseconds") is not None]
    if not words:
        return "no word timings"
    plan = pause_plan(text, ellipsis_pause_s, pace_break_s)
    toks, hits = _match_words(words, remove_bookmarks(text))
    index = {id(b): hit for b, hit in hits}
    upto, nxt = [], len(toks)                            # the text word each timing stands at, or the next one known
    for b in reversed(words):
        nxt = index.get(id(b), nxt)
        upto.append(nxt)
    upto.reverse()
    prev_end, prev_w, prev_text, used = None, -1, "", set()
    for k, b in enumerate(words):
        start = float(b["audio_offset"]) / AUDIO_OFFSET_RESOLUTION
        length = b["duration_milliseconds"] / 1000.0
        spoken = len(re.findall(r"[\d.,%]", str(b.get("text", ""))))   # "0.42" is read as four words
        if length > max_word_s + 0.45 * spoken:
            return f"the word {b.get('text')!r} lasts {length:.1f} s"
        w = index.get(id(b))
        if prev_end is not None:
            gap = start - prev_end
            at = [n for n in plan if prev_w < n <= upto[k] and n not in used]
            used.update(at)                              # a pause is allowed (and checked) once, at its first gap
            here = [plan[n] for n in at]
            if not here and prev_text.rstrip("\"')]").endswith(_ELLIPSIS_END):
                here = [ellipsis_pause_s]                # an ellipsis read from the timing itself
            if gap > max_gap_s + sum(here):
                return f"a {gap:.1f} s gap before {b.get('text')!r}"
            for s in here if w is not None else []:
                if s >= verify_min_s and gap < s - verify_tol_s:
                    return f"the planned {s:g} s pause before {b.get('text')!r} lasts {gap:.1f} s"
        prev_end, prev_text = start + length, str(b.get("text", ""))
        if w is not None:
            prev_w = w
    if duration - prev_end > max_tail_s:
        return f"{duration - prev_end:.1f} s of audio after the last word"
    speech = duration - sum(plan.values())
    wpm = 60.0 * spoken_words(text) / max(speech, 1e-6)
    if min_wpm and spoken_words(text) >= 8 and wpm < min_wpm:
        return f"{wpm:.0f} words per minute"
    return ""


def sentence_word_boundaries(text, spans, duration):
    """Estimated timings inside measured sentences, spans = [(char start, char end, t start, t end)]."""
    raw = mask_markup(remove_bookmarks(text))
    out = []
    for a, b, t0, t1 in spans:
        out += _spread(raw, a, b, t0, t1)
    return bookmark_safe(out, text, duration)


class SilentService(SpeechService):
    """Draft narration: silence as long as the words, the slow factor and the planned pauses would take."""

    def __init__(self, words_per_minute=150, ellipsis_pause_s=0.7, slow_factor=1.0, **kwargs):
        self.words_per_minute = words_per_minute
        self.ellipsis_pause_s = float(ellipsis_pause_s or 0.0)
        self.slow_factor = float(slow_factor or 1.0)
        super().__init__(**kwargs)

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        cache_dir = cache_dir or self.cache_dir
        clean = " ".join(remove_bookmarks(text).split())
        plan = pause_plan(clean, self.ellipsis_pause_s)
        slow = self.slow_factor if slow_block(clean) else 1.0
        data = {"input_text": clean, "service": "silent", "wpm": self.words_per_minute}
        if plan:
            data["pauses"] = sorted([n, s] for n, s in plan.items())
        if slow != 1.0:
            data["slow_factor"] = round(slow, 4)
        cached = self.get_cached_result(data, cache_dir)
        if cached is not None:
            return with_text(cached, text)
        speech = max(1.0, 60.0 * spoken_words(clean) / self.words_per_minute * slow)
        duration = speech + sum(plan.values())
        name = str(path) if path else self.get_audio_basename(data) + ".mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                        "-t", f"{duration:.3f}", "-q:a", "9", str(Path(cache_dir) / name)], check=True)
        return {"input_text": text, "input_data": data, "original_audio": name,
                "word_boundaries": paused_word_boundaries(text, speech, plan)}


def piper_settings(cfg):
    """voice.piper of config/channel.json; $PIPER_VOICE overrides the voice name."""
    p = dict(cfg.get("piper") or {})
    p["voice"] = os.environ.get("PIPER_VOICE") or p.get("voice") or DEFAULT_PIPER_VOICE
    return p


def piper_model(cfg=None, start=None):
    """(<voice>.onnx with its .onnx.json in $PIPER_MODEL, $PIPER_MODEL_DIR or .cache/piper/, else None; the places)."""
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
    """Piper, offline: one WAV per block, synthesized sentence by sentence, slowed down to max_wpm."""

    def __init__(self, model, voice=DEFAULT_PIPER_VOICE, length_scale=None, noise_scale=None, noise_w_scale=None,
                 speaker=None, sentence_pause_s=0.25, max_wpm=None, question_pause_s=None, ellipsis_pause_s=None,
                 slow_factor=1.0, **kwargs):
        self.model = Path(model)
        self.voice_name = voice
        self.synthesis = {"length_scale": length_scale, "noise_scale": noise_scale, "noise_w_scale": noise_w_scale,
                          "speaker_id": speaker}
        self.sentence_pause_s = float(sentence_pause_s)
        self.question_pause_s = None if question_pause_s is None else float(question_pause_s)
        self.ellipsis_pause_s = None if ellipsis_pause_s is None else float(ellipsis_pause_s)
        self.max_wpm = max_wpm
        self.slow_factor = float(slow_factor or 1.0)    # a [slow] block: length_scale stretched by this
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
        raw = mask_markup(remove_bookmarks(text))        # Piper has no break: planned pauses are not rendered
        settings = {k: v for k, v in self.synthesis.items() if v is not None}
        if slow_block(text) and self.slow_factor != 1.0:
            settings["length_scale"] = (settings.get("length_scale") or 1.0) * self.slow_factor
        data = {"input_text": " ".join(remove_bookmarks(text).split()), "service": "piper", "voice": self.voice_name,
                "model_bytes": self.model.stat().st_size, "pause_s": self.sentence_pause_s,
                "pauses_by_ending": [pause_after("?", self.sentence_pause_s, self.question_pause_s),
                                     pause_after("...", self.sentence_pause_s, ellipsis=self.ellipsis_pause_s)],
                **settings}
        if self.max_wpm:
            data["max_wpm"] = self.max_wpm
        cached = self.get_cached_result(data, cache_dir)
        if cached is not None:
            return with_text(cached, text)
        voice = self._load()
        rate = int(voice.config.sample_rate)

        def synth(settings):
            syn = SynthesisConfig(**settings)
            parts, spans, t, pause = [], [], 0.0, self.sentence_pause_s
            for a, b in sentence_spans(raw):
                chunks = []
                for c in voice.synthesize(" ".join(raw[a:b].split()), syn_config=syn):
                    pcm = c.audio_int16_array
                    chunks.append(np.asarray(pcm() if callable(pcm) else pcm, dtype=np.int16).reshape(-1))
                pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
                if parts:
                    gap = np.zeros(int(round(pause * rate)), dtype=np.int16)    # by how the last sentence ended
                    parts.append(gap)
                    t += len(gap) / rate
                spans.append((a, b, t, t + len(pcm) / rate))
                parts.append(pcm)
                t += len(pcm) / rate
                pause = pause_after(raw[a:b], self.sentence_pause_s, self.question_pause_s, self.ellipsis_pause_s)
            return (np.concatenate(parts) if parts else np.zeros(rate // 2, dtype=np.int16)), spans

        audio, spans = synth(settings)
        for _ in range(2):                                   # slow the block down to max_wpm
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
    """Audio made before rendering, video/voice/<block key>.<audio suffix>, with <key>.timings.json when there is one.
    Formats other than WAV and MP3, the two manim-voiceover can measure, are converted to WAV."""

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


def azure_settings(cfg):
    """voice.azure of config/channel.json with defaults, the voice ($AZURE_VOICE overrides) and the rates clamped."""
    a = dict(cfg.get("azure") or {})
    a["voice"] = os.environ.get("AZURE_VOICE") or cfg.get("azure_voice") or DEFAULT_AZURE_VOICE
    a.setdefault("ellipsis_pause_s", 0.7)
    a.setdefault("rate_pct", 0)
    a.setdefault("style", None)
    a.setdefault("retries", 3)
    a.setdefault("min_wpm", 110)
    a.setdefault("slow_rate_pct", -15)
    a.setdefault("pace_min_rate_pct", -15)
    a.setdefault("pace_break_max_s", 0.5)
    a.setdefault("max_break_ms", 4000)
    a["min_rate_pct"] = max(RATE_FLOOR_PCT, float(a.get("min_rate_pct", RATE_FLOOR_PCT)))
    for k in ("rate_pct", "slow_rate_pct", "pace_min_rate_pct"):
        a[k] = max(a["min_rate_pct"], float(a[k] or 0))
    a["slow_rate_pct"] = min(a["slow_rate_pct"], a["rate_pct"])
    return a


class AzureSpeechService(SpeechService):
    """Azure AI Speech: azure_ssml(), the reported word timings, faulty takes made again (voice_anomaly()), and a block
    faster than max_wpm paced by breaks at sentence ends, then a slower rate, then a "rewrite" flag. The key and
    region come from the environment and are never stored."""

    min_rate_pct = RATE_FLOOR_PCT        # class defaults also serve a service built without __init__ (tests)
    slow_rate_pct = -15.0
    pace_min_rate_pct = -15.0
    pace_break_max_s = 0.5
    max_break_s = None

    def __init__(self, voice=DEFAULT_AZURE_VOICE, rate_pct=0, ellipsis_pause_s=0.7, style=None, max_wpm=None,
                 min_rate_pct=RATE_FLOOR_PCT, output_format="Audio48Khz192KBitRateMonoMp3", retries=3, min_wpm=110,
                 slow_rate_pct=-15, pace_min_rate_pct=-15, pace_break_max_s=0.5, max_break_ms=None, **kwargs):
        self.voice_name = voice
        self.min_rate_pct = max(RATE_FLOOR_PCT, float(min_rate_pct))
        self.rate_pct = max(self.min_rate_pct, float(rate_pct or 0))
        self.slow_rate_pct = min(self.rate_pct, max(self.min_rate_pct, float(slow_rate_pct)))
        self.pace_min_rate_pct = max(self.min_rate_pct, float(pace_min_rate_pct))
        self.pace_break_max_s = float(pace_break_max_s or 0.0)
        self.max_break_s = float(max_break_ms) / 1000.0 if max_break_ms else None
        self.ellipsis_pause_s = float(ellipsis_pause_s)
        self.style = style
        self.max_wpm = max_wpm
        self.output_format = output_format
        self.retries = int(retries)
        self.min_wpm = min_wpm
        super().__init__(**kwargs)

    def _synthesize(self, ssml, out_path):
        import azure.cognitiveservices.speech as sdk
        cfg = sdk.SpeechConfig(subscription=os.environ["AZURE_SUBSCRIPTION_KEY"],
                               region=os.environ["AZURE_SERVICE_REGION"])
        proxy = proxy_settings()
        if proxy:
            cfg.set_proxy(*proxy)
        cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat[self.output_format])
        syn = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=sdk.audio.AudioOutputConfig(filename=str(out_path)))
        bounds = []

        def word(evt):
            if evt.boundary_type == sdk.SpeechSynthesisBoundaryType.Word:
                bounds.append({"audio_offset": int(evt.audio_offset), "text": evt.text,
                               "duration_milliseconds": int(evt.duration.total_seconds() * 1000)})
        syn.synthesis_word_boundary.connect(word)
        result = syn.speak_ssml_async(ssml).get()
        if result.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            details = getattr(result, "cancellation_details", None)
            why = getattr(details, "error_details", "") or str(result.reason)
            raise RuntimeError(f"Azure synthesis failed: {why}")
        del syn
        return bounds

    def _take(self, text, rate, out, pace_break_s=0.0):
        """One block at `rate`, taken again while faulty: (ssml, timings, duration, takes, the fault left or "")."""
        raw = remove_bookmarks(text)
        ssml = azure_ssml(text, self.voice_name, rate, self.ellipsis_pause_s, self.style, pace_break_s=pace_break_s,
                          max_break_s=self.max_break_s)
        best = None
        for n in range(1, self.retries + 2):
            tmp = out.with_name(f"{out.stem}.take{n}{out.suffix}")
            bounds = self._synthesize(ssml, tmp)
            duration = audio_duration(tmp)
            fault = voice_anomaly(bounds, raw, duration, self.ellipsis_pause_s, min_wpm=self.min_wpm,
                                  pace_break_s=pace_break_s)
            if fault:
                print(f"voice: take {n} of block {block_key(text)} rejected ({fault})", file=sys.stderr)
            if best is None or (best[3] and not fault) or (fault and best[3] and duration < best[2]):
                if best is not None:
                    best[0].unlink(missing_ok=True)
                best = (tmp, bounds, duration, fault)
            else:
                tmp.unlink(missing_ok=True)
            if not fault:
                break
        best[0].replace(out)
        return ssml, best[1], best[2], n, best[3]

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        cache_dir = cache_dir or self.cache_dir
        raw = remove_bookmarks(text)
        slow = slow_block(raw)
        data = {"input_text": " ".join(raw.split()), "service": "azure", "voice": self.voice_name,
                "rate_pct": self.rate_pct, "ellipsis_pause_s": self.ellipsis_pause_s, "style": self.style,
                "format": self.output_format,
                "pace": [self.pace_break_max_s, self.pace_min_rate_pct, self.min_rate_pct]}
        if slow:
            data["slow_rate_pct"] = self.slow_rate_pct
        if self.max_wpm:
            data["max_wpm"] = self.max_wpm
        cached = self.get_cached_result(data, cache_dir)
        if cached is not None:
            return with_text(cached, text)
        name = str(path) if path else self.get_audio_basename(data) + ".mp3"
        out = Path(cache_dir) / name
        planned = pause_plan(raw, self.ellipsis_pause_s)              # planned pauses do not count in the pace
        planned_s = sum(planned.values())
        words = spoken_words(raw)
        ends = len(pause_plan(raw, self.ellipsis_pause_s, 1.0)) - len(planned)   # sentence ends free for a break
        rate, brk, pace = self.slow_rate_pct if slow else self.rate_pct, 0.0, "ok"   # a slow block starts slow
        ssml, bounds, duration, takes, fault = self._take(text, rate, out)

        def wpm():
            return 60.0 * words / max(duration - planned_s, 1e-6)
        if self.max_wpm and wpm() > self.max_wpm:                     # the pace cap
            if ends and self.pace_break_max_s > 0:                    # 1. short breaks at the sentence ends
                need = 60.0 * words / self.max_wpm - (duration - planned_s)
                brk = min(self.pace_break_max_s, max(0.1, math.ceil(100.0 * need / ends) / 100.0))
                ssml, bounds, duration, more, fault = self._take(text, rate, out, brk)
                takes, pace = takes + more, "breaks"
            for _ in range(2):                                        # 2. a slower rate, never below the limit
                if wpm() <= self.max_wpm or rate <= self.pace_min_rate_pct:
                    break
                factor = wpm() / self.max_wpm * 1.02                  # how much longer the speech must last
                rate = max(self.pace_min_rate_pct, ((1.0 + rate / 100.0) / factor - 1.0) * 100.0)
                ssml, bounds, duration, more, fault = self._take(text, rate, out, brk)
                takes, pace = takes + more, "slowed"
            if wpm() > self.max_wpm:                                  # 3. the words must change
                pace = "rewrite"
                print(f"voice: block {block_key(text)} still at {wpm():.0f} words per minute with "
                      f"{brk:g} s breaks and a rate of {rate:.0f} %: shorten or split it (pace cap, rule P20)",
                      file=sys.stderr)
        if fault:
            print(f"voice: block {block_key(text)} kept with a fault after {takes} takes ({fault})", file=sys.stderr)
        made = dict(data, applied_rate_pct=round(rate, 1), takes=takes, fault=fault, pace=pace, pace_break_s=brk,
                    speech_wpm=round(wpm(), 1), slowest_rate_pct=round(rate, 1), slow=slow,
                    pauses=pause_report(bounds, raw, duration, planned))
        return {"input_text": text, "input_data": made, "ssml": ssml, "original_audio": name,
                "word_boundaries": bookmark_safe(bounds, text, duration)}


def _need(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise RuntimeError(f"voice service needs {', '.join(missing)} in the environment (a CI secret, never a file "
                           "in the repository); piper needs no key")


def _has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):            # a missing parent package raises instead of returning None
        return False


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
        if missing:
            return False, f"needs {', '.join(missing)} in the environment"
        if name == "azure" and not _has_module("azure.cognitiveservices.speech"):
            return False, ("the azure-cognitiveservices-speech package is not installed: "
                           "pip install -r requirements-voice.txt")
        return True, ""
    return False, f"unknown voice service {name!r} ({', '.join(SERVICES)})"


def resolve(name=None, draft=False, start=None):
    """(service, note): name, else $VOICE_SERVICE, else voice.service; silent for drafts; ValueError when unknown."""
    cfg = channel_config(start).get("voice", {})
    name = (name or os.environ.get("VOICE_SERVICE") or cfg.get("service") or "piper").strip().lower()
    if name not in SERVICES:
        raise ValueError(f"unknown voice service {name!r} ({', '.join(SERVICES)})")
    if draft:
        return "silent", ("" if name == "silent" else "drafts are silent")
    return name, ""


def speech_service(scene_dir=None, name=None, cache_dir=None):
    """The service `name`, else $VOICE_SERVICE, else silent, set up from config/channel.json."""
    cfg = channel_config(scene_dir).get("voice", {})
    name = (name or os.environ.get("VOICE_SERVICE") or "silent").strip().lower()
    kw = {"cache_dir": str(cache_dir)} if cache_dir else {}
    if name == "silent":
        return SilentService(words_per_minute=cfg.get("draft_words_per_minute", 150),
                             ellipsis_pause_s=azure_settings(cfg)["ellipsis_pause_s"], slow_factor=slow_factor(cfg),
                             **kw)
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
                            question_pause_s=p.get("question_pause_s"), ellipsis_pause_s=p.get("ellipsis_pause_s"),
                            max_wpm=pacing_limit(scene_dir), slow_factor=slow_factor(cfg), **kw)
    if name == "azure":
        _need(*KEYS["azure"])
        ok, why = available("azure", scene_dir)
        if not ok:
            raise RuntimeError(f"voice service azure: {why}; no other voice is used in its place")
        a = azure_settings(cfg)
        return AzureSpeechService(voice=a["voice"], rate_pct=a["rate_pct"], ellipsis_pause_s=a["ellipsis_pause_s"],
                                  style=a["style"], min_rate_pct=a["min_rate_pct"], retries=a["retries"],
                                  min_wpm=a["min_wpm"], max_wpm=a.get("max_wpm") or pacing_limit(scene_dir),
                                  slow_rate_pct=a["slow_rate_pct"], pace_min_rate_pct=a["pace_min_rate_pct"],
                                  pace_break_max_s=a["pace_break_max_s"], max_break_ms=a["max_break_ms"], **kw)
    raise ValueError(f"unknown voice service {name!r} ({', '.join(SERVICES)})")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
