"""Generate the placeholder podcast cover image.

Renders a 3000x3000 PNG suitable for Apple Podcasts (1400-3000 square).
The art is deliberately simple typography on the site's accent blue:
a circular "W" mark above the wordmark in serif italic.

Run from the repo root:

    source venv/bin/activate
    python pipeline/audio/generate_cover.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "site" / "img" / "podcast-cover.png"

SIZE = 3000
BG = (31, 111, 214)        # --accent
INK = (252, 252, 250)       # near-white --bg
INK_SOFT = (225, 237, 255)  # --accent-soft

CHARTER = "/System/Library/Fonts/Supplemental/Charter.ttc"
GEORGIA_ITALIC = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"


def main() -> None:
    img = Image.new("RGB", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)

    # Subtle border inset so the cover reads as framed.
    inset = 90
    draw.rectangle(
        [inset, inset, SIZE - inset, SIZE - inset],
        outline=INK_SOFT,
        width=4,
    )

    # Circular "W" mark, centered horizontally, sitting in the upper third.
    mark_radius = 380
    mark_cx = SIZE // 2
    mark_cy = int(SIZE * 0.34)
    draw.ellipse(
        [mark_cx - mark_radius, mark_cy - mark_radius,
         mark_cx + mark_radius, mark_cy + mark_radius],
        fill=INK,
    )
    w_font = ImageFont.truetype(GEORGIA_ITALIC, 540)
    bbox = draw.textbbox((0, 0), "W", font=w_font)
    draw.text(
        (mark_cx - (bbox[2] - bbox[0]) / 2 - bbox[0],
         mark_cy - (bbox[3] - bbox[1]) / 2 - bbox[1] - 8),
        "W",
        font=w_font,
        fill=BG,
    )

    # Wordmark.
    title_font = ImageFont.truetype(CHARTER, 290)
    title = "Weekly Thing"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text(
        ((SIZE - (bbox[2] - bbox[0])) / 2 - bbox[0], int(SIZE * 0.62)),
        title,
        font=title_font,
        fill=INK,
    )

    # Subtitle in mono uppercase.
    sub_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 78)
    sub = "AUDIO  ·  WEEKEND READING SINCE 2017"
    bbox = draw.textbbox((0, 0), sub, font=sub_font)
    draw.text(
        ((SIZE - (bbox[2] - bbox[0])) / 2 - bbox[0], int(SIZE * 0.74)),
        sub,
        font=sub_font,
        fill=INK_SOFT,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
