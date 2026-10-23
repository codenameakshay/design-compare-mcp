from __future__ import annotations

import itertools
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from skimage.color import rgb2lab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.metrics.color import color_score  # noqa: E402
from vision_worker.metrics import color as color_metric  # noqa: E402


COLORS = [(246, 246, 246), (28, 28, 32), (210, 45, 65),
          (32, 100, 220), (35, 160, 90), (235, 170, 35)]


def stripes(colors, widths):
    image = np.empty((160, sum(widths), 3), dtype=np.uint8)
    start = 0
    for color, width in zip(colors, widths):
        image[:, start:start + width] = color
        start += width
    return image


def calendar_grid():
    image = Image.new("RGB", (640, 480), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    colors = [(163, 211, 38), (250, 175, 35), (250, 48, 45),
              (30, 30, 30), (234, 234, 234)]
    for y in range(35, 425, 47):
        for x in range(30, 600, 45):
            color = colors[((x // 45) + (y // 47)) % 5]
            draw.rounded_rectangle((x, y, x + 32, y + 35), radius=5, fill=color)
            draw.text((x + 7, y + 10), str((x + y) % 29), fill=(65, 65, 65))
    return np.asarray(image)


def shaded_background(count, start=237):
    colors = np.array(list(itertools.product(range(start, start + 7), repeat=3)), dtype=np.uint8)[:count]
    candidate = np.resize(colors, (101, 160, 3))
    reference = candidate.copy()
    reference[:, :8] = COLORS[2]
    return reference, candidate


def transport_boundary_pair(extra_pixel=False):
    centers = np.array([[60, 60, 60], [220, 220, 220], [210, 50, 50],
                        [50, 180, 50], [50, 50, 210], [200, 180, 50]])
    colors = np.array([center + offset for center in centers
                       for offset in [[35, 0, 0], [-35, 0, 0], [0, 35, 0], [0, -35, 0]]],
                      dtype=np.uint8)
    extra = np.random.default_rng(987).integers(0, 256, (256, 3), dtype=np.uint8)
    extra = np.array([c for c in extra if not np.any(np.all(c == colors, axis=1))])[:232]
    colors = np.vstack((colors, extra))

    def image(weights):
        return np.vstack((np.repeat(colors, weights, axis=0),
                          np.tile(colors[-1], (236, 1)))).reshape(10, 768, 3)

    a = image(np.r_[np.tile([600, 600, 1, 1], 6), np.ones(232, int)])
    b = image(np.r_[np.tile([1, 1, 600, 600], 6), np.ones(232, int)])
    if extra_pixel:
        a[-1, -1, 0] += 1
        b[-1, -1, 0] += 1
    return a, b


def support_boundary_pair(extra_pixel=False):
    rgb = np.random.default_rng(31025).integers(0, 256, (24000, 3), dtype=np.uint8)
    ids = [22025, 13085, 14531, 17604, 21105, 13118, 4446, 8124, 8005, 16966,
           2433, 20792, 22388, 532, 8532, 13856, 20344, 21295, 23242, 16360,
           10291, 7393, 21591, 2270, 11335, 1901, 1175, 8730, 953, 21263, 21465, 13393]
    a = np.vstack((np.tile(rgb[ids[0]], (72930, 1)), rgb[ids[1:31]],
                   np.tile(rgb[5], (3840, 1)))).reshape(100, 768, 3)
    b = a.copy()
    b.reshape(-1, 3)[-3840:] = rgb[17292]
    if extra_pixel:
        a[0, 0] = b[0, 0] = rgb[ids[-1]]
    return a, b


class ColorStabilityTests(unittest.TestCase):
    def test_transport256_257_shared_pixel_cannot_hide_distribution(self):
        scores = []
        # v2 replaces the v1 anchors 62.080788052149614 and 62.08078357197323.
        for extra, expected in ((False, 58.9658244816432), (True, 58.9658193789908)):
            a, b = transport_boundary_pair(extra)
            score, findings, measurements = color_score(a, b)
            scores.append(score)
            self.assertAlmostEqual(score, expected, places=7)
            self.assertLess(score, 70.)
            self.assertEqual([f["type"] for f in findings], ["color_distribution"])
            self.assertGreater(measurements["weighted_coverage_distance"], measurements["mass_distance"])
            self.assertGreater(measurements["mass_distance"], 5.)
            self.assertEqual(measurements["certificate"]["missing_mass"], 0.)
            self.assertEqual(measurements["certificate"]["added_mass"], 0.)
            self.assertAlmostEqual(score, color_score(b, a)[0], places=10)
            self.assertAlmostEqual(score, color_score(a[:, ::-1], b[:, ::-1])[0], places=10)
        self.assertLess(abs(scores[1] - scores[0]), .01)

    def test_shortlist32_33_shared_pixel_cannot_create_false_absence(self):
        scores = []
        # v2 replaces the v1 anchors 77.84770273897678 and 77.8489152187426.
        for extra, expected in ((False, 77.3162682752747), (True, 77.3175164058364)):
            a, b = support_boundary_pair(extra)
            score, findings, measurements = color_score(a, b)
            scores.append(score)
            self.assertAlmostEqual(score, expected, places=7)
            self.assertLess(score, 85.)
            self.assertEqual([f["type"] for f in findings], ["color_coverage_deficit"])
            self.assertIn("does not prove exact color absence", findings[0]["observed"])
            self.assertEqual(measurements["certificate"]["missing_mass"], 0.)
            self.assertEqual(measurements["certificate"]["added_mass"], 0.)
            self.assertAlmostEqual(score, color_score(b, a)[0], places=10)
            self.assertAlmostEqual(score, color_score(a[:, ::-1], b[:, ::-1])[0], places=10)
        self.assertLess(abs(scores[1] - scores[0]), .01)

    def test_incidental_support_injection_keeps_material_coverage_deficit(self):
        reference = np.full((768, 768, 3), 240, dtype=np.uint8)
        reference[:, :38] = COLORS[2]
        candidate = np.full_like(reference, 240)
        before, findings, measurements = color_score(reference, candidate)
        self.assertEqual([f["type"] for f in findings], ["color_missing"])
        self.assertAlmostEqual(measurements["certificate"]["missing_mass"], 38 / 768, places=12)
        candidate[0, 0] = COLORS[2]
        after, findings, measurements = color_score(reference, candidate)
        self.assertGreater(before, 25.)
        self.assertLess(after, 45.)
        self.assertLess(abs(after - before), .1)
        self.assertAlmostEqual(before, 30.436102279019327, places=7)
        self.assertAlmostEqual(after, 30.486711184212, places=7)
        self.assertEqual([f["type"] for f in findings], ["color_coverage_deficit"])
        self.assertIn("does not prove exact color absence", findings[0]["observed"])
        self.assertEqual(measurements["certificate"]["missing_mass"], 0.)
        self.assertEqual(measurements["certificate"]["added_mass"], 0.)

    def test_smaller_support_injection_remains_material(self):
        reference = np.full((200, 200, 3), 246, dtype=np.uint8)
        reference.reshape(-1, 3)[:2000] = COLORS[2]
        candidate = np.full_like(reference, 246)
        before, findings, _ = color_score(reference, candidate)
        self.assertEqual([f["type"] for f in findings], ["color_missing"])
        candidate[0, 0] = COLORS[2]
        after, findings, _ = color_score(reference, candidate)
        self.assertAlmostEqual(before, 25.5827532228545, places=7)
        self.assertAlmostEqual(after, 26.320749308983395, places=7)
        self.assertLess(abs(after - before), 1.)
        self.assertGreater(after, 25.)
        self.assertLess(after, 45.)
        self.assertEqual([f["type"] for f in findings], ["color_coverage_deficit"])

    def test_lattice_conserves_mass_and_color_moment(self):
        for seed in range(12):
            rgb = np.random.default_rng(8710 + seed).integers(0, 256, (97, 1, 3), dtype=np.uint8)
            histogram = color_metric._histogram(rgb)
            lab = rgb2lab(rgb / 255).reshape(-1, 3)
            chroma = np.linalg.norm(lab[:, 1:], axis=1)
            lab[:, 1:] *= (np.log1p(.045 * chroma) / (.045 * chroma))[:, None]
            grid = np.indices((26, 25, 25)).reshape(3, -1).T * 4 + [0, -48, -48]
            with self.subTest(seed=seed):
                self.assertEqual(histogram.shape, (16250,))
                self.assertGreaterEqual(histogram.min(), 0)
                self.assertAlmostEqual(histogram.sum(), 1.0, places=13)
                np.testing.assert_allclose(histogram @ grid, lab.mean(axis=0), rtol=0, atol=1e-12)

    def test_nearby_hues_and_achromatic_colors_remain_close(self):
        rng = np.random.default_rng(621)
        rgb = rng.integers(0, 256, (1, 400, 3), dtype=np.uint8)
        rgb[0, :32] = np.arange(32)[:, None] * 8
        nearby = np.clip(rgb.astype(int) + rng.integers(-3, 4, rgb.shape), 0, 255).astype(np.uint8)
        score, findings, _ = color_score(rgb, nearby)
        self.assertGreater(score, 97.0)
        self.assertLess(score, 100.0)
        self.assertEqual(findings, [])

    def test_pixel_conversion_batches_are_bounded_without_sampling(self):
        rgb = np.full((1, 131073, 3), 240, dtype=np.uint8)
        converted = []
        original = color_metric._metric_coordinates

        def record(pixels):
            converted.append(len(pixels))
            return original(pixels)

        with patch.object(color_metric, "_metric_coordinates", side_effect=record):
            score, findings, _ = color_score(rgb, rgb)
        self.assertEqual(converted, [65536, 65536, 1, 65536, 65536, 1])
        self.assertEqual(score, 100.0)
        self.assertEqual(findings, [])

    def test_axis_transport_matches_literal_projected_w1(self):
        a, b = np.zeros(16250), np.zeros(16250)
        a[np.ravel_multi_index((1, 12, 12), (26, 25, 25))] = 1
        b[np.ravel_multi_index((4, 12, 12), (26, 25, 25))] = 1
        self.assertAlmostEqual(color_metric._mass_distance(a, b), 12.0, places=12)
        b *= .5
        b[np.ravel_multi_index((1, 12, 12), (26, 25, 25))] = .5
        self.assertAlmostEqual(color_metric._mass_distance(a, b), 6.0, places=12)

    def test_all_gray_channel_steps_remain_continuous(self):
        for value in range(255):
            a = np.full((1, 1, 3), value, dtype=np.uint8)
            score, findings, _ = color_score(a, a + np.uint8(1))
            with self.subTest(value=value):
                self.assertGreater(score, 97.0)
                self.assertLess(score, 100.0)
                self.assertEqual(findings, [])

    def test_exact_matches_are_order_invariant_on_rich_support(self):
        source = np.random.default_rng(903).integers(0, 256, (1, 1024, 3), dtype=np.uint8)
        score, findings, measurements = color_score(source, source[:, ::-1])
        self.assertAlmostEqual(score, 100.0, places=10)
        self.assertLess(measurements["distance"], 1e-12)
        self.assertEqual(findings, [])

    def test_versioned_measurements_disclose_proxy_contract(self):
        for rgb in (stripes(COLORS, [1] * len(COLORS)),
                    np.random.default_rng(711).integers(5, 250, (1, 128, 3), dtype=np.uint8)):
            score, _, measurements = color_score(rgb, rgb + np.uint8(1))
            self.assertGreater(score, 97.0)
            self.assertLess(score, 100.0)
            self.assertEqual(measurements["metric"], "soft_grid_source_density_scaled_clearance_v2")
            self.assertEqual(measurements["units"], "chroma_compressed_lab_proxy")
            self.assertEqual(measurements["coordinate_system"],
                             {"base": "D65_CIELab", "chroma_compression": .045})
            self.assertEqual(measurements["lattice"], {
                "step": 4.0, "origin": [0.0, -48.0, -48.0], "shape": [26, 25, 25],
                "nodes": 16250, "assignment": "trilinear_all_pixels", "pixel_batch": 65536,
            })
            self.assertEqual(measurements["mass_method"], {
                "name": "max_sliced_wasserstein_1d", "directions": 64, "exact_3d_transport": False,
            })
            self.assertEqual(measurements["coverage_method"], {
                "name": "source_density_scaled_bidirectional_soft_clearance",
                "radii": [0., 2., 4., 6., 8., 10., 14., 20., 28., 40., 60., 90., 140.],
                "mass_scale": .001, "density_sigma": 10., "density_cap": .05, "gain": .9,
                "source_alpha": "density_cap / max(source_density, density_cap)",
                "query_mass_resolution": "mass_scale / source_alpha",
                "occupancy_scaling": "same_source_query_alpha_for_own_and_target",
            })
            self.assertAlmostEqual(measurements["certificate"]["lattice_guard"], 13.856406460551018)
            self.assertEqual(measurements["certificate"]["distance"], 10.)
            self.assertEqual(measurements["certificate"]["mass_floor"], .001)
            self.assertEqual(measurements["decay"], 19.)
            self.assertAlmostEqual(score, 100 * np.exp(-measurements["distance"] / 19), places=12)
            self.assertEqual(measurements["distance"], max(measurements["mass_distance"],
                                                          measurements["weighted_coverage_distance"]))
            self.assertEqual(measurements["weighted_coverage_distance"], .9 * measurements["coverage_distance"])
            for obsolete in ("mean_delta_e", "transport_delta_e", "support_delta_e", "shifted_mass",
                             "top_deltas", "support_matching", "palette_size", "support_size"):
                self.assertNotIn(obsolete, measurements)

    def test_large_noise_and_far_palettes_complete_within_call_budget(self):
        for kind in ('noise512', 'noise768', 'independent768', 'far32'):
            size = 512 if kind == 'noise512' else 768
            rng = np.random.default_rng(42)
            if kind == 'far32':
                reference = rng.integers(0, 60, (32, 768, 3), dtype=np.uint8)
                candidate = rng.integers(195, 256, reference.shape, dtype=np.uint8)
            else:
                reference = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
                candidate = (np.random.default_rng(43).integers(0, 256, reference.shape, dtype=np.uint8)
                             if kind == 'independent768' else
                             np.clip(reference.astype(int) + 1, 0, 255).astype(np.uint8))
            started = time.perf_counter()
            score, _, measurements = color_score(reference, candidate)
            elapsed = time.perf_counter() - started
            with self.subTest(kind=kind):
                self.assertLess(elapsed, 30.0)
                if kind == 'far32':
                    self.assertLess(score, 10.0)
                else:
                    self.assertGreater(score, 90.0)
                self.assertEqual(measurements["lattice"]["nodes"], 16250)

    def test_conservative_certificate_bounds_exact_proxy_absence(self):
        for seed in range(12):
            rng = np.random.default_rng(921 + seed)
            source = rng.integers(0, 256, (1, 31, 3), dtype=np.uint8)
            target = rng.integers(0, 256, (1, 29, 3), dtype=np.uint8)
            score, findings, measurements = color_score(source, target)
            a, b = color_metric._metric_coordinates(source), color_metric._metric_coordinates(target)
            exact = np.sqrt(((a[:, None] - b[None]) ** 2).sum(axis=2))
            with self.subTest(seed=seed):
                self.assertLess(score, 100.)
                self.assertLessEqual(measurements["certificate"]["missing_mass"],
                                     np.mean(exact.min(axis=1) > 10) + 1e-12)
                self.assertLessEqual(measurements["certificate"]["added_mass"],
                                     np.mean(exact.min(axis=0) > 10) + 1e-12)
                for finding in findings:
                    self.assertNotIn("shift #", finding["suggested_fix"])

    def test_missing_accent_at_palette_cutoff_crop_and_common_pixel(self):
        for count in (250, 253, 254, 255, 256, 257, 258, 264, 300, 343):
            scores = []
            reference, candidate = shaded_background(count)
            for perturb in (False, True):
                a, b = reference.copy(), candidate.copy()
                if perturb:
                    a[0, 10, 0] -= 1
                    b[0, 10, 0] -= 1
                for origin in (0, 1):
                    with self.subTest(count=count, perturb=perturb, origin=origin):
                        score, findings, _ = color_score(a[origin:origin + 100], b[origin:origin + 100])
                        scores.append(score)
                        self.assertGreater(score, 25.0)
                        self.assertLess(score, 45.0)
                        self.assertEqual([f["type"] for f in findings], ["color_missing"])
                        self.assertIn("At least 5.00%", findings[0]["observed"])
                        self.assertIn("lattice uncertainty guards", findings[0]["observed"])
                        self.assertIn("does not identify their positions", findings[0]["suggested_fix"])
            self.assertLess(max(scores) - min(scores), 0.1)

    def test_support_is_not_diluted_by_nearby_background_shade_count(self):
        scores = []
        for count in (1, 6, 9, 15, 64, 128, 250, 254, 255, 256, 257, 264, 300, 343):
            reference, candidate = shaded_background(count)
            score, findings, _ = color_score(reference[1:], candidate[1:])
            scores.append(score)
            self.assertLess(score, 45.0)
            self.assertEqual([f["type"] for f in findings], ["color_missing"])
        # These clouds differ slightly in actual color, but all are one compact
        # background neighborhood with the same missing 5% red accent.
        self.assertLess(max(scores) - min(scores), 4.0)
        self.assertLess(max(scores[6:12]) - min(scores[6:12]), 1.0)

    def test_cutoff_common_pixel_across_background_density_bins(self):
        for start in (13, 29, 109, 237):
            reference, candidate = shaded_background(255, start)
            before, findings, _ = color_score(reference[:100], candidate[:100])
            reference[0, 10, 0] -= 1
            candidate[0, 10, 0] -= 1
            after, after_findings, _ = color_score(reference[:100], candidate[:100])
            with self.subTest(start=start):
                self.assertLess(abs(after - before), 0.1)
                self.assertLess(after, 70.0)
                self.assertEqual([f["type"] for f in findings], ["color_missing"])
                self.assertEqual(findings, after_findings)

    def test_rich_background_speck_accent_and_recolor_controls(self):
        _, plain = shaded_background(255)
        plain = plain[:100]
        scores = []
        for count in (1, 16, 80, 200, 800):
            reference = plain.copy()
            reference.reshape(-1, 3)[:count] = COLORS[2]
            score, findings, _ = color_score(reference, plain)
            scores.append(score)
            if count == 1:
                self.assertGreater(score, 99.0)
                self.assertEqual(findings, [])
            else:
                self.assertTrue(any(f["type"] == "color_missing" for f in findings))
        self.assertTrue(all(a > b for a, b in zip(scores, scores[1:])))
        self.assertLess(scores[-1], 45.0)
        recolored = reference.copy()
        recolored.reshape(-1, 3)[:800] = (165, 35, 205)
        score, findings, _ = color_score(reference, recolored)
        self.assertLess(score, 70.0)
        self.assertEqual({f["type"] for f in findings}, {"color_missing", "color_added", "color_shift"})

    def test_tiny_crop_shifts_with_unchanged_color_mass(self):
        image = calendar_grid()
        for shift in (0, 1, 2, 3, 4):
            with self.subTest(shift=shift):
                score, findings, measurements = color_score(
                    image[8:472], image[8 + shift:472 + shift]
                )
                self.assertAlmostEqual(score, 100.0, places=6)
                self.assertEqual(findings, [])
                self.assertAlmostEqual(measurements["distance"], 0.0, places=12)

    def test_near_identical_palette_can_split_without_becoming_a_new_color(self):
        reference = stripes(COLORS[:2], [128, 32])
        candidate = stripes(COLORS[:2] + [(247, 247, 247)], [64, 32, 64])
        score, findings, _ = color_score(reference, candidate)
        self.assertGreater(score, 99.0)
        self.assertLess(score, 100.0)
        self.assertEqual(findings, [])

    def test_small_channel_change_is_not_a_color_swap(self):
        reference = stripes(COLORS, [80, 32, 16, 16, 8, 8])
        candidate = reference + np.uint8(1)
        score, findings, _ = color_score(reference, candidate)
        self.assertGreater(score, 97.0)
        self.assertLess(score, 100.0)
        self.assertEqual(findings, [])

    def test_near_identical_palettes_with_more_colors_than_clusters(self):
        for seed in range(600):
            with self.subTest(seed=seed):
                rng = np.random.default_rng(seed)
                colors = rng.integers(5, 250, size=(7 + seed % 58, 3))
                widths = rng.integers(1, 33, size=len(colors))
                reference = stripes(colors, widths)
                score, findings, measurements = color_score(reference, reference + np.uint8(1))
                self.assertGreater(score, 97.0)
                self.assertLess(score, 100.0)
                self.assertEqual(findings, [])
                self.assertEqual(measurements["certificate"]["missing_mass"], 0.0)
                self.assertEqual(measurements["certificate"]["added_mass"], 0.0)

    def test_independent_partition_review_regressions(self):
        for seed, count in ((74, 9), (78, 15)):
            with self.subTest(seed=seed):
                colors = np.random.default_rng(seed).integers(5, 250, size=(count, 3))
                reference = stripes(colors, [16] * count)
                score, findings, measurements = color_score(reference, reference + np.uint8(1))
                self.assertGreater(score, 97.0)
                self.assertEqual(findings, [])
                self.assertEqual(measurements["certificate"]["missing_mass"], 0.0)
                self.assertEqual(measurements["certificate"]["added_mass"], 0.0)

    def test_dense_palettes_use_the_same_continuous_representation(self):
        for seed in range(60):
            with self.subTest(seed=seed):
                rng = np.random.default_rng(1000 + seed)
                count = 257 + seed * 13 % 512
                reference = stripes(rng.integers(5, 250, size=(count, 3)),
                                    rng.integers(1, 9, size=count))[:16]
                score, findings, measurements = color_score(reference, reference + np.uint8(1))
                self.assertGreater(score, 97.0)
                self.assertLess(score, 100.0)
                self.assertEqual(findings, [])
                self.assertLess(measurements["certificate"]["missing_mass"], 0.005)
                self.assertLess(measurements["certificate"]["added_mass"], 0.005)

    def test_color_gradients_and_channel_boundaries(self):
        for seed in range(40):
            with self.subTest(seed=seed):
                rng = np.random.default_rng(2000 + seed)
                endpoints = rng.integers(0, 256, size=(2, 3))
                reference = np.tile(np.linspace(*endpoints, 256).astype(np.uint8)[None], (16, 1, 1))
                candidate = np.clip(reference.astype(int) + 1, 0, 255).astype(np.uint8)
                score, findings, measurements = color_score(reference, candidate)
                self.assertGreater(score, 97.0)
                self.assertLess(score, 100.0)
                self.assertEqual(findings, [])
                self.assertEqual(measurements["certificate"]["missing_mass"], 0.0)
                self.assertEqual(measurements["certificate"]["added_mass"], 0.0)

    def test_dense_histogram_is_invariant_to_pixel_order_and_crop_origin(self):
        tile = np.random.default_rng(222).integers(5, 250, size=(17, 48, 3), dtype=np.uint8)
        image = np.tile(tile, (4, 1, 1))
        reference = image[:51]
        for offset in (1, 3, 8, 17):
            score, findings, _ = color_score(reference, image[offset:offset + 51])
            self.assertAlmostEqual(score, 100.0, places=6)
            self.assertEqual(findings, [])

    def test_bilinear_color_gradients_do_not_invent_mass_swaps(self):
        x, y = np.meshgrid(np.linspace(0, 1, 64), np.linspace(0, 1, 64))
        for seed in range(30):
            with self.subTest(seed=seed):
                corners = np.random.default_rng(3000 + seed).integers(0, 256, size=(4, 3))
                reference = (
                    (1 - x)[..., None] * (1 - y)[..., None] * corners[0]
                    + x[..., None] * (1 - y)[..., None] * corners[1]
                    + (1 - x)[..., None] * y[..., None] * corners[2]
                    + x[..., None] * y[..., None] * corners[3]
                ).astype(np.uint8)
                candidate = np.clip(reference.astype(int) + 1, 0, 255).astype(np.uint8)
                score, findings, _ = color_score(reference, candidate)
                self.assertGreater(score, 97.0)
                self.assertLess(score, 100.0)
                self.assertEqual(findings, [])
                # A true broad chromatic change on the same rich gradients
                # must remain penalized despite smooth quantization.
                candidate = reference.copy()
                candidate[:, :, 0] = np.minimum(candidate[:, :, 0].astype(int) + 80, 255)
                changed_score, _, _ = color_score(reference, candidate)
                self.assertLess(changed_score, 60.0)

    def test_rare_support_scales_with_fraction_not_centroid_count(self):
        for size in (100, 200, 768):
            scores = []
            for fraction in (0.0001, 0.001, 0.005, 0.0125, 0.05, 0.1):
                with self.subTest(size=size, fraction=fraction):
                    reference = np.full((size, size, 3), 240, dtype=np.uint8)
                    candidate = reference.copy()
                    count = round(size * size * fraction)
                    candidate.reshape(-1, 3)[:count] = COLORS[2]
                    score, findings, _ = color_score(reference, candidate)
                    scores.append(score)
                    self.assertFalse(any(f["type"] == "color_shift" for f in findings))
                    if fraction >= 0.001:
                        self.assertTrue(any(f["type"] == "color_added" for f in findings))
                    if fraction == 0.0001:
                        self.assertGreater(score, 99.0)
                    if fraction == 0.0125:
                        self.assertGreater(score, 60.0)
                        self.assertLess(score, 65.0)
            self.assertTrue(all(a > b for a, b in zip(scores[:4], scores[1:5])))
            # Support saturates at 5%; balanced transport continues to measure
            # distribution changes even when the max-support score plateaus.
            self.assertGreaterEqual(scores[4], scores[5])

    def test_genuine_small_accent_recoloring_controls(self):
        scores = []
        for width in (1, 2, 8, 16):
            reference = stripes([(240, 240, 240), COLORS[2]], [160 - width, width])
            candidate = stripes([(240, 240, 240), (165, 35, 205)], [160 - width, width])
            score, findings, _ = color_score(reference, candidate)
            scores.append(score)
            self.assertLess(score, 90.0)
            self.assertTrue(any(f["type"] == "color_missing" for f in findings))
            self.assertTrue(any(f["type"] == "color_added" for f in findings))
            self.assertTrue(any(f["type"] == "color_shift" for f in findings))
            self.assertFalse(any("shift #f0f0f0" in f["suggested_fix"] for f in findings))
        self.assertTrue(all(a >= b for a, b in zip(scores, scores[1:])))

    def test_recolor_monotonicity_across_representative_rgb_families(self):
        fractions = (.001, .00625, .0125, .025, .05, .1, .2, .4)
        for seed in (88100, 88106, 88108, 88127, 88129, 88177):
            colors = np.random.default_rng(seed).integers(0, 256, (3, 3), dtype=np.uint8)
            scores = []
            for fraction in fractions:
                width = round(8000 * fraction)
                reference = np.repeat(colors[:2], [8000 - width, width], axis=0)[None]
                candidate = np.repeat(colors[[0, 2]], [8000 - width, width], axis=0)[None]
                score, _, _ = color_score(reference, candidate)
                scores.append(score)
            with self.subTest(seed=seed):
                self.assertLess(scores[-1], scores[0] - 10.)
                for before, after in zip(scores, scores[1:]):
                    self.assertLessEqual(after, before + 1e-10)

    def test_original_recolor_family_all_integer_widths_remains_monotonic(self):
        scores = []
        for width in range(1, 161):
            reference = np.repeat(np.array([(240, 240, 240), COLORS[2]], dtype=np.uint8),
                                  [160 - width, width], axis=0)[None]
            candidate = np.repeat(np.array([(240, 240, 240), (165, 35, 205)], dtype=np.uint8),
                                  [160 - width, width], axis=0)[None]
            scores.append(color_score(reference, candidate)[0])
        self.assertLess(scores[-1], 20.)
        self.assertTrue(all(a >= b for a, b in zip(scores, scores[1:])))

    def test_single_pixel_contamination_over_image_sizes(self):
        for size, expected in ((32, 97.602030), (160, 99.988344), (768, 99.999494)):
            with self.subTest(size=size):
                reference = np.full((size, size, 3), 240, dtype=np.uint8)
                candidate = reference.copy()
                candidate[0, 0] = COLORS[2]
                score, findings, _ = color_score(reference, candidate)
                self.assertAlmostEqual(score, expected, places=5)
                if size == 768:
                    self.assertGreater(score, 99.99)
                self.assertFalse(any(f["type"] == "color_shift" for f in findings))

    def test_missing_accent_does_not_prescribe_recoloring_unchanged_background(self):
        reference = stripes([(240, 240, 240), COLORS[2]], [158, 2])
        candidate = stripes([(240, 240, 240)], [160])
        score, findings, _ = color_score(reference, candidate)
        self.assertLess(score, 90.0)
        self.assertTrue(any(f["type"] == "color_missing" for f in findings))
        self.assertFalse(any(f["type"] == "color_shift" for f in findings))
        self.assertFalse(any("shift #f0f0f0" in f["suggested_fix"] for f in findings))

    def test_near_identical_continuous_gray_gradient(self):
        ramp = np.tile(np.arange(256, dtype=np.uint8), (160, 1))
        reference = np.repeat(ramp[:, :, None], 3, axis=2)
        candidate = np.minimum(reference.astype(int) + 1, 255).astype(np.uint8)
        score, findings, _ = color_score(reference, candidate)
        self.assertGreater(score, 97.0)
        self.assertLess(score, 100.0)
        self.assertEqual(findings, [])

    def test_missing_rare_accent_among_six_colors(self):
        reference = stripes(COLORS, [80, 32, 2, 16, 16, 14])
        candidate = stripes(COLORS[:2] + COLORS[3:], [82, 32, 16, 16, 14])
        score, findings, _ = color_score(reference, candidate)
        # Versioned proxy metric anchor. The missing 1.25% accent remains actionable.
        self.assertAlmostEqual(score, 91.494002, places=5)
        self.assertTrue(any(f["type"] == "color_missing" for f in findings))

    def test_material_color_change_near_existing_support_has_conservative_findings(self):
        reference = stripes(COLORS, [80, 32, 16, 16, 8, 8])
        candidate = stripes(COLORS[:2] + [(165, 35, 205)] + COLORS[3:],
                            [80, 32, 16, 16, 8, 8])
        score, findings, measurements = color_score(reference, candidate)
        self.assertLess(score, 80.0)
        self.assertEqual({f["type"] for f in findings}, {"color_missing"})
        self.assertAlmostEqual(measurements["certificate"]["missing_mass"], .1, places=12)
        self.assertEqual(measurements["certificate"]["added_mass"], 0.)
        self.assertGreater(measurements["weighted_coverage_distance"], 1.)

    def test_missing_and_added_rare_accent_are_not_hidden_by_mass_weighting(self):
        accent = stripes(COLORS[:3], [126, 32, 2])
        plain = stripes(COLORS[:2], [128, 32])
        forward, findings, _ = color_score(accent, plain)
        reverse, reverse_findings, _ = color_score(plain, accent)
        # Migrated from the old CIEDE anchor 79.345413, without changing symmetry or findings.
        self.assertAlmostEqual(forward, 78.353378, places=5)
        self.assertAlmostEqual(forward, reverse, places=6)
        self.assertTrue(any(f["type"] == "color_missing" for f in findings))
        self.assertTrue(any(f["type"] == "color_added" for f in reverse_findings))

    def test_same_colors_with_different_mass_are_penalized(self):
        reference = stripes(COLORS[:2], [80, 80])
        scores = []
        for widths in ([80, 80], [88, 72], [96, 64], [128, 32]):
            score, findings, _ = color_score(reference, stripes(COLORS[:2], widths))
            scores.append(score)
        self.assertAlmostEqual(scores[0], 100.0, places=6)
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        self.assertGreater(scores[2], scores[3])
        self.assertLess(scores[2], 70.0)
        self.assertTrue(any(f["type"] == "color_distribution" for f in findings))

    def test_major_mass_swap_is_not_perfect_because_colors_still_exist(self):
        reference = stripes(COLORS[:2], [128, 32])
        candidate = stripes(COLORS[:2], [32, 128])
        score, findings, _ = color_score(reference, candidate)
        self.assertLess(score, 10.0)
        self.assertTrue(any(f["type"] == "color_distribution" for f in findings))

    def test_solid_recoloring_keeps_versioned_proxy_separation(self):
        score, findings, measurements = color_score(
            stripes([COLORS[2]], [160]), stripes([COLORS[3]], [160])
        )
        self.assertAlmostEqual(score, 8.544270, places=5)
        self.assertTrue(any(f["type"] == "color_shift" for f in findings))
        self.assertGreater(measurements["distance"], 40.0)

    def test_equal_mass_spatial_swap_remains_color_invariant(self):
        score, findings, _ = color_score(
            stripes(COLORS[2:4], [80, 80]), stripes(COLORS[3:1:-1], [80, 80])
        )
        self.assertAlmostEqual(score, 100.0, places=6)
        self.assertEqual(findings, [])

    def test_deterministic_and_symmetric(self):
        reference = calendar_grid()[8:472]
        candidate = np.clip(reference.astype(int) + 3, 0, 255).astype(np.uint8)
        first = color_score(reference, candidate)
        self.assertGreater(first[0], 85.0)
        self.assertLess(first[0], 100.0)
        self.assertEqual(first, color_score(reference, candidate))
        self.assertAlmostEqual(first[0], color_score(candidate, reference)[0], places=6)


if __name__ == "__main__":
    unittest.main()
