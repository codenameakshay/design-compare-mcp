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

# Named weight presets for specific comparison domains. Selectable via the
# `preset` argument; explicit `weights` still override individual dimensions.
PRESETS = {
    "default": DEFAULT_WEIGHTS,
    # Calibrated on a dark, single-theme motion component library (beUI -> Flutter
    # port), n=26 human-labeled component pairs. Layout dominates and typography
    # is secondary (the two dimensions that tracked human judgment: rho +0.33 /
    # +0.31); color is near-noise in a single dark theme; content & spacing are
    # excluded because region segmentation is unreliable on low-contrast dark UIs.
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
    """
    if preset and preset not in PRESETS:
        raise ValueError(f"unknown weight preset: {preset!r} (have {list(PRESETS)})")
    base = dict(PRESETS.get(preset or "default", DEFAULT_WEIGHTS))
    if weights:
        base.update({k: float(v) for k, v in weights.items()})
    return base


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
