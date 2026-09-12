"""Normalize a (reference, candidate) pair into a common comparison space.

Both images are resized to a canonical width (preserving each aspect ratio),
then the shorter is padded at the bottom so downstream metrics operate on
equal-sized arrays. Pad color is the modal color of a thin edge strip after
resize — never a hardcoded white. Ignore boxes are rasterized in original
reference pixels onto the shared canvas; ignored pixels are filled on the
metric canvases only.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

CANON_WIDTH = 768


@dataclass
class RgbCanvas:
    rgb: np.ndarray
    preview_rgb: np.ndarray
    pad_color: tuple[int, int, int]
    orig_w: int
    orig_h: int
    scale: float

    @property
    def gray(self) -> np.ndarray:
        return cv2.cvtColor(self.rgb, cv2.COLOR_RGB2GRAY)


@dataclass
class IgnoreMask:
    mask: np.ndarray


@dataclass
class CanonicalPair:
    ref: RgbCanvas
    cand: RgbCanvas
    ignore: IgnoreMask
    aspect_mismatch: float
    mapping: dict


def _resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    new_h = max(1, round(h * width / w))
    interp = cv2.INTER_AREA if width < w else cv2.INTER_CUBIC
    return cv2.resize(img, (width, new_h), interpolation=interp)


def _modal_rgb(pixels: np.ndarray) -> tuple[int, int, int]:
    packed = (
        pixels[:, 0].astype(np.uint32) << 16
        | pixels[:, 1].astype(np.uint32) << 8
        | pixels[:, 2].astype(np.uint32)
    )
    vals, counts = np.unique(packed, return_counts=True)
    mode = int(vals[int(counts.argmax())])
    return ((mode >> 16) & 255, (mode >> 8) & 255, mode & 255)


def _pad_color(img: np.ndarray) -> tuple[int, int, int]:
    h, w = img.shape[:2]
    t = 2 if min(h, w) >= 4 else 1
    strip = np.concatenate(
        [
            img[:t].reshape(-1, 3),
            img[-t:].reshape(-1, 3),
            img[:, :t].reshape(-1, 3),
            img[:, -t:].reshape(-1, 3),
        ],
        axis=0,
    )
    return _modal_rgb(strip)


def _pad_bottom(
    img: np.ndarray, canvas_h: int, width: int, pad_color: tuple[int, int, int]
) -> np.ndarray:
    h = img.shape[0]
    if h == canvas_h:
        return img
    out = np.empty((canvas_h, width, 3), np.uint8)
    out[:h] = img
    out[h:] = pad_color
    return out


def _rasterize_ignore(
    boxes, scale: float, canvas_h: int, canvas_w: int
) -> np.ndarray:
    mask = np.zeros((canvas_h, canvas_w), dtype=bool)
    if not boxes:
        return mask
    for box in boxes:
        x, y, bw, bh = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        x0 = int(round(x * scale))
        y0 = int(round(y * scale))
        x1 = int(round((x + bw) * scale))
        y1 = int(round((y + bh) * scale))
        x0, x1 = max(0, min(canvas_w, x0)), max(0, min(canvas_w, x1))
        y0, y1 = max(0, min(canvas_h, y0)), max(0, min(canvas_h, y1))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return mask


def normalize_pair(
    ref_rgb: np.ndarray,
    cand_rgb: np.ndarray,
    ignore_boxes=None,
    width: int = CANON_WIDTH,
) -> CanonicalPair:
    orig_rh, orig_rw = int(ref_rgb.shape[0]), int(ref_rgb.shape[1])
    orig_ch, orig_cw = int(cand_rgb.shape[0]), int(cand_rgb.shape[1])
    scale_r = width / orig_rw
    scale_c = width / orig_cw

    r = _resize_to_width(ref_rgb, width)
    c = _resize_to_width(cand_rgb, width)
    pad_r = _pad_color(r)
    pad_c = _pad_color(c)

    hr, hc = r.shape[0], c.shape[0]
    aspect_mismatch = abs(hr - hc) / max(hr, hc)
    canvas_h = max(hr, hc)

    preview_r = _pad_bottom(r, canvas_h, width, pad_r)
    preview_c = _pad_bottom(c, canvas_h, width, pad_c)

    ignore_mask = _rasterize_ignore(ignore_boxes, scale_r, canvas_h, width)
    metric_r = preview_r.copy()
    metric_c = preview_c.copy()
    if ignore_mask.any():
        metric_r[ignore_mask] = pad_r
        metric_c[ignore_mask] = pad_c

    mapping = {
        "width": int(width),
        "height": int(canvas_h),
        "ignore_input_space": "reference_original_pixels",
        "ignore_space": "canonical_768",
        "reference": {"orig_w": orig_rw, "orig_h": orig_rh, "scale": float(scale_r)},
        "candidate": {"orig_w": orig_cw, "orig_h": orig_ch, "scale": float(scale_c)},
    }
    return CanonicalPair(
        ref=RgbCanvas(
            rgb=metric_r,
            preview_rgb=preview_r,
            pad_color=pad_r,
            orig_w=orig_rw,
            orig_h=orig_rh,
            scale=float(scale_r),
        ),
        cand=RgbCanvas(
            rgb=metric_c,
            preview_rgb=preview_c,
            pad_color=pad_c,
            orig_w=orig_cw,
            orig_h=orig_ch,
            scale=float(scale_c),
        ),
        ignore=IgnoreMask(mask=ignore_mask),
        aspect_mismatch=float(aspect_mismatch),
        mapping=mapping,
    )
