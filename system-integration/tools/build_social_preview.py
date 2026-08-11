#!/usr/bin/env python3
"""Build a deterministic 1280x640 GitHub social-preview image."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 640
FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def fit_font(draw: ImageDraw.ImageDraw, text: str, maximum: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 24:
        candidate = font("segoeuib.ttf", size)
        if draw.textbbox((0, 0), text, font=candidate)[2] <= maximum:
            return candidate
        size -= 1
    return font("segoeuib.ttf", size)


def cover(source: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / source.width, height / source.height)
    resized = source.resize(
        (round(source.width * scale), round(source.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def build_evidence_card(args: argparse.Namespace, source: Image.Image) -> Image.Image:
    image_height = 430
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#0f172a")
    canvas.paste(cover(source, WIDTH, image_height), (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, image_height, WIDTH, image_height + 8), fill=args.accent)
    title_font = fit_font(draw, args.title, WIDTH - 96, 48)
    draw.text((48, 466), args.title, fill="white", font=title_font)
    draw.text((50, 548), args.subtitle, fill="#cbd5e1", font=font("segoeui.ttf", 24))
    return canvas


def build_title_card(args: argparse.Namespace, source: Image.Image) -> Image.Image:
    canvas = cover(source, WIDTH, HEIGHT)
    draw = ImageDraw.Draw(canvas)
    draw.text((44, 598), args.subtitle, fill=args.accent, font=font("segoeuib.ttf", 20))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--accent", default="#3b82f6")
    parser.add_argument("--layout", choices=("evidence", "title"), default="evidence")
    parser.add_argument("--crop-top-fraction", type=float, default=1.0)
    args = parser.parse_args()

    source = Image.open(args.input).convert("RGB")
    if not 0.0 < args.crop_top_fraction <= 1.0:
        parser.error("--crop-top-fraction must be greater than 0 and at most 1")
    if args.crop_top_fraction < 1.0:
        source = source.crop((0, 0, source.width, round(source.height * args.crop_top_fraction)))
    result = build_title_card(args, source) if args.layout == "title" else build_evidence_card(args, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, format="JPEG", quality=88, optimize=True, progressive=True)
    print(f"Saved {args.output} ({args.output.stat().st_size / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
