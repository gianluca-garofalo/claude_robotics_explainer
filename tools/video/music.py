#!/usr/bin/env python3
"""Original music for a video: a seeded, reproducible ambient bed with the channel's motif (numpy only, no samples).

Usage:
  python3 tools/video/music.py runs/<run> [--seed N] [--preset calm-pad] [--duration S]

Route A of the music rule ("original only"): every note is synthesised here from sine and triangle oscillators, so
the music has no third-party rights and no Content ID risk, and the same inputs give the same file bit for bit.
tools/video/assemble.py calls build() after it has joined the scenes and written the narration stem; run alone, this
reads video/final/assembly.json and video/final/narration.wav of an assembled run.

What it makes (preset "calm-pad", the only one so far; the owner approves a preset by ear once):
  bed      a slow chord pad (detuned sine and triangle voices, low-passed, with a synthetic reverb) that changes chord
           at every chapter start (chapters as assemble.py merges them) and every chord_s seconds inside long chapters
  bells    sparse soft FM bells on the chord tones, an octave or two up
  motif    the channel's four-note motif (scale degrees 1-3-5-2) as bells over a short swell: the "sting", on the
           title beat after the hook and at the start of the outro (config/channel.json music.stings)
  modes    per scene (plan.json scenes "music", default config/channel.json music.modes_by_role): "bed", "low" or
           "off"; v5: a scene may change mode at a narration block (plan.json "music_from", assemble.py
           music_changes). Music under explanation hurts recall and transfer (the coherence principle, Moreno and Mayer 2000),
           so the default is the bed in the hook, the title beat and the outro, and "low" (at least 20 LU under the
           voice) in the body; a scene can turn it off. Every cut between scenes gets a short swell (a transition).
  shape    a swell under the cold open (the picture moves before the first word), a gentle swell in every pause of
           the narration of at least pause_swell_s inside a scene whose mode is not "off" (v4: a pause of at least
           off_beat_swell_s inside an "off" scene is a planned beat, not a hole: the bed rises to the "low" level
           in it, so a beat is never digital silence; 0 turns this off), a lift under the outro and
           a fade over its last fade_out_s
The seed (default: from the run slug) fixes the voicings, the bell pattern and the phases. The level relative to the
voice and the ducking are set at the mix (assemble.py, duck_gain() here), not in this file.

Writes video/final/music.wav (48 kHz stereo, 16-bit) and video/final/music.json, the provenance stamp tools/gate.py
checks before any music may be in the final mix: generator, tool version and sha256, preset, seed, the events, and
the sha256 of music.wav.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import CONFIG, load_json, rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402

GENERATOR = "tools/video/music.py"
VERSION = "1.0"
SR = 48000
A4 = 440.0
PRESETS = {
    "calm-pad": {
        # Dmaj9 - Bm9 - Gmaj7#11 - Asus2 (MIDI notes): calm, unresolved
        "chords": [[50, 57, 61, 64, 66], [47, 54, 57, 61, 62], [43, 50, 54, 59, 61], [45, 52, 59, 61, 64]],
        "motif": [74, 78, 81, 76],          # D5 F#5 A5 E5: scale degrees 1-3-5-2, the channel's sonic identity
        "chord_s": 12.0,                    # a chord change inside long chapters
        "lowpass_hz": 1500.0,               # keeps the pad out of the 1-4 kHz band where speech is understood
        "bell_every_s": 5.0,
        "bell_level": 0.22,
        "reverb_rt60": 3.0,
        "reverb_wet": 0.35,
    },
}
DEFAULTS = {"enabled": True, "source": "generated", "preset": "calm-pad", "seed": None, "bed_in_gaps_lu": -9.0,
            "bed_under_voice_lu": -18.0, "attack_ms": 60, "release_ms": 900, "lookahead_ms": 150,
            "stings": ["hook_title", "outro"], "sting_lu": -4.0, "intro_swell_s": 2.5, "pause_swell_s": 1.2,
            "swell_db": 3.0, "outro_lift_db": 3.0, "fade_out_s": 3.0, "true_peak_dbtp": -1.0,
            "low_under_voice_lu": -24.0, "transition_swell_s": 1.2, "mode_ramp_s": 1.5,
            "modes_by_role": {"hook": "bed", "context": "bed", "outro": "bed", "recap": "low", "body": "low"},
            "sting_s": 3.2, "sting_margin_s": 0.2, "sting_duck_db": 14.0, "music_under_voice_max_lu": -12.0,
            "off_beat_swell_s": 1.8}
MODES = ("bed", "low", "off")


def scene_mode(scene: dict, cfg: dict | None = None) -> str:
    """A scene's music mode: plan.json "music", else the default for its role."""
    cfg = dict(DEFAULTS, **(cfg or {}))
    m = scene.get("music") or (cfg.get("modes_by_role") or {}).get(scene.get("role") or "body", "low")
    return m if m in MODES else "low"


def mode_offset_db(mode: str, cfg: dict) -> float:
    """The bed's level in a mode relative to "bed" (dB): low sits low_under_voice_lu instead of bed_under_voice_lu."""
    if mode == "bed":
        return 0.0
    if mode == "low":
        return float(cfg["low_under_voice_lu"]) - float(cfg["bed_under_voice_lu"])
    return -120.0


def settings() -> dict:
    """config/channel.json "music" over the defaults above."""
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG / "channel.json").get("music", {}) or {})
    return cfg


def seed_for(slug: str) -> int:
    """A stable seed from the run's slug: the same episode always gets the same music."""
    return int(hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8], 16)


def hz(midi: float) -> float:
    return A4 * 2 ** ((midi - 69) / 12)


# --------------------------------------------------------------------------- signal helpers (numpy only)
def fft_convolve(x: np.ndarray, h: np.ndarray, block: int = 1 << 18) -> np.ndarray:
    """Overlap-add convolution of each row of x (channels, n) with h (taps,) or (channels, taps); output length n."""
    x = np.atleast_2d(x)
    h = np.atleast_2d(h)
    if h.shape[0] == 1 and x.shape[0] > 1:
        h = np.repeat(h, x.shape[0], axis=0)
    n, m = x.shape[1], h.shape[1]
    size = 1 << int(np.ceil(np.log2(block + m - 1)))
    hf = np.fft.rfft(h, size, axis=1)
    out = np.zeros((x.shape[0], n + m - 1))
    for a in range(0, n, block):
        seg = x[:, a:a + block]
        y = np.fft.irfft(np.fft.rfft(seg, size, axis=1) * hf, size, axis=1)[:, :seg.shape[1] + m - 1]
        out[:, a:a + y.shape[1]] += y
    return out[:, :n]


def lowpass_fir(cut_hz: float, taps: int = 511) -> np.ndarray:
    k = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cut_hz / SR * k) * np.blackman(taps)
    return h / h.sum()


def osc(f: float, t: np.ndarray, detune_cents: float, phase: float) -> np.ndarray:
    f = f * 2 ** (detune_cents / 1200)
    ph = 2 * np.pi * f * t + phase
    tri = 2 / np.pi * np.arcsin(np.sin(ph))
    return 0.7 * np.sin(ph) + 0.3 * tri


def bell(f: float, dur: float, index: float = 2.0) -> np.ndarray:
    """A soft FM bell, mono."""
    tt = np.arange(int(dur * SR)) / SR
    idx = index * np.exp(-tt * 3.0)
    y = np.sin(2 * np.pi * f * tt + idx * np.sin(2 * np.pi * f * 3.5 * tt)) * np.exp(-tt * 1.6)
    return y * np.clip(tt / 0.01, 0, 1)


def reverb(x: np.ndarray, rng: np.random.Generator, rt60: float, wet: float) -> np.ndarray:
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((2, n)) * np.exp(-6.91 * t / rt60)
    ir = fft_convolve(ir, lowpass_fir(3500.0, 255))
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    return (1 - wet) * x + wet * fft_convolve(x, ir)


def bump(n: int, a: float, b: float, db: float, ramp: float = 0.8) -> np.ndarray:
    """A gain curve (dB) that rises by `db` between a and b seconds with raised-cosine ramps of `ramp` seconds."""
    t = np.arange(n) / SR
    up = np.clip((t - a) / ramp, 0, 1)
    down = np.clip((b - t) / ramp, 0, 1)
    return db * (0.5 - 0.5 * np.cos(np.pi * np.minimum(up, down)))


# --------------------------------------------------------------------------- events from the assembled video
def pauses(voice: np.ndarray, sr: int, min_s: float, floor_db: float = -45.0, hop_s: float = 0.02) -> list[list[float]]:
    """Spans of at least min_s seconds in which the narration (mono) stays below floor_db dBFS RMS."""
    hop = int(sr * hop_s)
    nfr = len(voice) // hop
    if nfr == 0:
        return []
    rms = np.sqrt(np.mean(voice[:nfr * hop].reshape(nfr, hop).astype(np.float64) ** 2, axis=1) + 1e-20)
    quiet = 20 * np.log10(rms) < floor_db
    spans, start = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * hop_s >= min_s:
                spans.append([round(start * hop_s, 2), round(i * hop_s, 2)])
            start = None
    return spans


def sting_slot(t0: float, t1: float, gaps: list[list[float]], cfg: dict) -> float:
    """Where a sting meant for the segment [t0, t1) starts, so that it sounds in a pause of the narration and ends
    sting_margin_s before the next word (a sting over the first words masks them: the v2 final-cut review, FC-1):
    at t0 when the pause there lasts long enough; else ending just before the speech that follows t0, when that
    pause is long enough; else in the first long enough pause inside the segment; else in its longest pause of at
    least half the sting; else None: no sting (it would sit on the words). Stings are also ducked under the voice
    (sting_duck_db) as a safety net."""
    need = float(cfg.get("sting_s", 3.2)) + float(cfg.get("sting_margin_s", 0.2))
    for a, b in gaps:
        if a - 0.05 <= t0 < b:
            if b - t0 >= need:
                return round(t0, 3)
            if b - a >= need:
                return round(b - need, 3)
    for a, b in gaps:
        if t0 <= a < t1 and b - a >= need:
            return round(a, 3)
    inside = [(min(b, t1) - a, a) for a, b in gaps if t0 <= a < t1 and min(b, t1) - a >= need / 2]
    if inside:                                   # the longest pause in the segment, even if the tail rings on
        return round(max(inside)[1], 3)
    return None


def under_voice(voice: np.ndarray, music: np.ndarray, sr: int, win_s: float = 0.4, hop_s: float = 0.1,
                floor_db: float = -45.0) -> float | None:
    """How loud the music gets while the narration speaks, relative to the narration (dB, RMS): the maximum, over
    windows of win_s in which the voice speaks (RMS within 6 dB of its median speaking level: whole words, not the
    soft onsets at the edge of a pause), of the music's RMS
    minus the voice's median speaking RMS. None when the voice never speaks. Both mono, same rate."""
    win, hop = int(win_s * sr), int(hop_s * sr)
    n = min(len(voice), len(music))
    if n < win:
        return None
    idx = np.arange(0, n - win, hop)
    cs_v = np.concatenate([[0.0], np.cumsum(voice[:n].astype(np.float64) ** 2)])
    cs_m = np.concatenate([[0.0], np.cumsum(music[:n].astype(np.float64) ** 2)])
    v = 10 * np.log10((cs_v[idx + win] - cs_v[idx]) / win + 1e-20)
    m = 10 * np.log10((cs_m[idx + win] - cs_m[idx]) / win + 1e-20)
    speaking = v > floor_db
    if not speaking.any():
        return None
    level = float(np.median(v[speaking]))
    loud = v > level - 6.0
    return round(float((m[loud] - level).max()), 2)


def momentary(path: Path) -> np.ndarray:
    """EBU R128 momentary loudness (LUFS, 400 ms windows every 100 ms, K-weighted) of a file, from ffmpeg ebur128:
    one value per 100 ms, indexed by time (silence and unparsable values read as -120)."""
    import re
    import subprocess
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    pairs = re.findall(r"\bt:\s*([\d.]+)\s+TARGET:\S+\s+LUFS\s+M:\s*(\S+)", p.stderr)
    if not pairs:
        return np.zeros(0)
    out = np.full(int(round(float(pairs[-1][0]) * 10)), -120.0)
    for t, m in pairs:
        k = int(round(float(t) * 10)) - 1
        try:
            val = float(m)
        except ValueError:
            val = -120.0
        if 0 <= k < len(out):
            out[k] = val if np.isfinite(val) else -120.0
    return out


def under_voice_files(voice_path: Path, music_path: Path, speaking_lu: float = 6.0) -> float | None:
    """How loud the music gets while the narration speaks, in LU relative to the narration (both K-weighted, EBU
    R128): the maximum, over the 400 ms windows in which the voice's momentary loudness is within speaking_lu of its
    integrated loudness (and so are the two windows on each side: whole words, not the edge of a pause), of the
    music's momentary loudness minus the voice's integrated loudness. None without
    speech or without ffmpeg."""
    import shutil
    if not shutil.which("ffmpeg"):
        return None
    v, m = momentary(voice_path), momentary(music_path)
    n = min(len(v), len(m))
    ref = loudness(voice_path)["integrated_lufs"]
    if n == 0 or ref <= -60:
        return None
    v, m = v[:n], m[:n]
    speaking = v > ref - speaking_lu
    core = speaking.copy()                       # whole words: drop the windows that straddle a pause's edge
    for k in (1, 2):
        core[k:] &= speaking[:-k]
        core[:-k] &= speaking[k:]
    speaking = core
    if not speaking.any():
        return None
    return round(float((m[speaking] - ref).max()), 2)


def plan_events(segments: list[dict], chapters: list[dict], duration: float, gaps: list[list[float]],
                cfg: dict) -> dict:
    """When the chords change, where the stings and swells go: from assemble.py's segments and merged chapters."""
    starts = sorted({round(float(c["start"]), 3) for c in chapters} | {0.0})
    stings = []
    roles = [s.get("role") for s in segments]
    if "hook_title" in cfg.get("stings", []) and "hook" in roles:
        i = roles.index("hook")
        if i + 1 < len(segments):                     # the beat right after the hook: the title / series context
            seg = segments[i + 1]
            t0 = float(seg["start"])
            t = sting_slot(t0, t0 + float(seg["duration"]), gaps, cfg)
            if t is not None:
                stings.append({"t": t, "kind": "hook_title"})
    outro_seg = next((s for s in segments if s.get("role") == "outro"), None)
    outro = None if outro_seg is None else float(outro_seg["start"])
    if "outro" in cfg.get("stings", []) and outro is not None:
        t = sting_slot(outro, outro + float(outro_seg["duration"]), gaps, cfg)
        if t is not None:
            stings.append({"t": t, "kind": "outro"})
    first_speech = gaps[0][1] if gaps and gaps[0][0] <= 0.05 else 0.0
    intro = first_speech if first_speech > 0.5 else float(cfg.get("intro_swell_s", 2.5))   # until the first word
    modes = []
    for s in segments:                             # v5: a scene may change mode at a narration block (music_changes)
        a, b = round(float(s["start"]), 3), round(float(s["start"]) + float(s["duration"]), 3)
        m = s.get("music") or scene_mode(s, cfg)
        for t, m2 in sorted(s.get("music_changes") or []):
            if a < float(t) < b and m2 in MODES:
                modes.append([a, round(float(t), 3), m])
                a, m = round(float(t), 3), m2
        modes.append([a, b, m])

    def mode_at(t):
        return next((m for a, b, m in modes if a <= t < b), "low")
    swells = [g for g in gaps if g[0] > 0.05 and g[1] < duration - 0.05 and mode_at((g[0] + g[1]) / 2) != "off"]
    min_beat = float(cfg.get("off_beat_swell_s") or 0.0)
    off_beats = [g for g in gaps if min_beat > 0 and g[1] - g[0] >= min_beat and g[0] > 0.05
                 and g[1] < duration - 0.05 and mode_at((g[0] + g[1]) / 2) == "off"]
    cuts = [round(float(s["start"]), 3) for s in segments[1:]]
    return {"chapters": starts, "stings": stings, "intro_s": round(intro, 2), "swells": swells, "modes": modes,
            "off_beats": off_beats, "cuts": cuts, "outro": None if outro is None else round(outro, 3),
            "duration": round(duration, 3)}


# --------------------------------------------------------------------------- synthesis
def chord_times(ev: dict, chord_s: float) -> list[float]:
    """A chord change at every chapter start, and every chord_s seconds inside a long chapter."""
    out, bounds = [], list(ev["chapters"]) + [ev["duration"]]
    for a, b in zip(bounds[:-1], bounds[1:]):
        k = max(1, int(round((b - a) / chord_s)))
        out += [a + j * (b - a) / k for j in range(k)]
    return out


def pad_layer(n: int, ev: dict, p: dict, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros((2, n))
    times = chord_times(ev, p["chord_s"])
    first = int(rng.integers(len(p["chords"])))
    attack, release = 2.0, 3.5
    for k, (a, b) in enumerate(zip(times, times[1:] + [n / SR])):
        notes = list(p["chords"][(first + k) % len(p["chords"])])
        if rng.random() < 0.5:                        # an inversion now and then: the top note an octave down
            notes[-1] -= 12
        i0, i1 = int(a * SR), min(n, int((b + release) * SR))
        tt = np.arange(i1 - i0) / SR
        hold = b - a
        env = np.clip(tt / attack, 0, 1) * np.clip((hold + release - tt) / release, 0, 1)
        env = env ** 1.5
        for m in notes:
            f = hz(m)
            for ch, det in ((0, -4.0), (1, 4.0)):
                v = osc(f, tt, det, rng.uniform(0, 2 * np.pi)) + osc(f, tt, -det / 2, rng.uniform(0, 2 * np.pi))
                lfo = 0.85 + 0.15 * np.sin(2 * np.pi * rng.uniform(0.05, 0.12) * tt + rng.uniform(0, 2 * np.pi))
                out[ch, i0:i1] += v * env * lfo / len(notes)
    return fft_convolve(out, lowpass_fir(p["lowpass_hz"]))


def bells_layer(n: int, ev: dict, p: dict, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros((2, n))
    times = chord_times(ev, p["chord_s"])
    t0 = 2.0
    while t0 < n / SR - 4:
        k = max(0, int(np.searchsorted(times, t0, side="right")) - 1)
        chord = p["chords"][k % len(p["chords"])]
        f = hz(int(rng.choice(chord)) + int(rng.choice([12, 24])))
        y = bell(f, 3.5)
        a = int(t0 * SR)
        b = min(n, a + len(y))
        pan = rng.uniform(0.3, 0.7)
        out[0, a:b] += y[:b - a] * (1 - pan) * p["bell_level"]
        out[1, a:b] += y[:b - a] * pan * p["bell_level"]
        t0 += p["bell_every_s"] * float(rng.choice([1.0, 1.0, 1.5, 2.0]))
    return out


def sting(p: dict, seconds: float = 3.2) -> np.ndarray:
    """The motif as bells over a soft swell of the first chord: deterministic (the same in every episode)."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros((2, n))
    swell = np.clip(t / 0.6, 0, 1) ** 2 * np.exp(-np.clip(t - 0.6, 0, None) * 1.1)
    for i, m in enumerate(p["chords"][0]):
        out[i % 2] += np.sin(2 * np.pi * hz(m + 12) * t) * swell / 4
    for i, m in enumerate(p["motif"]):
        y = bell(hz(m), seconds - 0.25 * i, index=1.5) * 0.6
        a = int((0.15 + 0.25 * i) * SR)
        b = min(n, a + len(y))
        out[0, a:b] += y[:b - a] * (0.6 - 0.05 * i)
        out[1, a:b] += y[:b - a] * (0.4 + 0.05 * i)
    return out


def mode_gain(n: int, ev: dict, cfg: dict) -> np.ndarray:
    """Linear gain of the bed from the scene modes (cosine ramps of mode_ramp_s at each change), raised to the bed
    level for transition_swell_s around every cut."""
    t = np.arange(n) / SR
    lin = np.zeros(n)
    for a, b, m in ev.get("modes") or [[0.0, ev["duration"], "bed"]]:
        i0, i1 = int(a * SR), min(n, int(b * SR))
        lin[i0:i1] = 10 ** (mode_offset_db(m, cfg) / 20)
    low = 10 ** (mode_offset_db("low", cfg) / 20)
    for a, b in ev.get("off_beats", []):                  # a planned beat in an "off" scene: the "low" level
        i0, i1 = int(a * SR), min(n, int(b * SR))
        lin[i0:i1] = np.maximum(lin[i0:i1], low)
    ramp = int(float(cfg["mode_ramp_s"]) * SR)
    if ramp > 1:                                          # smooth the steps: a moving average of mode_ramp_s
        c = np.concatenate([[0.0], np.cumsum(np.pad(lin, (ramp // 2, ramp - ramp // 2), mode="edge"))])
        lin = (c[ramp:ramp + n] - c[:n]) / ramp
    half = float(cfg["transition_swell_s"])
    for cut in ev.get("cuts", []):
        x = np.clip(1 - np.abs(t - cut) / max(half, 1e-3), 0, 1)
        lin = np.maximum(lin, 0.5 - 0.5 * np.cos(np.pi * x))
    return lin


def synthesize(ev: dict, seed: int, preset: str = "calm-pad", cfg: dict | None = None):
    """(bed, stings, raw), each (2, n) float in [-1, 1] at SR: the bed with its modes, swells and fades; the stings
    apart (mixed at their own level and ducked under the narration by sting_duck_db); and the bed before modes and swells (its loudness is the "bed"
    level the mix sets)."""
    cfg = dict(DEFAULTS, **(cfg or {}))
    p = PRESETS[preset]
    rng = np.random.default_rng(seed)
    n = int(round(ev["duration"] * SR))
    bed = pad_layer(n, ev, p, rng) + bells_layer(n, ev, p, rng)
    bed = reverb(bed, rng, p["reverb_rt60"], p["reverb_wet"])
    bed /= max(1e-9, np.abs(bed).max())
    raw = bed.copy()
    bed = bed * mode_gain(n, ev, cfg)
    gain_db = bump(n, -1.0, ev["intro_s"], cfg["swell_db"], ramp=1.0)
    for a, b in ev["swells"]:
        gain_db = np.maximum(gain_db, bump(n, a, b, cfg["swell_db"], ramp=min(0.8, (b - a) / 2)))
    if ev.get("outro") is not None:
        gain_db = np.maximum(gain_db, bump(n, ev["outro"], ev["duration"] + 5, cfg["outro_lift_db"], ramp=2.0))
    t = np.arange(n) / SR
    fade = np.clip((ev["duration"] - t) / max(cfg["fade_out_s"], 1e-3), 0, 1) * np.clip(t / 0.3, 0, 1)
    bed *= 10 ** (gain_db / 20) * fade
    st = np.zeros((2, n))
    one = sting(p)
    for s in ev["stings"]:
        a = int(s["t"] * SR)
        b = min(n, a + one.shape[1])
        if b > a:
            st[:, a:b] += one[:, :b - a]
    st /= max(1e-9, np.abs(st).max()) if np.abs(st).max() > 0 else 1.0
    return bed, st, raw


# --------------------------------------------------------------------------- ducking (the mix side)
def duck_gain(voice: np.ndarray, sr: int, duck_db: float, attack_ms: float, release_ms: float, lookahead_ms: float,
              threshold_db: float = -40.0, hop_s: float = 0.005) -> np.ndarray:
    """A sidechain gain (linear, one value per sample) that lowers the music by duck_db while the narration speaks.
    The key is the narration advanced by lookahead_ms, so the music dips just before each phrase; the gain falls
    with the attack time and recovers with the release time (one-pole smoothing on a 5 ms control grid)."""
    hop = max(1, int(sr * hop_s))
    nfr = int(np.ceil(len(voice) / hop))
    pad = np.zeros(nfr * hop)
    pad[:len(voice)] = voice
    rms = np.sqrt(np.mean(pad.reshape(nfr, hop) ** 2, axis=1) + 1e-20)
    active = (20 * np.log10(rms) > threshold_db).astype(float)
    shift = int(round(lookahead_ms / 1000 / hop_s))
    if shift:
        active = np.concatenate([active[shift:], np.zeros(shift)])
    # hold each detected frame across the look-ahead window, so the dip starts lookahead_ms before the word
    target = -duck_db * active
    a_att = np.exp(-hop_s / max(attack_ms / 1000, 1e-4))
    a_rel = np.exp(-hop_s / max(release_ms / 1000, 1e-4))
    g = np.empty(nfr)
    cur = 0.0
    for i, tv in enumerate(target):
        a = a_att if tv < cur else a_rel
        cur = a * cur + (1 - a) * tv
        g[i] = cur
    lin = 10 ** (np.repeat(g, hop)[:len(voice)] / 20)
    return lin


# --------------------------------------------------------------------------- measuring
def loudness(path: Path, extra: list[str] | None = None) -> dict:
    """EBU R128 of a file's first audio stream (ffmpeg ebur128 with true peak): integrated (LUFS), LRA (LU), true
    peak (dBTP). -70 stands for silence."""
    import re
    import subprocess
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *(extra or []), "-i", str(path), "-map", "0:a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = p.stderr[p.stderr.rfind("Summary:"):] if "Summary:" in p.stderr else ""

    def grab(pat, default):
        m = re.search(pat, tail, re.S)
        return float(m.group(1)) if m and m.group(1) not in ("-inf", "inf", "nan") else default
    return {"integrated_lufs": grab(r"Integrated loudness:.*?I:\s*(-?[\d.]+|-inf)", -70.0),
            "lra_lu": grab(r"Loudness range:.*?LRA:\s*(-?[\d.]+|-inf)", 0.0),
            "true_peak_dbtp": grab(r"True peak:.*?Peak:\s*(-?[\d.]+|-inf)", -70.0)}


# --------------------------------------------------------------------------- files
def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """(channels, n) float in [-1, 1] and the sample rate of a 16- or 32-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    dt = {2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dt).astype(np.float64) / float(np.iinfo(dt).max)
    return x.reshape(-1, ch).T, sr


def write_wav(path: Path, x: np.ndarray, sr: int = SR, bits: int = 16) -> None:
    x = np.atleast_2d(x)
    dt = {16: np.int16, 32: np.int32}[bits]
    pcm = (np.clip(x.T, -1, 1) * np.iinfo(dt).max).astype(dt)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(bits // 8)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def build(final: Path, slug: str, segments: list[dict], chapters: list[dict], duration: float,
          voice: np.ndarray | None, cfg: dict | None = None, seed: int | None = None,
          preset: str | None = None) -> dict:
    """Generate video/final/music.wav (bed) and stings.wav, and stamp them in music.json. Returns the stamp."""
    cfg = dict(DEFAULTS, **(cfg or {}))
    preset = preset or cfg.get("preset") or "calm-pad"
    if preset not in PRESETS:
        raise ValueError(f"unknown music preset {preset!r} (known: {', '.join(PRESETS)})")
    seed = int(seed if seed is not None else cfg.get("seed") if cfg.get("seed") is not None else seed_for(slug))
    gaps = pauses(voice, SR, float(cfg["pause_swell_s"])) if voice is not None else []
    ev = plan_events(segments, chapters, duration, gaps, cfg)
    bed, st, raw = synthesize(ev, seed, preset, cfg)
    write_wav(final / "music.wav", bed * 0.5)
    write_wav(final / "stings.wav", st * 0.5)
    probe = final / ".bed_level.wav"
    write_wav(probe, raw * 0.5)
    bed_level = loudness(probe)["integrated_lufs"]
    probe.unlink()
    sting_level = loudness(final / "stings.wav")["integrated_lufs"] if np.abs(st).max() > 0 else None
    stamp = {"schema_version": 1, "generator": GENERATOR, "tool_version": VERSION,
             "tool_sha256": sha256_file(Path(__file__)), "source": "generated",
             "licence": "original: synthesised by the channel's own tool from oscillators, no samples or recordings",
             "preset": preset, "seed": seed, "sample_rate": SR, "duration": ev["duration"], "events": ev,
             "levels": {"bed_lufs": bed_level, "sting_lufs": sting_level,
                        "note": "integrated loudness of the bed in mode 'bed' and of the stings while they sound, as "
                                "written (the mix sets them relative to the narration)"},
             "files": {"music.wav": sha256_file(final / "music.wav"), "stings.wav": sha256_file(final / "stings.wav")},
             "sha256": sha256_file(final / "music.wav"), "created_at": utc_now()}
    write_json(final / "music.json", stamp)
    return stamp


def verify(final: Path) -> list[str]:
    """Problems with the provenance stamp of the music in video/final (empty when it is sound)."""
    p = final / "music.json"
    if not p.exists():
        return ["no video/final/music.json (music must come from tools/video/music.py)"]
    m = json.loads(p.read_text(encoding="utf-8"))
    errs = []
    if m.get("generator") != GENERATOR:
        errs.append(f"generator is {m.get('generator')!r}, not {GENERATOR}")
    for k in ("tool_version", "preset", "seed", "sha256"):
        if m.get(k) in (None, ""):
            errs.append(f"stamp field {k} missing")
    if m.get("preset") not in PRESETS:
        errs.append(f"unknown preset {m.get('preset')!r}")
    for name, sha in (m.get("files") or {"music.wav": m.get("sha256")}).items():
        f = final / name
        if not f.exists():
            errs.append(f"{name} missing")
        elif sha256_file(f) != sha:
            errs.append(f"{name} differs from its stamp (sha256)")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--preset", choices=sorted(PRESETS))
    a = ap.parse_args()
    run = resolve_run(a.run)
    final = run / "video" / "final"
    asm = json.loads((final / "assembly.json").read_text(encoding="utf-8"))
    chs = json.loads((final / "chapters.json").read_text(encoding="utf-8")).get("chapters", [])
    voice = None
    if (final / "narration.wav").exists():
        x, sr = read_wav(final / "narration.wav")
        voice = x.mean(axis=0) if sr == SR else None
    slug = Path(asm["video"]).stem
    stamp = build(final, slug, asm["segments"], chs, float(asm["duration"]), voice, settings(), a.seed, a.preset)
    print(f"wrote {rel(final / 'music.wav')} and music.json: preset {stamp['preset']}, seed {stamp['seed']}, "
          f"{len(stamp['events']['chapters'])} chapter chords, {len(stamp['events']['stings'])} sting(s), "
          f"{len(stamp['events']['swells'])} swell(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
