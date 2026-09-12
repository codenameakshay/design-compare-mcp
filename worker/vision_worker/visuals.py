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


def hatch_ignore(preview: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    """Overlay a hatch on ignored pixels of a preview canvas. Preview is unchanged
    where the mask is false / empty."""
    out = preview.copy()
    arr = getattr(mask, "mask", mask)
    if arr is None or not np.any(arr):
        return out
    h, w = arr.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    hatch = ((xx + yy) % 8 == 0) | ((xx - yy) % 8 == 0)
    apply = arr.astype(bool) & hatch
    out[apply] = (220, 64, 64)
    return out


def side_by_side(ref_rgb: np.ndarray, cand_rgb: np.ndarray) -> str:
    gap = np.full((ref_rgb.shape[0], 8, 3), 200, np.uint8)
    combo = np.hstack([ref_rgb, gap, cand_rgb])
    return _png_b64(_rgb_to_bgr(combo))


def diff_heatmap(ssim_map: np.ndarray) -> str:
    d = np.clip(1.0 - ssim_map, 0.0, 2.0) / 2.0
    d8 = (np.clip(d, 0.0, 1.0) * 255).astype(np.uint8)
    return _png_b64(cv2.applyColorMap(d8, cv2.COLORMAP_INFERNO))


def overlay(ref_rgb: np.ndarray, cand_rgb: np.ndarray, alpha: float = 0.5) -> str:
    blend = cv2.addWeighted(ref_rgb, alpha, cand_rgb, 1.0 - alpha, 0.0)
    return _png_b64(_rgb_to_bgr(blend))


def motion_signature(ref_sig: list, cand_sig: list, w: int = 520, h: int = 200) -> str:
    """Line chart of the two motion signatures over time (reference vs candidate)."""
    canvas = np.full((h, w, 3), 28, np.uint8)
    pad = 14
    peak = max(max(ref_sig, default=0.0), max(cand_sig, default=0.0), 1e-6)

    def draw(sig, color):
        n = len(sig)
        if n == 0:
            return
        if n == 1:
            x = pad + (w - 2 * pad) // 2
            y = (h - pad) - int(min(sig[0] / peak, 1.0) * (h - 2 * pad))
            cv2.line(canvas, (x, h - pad), (x, y), color, 2, cv2.LINE_AA)
            cv2.circle(canvas, (x, y), 4, color, -1, cv2.LINE_AA)
            return
        pts = []
        for i, v in enumerate(sig):
            x = pad + int(i / (n - 1) * (w - 2 * pad))
            y = (h - pad) - int(min(v / peak, 1.0) * (h - 2 * pad))
            pts.append([x, y])
        cv2.polylines(canvas, [np.array(pts, np.int32)], False, color, 2, cv2.LINE_AA)

    draw(ref_sig, (120, 210, 120))
    draw(cand_sig, (235, 150, 60))
    cv2.putText(canvas, "ref", (w - 90, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 210, 120), 1, cv2.LINE_AA)
    cv2.putText(canvas, "cand", (w - 50, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 150, 60), 1, cv2.LINE_AA)
    return _png_b64(canvas)


def content_regions(ref_rgb: np.ndarray, viz: dict, cand_rgb: np.ndarray | None = None) -> str:
    """Draw content regions. Matched/missing on the reference; extras on the
    candidate (two-pane when extras exist) — never as if extras live on the
    reference alone."""
    ref_canvas = _rgb_to_bgr(ref_rgb).copy()
    for kind, color in (("matched", (0, 180, 0)), ("missing", (0, 0, 230))):
        for (x, y, bw, bh) in viz.get(kind, []):
            cv2.rectangle(ref_canvas, (x, y), (x + bw, y + bh), color, 2)

    extras = viz.get("extra") or []
    if extras:
        src = cand_rgb if cand_rgb is not None else ref_rgb
        cand_canvas = _rgb_to_bgr(src).copy()
        for (x, y, bw, bh) in extras:
            cv2.rectangle(cand_canvas, (x, y), (x + bw, y + bh), (0, 140, 255), 2)
        h = max(ref_canvas.shape[0], cand_canvas.shape[0])
        if ref_canvas.shape[0] != h:
            pad = np.full((h - ref_canvas.shape[0], ref_canvas.shape[1], 3), 200, np.uint8)
            ref_canvas = np.vstack([ref_canvas, pad])
        if cand_canvas.shape[0] != h:
            pad = np.full((h - cand_canvas.shape[0], cand_canvas.shape[1], 3), 200, np.uint8)
            cand_canvas = np.vstack([cand_canvas, pad])
        gap = np.full((h, 8, 3), 200, np.uint8)
        combo = np.hstack([ref_canvas, gap, cand_canvas])
        return _png_b64(combo)
    return _png_b64(ref_canvas)
