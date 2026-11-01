#!/usr/bin/env python3
"""Make the YouTube thumbnail from a frame of our own render, with the Remaining Action layout (deterministic).

Usage:
  python3 tools/video/thumbnail.py runs/<run> [--out video/final/thumbnail.jpg]

Takes the frame at plan.json "thumbnail" (scene class + seconds into that scene) from the assembled video, scales it
to 1280x720, lays a uniform dark panel (config/video.json "design"."thumbnail_title_shade") over everything under
the title, fading out to the right of it, writes the thumbnail text (at most 40 characters, two lines) and the
channel name. Original graphics only: nothing but our own frame and text. JPEG under 2 MB, as the YouTube API
requires. Also writes thumbnail.json (text boxes, sizes, colours, the frame's scene and time, the panel) for the
checks in check_design.py: legibility at 168 x 94, and nothing busy behind the title (frame text under it, edges).
Choose plan.json "thumbnail" so that the frame has no text where the title goes (the left half).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, load_json, rel, resolve_run  # noqa: E402
import plan as P  # noqa: E402

W, H = 1280, 720
INK, GREEN, MUTED = (226, 232, 240), (45, 212, 191), (148, 163, 184)
_BG_HEX = load_json(CONFIG / "video.json").get("palette", {}).get("background", "#0f172a").lstrip("#")
BG = tuple(int(_BG_HEX[i:i + 2], 16) for i in (0, 2, 4))          # config/video.json palette.background


FALLBACKS = {True: ["Arial Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc"],
             False: ["Arial.ttf", "LiberationSans-Regular.ttf", "Helvetica.ttc"]}
_warned = set()


def font(size: int, bold: bool = True):
    """DejaVu Sans (the scenes' font), found by file name in the system font folders (Pillow searches the Linux ones
    and, on macOS, ~/Library/Fonts and /Library/Fonts) or through fontconfig; else a common sans with a warning."""
    from PIL import ImageFont
    fname = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(fname, size)
    except OSError:
        pass
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", "DejaVu Sans:bold" if bold else "DejaVu Sans"],
                              capture_output=True, text=True).stdout.strip()
        if "dejavu" in Path(path).name.lower():                # fc-match always answers, often with another font
            return ImageFont.truetype(path, size)
    except (OSError, ValueError):
        pass
    for alt in FALLBACKS[bold]:
        try:
            f = ImageFont.truetype(alt, size)
        except OSError:
            continue
        if bold not in _warned:
            _warned.add(bold)
            print(f"warning: {fname} not found, the thumbnail uses {alt} (Linux: apt install fonts-dejavu-core; "
                  "macOS: brew install --cask font-dejavu)", file=sys.stderr)
        return f
    print(f"warning: {fname} not found and no fallback font: the thumbnail uses Pillow's default font",
          file=sys.stderr)
    return ImageFont.load_default(size=size)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--out")
    a = ap.parse_args()
    from PIL import Image, ImageDraw
    run = resolve_run(a.run)
    plan = P.load(run)
    asm = json.loads((run / "video" / "final" / "assembly.json").read_text(encoding="utf-8"))
    th = plan["thumbnail"]
    seg = next(s for s in asm["segments"] if s.get("class") == th["scene"])
    t = seg["start"] + min(float(th["time"]), max(seg["duration"] - 0.1, 0))
    frame = run / "video" / "build" / "thumb_frame.png"
    frame.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(P.final_video(run)), "-frames:v", "1",
                    str(frame)], check=True)
    img = Image.open(frame).convert("RGB").resize((W, H))
    channel = load_json(CONFIG / "channel.json")["channel_name"]
    lines = textwrap.wrap(th["text"], width=16)[:2]
    f_big = font(92)
    probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
    words = th["text"].split()
    if len(lines) == 1 and len(words) > 1 and probe.textlength(lines[0], font=f_big) > 0.45 * W:
        cut = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        lines = [" ".join(words[:cut]), " ".join(words[cut:])]   # two short lines leave the frame's right half clear
    y0 = H // 2 - len(lines) * 55
    boxes = [probe.textbbox((64, y0 + 110 * i), line, font=f_big) for i, line in enumerate(lines)]
    right = min(W, max(b[2] for b in boxes) + 48)        # the panel covers the title fully and evenly ...
    fade = int(W * 0.06)                                 # ... and fades out quickly beyond it, sparing the picture
    alpha = float(load_json(CONFIG / "video.json").get("design", {}).get("thumbnail_title_shade", 0.82))
    shade = Image.new("L", (W, H))
    for x in range(W):
        k = 1.0 if x <= right else max(0.0, 1 - (x - right) / fade)
        shade.paste(int(255 * alpha * k), (x, 0, x + 1, H))
    img = Image.composite(Image.new("RGB", (W, H), BG), img, shade)
    d = ImageDraw.Draw(img)
    y = y0
    for line in lines:
        d.text((64, y), line, font=f_big, fill=INK)
        y += 110
    d.rectangle((64, y + 6, 64 + 220, y + 14), fill=GREEN)
    d.text((64, H - 78), channel.upper(), font=font(34), fill=MUTED)
    union = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    elements = [{"role": "title", "text": th["text"], "font_px": 92, "bbox": union, "color": "#%02x%02x%02x" % INK},
                {"role": "channel", "text": channel.upper(), "font_px": 34, "decorative": True,
                 "bbox": list(d.textbbox((64, H - 78), channel.upper(), font=font(34))), "color": "#%02x%02x%02x" % MUTED}]
    out = Path(a.out) if a.out else run / "video" / "final" / "thumbnail.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    for q in (90, 80, 70, 60):
        img.save(out, "JPEG", quality=q, optimize=True)
        if out.stat().st_size < 2_000_000:
            break
    (out.parent / "thumbnail.json").write_text(json.dumps({"size": [W, H], "elements": elements,
                                                           "frame": {"scene": th["scene"], "scene_time": float(th["time"]),
                                                                     "video_time": round(t, 3)},
                                                           "panel": {"right": right, "fade": fade, "shade": alpha}},
                                                          indent=1), encoding="utf-8")
    print(f"wrote {rel(out)} ({out.stat().st_size / 1e3:.0f} kB, frame at {t:.1f} s of the final video)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
