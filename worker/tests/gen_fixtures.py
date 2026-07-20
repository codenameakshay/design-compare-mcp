"""Generate deterministic synthetic UI fixtures for pipeline tests.

Writes to <repo>/test/fixtures/. No randomness, so tests are stable.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 400, 700
OUT = Path(__file__).resolve().parents[2] / "test" / "fixtures"


def base(
    shift: int = 0,
    header=(40, 60, 120),
    card=(230, 230, 235),
    btn=(40, 120, 220),
    draw_button: bool = True,
) -> Image.Image:
    img = Image.new("RGB", (W, H), (250, 250, 252))
    d = ImageDraw.Draw(img)
    s = shift
    # header bar + logo
    d.rectangle([0, s, W, 80 + s], fill=header)
    d.rectangle([20, 30 + s, 160, 50 + s], fill=(255, 255, 255))
    # three content cards
    for i in range(3):
        y = 110 + i * 140 + s
        d.rectangle([20, y, W - 20, y + 110], fill=card, outline=(200, 200, 205), width=2)
        d.rectangle([36, y + 16, 140, y + 30], fill=(180, 180, 185))
        d.rectangle([36, y + 44, W - 40, y + 56], fill=(210, 210, 215))
    # primary button
    if draw_button:
        d.rectangle([120, 600 + s, 280, 645 + s], fill=btn)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    base().save(OUT / "reference.png")
    base().save(OUT / "identical.png")
    base(shift=12).save(OUT / "shifted.png")
    base(btn=(220, 60, 60), header=(120, 40, 60)).save(OUT / "recolored.png")
    base(draw_button=False).save(OUT / "missing_button.png")  # reference minus the CTA

    # A structurally very different screen.
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([50, 50, 350, 350], fill=(30, 30, 30))
    d.rectangle([60, 500, 340, 560], fill=(0, 0, 0))
    img.save(OUT / "different.png")

    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
