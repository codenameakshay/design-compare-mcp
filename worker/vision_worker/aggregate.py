"""Combine per-dimension sub-scores into an overall score.

Weighted **geometric mean** over dimensions with a numeric score (scored and
failed). Not-applicable dimensions (`score is None`) are skipped and the
remaining weights renormalized. Zero-weight keys may remain in the dict; they
add nothing. The geometric mean makes a weak dimension drag the whole score
down far more than an arithmetic mean would. Scores are floored at FLOOR so
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

KNOWN = ("layout", "color", "content", "typography", "spacing")

PRESETS = {
    "default": DEFAULT_WEIGHTS,
    "dark-ui": {
        "layout": 0.60,
        "color": 0.10,
        "content": 0.0,
        "typography": 0.30,
        "spacing": 0.0,
    },
}

FLOOR = 1.0


def resolve_weights(preset: str | None = None, weights: dict | None = None) -> dict:
    """Resolve a preset name and/or explicit overrides into a weight dict.

    Precedence: explicit `weights` entries > the named preset > DEFAULT_WEIGHTS.
    Unknown keys, negatives, or an all-zero result after merge raise ValueError.
    """
    if preset and preset not in PRESETS:
        raise ValueError(f"unknown weight preset: {preset!r} (have {list(PRESETS)})")
    base = dict(PRESETS.get(preset or "default", DEFAULT_WEIGHTS))
    if weights:
        for k, v in weights.items():
            if k not in KNOWN:
                raise ValueError(f"unknown weight key: {k!r}")
            fv = float(v)
            if fv < 0:
                raise ValueError(f"negative weight for {k!r}")
            base[k] = fv
    if all(float(v) == 0 for v in base.values()):
        raise ValueError("all weights are zero")
    return base


def aggregate(subscores: dict, weights: dict | None = None) -> float:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in KNOWN})

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
