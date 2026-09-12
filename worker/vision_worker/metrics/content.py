"""Content-presence dimension: are the reference's regions present in the candidate?

Segment each image into major content blocks (foreground vs background), match
reference regions to candidate regions by IoU, and report unmatched reference
regions as *missing* and unmatched candidate regions as *extra*. Naturally
monotonic: adding a missing element raises coverage and thus the score.

This is a coarse pixel-level heuristic (no DOM), so it is most reliable on
clean, high-contrast layouts and noisier on dense photographic UIs.
"""

from __future__ import annotations

import cv2
import numpy as np

Box = tuple[int, int, int, int, int]  # x, y, w, h, area
IOU_MATCH = 0.30
MIN_AREA_FRAC = 0.003
# Adaptive brightness-delta band. Otsu picks the split per image; we floor it so a
# flat image's noise isn't caught, and cap it so faint low-contrast dark-UI
# elements (card fill only a few gray levels off the background) still register.
BG_DELTA_FLOOR = 5
BG_DELTA_CAP = 45
# Gradient mask threshold, as a fraction of the image's own max gradient — scale-
# free, so bordered/text elements are found on both high- and low-contrast UIs.
GRAD_FRAC = 0.12


def detect_regions(rgb: np.ndarray, min_area_frac: float = MIN_AREA_FRAC) -> list[Box]:
    """Segment an image into content blocks (foreground vs background).

    Contrast-adaptive: a brightness mask (Otsu-thresholded delta from the modal
    background) is unioned with a gradient/edge mask, so elements register whether
    they differ in brightness (high-contrast UIs) or only carry borders/text
    (low-contrast dark UIs, where a fixed brightness threshold sees nothing).

    `min_area_frac` sets the smallest block kept: content uses the default (fine,
    catches small elements); spacing passes a larger value to keep only major
    blocks so inner text/detail doesn't dilute the margin/rhythm features.
    """
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Background = the most common gray value. Robust when a corner falls inside a
    # header/element (which poisons a corner-sampled estimate and floods the mask).
    bg = int(np.bincount(gray.reshape(-1), minlength=256).argmax())

    delta = np.abs(gray.astype(np.int16) - bg).astype(np.uint8)
    otsu_t, _ = cv2.threshold(delta, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    thr = min(max(int(otsu_t), BG_DELTA_FLOOR), BG_DELTA_CAP)
    bright = (delta > thr).astype(np.uint8) * 255

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    gmax = float(grad.max()) or 1.0
    edges = (grad > GRAD_FRAC * gmax).astype(np.uint8) * 255

    mask = cv2.bitwise_or(bright, edges)
    # Close fills element interiors (bordered cards -> solid blocks) and knits text
    # into lines, without bridging the gaps between separate blocks.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = min_area_frac * h * w
    boxes: list[Box] = []
    for i in range(1, n):  # 0 is background
        x, y, bw, bh, area = stats[i]
        if area >= min_area:
            boxes.append((int(x), int(y), int(bw), int(bh), int(area)))
    return boxes


def _iou(a: Box, b: Box) -> float:
    ax, ay, aw, ah, _ = a
    bx, by, bw, bh, _ = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def content_score(
    ref_rgb: np.ndarray, cand_rgb: np.ndarray
) -> tuple[float | None, list[dict], dict, dict]:
    ref_boxes = detect_regions(ref_rgb)
    cand_boxes = detect_regions(cand_rgb)

    if not ref_boxes:
        extra = cand_boxes
        viz = {"matched": [], "missing": [], "extra": [list(b[:4]) for b in extra]}
        meas = {
            "note": "no major regions detected in reference",
            "coverage": 0.0,
            "extra_ratio": 1.0 if extra else 0.0,
            "ref_regions": 0,
            "cand_regions": len(extra),
            "missing": 0,
            "extra": len(extra),
        }
        if not extra:
            return None, [], meas, viz
        extra_ratio = 1.0
        score = 100.0 * 0.0 * (1.0 - 0.5 * min(1.0, extra_ratio))
        findings = []
        total_cand_area = sum(b[4] for b in extra) or 1
        for b in sorted(extra, key=lambda x: -x[4])[:4]:
            findings.append(
                {
                    "area": "content",
                    "type": "extra_region",
                    "severity": "low",
                    "box": [b[0], b[1], b[2], b[3]],
                    "observed": f"an extra region at x={b[0]},y={b[1]} ({b[2]}x{b[3]}) is not in the reference",
                    "suggested_fix": "remove or relocate this element",
                }
            )
        meas["extra_ratio"] = round(sum(b[4] for b in extra) / total_cand_area, 3)
        return score, findings, meas, viz

    total_ref_area = sum(b[4] for b in ref_boxes) or 1
    total_cand_area = sum(b[4] for b in cand_boxes) or 1

    used: set[int] = set()
    matched: list[Box] = []
    missing: list[Box] = []
    matched_ref_area = 0

    for rb in ref_boxes:
        best_iou, best_k = 0.0, -1
        for k, cb in enumerate(cand_boxes):
            if k in used:
                continue
            iou = _iou(rb, cb)
            if iou > best_iou:
                best_iou, best_k = iou, k
        if best_iou >= IOU_MATCH:
            used.add(best_k)
            matched.append(rb)
            matched_ref_area += rb[4]
        else:
            missing.append(rb)

    extra = [cb for k, cb in enumerate(cand_boxes) if k not in used]

    coverage = matched_ref_area / total_ref_area
    extra_ratio = sum(b[4] for b in extra) / total_cand_area
    score = 100.0 * coverage * (1.0 - 0.5 * min(1.0, extra_ratio))

    findings: list[dict] = []
    for b in sorted(missing, key=lambda x: -x[4])[:4]:
        findings.append(
            {
                "area": "content",
                "type": "missing_region",
                "severity": "high" if b[4] > 0.05 * total_ref_area else "medium",
                "box": [b[0], b[1], b[2], b[3]],
                "observed": f"a reference region at x={b[0]},y={b[1]} ({b[2]}x{b[3]}) is absent",
                "suggested_fix": "add the missing element at this position",
            }
        )
    for b in sorted(extra, key=lambda x: -x[4])[:4]:
        findings.append(
            {
                "area": "content",
                "type": "extra_region",
                "severity": "low",
                "box": [b[0], b[1], b[2], b[3]],
                "observed": f"an extra region at x={b[0]},y={b[1]} ({b[2]}x{b[3]}) is not in the reference",
                "suggested_fix": "remove or relocate this element",
            }
        )

    measurements = {
        "coverage": round(coverage, 3),
        "extra_ratio": round(extra_ratio, 3),
        "ref_regions": len(ref_boxes),
        "cand_regions": len(cand_boxes),
        "missing": len(missing),
        "extra": len(extra),
    }
    viz = {
        "matched": [list(b[:4]) for b in matched],
        "missing": [list(b[:4]) for b in missing],
        "extra": [list(b[:4]) for b in extra],
    }
    return score, findings, measurements, viz
