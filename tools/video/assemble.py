#!/usr/bin/env python3
"""Assemble the final video: the narrated scenes in plan order, captions, chapters (deterministic).

Usage:
  python3 tools/video/assemble.py runs/<run> [--quality h|m|l] [--fps N]

Inputs:  video/plan.json; video/renders/<Class>.mp4 (+ .srt) for each scene; explainer.html (section headings, only
         for old plans without chapter titles); config/channel.json "video" (quality, loudness_lufs) and "music".
         No card is added: the video opens with the first scene's hook (no channel card) and ends with the plan's
         outro scene (takeaway card, channel name, teaser). The only thing added is original music (route A of the
         music rule): tools/video/music.py generates it, seeded and reproducible, with its provenance stamp.
Outputs: video/final/<slug>.mp4 (h264 + AAC), <slug>.srt (captions shifted to the final timeline), chapters.json
         (YouTube rules: first at 0:00, each at least 10 s, at least three), assembly.json (segments, and "audio":
         the music settings and the loudness and true peak measured on the encoded file), narration.wav (the
         narration stem, which the final gate measures), music.wav, stings.wav and music.json (when music is on).
Each segment is re-encoded to one size, frame rate and audio format, so the concatenation is exact.

Audio chain (after the concatenation): the narration stem (high-passed at 70 Hz, 2 dB less at 7 kHz, where the
synthetic voice has an edge); the music bed set bed_in_gaps_lu below the narration's loudness and ducked by
bed_in_gaps_lu - bed_under_voice_lu while the narration speaks (a sidechain keyed by the narration advanced by
lookahead_ms, attack_ms, release_ms), per scene mode (plan.json "music": bed, low or off; music.py); the stings at
sting_lu; then two passes to the target: the premix is measured
(EBU R128), a fixed gain brings it to video.loudness_lufs, an oversampled (192 kHz) limiter holds the peaks, and the
true peak is measured again after AAC encoding; above music.true_peak_dbtp the limiter is lowered and the encode
repeated, and a gain
shortfall the limiter caused (more than 0.3 LU) is made up (at most four encodes).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, rel, resolve_run, write_json  # noqa: E402
import music as MU  # noqa: E402
import plan as P  # noqa: E402

PRESETS = {"l": (854, 480, 15), "m": (1280, 720, 30), "h": (1920, 1080, 60), "k": (3840, 2160, 60)}
MIN_CHAPTER_S = 10.0
MAX_GAIN_DB = 24.0          # never raise a near-silent premix (a silent draft voice) by more than this
VOICE_FILTER = "highpass=f=70,equalizer=f=7000:t=q:w=1.5:g=-2"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"error: {' '.join(cmd[:4])} ... failed:\n{p.stderr[-2000:]}")
    return p.stdout


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)]))


def video_duration(info: dict) -> float:
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    return float(v.get("duration") or info["format"]["duration"])


def background_hex() -> str:
    """config/video.json palette.background as ffmpeg's 0xRRGGBB (the padding colour matches the scenes)."""
    return "0x" + load_json(CONFIG / "video.json").get("palette", {}).get("background", "#0f172a").lstrip("#")


def normalise(src: Path, dst: Path, w: int, h: int, fps: int) -> float:
    info = probe(src)
    dur = video_duration(info)
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={background_hex()},"
                   f"fps={fps},format=yuv420p",
            "-af", "apad", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(dst)]
    run(cmd)
    return float(probe(dst)["format"]["duration"])


def loudness(path: Path, extra: list[str] | None = None) -> dict:
    """EBU R128 of a file (music.py's measure): integrated LUFS, LRA, true peak dBTP."""
    return MU.loudness(path, extra)


def master_audio(joined: Path, out: Path, build: Path, final: Path, slug: str, segments: list[dict],
                 chs: list[dict], total: float, channel: dict) -> dict:
    """Narration stem, music (when on), ducking, two-pass loudness and the true-peak limit; muxes `out`."""
    import numpy as np
    target = float(channel.get("video", {}).get("loudness_lufs", -14))
    mcfg = MU.settings()
    tp_max = float(mcfg.get("true_peak_dbtp", -1.0))
    use_music = bool(mcfg.get("enabled")) and mcfg.get("source", "generated") == "generated"
    for name in ("music.wav", "stings.wav", "music.json"):       # never leave an old stamp behind
        if not use_music and (final / name).exists():
            (final / name).unlink()
    stem = final / "narration.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-map", "0:a:0", "-af", VOICE_FILTER, "-ar", str(MU.SR),
         "-ac", "2", "-c:a", "pcm_s16le", str(stem)])
    voice, _ = MU.read_wav(stem)
    n = voice.shape[1]
    voice_l = loudness(stem)
    silent_voice = voice_l["integrated_lufs"] <= -60
    ref = target if silent_voice else voice_l["integrated_lufs"]   # a silent draft voice: place the bed by the target
    mix = voice.copy()
    info = {"used": False}
    if use_music:
        stamp = MU.build(final, slug, segments, chs, total, voice.mean(axis=0), mcfg)
        bed, _ = MU.read_wav(final / "music.wav")
        st, _ = MU.read_wav(final / "stings.wav")
        bed, st = bed[:, :n], st[:, :n]
        if bed.shape[1] < n:
            bed = np.pad(bed, ((0, 0), (0, n - bed.shape[1])))
            st = np.pad(st, ((0, 0), (0, n - st.shape[1])))
        g_bed = (ref + float(mcfg["bed_in_gaps_lu"])) - stamp["levels"]["bed_lufs"]
        duck_db = float(mcfg["bed_in_gaps_lu"]) - float(mcfg["bed_under_voice_lu"])
        gain = MU.duck_gain(voice.mean(axis=0), MU.SR, duck_db, mcfg["attack_ms"], mcfg["release_ms"],
                            mcfg["lookahead_ms"]) if not silent_voice else np.ones(n)
        sl = stamp["levels"].get("sting_lufs")
        g_st = (ref + float(mcfg["sting_lu"])) - sl if sl is not None and sl > -70 else -120.0
        st_gain = MU.duck_gain(voice.mean(axis=0), MU.SR, float(mcfg.get("sting_duck_db", 14.0)),
                               mcfg["attack_ms"], mcfg["release_ms"], mcfg["lookahead_ms"]) \
            if not silent_voice else np.ones(n)
        music_mix = bed * gain * 10 ** (g_bed / 20) + st * st_gain * 10 ** (g_st / 20)
        mix = mix + music_mix
        under = None
        if not silent_voice:                      # K-weighted, as the loudness targets: the mixed music alone
            probe = build / "music_mix_probe.wav"
            MU.write_wav(probe, music_mix, bits=32)
            under = MU.under_voice_files(stem, probe)
            if under is None:
                under = MU.under_voice(voice.mean(axis=0), music_mix.mean(axis=0), MU.SR)
        info = {"used": True, "source": "generated", "generator": stamp["generator"], "tool_version":
                stamp["tool_version"], "preset": stamp["preset"], "seed": stamp["seed"], "sha256": stamp["sha256"],
                "stamp": rel(final / "music.json"), "bed_gain_db": round(g_bed, 2), "sting_gain_db": round(g_st, 2),
                "bed_in_gaps_lu": mcfg["bed_in_gaps_lu"], "bed_under_voice_lu": mcfg["bed_under_voice_lu"],
                "duck_db": round(duck_db, 2), "attack_ms": mcfg["attack_ms"], "release_ms": mcfg["release_ms"],
                "lookahead_ms": mcfg["lookahead_ms"], "low_under_voice_lu": mcfg["low_under_voice_lu"],
                "modes": stamp["events"]["modes"], "stings": stamp["events"]["stings"],
                "sting_duck_db": float(mcfg.get("sting_duck_db", 14.0)),
                "under_voice_max_db": under,
                "under_voice_limit_db": float(mcfg.get("music_under_voice_max_lu", -12.0))}
    premix = build / "premix.wav"
    headroom = max(1.0, float(np.abs(mix).max()) * 1.05)
    MU.write_wav(premix, mix / headroom, bits=32)
    pre = loudness(premix)
    gain_db = min(MAX_GAIN_DB, target - pre["integrated_lufs"])
    master = build / "master.wav"
    limit_db = tp_max - 1.0
    for attempt in range(4):
        lim = 10 ** (limit_db / 20)
        run(["ffmpeg", "-v", "error", "-y", "-i", str(premix), "-af",
             f"volume={gain_db:.2f}dB,aresample=192000,alimiter=limit={lim:.4f}:attack=3:release=60:level=false:"
             f"latency=true,aresample=48000", "-c:a", "pcm_s24le", str(master)])
        run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-i", str(master), "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest",
             "-movflags", "+faststart", str(out)])
        measured = loudness(out)
        off = target - measured["integrated_lufs"]
        tp_ok = measured["true_peak_dbtp"] <= tp_max
        if tp_ok and (abs(off) <= 0.3 or measured["integrated_lufs"] <= -60):
            break
        if not tp_ok:
            limit_db -= measured["true_peak_dbtp"] - tp_max + 0.3
        gain_db = min(MAX_GAIN_DB, gain_db + off)           # the limiter took some loudness: make it up
    return {"target_lufs": target, "true_peak_max_dbtp": tp_max, "voice_filter": VOICE_FILTER,
            "narration_stem": rel(stem), "narration": voice_l, "premix": pre, "gain_db": round(gain_db, 2),
            "limiter_dbfs": round(limit_db, 2), "passes": attempt + 1, "measured": measured,
            "music": info}


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    def t(s):
        hh, mm, rest = s.strip().split(":")
        ss, ms = rest.split(",")
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [x for x in block.splitlines() if x.strip()]
        if len(lines) >= 2 and "-->" in lines[1]:
            a, b = lines[1].split("-->")
            cues.append((t(a), t(b), " ".join(lines[2:]).strip()))
    return cues


def fmt_srt(sec: float) -> str:
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def fmt_chapter(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def section_titles(explainer: Path) -> dict[str, str]:
    import lint_html
    c = lint_html.Collector()
    c.feed(explainer.read_text(encoding="utf-8"))
    c.close()
    out = {}
    for sid, (_, text, _) in c.headings.items():
        text = re.sub(r"^\d+(\.\d+)*\.?\s+", "", text)
        out[sid] = re.sub(r"\s+", " ", text.replace("$", "").replace("<", "").replace(">", "")).strip()
    return out


def music_changes(scene: dict, layout: Path, t0: float) -> list[list]:
    """(v5) plan.json scenes[].music_from [{"says", "mode"}] as [[video seconds, mode]]: the start of the scene's first
    narration block (from its layout log) that contains the words; a cue whose words are not found is left out."""
    cues = scene.get("music_from") or []
    if not cues or not layout.exists():
        return []
    log = load_json(layout)
    vos = list(log.get("voiceovers") or [])
    for sc in (log.get("scenes") or {}).values():         # layout_probe.py logs: {"scenes": {name: {"voiceovers"}}}
        vos += sc.get("voiceovers") or []
    out = []
    for c in cues:
        says = str(c.get("says") or "").strip().lower()
        hit = next((v for v in vos if says and says in str(v.get("text", "")).lower()), None)
        if hit is not None and c.get("mode") in MU.MODES:
            out.append([round(t0 + float(hit["start"]), 3), c["mode"]])
        else:
            print(f"warning: {scene.get('class')}: music_from {says!r} matches no narration block; ignored",
                  file=sys.stderr)
    return sorted(out)


def chapters(segments: list[dict], titles: dict[str, str], total: float) -> list[dict]:
    """YouTube chapters from the scene segments: plan.json "chapter" titles (the explainer's heading only for old plans
    without one); consecutive scenes with the same title form one chapter."""
    raw = []
    for seg in segments:
        if seg["kind"] != "scene":
            continue
        title = seg.get("chapter") or titles.get(seg.get("section"), seg.get("section"))   # the video's own title first
        if raw and raw[-1]["title"] == title:
            continue
        raw.append({"start": seg["start"], "title": title})
    if not raw:
        return []
    raw[0]["start"] = 0.0                       # YouTube's first chapter starts at 0:00
    merged = []
    for i, ch in enumerate(raw):
        end = raw[i + 1]["start"] if i + 1 < len(raw) else total
        if merged and end - ch["start"] < MIN_CHAPTER_S:
            continue                            # too short: fold into the previous chapter
        merged.append(dict(ch))
    if len(merged) >= 2 and total - merged[-1]["start"] < MIN_CHAPTER_S:
        merged.pop()                            # a short last chapter folds back too
    for ch in merged:
        ch["label"] = f"{fmt_chapter(ch['start'])} {ch['title']}"
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--quality", choices=sorted(PRESETS), help="default: config/channel.json video.quality")
    ap.add_argument("--fps", type=int, help="frame rate other than the preset's (default: config video.fps if set)")
    a = ap.parse_args()
    runp = resolve_run(a.run)
    issues = P.problems(runp)
    if issues:
        print("\n".join(f"error: {i}" for i in issues), file=sys.stderr)
        return 1
    plan = P.load(runp)
    channel = load_json(CONFIG / "channel.json")
    q = a.quality or channel.get("video", {}).get("quality", "h")
    w, h, fps = PRESETS[q]
    fps = a.fps or channel.get("video", {}).get("fps") or fps
    slug = P.topic(runp)["slug"]
    renders, build, final = runp / "video" / "renders", runp / "video" / "build", runp / "video" / "final"
    build.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    order = [("scene", renders / f"{s['class']}.mp4", s) for s in plan["scenes"]]
    missing = [rel(p) for _, p, _ in order if not p.exists()]
    if missing:
        print("error: missing renders: " + ", ".join(missing), file=sys.stderr)
        return 1

    segments, t, cues = [], 0.0, []
    for i, (kind, src, scene) in enumerate(order):
        dst = build / f"seg_{i:02d}.mp4"
        dur = normalise(src, dst, w, h, fps)
        seg = {"kind": kind, "file": rel(src), "start": round(t, 3), "duration": round(dur, 3)}
        if scene:
            seg.update({"class": scene["class"], "section": scene.get("section"),     # context and outro may omit it
                        "chapter": scene.get("chapter") or scene.get("section") or scene["class"],
                        "role": scene.get("role", "body"), "music": MU.scene_mode(scene, MU.settings())})
            changes = music_changes(scene, src.with_suffix(".layout.json"), t)
            if changes:
                seg["music_changes"] = changes
            srt = src.with_suffix(".srt")
            if srt.exists():
                for a0, b0, text in parse_srt(srt.read_text(encoding="utf-8")):
                    cues.append((t + a0, min(t + b0, t + dur), text))
        segments.append(seg)
        t += dur
    (build / "concat.txt").write_text("".join(f"file 'seg_{i:02d}.mp4'\n" for i in range(len(order))), encoding="utf-8")
    joined = build / "joined.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(build / "concat.txt"), "-c", "copy",
         str(joined)])
    out = final / f"{slug}.mp4"
    audio = master_audio(joined, out, build, final, slug, segments,
                         chapters(segments, section_titles(runp / "explainer.html"), t), t, channel)
    total = float(probe(out)["format"]["duration"])

    srt_lines = []
    for n, (a0, b0, text) in enumerate(sorted(cues), 1):
        srt_lines += [str(n), f"{fmt_srt(a0)} --> {fmt_srt(max(b0, a0 + 0.05))}", text, ""]
    (final / f"{slug}.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    chs = chapters(segments, section_titles(runp / "explainer.html"), total)
    write_json(final / "chapters.json", {"schema_version": 1, "chapters": chs, "valid": len(chs) >= 3})
    write_json(final / "assembly.json", {"schema_version": 1, "quality": q, "size": [w, h], "fps": fps,
                                          "duration": round(total, 3), "video": rel(out),
                                          "captions": rel(final / f"{slug}.srt"), "cues": len(cues),
                                          "audio": audio, "segments": segments})
    print(f"wrote {rel(out)}: {total:.1f} s, {len(segments)} segments, {len(cues)} caption cues, "
          f"{len(chs)} chapters{'' if len(chs) >= 3 else ' (fewer than 3: YouTube shows none)'}")
    for ch in chs:
        print(f"  {ch['label']}")
    m = audio["measured"]
    print(f"audio: {m['integrated_lufs']} LUFS integrated, true peak {m['true_peak_dbtp']} dBTP, LRA {m['lra_lu']} LU "
          f"(target {audio['target_lufs']} LUFS, ceiling {audio['true_peak_max_dbtp']} dBTP); music: "
          + (f"generated, preset {audio['music']['preset']}, seed {audio['music']['seed']}" if audio["music"]["used"]
             else "off"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
