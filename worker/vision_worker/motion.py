"""Motion comparison — the temporal dimension static image comparison is blind to.

Given two frame sequences (reference and candidate) of an animating component,
compute a motion signature (per-frame change magnitude over time) for each and
compare their motion *energy* (how much they animate) and *temporal profile*
(the rhythm of that motion). Content-agnostic: it measures change over time, not
appearance, so it works even when the two sources show different example content
or differ in resting layout.

This lives in the library as the foundation for a future `compare_motion` tool;
the calibration surfaced that a static comparator cannot judge motion fidelity.
"""

from __future__ import annotations

import numpy as np

# Below this mean per-frame change (0-1) a sequence is treated as effectively
# static. Low enough to still count sparse motion (a small element moving in a
# large mostly-empty preview) as animation.
STATIC_EPS = 0.0008


def signature(frames: list[np.ndarray]) -> list[float]:
    """Per-frame-pair mean absolute change, normalized to 0-1. Frames are 2-D gray."""
    return [
        float(np.abs(frames[i + 1] - frames[i]).mean() / 255.0)
        for i in range(len(frames) - 1)
    ]


def _temporal_corr(a: list[float], b: list[float]) -> float | None:
    arr_a, arr_b = np.array(a), np.array(b)
    # Steady motion (near-constant signature) has no temporal profile to correlate.
    if arr_a.std() < 1e-6 or arr_b.std() < 1e-6:
        return None
    return float(np.corrcoef(arr_a, arr_b)[0, 1])


def compare_sequences(ref_frames: list[np.ndarray], cand_frames: list[np.ndarray]) -> dict:
    """Compare two grayscale frame sequences. Returns motion diagnostics + score."""
    if len(ref_frames) < 2 or len(cand_frames) < 2:
        raise ValueError("each sequence needs at least 2 frames")

    rs, cs = signature(ref_frames), signature(cand_frames)
    ref_e, cand_e = float(np.mean(rs)), float(np.mean(cs))
    ref_moving, cand_moving = ref_e > STATIC_EPS, cand_e > STATIC_EPS

    energy_ratio = min(ref_e, cand_e) / max(ref_e, cand_e) if max(ref_e, cand_e) > 1e-6 else 1.0
    # Temporal rhythm needs equal-length series; truncate to the shorter one.
    m = min(len(rs), len(cs))
    temporal = _temporal_corr(rs[:m], cs[:m]) if m >= 2 else None
    # If one side animates and the other is static, that's a hard motion miss
    # regardless of the energy ratio.
    if ref_moving != cand_moving:
        motion_score = 0.0
    else:
        motion_score = 100.0 * energy_ratio

    return {
        "ref_energy": round(ref_e, 5),
        "cand_energy": round(cand_e, 5),
        "energy_ratio": round(energy_ratio, 3),
        "temporal_corr": temporal,
        "ref_moving": ref_moving,
        "cand_moving": cand_moving,
        "motion_score": round(motion_score, 1),
        "ref_signature": [round(v, 4) for v in rs],
        "cand_signature": [round(v, 4) for v in cs],
    }
