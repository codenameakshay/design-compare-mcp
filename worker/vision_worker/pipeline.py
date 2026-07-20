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
from .aggregate import aggregate, resolve_weights
from .align import apply_warp, estimate_alignment
from .io_utils import load_frame_sequence, load_rgb
from .motion import compare_sequences
from .metrics.color import color_score
from .metrics.content import content_score
from .metrics.spacing import spacing_score
from .metrics.structure import structure_score
from .metrics.typography import typography_score
from .normalize import CANON_WIDTH, normalize_pair


def _sub(score: float | None, reason: str, measurements: dict | None = None) -> dict:
    """Build a sub-score entry. A None score marks the dimension not-applicable
    for this pair (e.g. no text / no major regions); aggregate() excludes it."""
    return {
        "score": None if score is None else round(float(score), 2),
        "reason": reason,
        "measurements": measurements or {},
    }


def compare(
    reference: str,
    candidate: str,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
    weights: dict | None = None,
    preset: str | None = None,
) -> dict:
    if not reference:
        raise ValueError("'reference' image path is required")
    if not candidate:
        raise ValueError("'candidate' image path is required")

    return compare_arrays(
        load_rgb(reference),
        load_rgb(candidate),
        mode=mode,
        ignore_regions=ignore_regions,
        return_visuals=return_visuals,
        weights=weights,
        preset=preset,
    )


def compare_arrays(
    ref_rgb,
    cand_rgb,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
    weights: dict | None = None,
    preset: str | None = None,
) -> dict:
    """Compare two already-loaded RGB arrays (no file I/O).

    Used by the file-based `compare()` and directly by the calibration harness.
    """
    ref_n, cand_n, aspect_mismatch = normalize_pair(ref_rgb, cand_rgb)
    ref_gray = cv2.cvtColor(ref_n, cv2.COLOR_RGB2GRAY)
    cand_gray = cv2.cvtColor(cand_n, cv2.COLOR_RGB2GRAY)

    warp, align_diag = estimate_alignment(ref_gray, cand_gray, mode)
    if warp is not None:
        cand_gray_a = apply_warp(cand_gray, warp, ref_gray.shape[:2])
        cand_rgb_a = apply_warp(cand_n, warp, ref_gray.shape[:2])
    else:
        cand_gray_a, cand_rgb_a = cand_gray, cand_n

    # --- dimensions (each isolated: one failing metric -> that dimension only) ---
    # Only structure (SSIM) uses the ALIGNED candidate — SSIM is hypersensitive to
    # any offset, so the global shift is registered away and layout measures shape.
    # The other four run on the UNWARPED candidate: color/typography are
    # alignment-invariant, and content/spacing must stay position-sensitive so a
    # genuine global shift surfaces as a spacing/placement finding rather than
    # being silently corrected. This also avoids warp interpolation artifacts.
    ssim_map = None
    content_viz: dict = {"matched": [], "missing": [], "extra": []}
    color_findings: list[dict] = []
    content_findings: list[dict] = []
    typo_findings: list[dict] = []
    spacing_findings: list[dict] = []

    def _guard(name, fn):
        """Run a metric; on failure return a None-scored sub-score with the error.
        Isolates one bad dimension (e.g. a degenerate image) from the rest."""
        try:
            return fn(), None
        except Exception as exc:  # keep the compare alive; dimension -> not applicable
            return None, {
                "score": None,
                "reason": f"{name} metric failed",
                "measurements": {"error": f"{type(exc).__name__}: {exc}"[:200]},
            }

    def _layout():
        nonlocal ssim_map
        score, ssim_map = structure_score(ref_gray, cand_gray_a)
        return _sub(score, "structural similarity (SSIM) after alignment", {
            "ssim": round(score / 100, 4),
            "alignment": align_diag,
            "aspect_mismatch": round(aspect_mismatch, 4),
        })

    def _color():
        nonlocal color_findings
        val, color_findings, meas = color_score(ref_n, cand_n)
        return _sub(val, "dominant-palette match (mean ΔE2000)", meas)

    def _content():
        nonlocal content_findings, content_viz
        val, content_findings, meas, content_viz = content_score(ref_n, cand_n)
        return _sub(val, "reference-region coverage (IoU matching)", meas)

    def _typography():
        nonlocal typo_findings
        val, typo_findings, meas = typography_score(ref_n, cand_n)
        return _sub(val, "text amount + scale (coarse; not font identity)", meas)

    def _spacing():
        nonlocal spacing_findings
        val, spacing_findings, meas = spacing_score(ref_n, cand_n)
        return _sub(val, "block margins + vertical rhythm (coarse)", meas)

    subscores = {}
    for name, fn in [
        ("layout", _layout), ("color", _color), ("content", _content),
        ("typography", _typography), ("spacing", _spacing),
    ]:
        ok, failed = _guard(name, fn)
        subscores[name] = failed if failed is not None else ok

    resolved_weights = resolve_weights(preset, weights)
    overall = aggregate(subscores, resolved_weights)

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
    findings.extend(typo_findings)
    findings.extend(spacing_findings)

    result: dict = {
        "overall": overall,
        "subscores": subscores,
        "cv_findings": findings,
        "visuals": [],
        "critique_rubric": (
            "Scored dimensions: layout (SSIM), color (ΔE palette), content-presence "
            "(region coverage), typography (text amount+scale), spacing (margins+rhythm). "
            "Typography and spacing are coarse pixel heuristics — treat them as hints and "
            "confirm font family/weight and fine spacing visually. Assemble a punch-list "
            "ordered by score impact: start with the lowest sub-score and the "
            "highest-severity cv_findings. Use `content_regions` (green=matched, "
            "red=missing, orange=extra), `diff_heatmap` (hot=structural divergence), and "
            "`overlay` to ground each item. Report each fix as {area, observed, expected, "
            "severity, suggested_fix}."
        ),
        "alignment": {"mode": mode, **align_diag},
        "canonical_width": CANON_WIDTH,
        "preset": preset or "default",
        "weights": {k: round(v, 3) for k, v in resolved_weights.items()},
        "stub": False,
    }

    if return_visuals:
        visuals = [
            {"name": "overlay", "mime_type": "image/png", "base64": V.overlay(ref_n, cand_rgb_a)},
            {"name": "content_regions", "mime_type": "image/png", "base64": V.content_regions(ref_n, content_viz)},
            {"name": "side_by_side", "mime_type": "image/png", "base64": V.side_by_side(ref_n, cand_n)},
        ]
        # diff_heatmap only exists if the structure metric produced an SSIM map.
        if ssim_map is not None:
            visuals.insert(1, {
                "name": "diff_heatmap", "mime_type": "image/png",
                "base64": V.diff_heatmap(ssim_map),
            })
        result["visuals"] = visuals

    return result


def compare_motion(
    reference,
    candidate,
    max_frames: int | None = None,
    return_visuals: bool = True,
) -> dict:
    """Compare the MOTION of a component from two frame sequences.

    `reference`/`candidate` are each a directory of frames or a list of frame
    paths. Measures whether the two animate with similar energy and rhythm — the
    temporal fidelity a static compare cannot see.
    """
    if not reference:
        raise ValueError("'reference' frame source is required")
    if not candidate:
        raise ValueError("'candidate' frame source is required")

    ref_frames = load_frame_sequence(reference, max_frames=max_frames)
    cand_frames = load_frame_sequence(candidate, max_frames=max_frames)
    result = compare_sequences(ref_frames, cand_frames)
    result["frames"] = {"reference": len(ref_frames), "candidate": len(cand_frames)}

    if not result["ref_moving"] and not result["cand_moving"]:
        verdict = "neither side animates in these frames"
    elif result["ref_moving"] != result["cand_moving"]:
        side = "candidate" if result["cand_moving"] else "reference"
        other = "reference" if result["cand_moving"] else "candidate"
        verdict = f"motion mismatch: {side} animates but {other} is static"
    else:
        verdict = f"both animate; motion energy ratio {result['energy_ratio']:.2f}"
    result["critique_rubric"] = (
        f"Motion comparison ({verdict}). `motion_score` is the energy-ratio match "
        "(0 when one side animates and the other is static). `temporal_corr` is the "
        "rhythm match (null for steady motion with no profile). Inspect the "
        "`motion_signature` chart (green=reference, blue=candidate): compare the "
        "curves' height (animation intensity) and shape (timing). Note this samples "
        "frames at a fixed cadence — a one-shot animation may have finished before "
        "capture, so a low score can mean 'not captured' as well as 'not faithful'."
    )
    result["stub"] = False

    if return_visuals:
        result["visuals"] = [{
            "name": "motion_signature", "mime_type": "image/png",
            "base64": V.motion_signature(result["ref_signature"], result["cand_signature"]),
        }]
    return result
