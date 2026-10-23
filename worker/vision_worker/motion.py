"""Compare motion energy and sampled change profiles, not measured timing fidelity.

`motion_score` retains its shipped energy-only meaning; `motion_energy_score` is
its explicit alias. Null scores remain inconclusive for static/blank captures.
`temporal_corr` describes frame-index signatures only, and is unavailable for
unequal lengths or uninformative profiles. Inputs have no timestamps, so timing
is always inconclusive, even when energy and sampled profiles agree perfectly.
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
    if arr_a.size != arr_b.size or arr_a.size < 2:
        return None
    if float(arr_a.std()) < 1e-6 or float(arr_b.std()) < 1e-6:
        return None
    corr = np.corrcoef(arr_a, arr_b)[0, 1]
    if corr is None or not np.isfinite(corr):
        return None
    val = float(corr)
    return val if math.isfinite(val) else None


def _timing_diagnostics(
    rs: list[float], cs: list[float], motion_status: str,
    ref_moving: bool, cand_moving: bool,
) -> dict:
    correlation = None
    if motion_status == "capture_unreliable":
        reason = "capture_unreliable"
        recommendation = "Recapture nonblank component frames before comparing motion."
    elif motion_status == "static":
        reason = "both_static"
        recommendation = (
            "Capture the active interaction window; two static captures cannot establish timing."
        )
    elif ref_moving != cand_moving:
        reason = "motion_presence_mismatch"
        recommendation = (
            "Check that both captures include the same active interaction; only one side moves."
        )
    elif len(rs) != len(cs):
        reason = "unequal_length"
        recommendation = (
            "Recapture equal-length sequences over independently verified matching windows; "
            "do not truncate or stretch their signatures to infer timing."
        )
    elif len(rs) < 2:
        reason = "insufficient_samples"
        recommendation = "Capture at least three frames per side to compare change profiles."
    else:
        correlation = _temporal_corr(rs, cs)
        if correlation is None:
            reason = "steady_motion"
            recommendation = (
                "At least one change profile is constant; its energy has no rhythm to correlate. "
                "Capture a varying interaction or review timestamped recordings."
            )
        else:
            reason = "cadence_unknown"
            recommendation = (
                "The sampled frame-index profiles differ; equal energy can coexist with wrong rhythm."
                if correlation <= 0.0 else
                "Frame-index profile correlation is a diagnostic, not proof of matching rhythm."
            )

    recommendation += (
        " These inputs contain no timestamps. Independently verify cadence, duration and "
        "interaction alignment using source timestamps before judging temporal fidelity."
    )
    sampled_profile = (
        {"status": "compared", "basis": "frame_index", "correlation": correlation}
        if correlation is not None else
        {"status": "inconclusive", "reason": reason, "correlation": None}
    )
    return {
        "status": "inconclusive",
        "reason": reason,
        "score": None,
        "cadence_verified": False,
        "sampled_profile": sampled_profile,
        "recommendation": recommendation,
    }


def compare_sequences(ref_frames: list[np.ndarray], cand_frames: list[np.ndarray]) -> dict:
    """Compare energy and frame-index profiles of two grayscale frame sequences."""
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

    energy_score = None if motion_score is None else round(float(motion_score), 1)
    timing = _timing_diagnostics(rs, cs, motion_status, ref_moving, cand_moving)

    return {
        "ref_energy": round(ref_e, 5),
        "cand_energy": round(cand_e, 5),
        "energy_ratio": round(float(energy_ratio), 3),
        "temporal_corr": timing["sampled_profile"]["correlation"],
        "ref_moving": ref_moving,
        "cand_moving": cand_moving,
        "motion_status": motion_status,
        "motion_score": energy_score,
        "motion_energy_score": energy_score,
        "motion_score_meaning": "motion_energy_similarity_only",
        "timing_diagnostics": timing,
        "ref_signature": [round(float(v), 4) for v in rs],
        "cand_signature": [round(float(v), 4) for v in cs],
    }
