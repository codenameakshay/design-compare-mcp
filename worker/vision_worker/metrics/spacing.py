"""Spacing dimension: outer margins + vertical rhythm between major blocks.

Reuses the content dimension's region detector, derives normalized layout
features (left/right/top/bottom margins and the mean inter-block vertical gap),
and compares them with a tolerance. Coarse by nature — most meaningful when the
two layouts are already broadly similar; it carries modest weight.
"""

from __future__ import annotations

import numpy as np

from .content import detect_regions

# Normalized-feature difference at which similarity hits zero (a 12%-of-dimension
# gap/margin difference is treated as a full miss).
TOL = 0.12
FEATURES = ("left", "right", "top", "bottom", "mean_gap")
# Spacing reads margins + rhythm from MAJOR blocks only; small inner detail would
# dilute the gap signal (the fine-grained detector catches text/icons too).
MAJOR_AREA_FRAC = 0.01


def _features(rgb: np.ndarray) -> dict | None:
    boxes = detect_regions(rgb, min_area_frac=MAJOR_AREA_FRAC)
    if not boxes:
        return None
    h, w = rgb.shape[:2]
    xs = [b[0] for b in boxes]
    xe = [b[0] + b[2] for b in boxes]
    ys = [b[1] for b in boxes]
    ye = [b[1] + b[3] for b in boxes]

    by_y = sorted(boxes, key=lambda b: b[1])
    gaps = [
        (nxt[1] - (cur[1] + cur[3])) / h
        for cur, nxt in zip(by_y, by_y[1:])
        if nxt[1] - (cur[1] + cur[3]) > 0
    ]
    return {
        "left": min(xs) / w,
        "right": (w - max(xe)) / w,
        "top": min(ys) / h,
        "bottom": (h - max(ye)) / h,
        "mean_gap": float(np.mean(gaps)) if gaps else 0.0,
    }


def spacing_score(
    ref_rgb: np.ndarray, cand_rgb: np.ndarray
) -> tuple[float | None, list[dict], dict]:
    rf = _features(ref_rgb)
    cf = _features(cand_rgb)
    if rf is None and cf is None:
        # Neither side has major blocks: not applicable — exclude from overall.
        return None, [], {"note": "no major regions to assess spacing"}
    if rf is None or cf is None:
        # One side has blocks and the other has none: a real spacing mismatch.
        return 0.0, [], {"note": "one image has no major regions"}

    sims = {k: max(0.0, 1.0 - abs(rf[k] - cf[k]) / TOL) for k in FEATURES}
    score = 100.0 * float(np.mean(list(sims.values())))

    findings: list[dict] = []
    worst = min(FEATURES, key=lambda k: sims[k])
    if sims[worst] < 0.6:
        label = {
            "left": "left margin",
            "right": "right margin",
            "top": "top margin",
            "bottom": "bottom margin",
            "mean_gap": "vertical gap between blocks",
        }[worst]
        findings.append(
            {
                "area": "spacing",
                "type": "spacing_mismatch",
                "severity": "medium" if sims[worst] < 0.3 else "low",
                "observed": (
                    f"{label} differs: reference ~{rf[worst] * 100:.1f}% vs "
                    f"candidate ~{cf[worst] * 100:.1f}% of the canvas"
                ),
                "suggested_fix": f"adjust the {label} toward the reference",
            }
        )

    measurements = {
        "ref": {k: round(rf[k], 4) for k in FEATURES},
        "cand": {k: round(cf[k], 4) for k in FEATURES},
        "sims": {k: round(sims[k], 3) for k in FEATURES},
    }
    return score, findings, measurements
