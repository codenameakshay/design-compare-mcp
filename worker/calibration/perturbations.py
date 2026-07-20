"""Controlled single-dimension perturbation series.

Each generator returns (reference_rgb, [(level, candidate_rgb), ...]) where the
candidate diverges from the reference along exactly one dimension by an
increasing amount. The monotonicity test asserts the corresponding sub-score
decreases as `level` increases.
"""

from __future__ import annotations

import cv2
import numpy as np

from .synthetic import card_screen, text_screen

REF_HEADER = (40, 60, 120)
REF_BTN = (40, 120, 220)


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def color_series(n: int = 6):
    """Progressively recolor header+button away from the reference palette."""
    ref = card_screen()
    tgt_header, tgt_btn = (140, 40, 60), (220, 60, 60)
    series = []
    for i in range(n):
        t = i / (n - 1)
        cand = card_screen(header=_lerp(REF_HEADER, tgt_header, t), btn=_lerp(REF_BTN, tgt_btn, t))
        series.append((float(t), cand))
    return ref, series


def content_series():
    """Progressively remove elements (button, then cards)."""
    ref = card_screen(n_cards=3, draw_button=True)
    variants = [
        (0.0, card_screen(n_cards=3, draw_button=True)),
        (1.0, card_screen(n_cards=3, draw_button=False)),
        (2.0, card_screen(n_cards=2, draw_button=False)),
        (3.0, card_screen(n_cards=1, draw_button=False)),
    ]
    return ref, variants


def layout_series(n: int = 6):
    """Progressive Gaussian blur degrades structural similarity."""
    ref = card_screen()
    series = []
    for i in range(n):
        sigma = i * 1.6
        cand = ref if sigma == 0 else cv2.GaussianBlur(ref, (0, 0), sigmaX=sigma)
        series.append((float(sigma), cand))
    return ref, series


def typography_series(n: int = 6):
    """Progressively shrink body text size."""
    ref = text_screen(body_size=18)
    series = []
    for i in range(n):
        size = 18 - i * 2  # 18, 16, ... 8
        series.append((float(18 - size), text_screen(body_size=size)))
    return ref, series


def spacing_series(n: int = 6):
    """Progressively tighten the vertical rhythm between cards."""
    ref = card_screen(stride=140)
    series = []
    for i in range(n):
        stride = 140 - i * 14  # 140 down to ~70
        series.append((float(140 - stride), card_screen(stride=stride)))
    return ref, series
