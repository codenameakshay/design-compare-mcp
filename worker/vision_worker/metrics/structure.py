"""Structural similarity (SSIM) — the Phase 1 layout signal."""

from __future__ import annotations

import numpy as np
from skimage.metrics import structural_similarity


def structure_score(ref_gray: np.ndarray, cand_gray: np.ndarray) -> tuple[float, np.ndarray]:
    """Return (score_0_100, ssim_map).

    ssim_map values are in [-1, 1] with 1 == identical; used for the diff heatmap.
    """
    score, ssim_map = structural_similarity(
        ref_gray, cand_gray, full=True, data_range=255
    )
    clamped = float(max(0.0, min(1.0, score)))
    return clamped * 100.0, ssim_map
