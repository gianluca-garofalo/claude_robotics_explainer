#!/usr/bin/env python3
"""The channel's video watermark: the RA monogram on its plate (templates/manim/brand.py) as a 150 x 150 PNG, to upload
once in YouTube Studio (Customization, Branding, Video watermark). badge() draws the same plate for thumbnail.py.

Usage:
  python3 tools/video/watermark.py [--out watermark.png] [--size 150]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import TEMPLATES, rel  # noqa: E402

SUPERSAMPLE = 4                      # drawn at this many times the size, then scaled down: smooth edges at 150 px


def badge(px: int):
    """The monogram on its plate, px x px, as a Pillow RGBA image, transparent outside the plate's rounded corners."""
    from PIL import Image
    sys.path.insert(0, str(TEMPLATES / "manim"))
    from manim import Camera
    import brand
    big = px * SUPERSAMPLE
    cam = Camera(pixel_width=big, pixel_height=big, frame_width=2.0, frame_height=2.0, background_opacity=0.0)
    mark = brand.monogram(1.0, plate=True)
    mark.scale(1.96 / mark.plate.width, scale_stroke=True)          # the plate's rim stays inside the square
    cam.capture_mobjects([mark])
    return cam.get_image().convert("RGBA").resize((px, px), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="watermark.png", help="the PNG to write (default: watermark.png here)")
    ap.add_argument("--size", type=int, default=150, help="pixels per side (YouTube Studio asks for 150)")
    a = ap.parse_args()
    if a.size < 16:
        print("error: --size must be at least 16", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    badge(a.size).save(out)
    print(f"wrote {rel(out)} ({a.size} x {a.size} px): upload it once in YouTube Studio, Customization, Branding, "
          "Video watermark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
