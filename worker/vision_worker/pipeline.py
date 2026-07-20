"""Phase 1 comparison pipeline: load -> normalize -> align -> SSIM -> visuals.

Only the `layout` (structural) dimension is scored in Phase 1; the remaining
dimensions are returned as pending so the result shape stays stable while later
phases fill them in. `overall` is the mean of the scored dimensions.
"""

from __future__ import annotations

from typing import Any

import cv2

from . import visuals as V
from .align import apply_warp, estimate_alignment
from .io_utils import load_rgb
from .metrics.structure import structure_score
from .normalize import CANON_WIDTH, normalize_pair


def _sub(score: float, reason: str, measurements: dict | None = None) -> dict:
    return {"score": score, "reason": reason, "measurements": measurements or {}}


def _pending(reason: str = "not scored until a later phase") -> dict:
    return {"score": None, "reason": reason, "measurements": {}}


def compare(
    reference: str,
    candidate: str,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
) -> dict:
    if not reference:
        raise ValueError("'reference' image path is required")
    if not candidate:
        raise ValueError("'candidate' image path is required")

    ref_rgb = load_rgb(reference)
    cand_rgb = load_rgb(candidate)

    ref_n, cand_n, aspect_mismatch = normalize_pair(ref_rgb, cand_rgb)
    ref_gray = cv2.cvtColor(ref_n, cv2.COLOR_RGB2GRAY)
    cand_gray = cv2.cvtColor(cand_n, cv2.COLOR_RGB2GRAY)

    warp, align_diag = estimate_alignment(ref_gray, cand_gray, mode)
    if warp is not None:
        cand_gray_a = apply_warp(cand_gray, warp, ref_gray.shape[:2])
        cand_rgb_a = apply_warp(cand_n, warp, ref_gray.shape[:2])
    else:
        cand_gray_a, cand_rgb_a = cand_gray, cand_n

    layout_score, ssim_map = structure_score(ref_gray, cand_gray_a)

    findings: list[dict] = []
    if aspect_mismatch > 0.02:
        findings.append(
            {
                "area": "layout",
                "type": "aspect_mismatch",
                "severity": "medium" if aspect_mismatch > 0.10 else "low",
                "observed": (
                    f"candidate proportions differ from the reference by "
                    f"{aspect_mismatch * 100:.1f}% after width normalization"
                ),
                "suggested_fix": "match the overall height/proportions of the reference screen",
            }
        )

    # Phase 1: overall == the only scored dimension (layout). Later phases combine
    # dimensions via the weighted geometric mean described in PLAN.md.
    overall = round(layout_score, 2)

    result: dict = {
        "overall": overall,
        "subscores": {
            "layout": _sub(
                round(layout_score, 2),
                "structural similarity (SSIM) after alignment",
                {
                    "ssim": round(layout_score / 100, 4),
                    "alignment": align_diag,
                    "aspect_mismatch": round(aspect_mismatch, 4),
                },
            ),
            "color": _pending(),
            "content": _pending(),
            "typography": _pending(),
            "spacing": _pending(),
        },
        "cv_findings": findings,
        "visuals": [],
        "critique_rubric": (
            "Phase 1 scores structure only (SSIM). Inspect the `overlay` and "
            "`diff_heatmap` images to locate where the candidate diverges from the "
            "reference — brighter heatmap regions mean larger structural difference. "
            "Color, content, typography, and spacing are not yet scored, so do not "
            "infer those from the number; call them out qualitatively from the images."
        ),
        "alignment": {"mode": mode, **align_diag},
        "canonical_width": CANON_WIDTH,
        "stub": False,
    }

    if return_visuals:
        result["visuals"] = [
            {"name": "overlay", "mime_type": "image/png", "base64": V.overlay(ref_n, cand_rgb_a)},
            {"name": "diff_heatmap", "mime_type": "image/png", "base64": V.diff_heatmap(ssim_map)},
            {"name": "side_by_side", "mime_type": "image/png", "base64": V.side_by_side(ref_n, cand_n)},
        ]

    return result
