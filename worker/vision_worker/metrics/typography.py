"""Typography dimension: text amount + text scale (NOT font identity).

Font family/weight identity from raw pixels is unreliable, so this dimension
deliberately measures only what pixels support well: how much text there is and
how large it is. Text lines are detected with a morphological recipe (gradient →
Otsu → horizontal close → aspect/size filtering) — no OCR or ML model. Font
family/weight judgments are left to the host's vision model.

This is a coarse proxy and carries modest weight in the overall score.
"""

from __future__ import annotations

import cv2
import numpy as np


def _text_lines(rgb: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    grad = cv2.morphologyEx(
        gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Connect characters within a line, without bridging separate lines.
    kw = max(9, int(w * 0.02)) | 1  # odd, ~2% of width
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    connected = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)

    n, _, stats, _ = cv2.connectedComponentsWithStats(connected, connectivity=8)
    lines = []
    for i in range(1, n):
        x, y, bw_, bh, area = stats[i]
        if bh < 4:
            continue
        aspect = bw_ / max(1, bh)
        fill = area / max(1, bw_ * bh)
        if aspect >= 2.0 and bh <= 0.22 * h and bw_ >= 0.03 * w and 0.15 < fill < 0.98:
            lines.append((int(x), int(y), int(bw_), int(bh), int(area)))
    return lines


def _stats(lines: list, shape: tuple) -> dict:
    h, w = shape[:2]
    if not lines:
        return {"area_frac": 0.0, "median_h": 0.0, "count": 0}
    return {
        "area_frac": sum(b[4] for b in lines) / (h * w),
        "median_h": float(np.median([b[3] for b in lines])),
        "count": len(lines),
    }


def _ratio(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    return min(a, b) / max(a, b)


def typography_score(
    ref_rgb: np.ndarray, cand_rgb: np.ndarray
) -> tuple[float | None, list[dict], dict]:
    rs = _stats(_text_lines(ref_rgb), ref_rgb.shape)
    cs = _stats(_text_lines(cand_rgb), cand_rgb.shape)

    # No text on either side: nothing to compare — not applicable.
    if rs["count"] == 0 and cs["count"] == 0:
        return None, [], {"note": "no text detected in either image", "ref": rs, "cand": cs}

    area_sim = _ratio(rs["area_frac"], cs["area_frac"])
    height_sim = _ratio(rs["median_h"], cs["median_h"])
    score = 100.0 * (0.5 * area_sim + 0.5 * height_sim)

    findings: list[dict] = []
    if height_sim < 0.8 and rs["median_h"] and cs["median_h"]:
        rel = "larger" if cs["median_h"] > rs["median_h"] else "smaller"
        findings.append(
            {
                "area": "typography",
                "type": "text_scale",
                "severity": "medium" if height_sim < 0.6 else "low",
                "observed": (
                    f"candidate text scale looks {rel} (median line height "
                    f"~{cs['median_h']:.0f}px vs reference ~{rs['median_h']:.0f}px)"
                ),
                "suggested_fix": "adjust font sizes toward the reference",
            }
        )
    if area_sim < 0.8:
        rel = "more" if cs["area_frac"] > rs["area_frac"] else "less"
        findings.append(
            {
                "area": "typography",
                "type": "text_amount",
                "severity": "medium" if area_sim < 0.5 else "low",
                "observed": f"candidate shows {rel} text overall than the reference",
                "suggested_fix": "match the amount/density of text content",
            }
        )

    measurements = {
        "ref": {k: round(v, 4) if isinstance(v, float) else v for k, v in rs.items()},
        "cand": {k: round(v, 4) if isinstance(v, float) else v for k, v in cs.items()},
        "area_sim": round(area_sim, 3),
        "height_sim": round(height_sim, 3),
    }
    return score, findings, measurements
