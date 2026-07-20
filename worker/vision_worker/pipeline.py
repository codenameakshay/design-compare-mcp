"""Phase 2 comparison pipeline.

load -> normalize -> align -> {structure (SSIM), color (ΔE palette),
content-presence (region matching)} -> weighted geometric-mean overall -> visuals.

Typography and spacing are still returned as pending. `overall` combines only the
scored dimensions (see aggregate.py).
"""

from __future__ import annotations

from typing import Any

import cv2

from . import visuals as V
from .aggregate import aggregate
from .align import apply_warp, estimate_alignment
from .io_utils import load_rgb
from .metrics.color import color_score
from .metrics.content import content_score
from .metrics.structure import structure_score
from .normalize import CANON_WIDTH, normalize_pair


def _sub(score: float, reason: str, measurements: dict | None = None) -> dict:
    return {"score": round(float(score), 2), "reason": reason, "measurements": measurements or {}}


def _pending(reason: str = "not scored until a later phase") -> dict:
    return {"score": None, "reason": reason, "measurements": {}}


def compare(
    reference: str,
    candidate: str,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
    weights: dict | None = None,
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

    # --- dimensions ---
    layout_score, ssim_map = structure_score(ref_gray, cand_gray_a)
    color_val, color_findings, color_meas = color_score(ref_n, cand_rgb_a)
    content_val, content_findings, content_meas, content_viz = content_score(ref_n, cand_rgb_a)

    subscores = {
        "layout": _sub(
            layout_score,
            "structural similarity (SSIM) after alignment",
            {
                "ssim": round(layout_score / 100, 4),
                "alignment": align_diag,
                "aspect_mismatch": round(aspect_mismatch, 4),
            },
        ),
        "color": _sub(color_val, "dominant-palette match (mean ΔE2000)", color_meas),
        "content": _sub(content_val, "reference-region coverage (IoU matching)", content_meas),
        "typography": _pending(),
        "spacing": _pending(),
    }

    overall = aggregate(subscores, weights)

    # --- findings ---
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
    findings.extend(content_findings)
    findings.extend(color_findings)

    result: dict = {
        "overall": overall,
        "subscores": subscores,
        "cv_findings": findings,
        "visuals": [],
        "critique_rubric": (
            "Scored dimensions: layout (SSIM), color (ΔE palette), content-presence "
            "(region coverage). Typography and spacing are not yet scored — assess "
            "those qualitatively from the images. Assemble a punch-list ordered by "
            "score impact: start with the lowest sub-score and the highest-severity "
            "cv_findings. Use `content_regions` (green=matched, red=missing, "
            "orange=extra), `diff_heatmap` (hot=structural divergence), and `overlay` "
            "to ground each item. Report each fix as {area, observed, expected, "
            "severity, suggested_fix}."
        ),
        "alignment": {"mode": mode, **align_diag},
        "canonical_width": CANON_WIDTH,
        "stub": False,
    }

    if return_visuals:
        result["visuals"] = [
            {"name": "overlay", "mime_type": "image/png", "base64": V.overlay(ref_n, cand_rgb_a)},
            {"name": "diff_heatmap", "mime_type": "image/png", "base64": V.diff_heatmap(ssim_map)},
            {"name": "content_regions", "mime_type": "image/png", "base64": V.content_regions(ref_n, content_viz)},
            {"name": "side_by_side", "mime_type": "image/png", "base64": V.side_by_side(ref_n, cand_n)},
        ]

    return result
