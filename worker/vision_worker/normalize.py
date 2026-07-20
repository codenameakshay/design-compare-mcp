"""Normalize a (reference, candidate) pair into a common comparison space.

Both images are resized to a canonical width (preserving each aspect ratio),
then the shorter is padded to the taller so downstream metrics operate on
equal-sized arrays. Any height/aspect divergence is reported so it can surface
as a finding rather than silently distorting the score.
"""

from __future__ import annotations

import cv2
import numpy as np

CANON_WIDTH = 768


def _resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    new_h = max(1, round(h * width / w))
    interp = cv2.INTER_AREA if width < w else cv2.INTER_CUBIC
    return cv2.resize(img, (width, new_h), interpolation=interp)


def normalize_pair(
    ref_rgb: np.ndarray, cand_rgb: np.ndarray, width: int = CANON_WIDTH
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (ref_norm, cand_norm, aspect_mismatch) at a shared canvas size."""
    r = _resize_to_width(ref_rgb, width)
    c = _resize_to_width(cand_rgb, width)

    hr, hc = r.shape[0], c.shape[0]
    aspect_mismatch = abs(hr - hc) / max(hr, hc)
    canvas_h = max(hr, hc)

    def pad_h(img: np.ndarray) -> np.ndarray:
        h = img.shape[0]
        if h == canvas_h:
            return img
        out = np.full((canvas_h, width, 3), 255, np.uint8)
        out[:h] = img
        return out

    return pad_h(r), pad_h(c), float(aspect_mismatch)
