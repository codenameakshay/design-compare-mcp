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
BG_DELTA = 12


def detect_regions(rgb: np.ndarray) -> list[Box]:
    """Segment an image into major content blocks (foreground vs background).

    Shared by the content and spacing dimensions.
    """
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Background = the most common gray value. Robust when a corner falls inside a
    # header/element (which poisons a corner-sampled estimate and floods the mask).
    bg = int(np.bincount(gray.reshape(-1), minlength=256).argmax())

    mask = (np.abs(gray.astype(int) - bg) > BG_DELTA).astype(np.uint8) * 255
    # Light close knits each element together without bridging neighboring blocks.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = MIN_AREA_FRAC * h * w
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

    # Content-presence measures reproduction of the reference's major blocks. If
    # the reference has none (e.g. a pure-text screen), the dimension is not
    # applicable — return None so it is excluded from the overall score.
    if not ref_boxes:
        viz = {"matched": [], "missing": [], "extra": [list(b[:4]) for b in cand_boxes]}
        return None, [], {"note": "no major regions detected in reference", "ref_regions": 0}, viz

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
