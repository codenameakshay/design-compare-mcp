"""Deterministic synthetic screens as RGB arrays (for perturbation series)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 400, 700


def card_screen(
    header=(40, 60, 120),
    card=(230, 230, 235),
    btn=(40, 120, 220),
    stride: int = 140,
    n_cards: int = 3,
    draw_button: bool = True,
) -> np.ndarray:
    img = Image.new("RGB", (W, H), (250, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 80], fill=header)
    d.rectangle([20, 30, 160, 50], fill=(255, 255, 255))
    for i in range(n_cards):
        y = 110 + i * stride
        d.rectangle([20, y, W - 20, y + 110], fill=card, outline=(200, 200, 205), width=2)
        d.rectangle([36, y + 16, 140, y + 30], fill=(180, 180, 185))
        d.rectangle([36, y + 44, W - 40, y + 56], fill=(210, 210, 215))
    if draw_button:
        d.rectangle([120, 600, 280, 645], fill=btn)
    return np.asarray(img)


def text_screen(title_size: int = 30, body_size: int = 16, body_lines: int = 6) -> np.ndarray:
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    tf = ImageFont.load_default(size=title_size)
    bf = ImageFont.load_default(size=body_size)
    d.text((24, 30), "Dashboard Overview", fill=(20, 20, 20), font=tf)
    y = 30 + title_size + 24
    for i in range(body_lines):
        d.text((24, y), f"Metric {i + 1}: descriptive body text for this row.",
                fill=(60, 60, 60), font=bf)
        y += body_size + 18
    return np.asarray(img)
