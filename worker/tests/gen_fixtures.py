"""Generate deterministic synthetic UI fixtures for pipeline tests.

Writes to <repo>/test/fixtures/. No randomness, so tests are stable.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 400, 700
OUT = Path(__file__).resolve().parents[2] / "test" / "fixtures"


def base(
    shift: int = 0,
    header=(40, 60, 120),
    card=(230, 230, 235),
    btn=(40, 120, 220),
    draw_button: bool = True,
    stride: int = 140,
) -> Image.Image:
    img = Image.new("RGB", (W, H), (250, 250, 252))
    d = ImageDraw.Draw(img)
    s = shift
    # header bar + logo
    d.rectangle([0, s, W, 80 + s], fill=header)
    d.rectangle([20, 30 + s, 160, 50 + s], fill=(255, 255, 255))
    # three content cards
    for i in range(3):
        y = 110 + i * stride + s
        d.rectangle([20, y, W - 20, y + 110], fill=card, outline=(200, 200, 205), width=2)
        d.rectangle([36, y + 16, 140, y + 30], fill=(180, 180, 185))
        d.rectangle([36, y + 44, W - 40, y + 56], fill=(210, 210, 215))
    # primary button
    if draw_button:
        d.rectangle([120, 600 + s, 280, 645 + s], fill=btn)
    return img


def text_screen(title_size: int = 30, body_size: int = 16, body_lines: int = 6) -> Image.Image:
    """A text-forward screen for the typography dimension (scalable default font)."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    title_font = ImageFont.load_default(size=title_size)
    body_font = ImageFont.load_default(size=body_size)
    d.text((24, 30), "Dashboard Overview", fill=(20, 20, 20), font=title_font)
    y = 30 + title_size + 24
    for i in range(body_lines):
        d.text((24, y), f"Metric {i + 1}: descriptive body text for this row.",
                fill=(60, 60, 60), font=body_font)
        y += body_size + 18
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    base().save(OUT / "reference.png")
    base().save(OUT / "identical.png")
    base(shift=12).save(OUT / "shifted.png")
    base(btn=(220, 60, 60), header=(120, 40, 60)).save(OUT / "recolored.png")
    base(draw_button=False).save(OUT / "missing_button.png")  # reference minus the CTA
    base(stride=95).save(OUT / "spacing_tight.png")  # same blocks, tighter vertical rhythm

    # Typography fixtures.
    text_screen().save(OUT / "text_ref.png")
    text_screen(title_size=20, body_size=11).save(OUT / "text_smaller.png")  # smaller type
    text_screen(body_lines=2).save(OUT / "text_less.png")  # less text

    # A structurally very different screen.
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([50, 50, 350, 350], fill=(30, 30, 30))
    d.rectangle([60, 500, 340, 560], fill=(0, 0, 0))
    img.save(OUT / "different.png")

    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
