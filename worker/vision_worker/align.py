"""Register the candidate onto the reference.

Phase 1 uses ECC translation for `screen` mode (cheap, robust to small offsets)
and identity for `widget` mode (a tight crop is assumed to already be aligned).
Any ECC failure falls back to identity so a bad registration never crashes the
comparison — it just degrades to unaligned scoring, which is flagged in diags.
"""

from __future__ import annotations

import cv2
import numpy as np


def estimate_alignment(
    ref_gray: np.ndarray, cand_gray: np.ndarray, mode: str
) -> tuple[np.ndarray | None, dict]:
    """Return (warp_2x3 or None, diagnostics)."""
    if mode == "widget":
        return None, {"method": "identity", "note": "widget mode assumes a pre-aligned crop"}

    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    try:
        cc, warp = cv2.findTransformECC(
            ref_gray, cand_gray, warp, cv2.MOTION_TRANSLATION, criteria, None, 5
        )
    except cv2.error as exc:  # pragma: no cover - depends on image content
        return None, {
            "method": "identity",
            "note": f"ECC did not converge; fell back to identity ({exc.__class__.__name__})",
        }

    return warp, {
        "method": "ecc_translation",
        "cc": round(float(cc), 4),
        "dx": round(float(warp[0, 2]), 2),
        "dy": round(float(warp[1, 2]), 2),
    }


def apply_warp(img: np.ndarray, warp: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    h, w = shape_hw
    return cv2.warpAffine(
        img,
        warp,
        (w, h),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
