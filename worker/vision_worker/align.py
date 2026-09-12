"""Register the candidate onto the reference.

Screen mode uses ECC translation. Widget mode is identity (a tight crop is
assumed to already be aligned). ECC that fails, correlates poorly, translates
too far, or *worsens* SSIM versus identity falls back to identity so a bad
registration never crashes the comparison.
"""

from __future__ import annotations

import cv2
import numpy as np

from .metrics.structure import structure_score


def estimate_alignment(
    ref_gray: np.ndarray, cand_gray: np.ndarray, mode: str
) -> tuple[np.ndarray | None, dict]:
    """Return (warp_2x3 or None, diagnostics). `fallback` is always present."""
    if mode == "widget":
        return None, {
            "method": "identity",
            "fallback": True,
            "note": "widget mode assumes a pre-aligned crop",
        }

    h, w = ref_gray.shape[:2]
    limit = 0.25 * min(h, w)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)

    def _identity(note: str, **extra) -> tuple[None, dict]:
        diag = {"method": "identity", "fallback": True, "note": note}
        diag.update(extra)
        return None, diag

    try:
        cc, warp = cv2.findTransformECC(
            ref_gray, cand_gray, warp, cv2.MOTION_TRANSLATION, criteria, None, 5
        )
    except Exception as exc:
        return _identity(
            f"ECC did not converge; fell back to identity ({exc.__class__.__name__})"
        )

    cc_f = float(cc)
    dx = float(warp[0, 2])
    dy = float(warp[1, 2])
    extra = {"cc": round(cc_f, 4), "dx": round(dx, 2), "dy": round(dy, 2)}

    if cc_f < 0.3:
        return _identity(f"ECC correlation {cc_f:.3f} below 0.3", **extra)
    if abs(dx) > limit or abs(dy) > limit:
        return _identity(
            f"ECC translation too large (dx={dx:.1f}, dy={dy:.1f})", **extra
        )

    try:
        warped = apply_warp(cand_gray, warp, (h, w))
        ssim_warp, _ = structure_score(ref_gray, warped)
        ssim_id, _ = structure_score(ref_gray, cand_gray)
        if ssim_warp < ssim_id:
            return _identity("ECC warp reduced SSIM vs identity", **extra)
    except Exception as exc:
        return _identity(
            f"ECC warp SSIM check failed ({exc.__class__.__name__})", **extra
        )

    return warp, {
        "method": "ecc_translation",
        "fallback": False,
        "cc": round(cc_f, 4),
        "dx": round(dx, 2),
        "dy": round(dy, 2),
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
