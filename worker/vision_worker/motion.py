"""Motion comparison — the temporal dimension static image comparison is blind to.

Given two frame sequences (reference and candidate) of an animating component,
compute a motion signature (per-frame change magnitude over time) for each and
compare their motion *energy* (how much they animate) and *temporal profile*
(the rhythm of that motion). Content-agnostic: it measures change over time, not
appearance.

`motion_status` distinguishes a real comparison from static or unreliable capture.
A null `motion_score` is inconclusive, never a fake 100.
"""

from __future__ import annotations

import math

import numpy as np

STATIC_EPS = 0.0008
BLANK_STD = 2.0


def signature(frames: list[np.ndarray]) -> list[float]:
    """Per-frame-pair mean absolute change, normalized to 0-1. Frames are 2-D gray."""
    return [
        float(np.abs(frames[i + 1] - frames[i]).mean() / 255.0)
        for i in range(len(frames) - 1)
    ]


def _is_blank(frames: list[np.ndarray]) -> bool:
    return all(float(np.std(f)) < BLANK_STD for f in frames)


def _temporal_corr(a: list[float], b: list[float]) -> float | None:
    arr_a, arr_b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if arr_a.size < 2 or arr_b.size < 2:
        return None
    if float(arr_a.std()) < 1e-6 or float(arr_b.std()) < 1e-6:
        return None
    corr = np.corrcoef(arr_a, arr_b)[0, 1]
    if corr is None or not np.isfinite(corr):
        return None
    val = float(corr)
    return val if math.isfinite(val) else None


def compare_sequences(ref_frames: list[np.ndarray], cand_frames: list[np.ndarray]) -> dict:
    """Compare two grayscale frame sequences. Returns motion diagnostics + score."""
    if len(ref_frames) < 2 or len(cand_frames) < 2:
        raise ValueError("each sequence needs at least 2 frames")

    ref_blank = _is_blank(ref_frames)
    cand_blank = _is_blank(cand_frames)

    rs, cs = signature(ref_frames), signature(cand_frames)
    ref_e, cand_e = float(np.mean(rs)), float(np.mean(cs))
    ref_moving, cand_moving = bool(ref_e > STATIC_EPS), bool(cand_e > STATIC_EPS)

    energy_ratio = (
        min(ref_e, cand_e) / max(ref_e, cand_e) if max(ref_e, cand_e) > 1e-6 else 1.0
    )
    m = min(len(rs), len(cs))
    temporal = _temporal_corr(rs[:m], cs[:m]) if m >= 2 else None
    if temporal is not None and not math.isfinite(temporal):
        temporal = None

    if ref_blank or cand_blank:
        motion_status = "capture_unreliable"
        motion_score = None
    elif not ref_moving and not cand_moving:
        motion_status = "static"
        motion_score = None
    elif ref_moving != cand_moving:
        motion_status = "compared"
        motion_score = 0.0
    else:
        motion_status = "compared"
        motion_score = 100.0 * energy_ratio

    return {
        "ref_energy": round(ref_e, 5),
        "cand_energy": round(cand_e, 5),
        "energy_ratio": round(float(energy_ratio), 3),
        "temporal_corr": None if temporal is None else float(temporal),
        "ref_moving": ref_moving,
        "cand_moving": cand_moving,
        "motion_status": motion_status,
        "motion_score": None if motion_score is None else round(float(motion_score), 1),
        "ref_signature": [round(float(v), 4) for v in rs],
        "cand_signature": [round(float(v), 4) for v in cs],
    }
