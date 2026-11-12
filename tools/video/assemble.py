#!/usr/bin/env python3
"""Assemble the final video: the scenes in plan order, the mastered narration and music, captions and chapters.

Usage:
  python3 tools/video/assemble.py runs/<run> [--quality h|m|l] [--fps N]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, rel, resolve_run, write_json  # noqa: E402
import checks  # noqa: E402
import music as MU  # noqa: E402
import plan as P  # noqa: E402
from media import loudness, probe, read_srt, run, write_srt  # noqa: E402

PRESETS = {"l": (854, 480, 15), "m": (1280, 720, 30), "h": (1920, 1080, 60), "k": (3840, 2160, 60)}
MIN_CHAPTER_S = 10.0
MAX_GAIN_DB = 24.0          # never raise a near-silent premix (a silent draft voice) by more than this
VOICE_FILTER = "highpass=f=70,equalizer=f=7000:t=q:w=1.5:g=-2"   # softens the synthetic voice's edge at 7 kHz


def background_hex() -> str:
    return "0x" + load_json(CONFIG / "video.json").get("palette", {}).get("background", "#0f172a").lstrip("#")


def normalise(src: Path, dst: Path, w: int, h: int, fps: int) -> float:
    """Re-encode a scene to one size, frame rate and audio format, so that the concatenation is exact."""
    info = probe(src)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    dur = float(v.get("duration") or info["format"]["duration"])
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


def master_audio(joined: Path, out: Path, build: Path, final: Path, slug: str, segments: list[dict],
                 chs: list[dict], total: float, channel: dict) -> dict:
    """Narration stem, music ducked under it, the gain to the loudness target and the true-peak limit after AAC
    encoding (at most four encodes); muxes `out` and returns the audio record."""
    import numpy as np
    target = float(channel.get("video", {}).get("loudness_lufs", -14))
    mcfg = MU.settings()
    tp_max = float(mcfg.get("true_peak_dbtp", -1.0))
    use_music = bool(mcfg.get("enabled")) and mcfg.get("source", "generated") == "generated"
    if not use_music:                                       # never leave an old stamp behind
        for name in ("music.wav", "stings.wav", "music.json"):
            (final / name).unlink(missing_ok=True)
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
        st_gain = np.maximum(st_gain, MU.sting_hold(n, stamp["events"]["stings"]))   # the bells under the logo
        music_mix = bed * gain * 10 ** (g_bed / 20) + st * st_gain * 10 ** (g_st / 20)
        mix = mix + music_mix
        under = None
        if not silent_voice:                      # the mixed music alone, K-weighted like the loudness target
            probe_wav = build / "music_mix_probe.wav"
            MU.write_wav(probe_wav, music_mix, bits=32)
            under = MU.under_voice_files(stem, probe_wav)
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
    """plan.json music_from cues as [[video seconds, mode]]: the start of the scene's first narration block (from its
    layout log) that holds the cue's words; a cue whose words match no block is left out."""
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
    """YouTube chapters: the scenes' plan.json "chapter" titles (else their section's heading); consecutive scenes
    with one title form one chapter, and chapters under MIN_CHAPTER_S fold into the one before."""
    raw = []
    for seg in segments:
        if seg["kind"] != "scene":
            continue
        title = seg.get("chapter") or titles.get(seg.get("section"), seg.get("section"))
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
            continue
        merged.append(dict(ch))
    if len(merged) >= 2 and total - merged[-1]["start"] < MIN_CHAPTER_S:
        merged.pop()
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
            sting = checks.logo_sting(checks.scene_log(renders, scene["class"])[0])
            if sting is not None:                    # music.py rings the hook_title bells on the logo sting
                seg["logo_at"], seg["logo_s"] = round(sting[0], 3), round(sting[1] - sting[0], 3)
            for a0, b0, text in read_srt(src.with_suffix(".srt")):
                cues.append((t + a0, min(t + b0, t + dur), text))
        segments.append(seg)
        t += dur
    (build / "concat.txt").write_text("".join(f"file 'seg_{i:02d}.mp4'\n" for i in range(len(order))), encoding="utf-8")
    joined = build / "joined.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(build / "concat.txt"), "-c", "copy",
         str(joined)])
    out = final / f"{slug}.mp4"
    titles = section_titles(runp / "explainer.html")
    audio = master_audio(joined, out, build, final, slug, segments, chapters(segments, titles, t), t, channel)
    total = float(probe(out)["format"]["duration"])

    write_srt(final / f"{slug}.srt", [(a0, max(b0, a0 + 0.05), text) for a0, b0, text in sorted(cues)])
    chs = chapters(segments, titles, total)
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
    try:
        sys.exit(main())
    except RuntimeError as exc:                 # ffmpeg or ffprobe failed
        sys.exit(f"error: {exc}")
