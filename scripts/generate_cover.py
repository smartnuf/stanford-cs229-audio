#!/usr/bin/env python3
"""Generate the 3000 px public cover without third-party branding."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 3000


def font(name: str, size: int, override: str | None) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(override or name, size=size)


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, face: ImageFont.FreeTypeFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=face)
    width = box[2] - box[0]
    draw.text(((SIZE - width) / 2, y), text, font=face, fill=fill)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font", help="optional path to a TrueType font")
    args = parser.parse_args()

    image = Image.new("RGB", (SIZE, SIZE), "#071B2A")
    draw = ImageDraw.Draw(image)
    # A restrained waveform/network motif; it is decorative rather than a logo.
    points = [(180, 2310), (560, 2020), (940, 2210), (1320, 1910), (1700, 2170), (2080, 1880), (2460, 2110), (2790, 1940)]
    draw.line(points, fill="#45D6C1", width=42, joint="curve")
    for x, y in points:
        draw.ellipse((x - 38, y - 38, x + 38, y + 38), fill="#F4C15D")
    draw.rounded_rectangle((150, 150, 2850, 2850), radius=80, outline="#2B5368", width=12)

    centered(draw, "CS229", 400, font("DejaVuSans-Bold.ttf", 500, args.font), "#F7FAFC")
    centered(draw, "MACHINE LEARNING", 1030, font("DejaVuSans-Bold.ttf", 185, args.font), "#45D6C1")
    centered(draw, "UNOFFICIAL", 1370, font("DejaVuSans-Bold.ttf", 190, args.font), "#F7FAFC")
    centered(draw, "AUDIO PRESERVATION EDITION", 1600, font("DejaVuSans.ttf", 96, args.font), "#AFC7D2")
    centered(draw, "INDEPENDENT • NON-COMMERCIAL", 2580, font("DejaVuSans.ttf", 66, args.font), "#AFC7D2")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="JPEG", quality=92, optimize=True, progressive=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
