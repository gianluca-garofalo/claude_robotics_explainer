#!/usr/bin/env python3
"""Frames of the final assembled video for the final-cut reviewer, who watches it the way a viewer would.

Usage:
  python3 tools/video/final_frames.py runs/<run> [--every 2] [--scene-threshold 0.3] [--width 960]

Takes a frame every --every seconds, at every scene change (ffmpeg scene detection), at every chapter start and just
after the end of every scene (leftovers after a transition), from video/final/<slug>.mp4. Writes
review/final_cut/frames/t<seconds>.jpg, contact sheets review/final_cut/sheet-NN.jpg (12 frames each, labelled with
time, chapter and the caption on screen at that moment) and review/final_cut/frames.json: for every frame its time,
why it was taken (every, scene-change, chapter, after-scene), the chapter, the scene and the caption shown then, plus
the narration blocks with their times (from the captions). The final-cut-reviewer subagent reads these; it can
extract any other moment with ffmpeg -ss. Needs ffmpeg and Pillow.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import rel, resolve_run, sha256_file, utc_now, write_json  # noqa: E402
import plan as P  # noqa: E402


def srt(path: Path) -> list[tuple[float, float, str]]:
    def t(s):
        hh, mm, rest = s.strip().split(":")
        ss, ms = rest.split(",")
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000
    cues = []
    if path.exists():
        for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
            lines = [x for x in block.splitlines() if x.strip()]
            if len(lines) >= 2 and "-->" in lines[1]:
                a, b = lines[1].split("-->")
                cues.append((t(a), t(b), " ".join(lines[2:]).strip()))
    return cues


def scene_changes(video: Path, threshold: float) -> list[float]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf",
                        f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [round(float(m), 2) for m in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def grab(video: Path, t: float, out: Path, width: int) -> bool:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], capture_output=True)
    return r.returncode == 0 and out.exists()


def sheets(frames: list[dict], folder: Path, out_dir: Path) -> list[str]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    names = []
    cols, rows, tw = 4, 3, 480
    for k in range(0, len(frames), cols * rows):
        chunk = frames[k:k + cols * rows]
        ims = [Image.open(folder / f["file"]).convert("RGB") for f in chunk]
        th = int(tw * ims[0].height / ims[0].width)
        cap_h = 54
        sheet = Image.new("RGB", (cols * tw, rows * (th + cap_h)), (8, 12, 24))
        d = ImageDraw.Draw(sheet)
        for i, (f, im) in enumerate(zip(chunk, ims)):
            x, y = (i % cols) * tw, (i // cols) * (th + cap_h)
            sheet.paste(im.resize((tw, th)), (x, y))
            mm = f"{int(f['t']) // 60}:{f['t'] % 60:05.2f}"
            d.text((x + 4, y + th + 3), f"{mm}  {f['why']}  [{f['chapter'][:28]}]", fill=(200, 210, 225), font=font)
            d.text((x + 4, y + th + 22), (f["caption"] or "")[:62], fill=(148, 163, 184), font=font)
        name = f"sheet-{k // (cols * rows) + 1:02d}.jpg"
        sheet.save(out_dir / name, "JPEG", quality=80)
        names.append(name)
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--scene-threshold", type=float, default=0.3)
    ap.add_argument("--width", type=int, default=960)
    a = ap.parse_args()
    run = resolve_run(a.run)
    video = P.final_video(run)
    if not video.exists() or not shutil.which("ffmpeg"):
        print(f"error: {rel(video)} or ffmpeg missing: assemble first", file=sys.stderr)
        return 1
    asm = json.loads((run / "video" / "final" / "assembly.json").read_text(encoding="utf-8"))
    chs = json.loads((run / "video" / "final" / "chapters.json").read_text(encoding="utf-8")).get("chapters", [])
    cues = srt(video.with_suffix(".srt"))
    dur = asm["duration"]
    times: dict[float, set] = {}

    def want(t, why):
        t = round(min(max(t, 0.0), max(dur - 0.05, 0.0)), 2)
        times.setdefault(t, set()).add(why)
    k = 0.0
    while k < dur:
        want(k + 0.5 if k == 0 else k, "every")
        k += a.every
    for t in scene_changes(video, a.scene_threshold):
        want(t + 0.1, "scene-change")
    for ch in chs:
        want(ch["start"] + 0.5, "chapter")
    for sg in asm["segments"]:
        want(sg["start"] + sg["duration"] - 0.25, "after-scene")
    out = run / "review" / "final_cut"
    folder = out / "frames"
    shutil.rmtree(folder, ignore_errors=True)
    for old in out.glob("sheet-*.jpg"):
        old.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in sorted(times):
        f = folder / f"t{t:07.2f}.jpg"
        if not grab(video, t, f, a.width):
            continue
        seg = next((sg for sg in asm["segments"] if sg["start"] <= t < sg["start"] + sg["duration"]), asm["segments"][-1])
        chapter = next((c["title"] for c in reversed(chs) if c["start"] <= t), chs[0]["title"] if chs else "")
        cap = next((c for c in cues if c[0] <= t <= c[1] + 0.3), None)
        frames.append({"t": t, "file": f.name, "why": "+".join(sorted(times[t])), "chapter": chapter,
                       "scene": seg.get("class", seg.get("kind")), "role": seg.get("role", "body"),
                       "caption": cap[2] if cap else ""})
    names = sheets(frames, folder, out)
    write_json(out / "frames.json", {"schema_version": 1, "video": rel(video), "video_sha256": sha256_file(video),
                                     "duration": dur, "made_at": utc_now(), "every_s": a.every, "frames": frames,
                                     "sheets": names, "chapters": chs,
                                     "segments": [{k: sg.get(k) for k in ("class", "role", "start", "duration",
                                                                          "chapter")} for sg in asm["segments"]],
                                     "captions": [{"start": round(x, 2), "end": round(y, 2), "text": z}
                                                  for x, y, z in cues]})
    print(f"wrote {len(frames)} frames and {len(names)} contact sheets to {rel(out)} ({rel(out / 'frames.json')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
