from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from PIL import Image

import vision_worker.align as A
import vision_worker.pipeline as P
import vision_worker.reliability as R
from vision_worker.aggregate import FLOOR, resolve_weights
from vision_worker.normalize import normalize_pair

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"scopeId": "year-stats-v2", "protocolKey": "a" * 64}
cv2.setNumThreads(1)


def solid(value=245, height=192, width=192):
    return np.full((height, width, 3), value, np.uint8)


def textured():
    rgb = solid()
    for x, y, w, h, color in [
        (15, 12, 145, 20, (20, 30, 40)), (14, 47, 55, 47, (210, 40, 30)),
        (85, 47, 87, 47, (20, 150, 90)), (15, 110, 145, 15, (30, 60, 100)),
        (15, 140, 95, 32, (100, 50, 180)),
    ]:
        rgb[y:y+h, x:x+w] = color
    return rgb


def compare(ref, cand=None, **kw):
    return P.compare_arrays(ref, ref if cand is None else cand, return_visuals=False, **kw)


def codes(result):
    return {issue["code"] for issue in result["diagnostics"]["issues"]}


def provenance(ref, cand=None, **kw):
    settings = {"mode": "screen", "preset": None, "weights": resolve_weights(),
                "ignore_regions": None, "comparison_context": None}
    settings.update(kw)
    return R.make_provenance(ref, ref if cand is None else cand, **settings)


class CaptureAndDiagnosticsTests(unittest.TestCase):
    def test_stats_match_float64_population_stddev(self):
        sparse = solid(245)
        sparse[20:23, 30:33] = 244
        random = np.random.default_rng(41).integers(0, 256, (113, 107, 3), dtype=np.uint8)
        fixture = np.asarray(Image.open(ROOT / "test/fixtures/reference.png").convert("RGB"))
        for rgb in (solid(), sparse, textured(), random, fixture, random[::2, ::2]):
            with self.subTest(shape=rgb.shape):
                stats = R.capture_stats(rgb)
                expected = float(np.std(rgb, axis=(0, 1), dtype=np.float64).max())
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                self.assertAlmostEqual(stats["rgb_stddev_max"], expected, delta=1e-7)
                self.assertAlmostEqual(stats["gray_stddev"], float(np.std(gray, dtype=np.float64)), delta=1e-7)
                self.assertEqual(stats["near_uniform"], expected < 2)

    def test_uniform_identity_is_review_not_failed_capture(self):
        for mode in ("screen", "widget"):
            out = compare(solid(), mode=mode)
            self.assertEqual(out["overall"], 100)
            self.assertEqual(codes(out), {"near_uniform_input"})
            self.assertEqual(out["diagnostics"]["status"], "review")
            self.assertEqual(out["diagnostics"]["layout_identity_score"], 100)
            self.assertNotIn("capture_unreliable", json.dumps(out))
            self.assertEqual(out["subscores"]["typography"]["status"], "not_applicable")
        self.assertEqual(out["alignment"]["reason"], "widget_identity")
        self.assertEqual(out["alignment"]["outcome"], "not_requested")
        self.assertTrue(out["alignment"]["fallback"])

    def test_uniform_threshold_and_white_decoded_input(self):
        boundary = solid(126)
        boundary[:, ::2] = 130
        self.assertEqual(R.capture_stats(boundary)["rgb_stddev_max"], 2)
        self.assertFalse(R.capture_stats(boundary)["near_uniform"])
        boundary[:, ::2] = 129
        self.assertTrue(R.capture_stats(boundary)["near_uniform"])
        with tempfile.TemporaryDirectory() as temp:
            white = Path(temp) / "white.png"
            Image.fromarray(solid(255)).save(white)
            out = P.compare(str(white), str(white), return_visuals=False)
        self.assertEqual(out["diagnostics"]["capture"]["reference"]["rgb_stddev_max"], 0)
        self.assertEqual(codes(out), {"near_uniform_input"})

    def test_uniform_reference_content_candidate_retains_metric_evidence(self):
        out = compare(solid(), textured())
        near_uniform = [i["side"] for i in out["diagnostics"]["issues"] if i["code"] == "near_uniform_input"]
        self.assertEqual(near_uniform, ["reference"])
        self.assertEqual(out["subscores"]["content"]["score"], 0)
        self.assertLess(out["subscores"]["color"]["score"], 100)
        self.assertTrue(out["cv_findings"])

    def test_unequal_uniform_screen_does_not_use_rounded_ssim_identity(self):
        out = compare(solid(), solid(244))
        self.assertIn("alignment_unresolved", codes(out))
        self.assertIn("near_uniform_input", codes(out))
        self.assertLess(out["overall"], 100)

    def test_equal_textured_identity_and_forced_fallback(self):
        out = compare(textured())
        self.assertEqual(out["overall"], 100)
        self.assertEqual(out["diagnostics"]["status"], "ok")
        self.assertNotIn("translation_applied", codes(out))
        with patch.object(A.cv2, "findTransformECC", side_effect=RuntimeError("controlled")):
            fallback = compare(textured())
        self.assertEqual(fallback["alignment"]["reason"], "ecc_nonconvergence")
        self.assertNotIn("alignment_unresolved", codes(fallback))

    def test_gray_equality_is_not_rgb_identity(self):
        ref, cand = solid(0), solid(0)
        ref[:] = (255, 0, 0)
        cand[:] = (0, 130, 0)
        np.testing.assert_array_equal(cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY),
                                      cv2.cvtColor(cand, cv2.COLOR_RGB2GRAY))
        out = compare(ref, cand)
        self.assertIn("alignment_unresolved", codes(out))
        self.assertLess(out["subscores"]["color"]["score"], 100)
        self.assertTrue(out["cv_findings"])

    def test_sparse_low_contrast_widget_is_observation_not_verdict(self):
        ref = solid()
        ref[40:60, 20:50] = 244
        out = compare(ref, mode="widget")
        self.assertIn("near_uniform_input", codes(out))
        self.assertNotIn("alignment_unresolved", codes(out))
        self.assertEqual(out["overall"], 100)

    def test_global_translation_exposes_identity_and_unwarped_evidence(self):
        ref = textured()
        cand = cv2.warpAffine(ref, np.float32([[1, 0, 0], [0, 1, 6]]), (192, 192),
                              borderMode=cv2.BORDER_REPLICATE)
        screen, widget = compare(ref, cand), compare(ref, cand, mode="widget")
        self.assertEqual(screen["alignment"]["outcome"], "applied")
        self.assertIn("translation_applied", codes(screen))
        self.assertGreater(screen["subscores"]["layout"]["score"],
                           widget["subscores"]["layout"]["score"] + 5)
        self.assertAlmostEqual(screen["diagnostics"]["layout_identity_score"],
                               widget["subscores"]["layout"]["score"], delta=.01)
        self.assertLess(screen["subscores"]["spacing"]["score"], 100)
        for name in ("color", "content", "typography", "spacing"):
            self.assertEqual(screen["subscores"][name], widget["subscores"][name])
        self.assertAlmostEqual(screen["alignment"]["dy"] / screen["canvas"]["candidate"]["scale"],
                               6, delta=.1)

    def test_local_displacement_remains_visible_with_fixed_anchors(self):
        ref = solid()
        ref[12:32, 15:160] = (20, 30, 40)
        ref[160:180, 15:160] = (30, 60, 100)
        ref[65:85, 40:80] = (210, 40, 30)
        cand = ref.copy()
        cand[65:85, 40:80] = 245
        cand[105:125, 40:80] = (210, 40, 30)
        out = compare(ref, cand)
        self.assertLess(out["subscores"]["layout"]["score"], 99)
        self.assertLess(out["overall"], 99)
        self.assertTrue(out["cv_findings"])

    def test_masks_keep_legacy_fill_and_original_capture_stats(self):
        ref, cand = textured(), textured()
        ref[95:180] = (200, 30, 140)
        cand[95:180] = 245
        unmasked = compare(ref, cand, mode="widget")
        masked = compare(ref, cand, mode="widget", ignore_regions=[[0, 95, 192, 85]])
        cropped = compare(ref[:90], cand[:90], mode="widget")
        self.assertGreater(masked["overall"], unmasked["overall"])
        self.assertEqual(cropped["overall"], 100)
        self.assertIn("mask_fill_semantics", codes(masked))
        self.assertAlmostEqual(masked["diagnostics"]["scope"]["ignored_fraction"], 85/192)
        full = compare(ref, cand, mode="widget", ignore_regions=[[0, 0, 192, 192]])
        self.assertEqual(full["diagnostics"]["status"], "inconclusive")
        self.assertEqual(full["overall"], 100)
        self.assertEqual(full["diagnostics"]["capture"], unmasked["diagnostics"]["capture"])
        self.assertNotIn("near_uniform_input", codes(full))

    def test_all_ignored_different_fills_still_inconclusive(self):
        ref, cand = solid(255), solid(0)
        ref[40:150, 40:150] = cand[40:150, 40:150] = (70, 120, 190)
        out = compare(ref, cand, mode="widget", ignore_regions=[[0, 0, 192, 192]])
        self.assertEqual(out["overall"], 1)
        self.assertEqual(out["diagnostics"]["status"], "inconclusive")
        self.assertEqual(out["diagnostics"]["scope"]["compared_fraction"], 0)
        self.assertTrue({"mask_fill_colors_differ", "empty_compare_scope"} <= codes(out))

    def test_mask_union_clipping_zero_area_and_crop_local_coordinates(self):
        boxes = [[-20, -20, 60, 60], [20, 20, 40, 40], [20, 20, 40, 40],
                 [0, 0, 0, 99], [0, 0, -10, 99], [200, 0, 20, 20]]
        out = compare(textured(), mode="widget", ignore_regions=boxes)
        self.assertAlmostEqual(out["diagnostics"]["scope"]["ignored_fraction"], 2800/192**2)
        self.assertEqual(out["canvas"]["reference"]["scale"], 4)
        empty = compare(textured(), mode="widget", ignore_regions=boxes[3:])
        self.assertEqual(empty["diagnostics"]["scope"]["ignored_fraction"], 0)
        self.assertNotIn("mask_fill_semantics", codes(empty))
        crop = textured()[40:140, 20:120]
        local = compare(crop, mode="widget", ignore_regions=[[0, 0, 50, 50]])
        self.assertEqual(local["diagnostics"]["scope"]["ignored_fraction"], .25)

    def test_full_mask_iterator_matches_list_provenance_diagnostics_and_scores(self):
        ref, cand = textured(), textured()
        cand[30:60, 30:60] = (80, 110, 150)
        boxes = [[0, 0, 192, 192]]
        listed = compare(ref, cand, mode="widget", ignore_regions=boxes)
        streamed = compare(ref, cand, mode="widget", ignore_regions=iter(boxes))
        self.assertEqual(listed["diagnostics"]["scope"],
                         {"ignored_fraction": 1, "compared_fraction": 0})
        self.assertEqual(listed["diagnostics"]["status"], "inconclusive")
        self.assertIn("empty_compare_scope", codes(listed))
        self.assertEqual(listed["overall"], 100)
        self.assertLess(compare(ref, cand, mode="widget")["subscores"]["layout"]["score"], 100)
        self.assertEqual(streamed, listed)

    def test_overlapping_mask_order_duplicates_and_iterator_preserve_effective_union(self):
        ref, cand = textured(), textured()
        cand[20:40, 20:40] = (80, 110, 150)
        boxes = [[-24, 0, 120, 96], [48, 48, 96, 96],
                 [0, 0, 0, 192], [0, 0, -10, 192], [200, 0, 20, 20]]
        listed = compare(ref, cand, mode="widget", ignore_regions=boxes)
        self.assertEqual(listed["diagnostics"]["scope"],
                         {"ignored_fraction": 7/16, "compared_fraction": 9/16})
        self.assertIn("mask_fill_semantics", codes(listed))
        self.assertEqual(listed["overall"], 100)
        for regions in (iter(boxes), list(reversed(boxes)) + boxes[:2],
                        (box for box in reversed(boxes + boxes))):
            self.assertEqual(compare(ref, cand, mode="widget", ignore_regions=regions), listed)

    def test_aspect_padding_does_not_change_original_stats_or_comparison_series(self):
        ref = solid()
        base = compare(ref)
        out = compare(ref, solid(height=96))
        self.assertEqual(out["overall"], 100)
        self.assertIn("aspect_mismatch", codes(out))
        self.assertTrue(any(f["type"] == "aspect_mismatch" for f in out["cv_findings"]))
        self.assertEqual(base["provenance"]["comparison_key"], out["provenance"]["comparison_key"])
        self.assertNotEqual(base["provenance"]["run_key"], out["provenance"]["run_key"])
        self.assertIn("alignment_unresolved", codes(out))

    def test_failed_metrics_remain_failed_even_with_zero_weight(self):
        ref = textured()
        with patch.object(P, "color_score", side_effect=RuntimeError("controlled")):
            failed = compare(ref, mode="widget")
            zero = compare(ref, mode="widget", weights={"color": 0})
        self.assertEqual(failed["subscores"]["color"]["score"], FLOOR)
        self.assertEqual(failed["subscores"]["color"]["status"], "failed")
        self.assertLess(failed["overall"], 100)
        self.assertEqual(zero["overall"], 100)
        for out in (failed, zero):
            self.assertIn({"code": "metric_failed", "metric": "color"}, out["diagnostics"]["issues"])
        with patch.object(P, "structure_score", side_effect=RuntimeError("controlled")):
            bad_layout = compare(ref, mode="widget")
        self.assertIsNone(bad_layout["diagnostics"]["layout_identity_score"])
        self.assertEqual(bad_layout["subscores"]["layout"]["status"], "failed")

    def test_equal_rgb_does_not_clear_other_issues(self):
        with patch.object(P, "spacing_score", side_effect=RuntimeError("controlled")):
            out = compare(solid(), ignore_regions=[[0, 0, 192, 192]])
        self.assertTrue({"near_uniform_input", "empty_compare_scope", "metric_failed"} <= codes(out))
        self.assertNotIn("alignment_unresolved", codes(out))


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.ref = np.arange(32*32, dtype=np.uint8).reshape(32, 32)
        self.cand = np.flipud(self.ref).copy()

    def estimate(self, cc=.8, dx=1, dy=0, scores=(95, 90), error=None):
        warp = np.float32([[1, 0, dx], [0, 1, dy]])
        score_effect = error if error else [(v, np.zeros((32, 32))) for v in scores]
        with patch.object(A.cv2, "findTransformECC", return_value=(cc, warp)) as ecc, \
             patch.object(A, "structure_score", side_effect=score_effect) as score:
            result = A.estimate_alignment(self.ref, self.cand, "screen")
        self.assertEqual(ecc.call_args.args[3], cv2.MOTION_TRANSLATION)
        return result, score

    def test_all_guard_reasons_and_actual_identity(self):
        cases = [
            ({"cc": .29999}, "ecc_low_correlation"),
            ({"dx": 8.001}, "ecc_translation_limit"),
            ({"dy": -8.001}, "ecc_translation_limit"),
            ({"scores": (89, 90)}, "ecc_worsened_ssim"),
            ({"error": RuntimeError("controlled")}, "ecc_ssim_check_failed"),
        ]
        for kwargs, reason in cases:
            with self.subTest(reason=reason, kwargs=kwargs):
                (warp, diag), _ = self.estimate(**kwargs)
                self.assertIsNone(warp)
                self.assertTrue(diag["fallback"])
                self.assertEqual(diag["outcome"], "identity_fallback")
                self.assertEqual(diag["reason"], reason)
                self.assertEqual(diag["dx"], round(kwargs.get("dx", 1), 2))
                self.assertEqual(diag["dy"], round(kwargs.get("dy", 0), 2))

    def test_correlation_translation_and_ssim_equality_boundaries(self):
        (warp, diag), score = self.estimate(cc=.3, dx=8, dy=-8, scores=(90, 90))
        self.assertIsNotNone(warp)
        self.assertEqual(diag["reason"], "ecc_accepted")
        self.assertEqual(diag["outcome"], "applied")
        self.assertEqual(score.call_count, 2)
        self.assertEqual(diag["_layout_identity_score"], 90)
        with patch.object(A.cv2, "findTransformECC", side_effect=RuntimeError("controlled")):
            warp, diag = A.estimate_alignment(self.ref, self.cand, "screen")
        self.assertIsNone(warp)
        self.assertEqual(diag["reason"], "ecc_nonconvergence")

    def test_widget_never_runs_ecc(self):
        with patch.object(A.cv2, "findTransformECC") as ecc:
            warp, diag = A.estimate_alignment(self.ref, self.cand, "widget")
        ecc.assert_not_called()
        self.assertIsNone(warp)
        self.assertEqual(diag["outcome"], "not_requested")

    def test_translation_review_uses_raw_warp_not_rounded_legacy_dx(self):
        for dx, warning in ((.9999, False), (1.0001, True), (-1, True)):
            warp = np.float32([[1, 0, dx], [0, 1, 0]])
            with patch.object(A.cv2, "findTransformECC", return_value=(.9, warp)), \
                 patch.object(A, "structure_score", side_effect=[(100, None), (99, None)]):
                out = compare(textured())
            self.assertEqual(out["alignment"]["dx"], round(dx, 2))
            self.assertEqual("translation_applied" in codes(out), warning)
            self.assertEqual(out["diagnostics"]["layout_identity_score"], 99)
            self.assertNotIn("_layout_identity_score", json.dumps(out))

    def test_rejected_warp_never_reaches_metrics_and_mask_coverage_is_prewarp(self):
        ref, cand = textured(), np.roll(textured(), 3, axis=0)
        boxes = [[10, 10, 40, 40]]
        pair = normalize_pair(ref, cand, ignore_boxes=boxes)
        warp = np.float32([[1, 0, 20], [0, 1, 30]])
        with patch.object(A.cv2, "findTransformECC", return_value=(.2, warp)), \
             patch.object(P, "apply_warp") as apply, \
             patch.object(P, "content_score", wraps=P.content_score) as content, \
             patch.object(P, "spacing_score", wraps=P.spacing_score) as spacing:
            out = compare(ref, cand, ignore_regions=boxes)
        apply.assert_not_called()
        self.assertEqual(out["alignment"]["dx"], 20)
        for metric in (content, spacing):
            np.testing.assert_array_equal(metric.call_args.args[0], pair.ref.rgb)
            np.testing.assert_array_equal(metric.call_args.args[1], pair.cand.rgb)
        self.assertEqual(out["diagnostics"]["scope"]["ignored_fraction"], float(pair.ignore.mask.mean()))
        self.assertNotIn("translation_applied", codes(out))

    def test_accepted_warp_keeps_mask_coverage_and_other_metrics_unwarped(self):
        ref, cand = textured(), np.roll(textured(), 3, axis=0)
        boxes = [[10, 10, 40, 40]]
        pair = normalize_pair(ref, cand, ignore_boxes=boxes)
        warp = np.float32([[1, 0, 0], [0, 1, 12]])
        with patch.object(A.cv2, "findTransformECC", return_value=(.9, warp)), \
             patch.object(A, "structure_score", side_effect=[(99, None), (90, None)]), \
             patch.object(P, "content_score", wraps=P.content_score) as content:
            out = compare(ref, cand, ignore_regions=boxes)
        np.testing.assert_array_equal(content.call_args.args[1], pair.cand.rgb)
        self.assertEqual(out["alignment"]["outcome"], "applied")
        self.assertEqual(out["diagnostics"]["scope"]["ignored_fraction"], float(pair.ignore.mask.mean()))
        self.assertIn("translation_applied", codes(out))


class ProvenanceTests(unittest.TestCase):
    def test_domain_separated_pixel_hash_and_noncontiguous_input(self):
        rgb = textured()[:, ::2]
        expected = hashlib.sha256(b"dcm-rgb-v1\0" + struct.pack(">QQ", 96, 192) + rgb.tobytes()).hexdigest()
        self.assertEqual(R.pixel_identity(rgb)["rgb_sha256"], expected)
        self.assertEqual(R.pixel_identity(rgb), R.pixel_identity(rgb.copy()))

    def test_candidate_only_changes_exact_run_key(self):
        ref, cand = textured(), textured()
        base = provenance(ref)
        cand[0, 0] = 0
        changed = provenance(ref, cand)
        self.assertEqual(base["comparison_key"], changed["comparison_key"])
        self.assertNotEqual(base["run_key"], changed["run_key"])
        resized = provenance(ref, cand[:100])
        self.assertEqual(base["comparison_key"], resized["comparison_key"])
        self.assertNotEqual(base["run_key"], resized["run_key"])
        expected = hashlib.sha256(b"dcm-compare-v1\0" + R.canonical_json({
            "reference": base["inputs"]["reference"], "settings": base["settings"],
        })).hexdigest()
        self.assertEqual(base["comparison_key"], expected)
        self.assertEqual(base["run_key"], hashlib.sha256(b"dcm-run-v1\0" + R.canonical_json({
            "comparison_key": expected, "candidate": base["inputs"]["candidate"],
        })).hexdigest())

    def test_reference_crop_and_every_resolved_setting_split_series(self):
        ref = textured()
        base = provenance(ref)
        for changed in (provenance(ref[10:]), provenance(np.roll(ref, 1, axis=0))):
            self.assertNotEqual(base["comparison_key"], changed["comparison_key"])
        variants = [
            {"mode": "widget"}, {"preset": "dark-ui", "weights": resolve_weights("dark-ui")},
            {"ignore_regions": [[0, 0, 30, 40]]}, {"comparison_context": CONTEXT},
            {"weights": resolve_weights(weights={"layout": .3500000001})},
        ]
        for kw in variants:
            self.assertNotEqual(base["comparison_key"], provenance(ref, **kw)["comparison_key"])
        w1 = provenance(ref, weights=resolve_weights(weights={"layout": .3500000001}))
        w2 = provenance(ref, weights=resolve_weights(weights={"layout": .3500000002}))
        self.assertNotEqual(w1["comparison_key"], w2["comparison_key"])
        ctx = provenance(ref, comparison_context=CONTEXT)
        for override in ({"protocolKey": "b"*64}, {"scopeId": "different"}):
            other = provenance(ref, comparison_context={**CONTEXT, **override})
            self.assertNotEqual(ctx["comparison_key"], other["comparison_key"])
        for field, value in (("engine_revision", "other-engine"), ("runtime_versions", {"python": "0"})):
            with patch.dict(R._ENGINE_IDENTITY, {field: value}):
                changed = provenance(ref)
            self.assertNotEqual(base["comparison_key"], changed["comparison_key"])
        with patch.object(R, "CANON_WIDTH", 769):
            self.assertNotEqual(base["comparison_key"], provenance(ref)["comparison_key"])

    def test_same_size_changed_crop_origin_changes_comparison_not_canvas(self):
        ref = textured()
        before = compare(ref[:96], mode="widget")
        after = compare(ref[80:176], mode="widget")
        self.assertEqual(before["canvas"], after["canvas"])
        self.assertNotEqual(before["provenance"]["comparison_key"], after["provenance"]["comparison_key"])

    def test_context_is_metadata_only_not_scoring_or_capture_verification(self):
        ref = textured()
        omitted, declared = compare(ref), compare(ref, comparison_context=CONTEXT)
        for key in ("overall", "subscores", "diagnostics", "alignment", "canvas", "cv_findings"):
            self.assertEqual(omitted[key], declared[key])
        self.assertIsNone(omitted["provenance"]["settings"]["comparison_context"])

    def test_canonical_settings_defaults_order_deduplication_negative_zero(self):
        ref = textured()
        self.assertEqual(provenance(ref), provenance(ref, preset="default", ignore_regions=[]))
        boxes = [[-0., 0, 20, 30], [10, 20, 40, 50]]
        a = provenance(ref, ignore_regions=boxes + boxes, comparison_context=CONTEXT)
        b = provenance(ref, ignore_regions=list(reversed(boxes)),
                       weights=dict(reversed(list(resolve_weights().items()))),
                       comparison_context=dict(reversed(list(CONTEXT.items()))))
        self.assertEqual(a, b)
        self.assertEqual(a["settings"]["ignore_regions"], [[0., 0., 20., 30.], [10., 20., 40., 50.]])
        self.assertEqual(R.canonical_json({"a": -0.0}), R.canonical_json({"a": 0}))
        for bad in (float("inf"), float("nan"), -float("inf")):
            with self.assertRaises(ValueError):
                provenance(ref, weights={"layout": bad})
            with self.assertRaises(ValueError):
                provenance(ref, ignore_regions=[[0, 0, bad, 10]])

    def test_comparison_context_validation(self):
        for bad in ({}, "text", {**CONTEXT, "extra": 1}, {**CONTEXT, "scopeId": ""},
                    {**CONTEXT, "scopeId": "a"*129}, {**CONTEXT, "scopeId": "😀"*65},
                    {**CONTEXT, "protocolKey": "A"*64}, {**CONTEXT, "protocolKey": "a"*63},
                    {**CONTEXT, "protocolKey": "a"*64 + "\n"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                compare(solid(), comparison_context=bad)
        self.assertEqual(R.validate_context({**CONTEXT, "scopeId": "😀"*64})["scopeId"], "😀"*64)

    def test_lone_surrogates_are_context_validation_errors_before_hashing(self):
        for scope in ("\ud800", "\udc00", "a\ud800b", "\ud800\ud800", "\udc00\ud800",
                      "😀\ud800", "\ud800😀"):
            context = {**CONTEXT, "scopeId": scope}
            with self.subTest(scope=repr(scope)):
                for validate in (R.validate_context,
                                 lambda ctx: compare(solid(), comparison_context=ctx)):
                    with self.assertRaisesRegex(ValueError, "scopeId must contain valid Unicode") as error:
                        validate(context)
                    self.assertIs(type(error.exception), ValueError)

    def test_valid_surrogate_pairs_and_astral_unicode_share_context_and_keys(self):
        for scope, paired in (("😀"*64, "\ud83d\ude00"*64),
                              ("x"*126 + "😀", "x"*126 + "\ud83d\ude00"),
                              ("x"*128, "x"*128)):
            with self.subTest(scope=scope):
                expected = {**CONTEXT, "scopeId": scope}
                context = {**CONTEXT, "scopeId": paired}
                self.assertEqual(R.validate_context(context), expected)
                out = compare(solid(), comparison_context=context)
                self.assertEqual(out["provenance"]["settings"]["comparison_context"], expected)
                self.assertEqual(out["overall"], 100)
                self.assertEqual(out, compare(solid(), comparison_context=expected))

    def test_source_identity_covers_production_not_test_docs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "vision_worker"
            package.mkdir()
            (package / "pipeline.py").write_text("score = 1\n")
            before = R.scoring_source_digest(package)
            (root / "tests").mkdir()
            (root / "tests/test_score.py").write_text("assert True\n")
            (root / "design.md").write_text("documentation\n")
            self.assertEqual(before, R.scoring_source_digest(package))
            (package / "motion.py").write_text("energy = 1\n")
            self.assertNotEqual(before, R.scoring_source_digest(package))
        self.assertTrue(R._ENGINE_IDENTITY["engine_revision"].startswith("sha256:"))
        self.assertTrue({"python", "numpy", "opencv", "Pillow", "scikit-image", "scipy", "scikit-learn"}
                        <= R._ENGINE_IDENTITY["runtime_versions"].keys())

    def test_files_arrays_lossless_encoding_exif_and_visuals(self):
        rgb = textured()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            png, bmp, oriented = root/"a.png", root/"elsewhere.bmp", root/"oriented.png"
            Image.fromarray(rgb).save(png)
            Image.fromarray(rgb).save(bmp)
            im = Image.fromarray(np.rot90(rgb))
            exif = Image.Exif()
            exif[274] = 6
            im.save(oriented, exif=exif)
            arrays = compare(rgb, mode="widget")
            file = P.compare(str(png), str(bmp), mode="widget", return_visuals=False)
            orient = P.compare(str(oriented), str(png), mode="widget", return_visuals=False)
            self.assertEqual(arrays["provenance"], file["provenance"])
            self.assertEqual(arrays["provenance"], orient["provenance"])
            with_visuals = P.compare(str(png), str(bmp), mode="widget", return_visuals=True)
            self.assertEqual(file["provenance"], with_visuals["provenance"])
            self.assertEqual(file["diagnostics"], with_visuals["diagnostics"])
            self.assertEqual(list(file)[:3], ["overall", "diagnostics", "provenance"])

    def test_json_lines_worker_dispatch_and_legacy_context_omission(self):
        fixture = str(ROOT / "test/fixtures/reference.png")
        params = {"reference": fixture, "candidate": fixture, "mode": "widget",
                  "ignoreRegions": [[0, 0, 25, 25]], "comparisonContext": CONTEXT, "returnVisuals": False}
        requests = [{"id": i, "method": "compare_designs", "params": p} for i, p in enumerate([
            params, {k: v for k, v in params.items() if k != "comparisonContext"},
            {**params, "comparisonContext": {**CONTEXT, "extra": True}},
            {**params, "comparisonContext": None},
            *({**params, "comparisonContext": {**CONTEXT, "scopeId": scope}}
              for scope in ("\ud800", "\udc00", "a\ud800b", "\ud83d\ude00"*64, "😀"*64)),
        ])]
        proc = subprocess.run([sys.executable, "-m", "vision_worker"], cwd=ROOT/"worker",
                              input="".join(json.dumps(r)+"\n" for r in requests), text=True,
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ready, with_context, legacy, invalid, invalid_null, *unicode_results = [
            json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(ready["event"], "ready")
        self.assertTrue(with_context["ok"])
        out = with_context["result"]
        self.assertEqual(out["provenance"]["settings"]["comparison_context"], CONTEXT)
        self.assertIn("mask_fill_semantics", codes(out))
        self.assertEqual(out["visuals"], [])
        self.assertTrue(legacy["ok"])
        self.assertIsNone(legacy["result"]["provenance"]["settings"]["comparison_context"])
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["error"]["type"], "ValueError")
        self.assertFalse(invalid_null["ok"])
        for rejected in unicode_results[:3]:
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["type"], "ValueError")
            self.assertIn("scopeId must contain valid Unicode", rejected["error"]["message"])
        for accepted in unicode_results[3:]:
            self.assertTrue(accepted["ok"])
            self.assertEqual(accepted["result"]["provenance"]["settings"]["comparison_context"],
                             {**CONTEXT, "scopeId": "😀"*64})
        self.assertEqual(unicode_results[3]["result"], unicode_results[4]["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
