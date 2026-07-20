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


def motion_signature(ref_sig: list, cand_sig: list, w: int = 520, h: int = 200) -> str:
    """Line chart of the two motion signatures over time (reference vs candidate)."""
    canvas = np.full((h, w, 3), 28, np.uint8)  # dark ground
    pad = 14
    peak = max(max(ref_sig, default=0.0), max(cand_sig, default=0.0), 1e-6)

    def draw(sig, color):
        n = len(sig)
        if n < 2:
            return
        pts = []
        for i, v in enumerate(sig):
            x = pad + int(i / (n - 1) * (w - 2 * pad))
            y = (h - pad) - int(min(v / peak, 1.0) * (h - 2 * pad))
            pts.append([x, y])
        cv2.polylines(canvas, [np.array(pts, np.int32)], False, color, 2, cv2.LINE_AA)

    draw(ref_sig, (120, 210, 120))  # reference — green (BGR)
    draw(cand_sig, (235, 150, 60))  # candidate — blue (BGR)
    cv2.putText(canvas, "ref", (w - 90, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 210, 120), 1, cv2.LINE_AA)
    cv2.putText(canvas, "cand", (w - 50, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 150, 60), 1, cv2.LINE_AA)
    return _png_b64(canvas)


def content_regions(ref_rgb: np.ndarray, viz: dict) -> str:
    """Draw content regions on the reference: matched=green, missing=red, extra=orange."""
    canvas = _rgb_to_bgr(ref_rgb).copy()
    colors = {"matched": (0, 180, 0), "missing": (0, 0, 230), "extra": (0, 140, 255)}
    for kind, color in colors.items():
        for (x, y, w, h) in viz.get(kind, []):
            cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
    return _png_b64(canvas)
