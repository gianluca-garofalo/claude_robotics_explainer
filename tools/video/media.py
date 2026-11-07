"""Media helpers of the video tools: ffprobe, EBU R128 loudness (ffmpeg ebur128), WAV files and SRT captions."""
from __future__ import annotations

import json
import re
import subprocess
import wave
from datetime import timedelta
from pathlib import Path

import numpy as np
import srt

MOMENTARY = re.compile(r"\bt:\s*([\d.]+)\s+TARGET:\S+\s+LUFS\s+M:\s*(\S+)")


def run(cmd: list[str]) -> str:
    """stdout of cmd; RuntimeError with the end of its stderr when it fails."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])} ... failed:\n{p.stderr[-2000:]}")
    return p.stdout


def probe(path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                           str(path)]))


def _number(text: str, default: float) -> float:
    try:
        x = float(text)
    except ValueError:
        return default
    return x if np.isfinite(x) else default


def ebur128(path) -> tuple[dict, np.ndarray]:
    """The summary of a file's first audio stream (integrated LUFS, LRA in LU, true peak in dBTP; -70 is silence)
    and its momentary loudness (400 ms windows) every 100 ms, indexed by time (-120 is silence)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                          "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""

    def grab(label, default):
        m = re.search(label + r":\s*(\S+)", summary)
        return _number(m.group(1), default) if m else default
    pairs = MOMENTARY.findall(err)
    momentary = np.full(int(round(float(pairs[-1][0]) * 10)) if pairs else 0, -120.0)
    for t, value in pairs:
        k = int(round(float(t) * 10)) - 1
        if 0 <= k < len(momentary):
            momentary[k] = _number(value, -120.0)
    return ({"integrated_lufs": grab(r"\bI", -70.0), "lra_lu": grab("LRA", 0.0), "true_peak_dbtp": grab("Peak", -70.0)},
            momentary)


def loudness(path) -> dict:
    return ebur128(path)[0]


def read_wav(path) -> tuple[np.ndarray, int]:
    """(channels, n) floats in [-1, 1] and the sample rate of a 16- or 32-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dt = {2: np.int16, 4: np.int32}[width]
    return (np.frombuffer(raw, dtype=dt).astype(np.float64) / float(np.iinfo(dt).max)).reshape(-1, ch).T, sr


def write_wav(path, x: np.ndarray, sr: int = 48000, bits: int = 16) -> None:
    """Write (channels, n) or (n,) floats in [-1, 1] as 16- or 32-bit PCM."""
    x = np.atleast_2d(x)
    dt = {16: np.int16, 32: np.int32}[bits]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(bits // 8)
        w.setframerate(sr)
        w.writeframes((np.clip(x.T, -1, 1) * np.iinfo(dt).max).astype(dt).tobytes())


def read_srt(path) -> list[tuple[float, float, str]]:
    """(start s, end s, text on one line) of each caption of an SRT file; [] without the file."""
    path = Path(path)
    if not path.exists():
        return []
    return [(c.start.total_seconds(), c.end.total_seconds(), " ".join(x for x in c.content.splitlines() if x.strip())
             .strip()) for c in srt.parse(path.read_text(encoding="utf-8"))]


def write_srt(path, cues) -> None:
    """Write (start s, end s, text) captions, numbered from 1 in the order given, times rounded to the millisecond."""
    def ms(s):
        return timedelta(milliseconds=round(s * 1000))
    subs = [srt.Subtitle(i, ms(a), ms(b), text) for i, (a, b, text) in enumerate(cues, 1)]
    Path(path).write_text(srt.compose(subs, reindex=False), encoding="utf-8")
