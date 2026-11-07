#!/usr/bin/env python3
"""Check rendered videos: decodable, the quality preset's size and frame rate, length, not blank, captions.

Usage:
  python3 tools/check_video.py VIDEO.mp4 [...] [--quality l|m|h|k] [--fps N] [--min-duration 2] [--max-duration 1200]
                                [--json report.json]      # exit status 1 when a video has an error
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
from media import probe  # noqa: E402

PRESETS = {"l": (854, 480, 15), "m": (1280, 720, 30), "h": (1920, 1080, 60), "k": (3840, 2160, 60)}


def frame_gray(path: Path, t: float) -> bytes:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    return p.stdout


def check(path: Path, quality: str | None, dmin: float, dmax: float, fps_override: float | None = None) -> dict:
    r = {"file": path.name, "errors": [], "warnings": []}
    try:
        info = probe(path)
    except (RuntimeError, json.JSONDecodeError) as exc:
        r["errors"].append(f"not decodable: {exc}")
        return r
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        r["errors"].append("no video stream")
        return r
    dur = float(info.get("format", {}).get("duration") or v.get("duration") or 0)
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    r.update(codec=v.get("codec_name"), width=v.get("width"), height=v.get("height"), fps=round(fps, 2),
             duration=round(dur, 2), frames=int(v.get("nb_frames") or 0),
             audio=any(s.get("codec_type") == "audio" for s in info["streams"]),
             size_mb=round(path.stat().st_size / 1e6, 2))
    if v.get("codec_name") != "h264":
        r["warnings"].append(f"codec {v.get('codec_name')} (h264 plays everywhere)")
    if not (dmin <= dur <= dmax):
        r["errors"].append(f"duration {dur:.1f} s outside [{dmin}, {dmax}]")
    if quality:
        w, h, f = PRESETS[quality]
        f = fps_override or f
        if (v.get("width"), v.get("height")) != (w, h):
            r["errors"].append(f"size {v.get('width')}x{v.get('height')}, expected {w}x{h} for -q{quality}")
        if abs(fps - f) > 0.5:
            r["errors"].append(f"{fps:.1f} fps, expected {f:g} for -q{quality}")
    srt = path.with_suffix(".srt")
    if srt.exists():
        try:
            import check_selfcontained as SC
            st = SC.settings()
            found = SC.check_items([{"source": "captions", "where": srt.name, "text": SC.srt_text(srt),
                                     "kind": "plain", "order": (0, 0, 0)}], st)
            r["errors"] += [f"captions not self-contained: {f['rule']} '{f['match']}'" for f in found]
        except ImportError:
            r["warnings"].append("captions not checked (tools/video/check_selfcontained.py missing)")
    frames = [frame_gray(path, dur * x) for x in (0.1, 0.5, 0.9)] if dur > 0 else []
    frames = [fr for fr in frames if fr]
    if not frames:
        r["errors"].append("could not decode sample frames")
    else:
        stds = [statistics.pstdev(fr) for fr in frames]
        r["frame_std"] = [round(s, 1) for s in stds]
        if max(stds) < 2.0:
            r["errors"].append("sample frames are flat: the video looks blank")
        if len(frames) == 3 and frames[0] == frames[1] == frames[2]:
            r["warnings"].append("the three sample frames are identical: frozen video?")
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--quality", choices=sorted(PRESETS))
    ap.add_argument("--fps", type=float, help="expected frame rate when it is not the preset's")
    ap.add_argument("--min-duration", type=float, default=2.0)
    ap.add_argument("--max-duration", type=float, default=1200.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    for tool in ("ffprobe", "ffmpeg"):
        if not shutil.which(tool):
            print(f"error: {tool} not found (install ffmpeg)", file=sys.stderr)
            return 3
    results = [check(Path(p), a.quality, a.min_duration, a.max_duration, a.fps) for p in a.videos]
    ok = all(not r["errors"] for r in results)
    for r in results:
        desc = (f"{r.get('width')}x{r.get('height')} {r.get('fps')} fps {r.get('duration')} s {r.get('codec')} "
                f"{r.get('size_mb')} MB")
        print(f"{'ok  ' if not r['errors'] else 'FAIL'}  {r['file']}: {desc}")
        for e in r["errors"]:
            print(f"      ERROR   {e}")
        for w in r["warnings"]:
            print(f"      warning {w}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"schema_version": 1, "quality": a.quality, "fps": a.fps, "pass": ok, "videos": results},
                                           indent=2) + "\n", encoding="utf-8")
    print(f"check_video: {'ok' if ok else 'FAIL'} ({len(results)} file(s))")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
