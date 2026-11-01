#!/usr/bin/env python3
"""Assemble the final video: the narrated scenes in plan order, captions, chapters (deterministic).

Usage:
  python3 tools/video/assemble.py runs/<run> [--quality h|m|l] [--fps N]

Inputs:  video/plan.json; video/renders/<Class>.mp4 (+ .srt) for each scene; explainer.html (section headings, only
         for old plans without chapter titles). Nothing is added: the video opens with the first scene's hook (no
         channel card) and ends with the plan's outro scene (takeaway card, channel name, teaser).
Outputs: video/final/<slug>.mp4 (h264 + AAC, loudness-normalised), <slug>.srt (captions shifted to the final
         timeline), chapters.json (YouTube rules: first at 0:00, each at least 10 s, at least three), assembly.json.
Each segment is re-encoded to one size, frame rate and audio format, so the concatenation is exact.
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
import plan as P  # noqa: E402

PRESETS = {"l": (854, 480, 15), "m": (1280, 720, 30), "h": (1920, 1080, 60), "k": (3840, 2160, 60)}
MIN_CHAPTER_S = 10.0


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
                        "role": scene.get("role", "body")})
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
    lufs = channel.get("video", {}).get("loudness_lufs", -16)
    out = final / f"{slug}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-c:v", "copy",
         "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(out)])
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
                                          "segments": segments})
    print(f"wrote {rel(out)}: {total:.1f} s, {len(segments)} segments, {len(cues)} caption cues, "
          f"{len(chs)} chapters{'' if len(chs) >= 3 else ' (fewer than 3: YouTube shows none)'}")
    for ch in chs:
        print(f"  {ch['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
