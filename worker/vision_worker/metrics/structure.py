"""Structural similarity (SSIM) — the layout signal."""

from __future__ import annotations

import numpy as np
from skimage.metrics import structural_similarity


def structure_score(ref_gray: np.ndarray, cand_gray: np.ndarray) -> tuple[float, np.ndarray]:
    """Return (score_0_100, ssim_map).

    ssim_map values are in [-1, 1] with 1 == identical; used for the diff heatmap.
    """
    h, w = ref_gray.shape[:2]
    # SSIM requires an odd window no larger than the smallest side. Clamp so thin/
    # tiny canvases don't raise; below 3px there is no meaningful structure to score.
    m = min(7, h, w)
    win = m if m % 2 == 1 else m - 1
    if win < 3:
        raise ValueError(f"image too small for SSIM ({h}x{w})")
    score, ssim_map = structural_similarity(
        ref_gray, cand_gray, full=True, data_range=255, win_size=win
    )
    clamped = float(max(0.0, min(1.0, score)))
    return clamped * 100.0, ssim_map
