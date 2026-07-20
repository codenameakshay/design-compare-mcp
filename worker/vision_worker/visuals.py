"""Diagnostic images returned to the host so its vision model can *see* the diff."""

from __future__ import annotations

import base64

import cv2
import numpy as np


def _png_b64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _rgb_to_bgr(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def side_by_side(ref_rgb: np.ndarray, cand_rgb: np.ndarray) -> str:
    gap = np.full((ref_rgb.shape[0], 8, 3), 200, np.uint8)
    combo = np.hstack([ref_rgb, gap, cand_rgb])
    return _png_b64(_rgb_to_bgr(combo))


def diff_heatmap(ssim_map: np.ndarray) -> str:
    # ssim_map: 1 == identical. Map divergence to [0,1] and colorize (hot = different).
    d = np.clip(1.0 - ssim_map, 0.0, 2.0) / 2.0
    d8 = (np.clip(d, 0.0, 1.0) * 255).astype(np.uint8)
    return _png_b64(cv2.applyColorMap(d8, cv2.COLORMAP_INFERNO))


def overlay(ref_rgb: np.ndarray, cand_rgb: np.ndarray, alpha: float = 0.5) -> str:
    blend = cv2.addWeighted(ref_rgb, alpha, cand_rgb, 1.0 - alpha, 0.0)
    return _png_b64(_rgb_to_bgr(blend))


def content_regions(ref_rgb: np.ndarray, viz: dict) -> str:
    """Draw content regions on the reference: matched=green, missing=red, extra=orange."""
    canvas = _rgb_to_bgr(ref_rgb).copy()
    colors = {"matched": (0, 180, 0), "missing": (0, 0, 230), "extra": (0, 140, 255)}
    for kind, color in colors.items():
        for (x, y, w, h) in viz.get(kind, []):
            cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
    return _png_b64(canvas)
