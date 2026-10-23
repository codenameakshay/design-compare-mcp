"""Comparison pipeline.

load -> normalize -> align -> {structure (SSIM), color (fixed-lattice
max-sliced mass and soft rare-color coverage in chroma-compressed Lab proxy units),
content-presence (region matching), typography (text amount+scale),
spacing (margins+rhythm)} -> weighted geometric-mean overall -> visuals.

Color measurements use soft_grid_source_density_scaled_clearance_v2 and
chroma_compressed_lab_proxy units, not CIEDE2000 or 3D optimal transport.
distance = max(mass_distance, weighted_coverage_distance), where
coverage_distance is raw S, weighted_coverage_distance is 0.9*S, and decay is 19.
Source-query alpha = .05/max(rho_source,.05) scales BOTH own and target
occupancy per direction. Effective query mass resolution is .001/alpha.
coverage_method.name is source_density_scaled_bidirectional_soft_clearance.
The single coverage policy integrates own and target clearance before subtraction.
Method and conservative absence-certificate metadata do not identify spatial matches.
color_shift summarizes two certified unmatched masses, not every recoloring.
Failure to certify absence does not prove presence or a nearby counterpart.

`overall` combines numeric scores (scored and failed); not-applicable
dimensions are skipped (see aggregate.py).
"""

from __future__ import annotations

from typing import Any

from . import visuals as V
from .aggregate import FLOOR, aggregate, resolve_weights
from .align import apply_warp, estimate_alignment
from .io_utils import load_frame_sequence, load_rgb
from .motion import compare_sequences
from .metrics.color import color_score
from .metrics.content import content_score
from .metrics.spacing import spacing_score
from .metrics.structure import structure_score
from .metrics.typography import typography_score
from .normalize import CANON_WIDTH, normalize_pair
from .reliability import make_diagnostics, make_provenance

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def _sub(score: float | None, reason: str, measurements: dict | None = None,
         status: str | None = None) -> dict:
    if status is None:
        status = "not_applicable" if score is None else "scored"
    return {
        "score": None if score is None else round(float(score), 2),
        "reason": reason,
        "measurements": measurements or {},
        "status": status,
    }


def compare(
    reference: str,
    candidate: str,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
    weights: dict | None = None,
    preset: str | None = None,
    comparison_context: dict | None = None,
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
        comparison_context=comparison_context,
    )


def compare_arrays(
    ref_rgb,
    cand_rgb,
    mode: str = "screen",
    ignore_regions: Any = None,
    return_visuals: bool = True,
    weights: dict | None = None,
    preset: str | None = None,
    comparison_context: dict | None = None,
) -> dict:
    """Compare two already-loaded RGB arrays (no file I/O).

    Used by the file-based `compare()` and directly by the calibration harness.
    """
    resolved_weights = resolve_weights(preset, weights)
    provenance = make_provenance(
        ref_rgb, cand_rgb, mode=mode, preset=preset, weights=resolved_weights,
        ignore_regions=ignore_regions, comparison_context=comparison_context,
    )
    pair = normalize_pair(
        ref_rgb, cand_rgb, ignore_boxes=provenance["settings"]["ignore_regions"],
    )
    aspect_mismatch = pair.aspect_mismatch
    ref_n, cand_n = pair.ref.rgb, pair.cand.rgb
    ref_gray = pair.ref.gray
    cand_gray = pair.cand.gray

    warp, align_diag = estimate_alignment(ref_gray, cand_gray, mode)
    identity_score = align_diag.pop("_layout_identity_score", None)
    if warp is not None:
        cand_gray_a = apply_warp(cand_gray, warp, ref_gray.shape[:2])
        cand_rgb_a = apply_warp(cand_n, warp, ref_gray.shape[:2])
    else:
        cand_gray_a, cand_rgb_a = cand_gray, cand_n

    ssim_map = None
    content_viz: dict = {"matched": [], "missing": [], "extra": []}
    color_findings: list[dict] = []
    content_findings: list[dict] = []
    typo_findings: list[dict] = []
    spacing_findings: list[dict] = []

    def _guard(name, fn):
        try:
            return fn(), None
        except Exception as exc:
            return None, _sub(
                FLOOR,
                f"{name} metric failed",
                {"error": f"{type(exc).__name__}: {exc}"[:200]},
                status="failed",
            )

    def _layout():
        nonlocal ssim_map, identity_score
        score, ssim_map = structure_score(ref_gray, cand_gray_a)
        if warp is None:
            identity_score = score
        return _sub(score, "structural similarity (SSIM) after alignment", {
            "ssim": round(score / 100, 4),
            "alignment": align_diag,
            "aspect_mismatch": round(aspect_mismatch, 4),
        })

    def _color():
        nonlocal color_findings
        val, color_findings, meas = color_score(ref_n, cand_n)
        return _sub(val, "fixed-lattice max-sliced mass and source-density-scaled soft rare-color coverage (chroma-compressed Lab proxy)", meas)

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

    overall = aggregate(subscores, resolved_weights)
    diagnostics = make_diagnostics(
        ref_rgb, cand_rgb, pair, align_diag, warp, subscores, identity_score,
    )

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
    layout_score = subscores["layout"]["score"]
    if isinstance(layout_score, (int, float)) and layout_score < 70:
        findings.append(
            {
                "area": "layout",
                "type": "layout_mismatch",
                "severity": "high" if layout_score < 40 else "medium",
                "observed": (
                    f"layout score {layout_score:.1f} is below 70 after alignment"
                ),
                "suggested_fix": "match the reference structure, spacing, and proportions",
            }
        )
    findings.extend(content_findings)
    findings.extend(color_findings)
    findings.extend(typo_findings)
    findings.extend(spacing_findings)
    findings.sort(key=lambda f: _SEV_ORDER.get(f.get("severity", "low"), 9))

    result: dict = {
        "overall": overall,
        "diagnostics": diagnostics,
        "provenance": provenance,
        "subscores": subscores,
        "cv_findings": findings,
        "visuals": [],
        "critique_rubric": (
            "Resolve diagnostics capture/state and scope before turning findings into product work. "
            "status=ok is not capture verification or a design pass. near_uniform_input means "
            "near-uniform pixels; confirm expected content/state. alignment_unresolved means "
            "identity fallback, not failed capture. translation_applied means layout tolerates "
            "a global translation; inspect unaligned placement and layout_identity_score. "
            "Alignment dx/dy are canonical pixels; divide by canvas.reference.scale or "
            "canvas.candidate.scale for original pixels. Rejected dx/dy are attempted, not applied. "
            "aspect_mismatch may be capture/crop protocol or real proportions. mask_fill_semantics "
            "means fill, not true exclusion; mask_fill_colors_differ means unequal fills. Scope "
            "fractions describe the clipped union on the padded canvas, not metric confidence. "
            "empty_compare_scope is inconclusive: show raw numeric overall but do not rank or accept it. "
            "metric_failed means failed measurement, not measured defect; its legacy floor remains. "
            "comparison_key excludes candidate content; run_key includes it. Missing/different "
            "comparison keys require baseline re-scoring before reporting deltas. comparison_context "
            "is caller-declared metadata, never verified capture proof; omission leaves external "
            "capture/crop state unknown. Scored on a 768-wide canonical canvas; ignores use original "
            "reference pixels. Dimensions: layout (SSIM), color (fixed-lattice max-sliced mass and "
            "source-density-scaled soft rare-color coverage in chroma-compressed Lab proxy units), content (region coverage), "
            "typography (text amount/scale), spacing (margins/rhythm). Confirm coarse typography/spacing "
            "hints visually. "
            "Color is not CIEDE2000, exact color matching or 3D optimal transport. Projected-mass "
            "distance does not identify transport edges, moved-pixel fractions or spatial correspondence. "
            "Source-query alpha=.05/max(rho_source,.05) scales both own and target occupancy per "
            "direction; query mass resolution is .001/alpha. "
            "Missing/added findings need conservative absence certificates. color_shift summarizes "
            "two certified unmatched masses, not any recoloring. Failure to certify absence does not "
            "prove presence or a nearby counterpart. color_coverage_deficit "
            "does not prove exact absence. Color scores need version-matched baselines, not historical anchors. "
            "Ground fixes in unaligned side_by_side, overlay, diff_heatmap and "
            "content_regions; order by score impact/severity. Report each fix as "
            "{area, observed, expected, severity, suggested_fix}."
        ),
        "alignment": {"mode": mode, **align_diag},
        "canvas": pair.mapping,
        "canonical_width": CANON_WIDTH,
        "preset": preset or "default",
        "weights": {k: round(v, 3) for k, v in resolved_weights.items()},
        "stub": False,
    }

    if return_visuals:
        ignore_mask = pair.ignore.mask
        ref_prev = V.hatch_ignore(pair.ref.preview_rgb, ignore_mask)
        cand_prev = V.hatch_ignore(pair.cand.preview_rgb, ignore_mask)
        visuals = [
            {"name": "overlay", "mime_type": "image/png", "base64": V.overlay(ref_n, cand_rgb_a)},
            {"name": "content_regions", "mime_type": "image/png",
             "base64": V.content_regions(ref_prev, content_viz, cand_prev)},
            {"name": "side_by_side", "mime_type": "image/png",
             "base64": V.side_by_side(ref_prev, cand_prev)},
        ]
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
    """Compare sampled motion energy from two frame sequences.

    `reference`/`candidate` are each a directory of frames or a list of frame
    paths. Energy similarity is not animation fidelity. No timestamps are
    supplied, so timing is inconclusive and cadence is not verified. Optional
    profile correlation compares frame indices only.
    """
    if not reference:
        raise ValueError("'reference' frame source is required")
    if not candidate:
        raise ValueError("'candidate' frame source is required")

    ref_frames = load_frame_sequence(reference, max_frames=max_frames)
    cand_frames = load_frame_sequence(candidate, max_frames=max_frames)
    result = compare_sequences(ref_frames, cand_frames)
    result["frames"] = {"reference": len(ref_frames), "candidate": len(cand_frames)}

    status = result.get("motion_status")
    if status == "capture_unreliable":
        verdict = "capture is unreliable (blank or near-uniform frames)"
    elif status == "static" or (
        result["motion_score"] is None and not result["ref_moving"] and not result["cand_moving"]
    ):
        verdict = "neither side animates in these frames"
    elif result["ref_moving"] != result["cand_moving"]:
        side = "candidate" if result["cand_moving"] else "reference"
        other = "reference" if result["cand_moving"] else "candidate"
        verdict = f"motion mismatch: {side} animates but {other} is static"
    else:
        verdict = f"both animate; motion energy ratio {result['energy_ratio']:.2f}"
    result["critique_rubric"] = (
        f"Motion comparison ({verdict}). `motion_status` is {status}. "
        "A null `motion_score` is inconclusive (static or capture_unreliable), "
        "not a perfect 100. `motion_energy_score` aliases `motion_score` and measures "
        "energy similarity only, not animation fidelity. Read timing_diagnostics status, "
        "reason and recommendation: without timestamps timing is inconclusive and "
        "cadence is not verified. sampled_profile and its temporal_corr alias are "
        "optional frame-index correlation, not rhythm or elapsed-time alignment. "
        "The motion_signature chart (green=reference, blue=candidate) shows sampled "
        "intensity against frame index, not guaranteed capture cadence. A one-shot "
        "animation may have finished before capture. Confirm capture state before "
        "attributing a low energy score to the product."
    )
    result["stub"] = False

    if return_visuals:
        result["visuals"] = [{
            "name": "motion_signature", "mime_type": "image/png",
            "base64": V.motion_signature(result["ref_signature"], result["cand_signature"]),
        }]
    return result
