#!/usr/bin/env python3
"""Make the YouTube thumbnail (JPEG under 2 MB, and thumbnail.json for check_design.py) from plan.json "thumbnail", with
the channel's badge (tools/video/watermark.py) in the bottom-left corner.

Usage:
  python3 tools/video/thumbnail.py runs/<run> [--out video/final/thumbnail.jpg]
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
BADGE_PX, BADGE_MARGIN = 84, 40      # the channel's badge (tools/video/watermark.py) in the bottom-left corner
INK, GREEN, MUTED = (226, 232, 240), (45, 212, 191), (148, 163, 184)
_BG_HEX = load_json(CONFIG / "video.json").get("palette", {}).get("background", "#0f172a").lstrip("#")
BG = tuple(int(_BG_HEX[i:i + 2], 16) for i in (0, 2, 4))
FALLBACKS = {True: ["Arial Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc"],
             False: ["Arial.ttf", "LiberationSans-Regular.ttf", "Helvetica.ttc"]}
_warned = set()


def font(size: int, bold: bool = True):
    """DejaVu Sans (the scenes' font) by file name or through fontconfig; else a common sans, with a warning."""
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


def save(img, out: Path, meta: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    for q in (90, 80, 70, 60):
        img.save(out, "JPEG", quality=q, optimize=True)
        if out.stat().st_size < 2_000_000:
            break
    (out.parent / "thumbnail.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def badge_image():
    """The channel's badge (the watermark's plate), BADGE_PX square; None, with a warning, without Manim."""
    try:
        import watermark
        return watermark.badge(BADGE_PX)
    except Exception as exc:                  # no Manim or Cairo here: the channel's name alone
        print(f"warning: no badge on the thumbnail ({type(exc).__name__}: {exc})", file=sys.stderr)
        return None


def badge_slot() -> tuple[int, int, int, int]:
    return 64, H - BADGE_MARGIN - BADGE_PX, 64 + BADGE_PX, H - BADGE_MARGIN


def has_content(img, box, delta: int = 28) -> bool:
    """True when anything inside box differs from the background by more than delta."""
    from PIL import Image, ImageChops
    part = img.crop(box)
    diff = ImageChops.difference(part, Image.new("RGB", part.size, BG)).convert("L")
    return diff.point(lambda v: 255 if v > delta else 0).getbbox() is not None


def content_box(img, pad: float = 0.04, delta: int = 28) -> tuple[int, int, int, int]:
    """Bounding box of what differs from the background, padded by `pad` of the frame; the whole frame if nothing."""
    from PIL import ImageChops, Image
    diff = ImageChops.difference(img, Image.new("RGB", img.size, BG)).convert("L").point(lambda v: 255 if v > delta
                                                                                          else 0)
    box = diff.getbbox()
    if not box:
        return (0, 0, img.size[0], img.size[1])
    px, py = int(pad * img.size[0]), int(pad * img.size[1])
    return (max(0, box[0] - px), max(0, box[1] - py), min(img.size[0], box[2] + px), min(img.size[1], box[3] + py))


def picture_layout(run: Path, a, img, th: dict, t: float, channel: str) -> int:
    """Layout "picture": the title in a band across the top, the frame's content cropped and fitted whole under it."""
    from PIL import Image, ImageDraw
    size = 84
    f_big = font(size)
    probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
    text = th["text"].strip()
    while probe.textlength(text, font=f_big) > W - 2 * 64 and size > 56:
        size -= 4
        f_big = font(size)
    x0, y0 = 64, 24
    tb = probe.textbbox((x0, y0), text, font=f_big)
    band = tb[3] + 26
    crop = content_box(img)
    pic = img.crop(crop)

    def place(room_h):
        """The picture fitted whole under the band, centred in a room room_h tall: (canvas, its box, its scale)."""
        k = min((W - 2 * 24) / pic.size[0], room_h / pic.size[1])
        pw, ph = max(1, int(pic.size[0] * k)), max(1, int(pic.size[1] * k))
        canvas = Image.new("RGB", (W, H), BG)
        px, py = (W - pw) // 2, band + 8 + (room_h - ph) // 2
        canvas.paste(pic.resize((pw, ph), Image.LANCZOS), (px, py))
        return canvas, [px, py, px + pw, py + ph], k
    img, box, k = place(H - band - 16)
    badge, slot = badge_image(), badge_slot()
    if badge is not None:
        if has_content(img, (slot[0] - 8, slot[1] - 8, slot[2] + 8, slot[3] + 8)):
            img, box, k = place(slot[1] - band - 16)                  # the picture ends above the badge
        img.paste(badge, slot[:2], badge)
    alpha = float(load_json(CONFIG / "video.json").get("design", {}).get("thumbnail_title_shade", 0.82))
    d = ImageDraw.Draw(img)
    d.text((x0, y0), text, font=f_big, fill=INK)
    d.rectangle((x0, tb[3] + 8, x0 + 180, tb[3] + 14), fill=GREEN)
    f_ch = font(22)
    cb = d.textbbox((0, 0), channel.upper(), font=f_ch)
    cx, cy = x0 + 200, tb[3] + 11 - (cb[3] + cb[1]) // 2
    d.text((cx, cy), channel.upper(), font=f_ch, fill=MUTED)
    elements = [{"role": "title", "text": text, "font_px": size, "bbox": list(tb), "color": "#%02x%02x%02x" % INK},
                {"role": "channel", "text": channel.upper(), "font_px": 22, "decorative": True,
                 "bbox": list(d.textbbox((cx, cy), channel.upper(), font=f_ch)), "color": "#%02x%02x%02x" % MUTED}]
    if badge is not None:
        elements.append({"role": "badge", "decorative": True, "bbox": list(slot)})
    out = Path(a.out) if a.out else run / "video" / "final" / "thumbnail.jpg"
    save(img, out, {"size": [W, H], "layout": "picture", "elements": elements,
                    "frame": {"scene": th["scene"], "scene_time": float(th["time"]), "video_time": round(t, 3)},
                    "picture": {"crop": list(crop), "box": box, "scale": round(k, 3)},
                    "panel": {"band": band, "fade": 0, "shade": alpha}})
    print(f"wrote {rel(out)} ({out.stat().st_size / 1e3:.0f} kB, picture layout, frame at {t:.1f} s of the final "
          f"video, content {crop} scaled {k:.2f} under the title band)")
    return 0


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
    if th.get("layout") == "picture":
        return picture_layout(run, a, img, th, t, channel)
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
    badge, slot = badge_image(), badge_slot()
    name_at = (64, H - 78)
    if badge is not None:                               # the badge in the corner, the channel's name beside it
        img.paste(badge, slot[:2], badge)
        nb = d.textbbox((0, 0), channel.upper(), font=font(34))
        name_at = (slot[2] + 18, (slot[1] + slot[3]) // 2 - (nb[1] + nb[3]) // 2)
    d.text(name_at, channel.upper(), font=font(34), fill=MUTED)
    union = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    elements = [{"role": "title", "text": th["text"], "font_px": 92, "bbox": union, "color": "#%02x%02x%02x" % INK},
                {"role": "channel", "text": channel.upper(), "font_px": 34, "decorative": True,
                 "bbox": list(d.textbbox(name_at, channel.upper(), font=font(34))), "color": "#%02x%02x%02x" % MUTED}]
    if badge is not None:
        elements.append({"role": "badge", "decorative": True, "bbox": list(slot)})
    out = Path(a.out) if a.out else run / "video" / "final" / "thumbnail.jpg"
    save(img, out, {"size": [W, H], "elements": elements,
                    "frame": {"scene": th["scene"], "scene_time": float(th["time"]), "video_time": round(t, 3)},
                    "panel": {"right": right, "fade": fade, "shade": alpha}})
    print(f"wrote {rel(out)} ({out.stat().st_size / 1e3:.0f} kB, frame at {t:.1f} s of the final video)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
