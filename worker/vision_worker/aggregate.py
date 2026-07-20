"""Combine per-dimension sub-scores into an overall score.

Weighted **geometric mean** over the scored dimensions (pending dimensions are
skipped and the remaining weights renormalized). The geometric mean makes a weak
dimension drag the whole score down far more than an arithmetic mean would, so no
single dimension can be farmed to mask the others. Scores are floored at FLOOR so
one zeroed dimension pulls hard toward — but not exactly to — zero.
"""

from __future__ import annotations

import math

DEFAULT_WEIGHTS = {
    "layout": 0.35,
    "color": 0.20,
    "content": 0.15,
    "typography": 0.15,
    "spacing": 0.15,
}
FLOOR = 1.0


def aggregate(subscores: dict, weights: dict | None = None) -> float:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})

    scored = {
        k: v["score"]
        for k, v in subscores.items()
        if v.get("score") is not None and k in w
    }
    if not scored:
        return 0.0

    total_w = sum(w[k] for k in scored) or 1.0
    acc = 0.0
    for k, s in scored.items():
        clamped = max(FLOOR, min(100.0, float(s)))
        acc += (w[k] / total_w) * math.log(clamped)
    return round(math.exp(acc), 2)
