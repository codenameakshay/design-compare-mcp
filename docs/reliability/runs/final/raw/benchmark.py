#!/usr/bin/env python3
"""Public synthetic comparison benchmark. See docs/reliability/README.md.

No existing screenshots are read. Each implementation runs in a fresh process
from an immutable source snapshot, using this script's Python and dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import itertools
import json
import os
import platform
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_VERSION = "v5"
GENERATOR = (
    f"calendar-motion-and-color-controls-{GENERATOR_VERSION}; Pillow drawing, integer coordinates, "
    "NumPy default_rng(74) for nine-stripe colors; exact new256color boundary histograms; "
    "review3 common-pixel transport and shortlist controls"
)
REVIEW3_CASE_PREFIXES = ("color_transport256_", "color_shortlist32_")
THREAD_ENV = {key: "1" for key in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
)}
THREAD_ENV["PYTHONHASHSEED"] = "0"


def generator_version(generator: str) -> str:
    for version in ("v3", "v4", GENERATOR_VERSION):
        if generator.startswith(f"calendar-motion-and-color-controls-{version};"):
            return version
    raise ValueError(f"Unsupported fixture generator: {generator}")


def canonical_cases_for_generator(cases: list[dict], generator: str) -> list[dict]:
    version = generator_version(generator)
    excluded = REVIEW3_CASE_PREFIXES if version in ("v3", "v4") else ()
    if version == "v3":
        excluded += ("color_new256color_",)
    return [case for case in cases if not case["id"].startswith(excluded)]


def assertions_for_generator(rows: dict, generator: str) -> list[dict]:
    version = generator_version(generator)
    return assertions(rows, include_boundary=version != "v3",
                      include_review3=version == GENERATOR_VERSION,
                      legacy_execution_observation=version == "v3")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def source_manifest(root: Path) -> dict:
    files = sorted((root / "worker" / "vision_worker").rglob("*.py"))
    files.append(root / "worker" / "pyproject.toml")
    hashes = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in files}
    return {"sha256": sha(encoded(hashes)), "files": hashes}


def generate_fixtures(out: Path) -> tuple[list[dict], dict]:
    import numpy as np
    from PIL import Image, ImageDraw

    fixtures = {}
    cases = []

    def save(name, image):
        relative = f"fixtures/{name}.png"
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, optimize=False, compress_level=9)
        pixels = np.asarray(image)
        fixtures[relative] = {
            "sha256": sha(path.read_bytes()), "pixels_sha256": sha(pixels.tobytes()),
            "shape": list(pixels.shape), "mode": image.mode,
        }
        return relative

    def case(name, reference, candidate, description, *, kind="screen", **params):
        cases.append({
            "id": name, "kind": kind, "description": description,
            "reference": reference, "candidate": candidate,
            "params": {"return_visuals": False, **params},
        })

    background = (245, 246, 250)
    accents = [(73, 105, 218), (214, 85, 112), (39, 151, 135),
               (232, 169, 60), (142, 93, 191), (48, 150, 202), (219, 116, 57)]

    def calendar(*, recolor=False, missing=False, header=True):
        im = Image.new("RGB", (384, 320), background)
        d = ImageDraw.Draw(im)
        if header:
            d.rectangle((16, 12, 367, 73), fill=(27, 35, 63))
            d.ellipse((27, 24, 63, 60), fill=(232, 169, 60))
            d.rectangle((77, 27, 196, 32), fill=(239, 243, 255))
            d.rectangle((77, 42, 154, 46), fill=(150, 165, 200))
            d.rectangle((320, 30, 350, 52), fill=(73, 105, 218))
        for row in range(4):
            for col in range(7):
                x, y = 17 + col * 50, 88 + row * 53
                d.rectangle((x, y, x + 45, y + 47), fill=(255, 255, 255),
                            outline=(219, 224, 235))
                d.rectangle((x + 5, y + 6, x + 9 + (row + col) % 5, y + 8),
                            fill=(70, 77, 94))
                color = accents[(row * 3 + col) % len(accents)]
                if recolor and color == accents[0]:
                    color = (224, 48, 55)
                if not missing or (row * 3 + col) % len(accents) != 0:
                    d.rectangle((x + 4, y + 18, x + 40, y + 27), fill=color)
                    d.rectangle((x + 4, y + 31, x + 29, y + 35), fill=color)
        return im

    ref = calendar()
    ref_path = save("calendar-reference", ref)
    case("screen_identical", ref_path, ref_path, "Identical full generated UI.")
    for offset in (-2, -1, 1, 2):
        shifted = Image.new("RGB", ref.size, background)
        shifted.paste(ref, (offset, -offset))
        path = save(f"calendar-translation-{offset:+d}", shifted)
        case(f"translation_{offset:+d}", ref_path, path,
             f"Translate content dx={offset}, dy={-offset} input pixels; exposed border is background.")
        box = (abs(offset), abs(offset), 384, 320) if offset > 0 else (
            0, 0, 384 - abs(offset), 320 - abs(offset))
        path = save(f"calendar-crop-{offset:+d}", ref.crop(box))
        case(f"crop_{offset:+d}", ref_path, path,
             f"Crop {abs(offset)} input pixels from {'left/top' if offset > 0 else 'right/bottom'}; normal width normalization still applies.")
    case("accent_recolored", ref_path, save("calendar-recolored", calendar(recolor=True)),
         "Replace all blue calendar accents with red; preserve geometry and other colors.")
    case("accent_missing", ref_path, save("calendar-missing-accent", calendar(missing=True)),
         "Remove all blue calendar accents, leaving their white card backgrounds.")

    def color_control(name, image):
        path = save(name, image)
        colors, counts = np.unique(np.asarray(image).reshape(-1, 3), axis=0, return_counts=True)
        histogram = [{"rgb": color.tolist(), "pixels": int(count)}
                     for color, count in zip(colors, counts)]
        fixtures[path]["rgb_histogram"] = histogram
        fixtures[path]["rgb_histogram_sha256"] = sha(encoded(histogram))
        return path

    def mass_stripes(light_width):
        im = Image.new("RGB", (768, 160), (28, 28, 32))
        ImageDraw.Draw(im).rectangle((0, 0, light_width - 1, 159), fill=(246, 246, 246))
        return color_control(f"color-mass-light-width-{light_width}", im)

    mass_paths = {width: mass_stripes(width) for width in (384, 432, 480, 624, 144)}
    for suffix, width in (("50", 384), ("56_25", 432), ("62_5", 480), ("81_25", 624)):
        case(f"color_mass_50_to_{suffix}", mass_paths[384], mass_paths[width],
             f"Same two RGB colors, light coverage 50% to {width / 768 * 100:g}%. "
             "Canonical-width input and exact old sampling boundaries isolate mass changes; widget mode skips registration.",
             mode="widget")
    case("color_mass_81_25_to_18_75", mass_paths[624], mass_paths[144],
         "Same two RGB colors, light coverage 81.25% to 18.75%. A major visible mass swap, not recoloring.",
         mode="widget")

    # Each 480px crop contains ten complete 48px periods, at every origin.
    tile = Image.new("RGB", (768, 48), (250, 250, 250))
    draw = ImageDraw.Draw(tile)
    periodic_colors = [(163, 211, 38), (250, 175, 35), (250, 48, 45),
                       (30, 30, 30), (234, 234, 234)]
    for col, x in enumerate(range(12, 740, 45)):
        draw.rounded_rectangle((x, 5, x + 32, 40), radius=5,
                               fill=periodic_colors[col % len(periodic_colors)])
        draw.text((x + 7, 15), str(col + 1), fill=(65, 65, 65))
    periodic = Image.new("RGB", (768, 528))
    for y in range(0, 528, 48):
        periodic.paste(tile, (0, y))
    periodic_paths = {shift: color_control(f"color-periodic-crop-{shift}px",
                                          periodic.crop((0, shift, 768, 480 + shift)))
                      for shift in range(5)}
    for shift, path in periodic_paths.items():
        case(f"color_periodic_crop_{shift}px", periodic_paths[0], path,
             f"Crop ten complete 48px periods from origin y={shift}. Exact RGB histogram is unchanged; "
             "canonical width avoids normalization interpolation. Only color invariance is expected, not identical layout/overall.",
             mode="widget")

    stripe_colors = np.random.default_rng(74).integers(5, 250, size=(9, 3))
    stripe_rgb = np.repeat(np.repeat(stripe_colors[None, :, :], 16, axis=1), 160, axis=0)
    case("color_nine_stripes_rgb_plus_one",
         color_control("color-nine-stripes-reference", Image.fromarray(stripe_rgb.astype(np.uint8))),
         color_control("color-nine-stripes-rgb-plus-one", Image.fromarray((stripe_rgb + 1).astype(np.uint8))),
         "Nine seeded RGB stripes, each 16px wide and 160px high; candidate adds one to every RGB channel. "
         "The 144px-wide inputs exercise normal public pipeline upscaling, not direct metric calls.",
         mode="widget")
    gray_rgb = np.full((768, 768, 3), 240, dtype=np.uint8)
    gray_path = color_control("color-gray-240-reference", Image.fromarray(gray_rgb))
    speck_rgb = gray_rgb.copy()
    speck_rgb[384, 384] = (210, 45, 65)
    case("color_single_red_pixel", gray_path,
         color_control("color-gray-single-red-pixel", Image.fromarray(speck_rgb)),
         "One red RGB(210,45,65) pixel on a 768x768 RGB(240,240,240) canvas. "
         "Negligible contamination must not act like a dominant palette change.", mode="widget")
    accent_rgb = gray_rgb.copy()
    # Round 1.25% to the nearest whole pixel and place a contiguous 96px-wide patch.
    accent_pixels = round(gray_rgb.shape[0] * gray_rgb.shape[1] * .0125)
    accent_rows, accent_remainder = divmod(accent_pixels, 96)
    accent_rgb[96:96 + accent_rows, 96:192] = (210, 45, 65)
    accent_rgb[96 + accent_rows, 96:96 + accent_remainder] = (210, 45, 65)
    case("color_small_red_accent_missing",
         color_control("color-gray-small-red-accent", Image.fromarray(accent_rgb)), gray_path,
         f"Remove a contiguous {accent_pixels}-pixel red RGB(210,45,65) accent, approximately 1.25% "
         "of a 768x768 gray canvas. This meaningful accent must remain distinct from one-pixel contamination.",
         mode="widget")
    # Repeated rows preserve exact background counts across crop origins.
    # The five full accent rows occupy exactly 5% of either 100-row crop.
    boundary_colors = np.array(list(itertools.product(range(237, 244), repeat=3)),
                               dtype=np.uint8)[:255]
    boundary_row = np.tile(boundary_colors, (4, 1))[:768]
    boundary_cand = np.tile(boundary_row[None, :, :], (101, 1, 1))
    boundary_ref = boundary_cand.copy()
    boundary_ref[10:100:20] = (210, 45, 65)
    for perturb in (False, True):
        ref_pixels, cand_pixels = boundary_ref.copy(), boundary_cand.copy()
        if perturb:
            # Both sides gain the same previously absent background RGB value.
            ref_pixels[0, 10, 0] -= 1
            cand_pixels[0, 10, 0] -= 1
        for origin in (0, 1):
            suffix = f"{'common_pixel' if perturb else 'clean'}_crop_{origin}px"
            case(f"color_new256color_{suffix}",
                 color_control(f"color-new256color-{suffix}-reference",
                               Image.fromarray(ref_pixels[origin:origin + 100])),
                 color_control(f"color-new256color-{suffix}-candidate",
                               Image.fromarray(cand_pixels[origin:origin + 100])),
                 "Remove exactly 3840 red RGB(210,45,65) pixels, 5% of a 768x100 canvas, "
                 f"against 255 near-white background colors; crop origin y={origin}. "
                 + ("The same one-level background-pixel perturbation at source [0,10,0] "
                    "is included only at origin 0, crossing the reference's 256-color cutoff. "
                    if perturb else "No background perturbation. ")
                 + "Repeated rows keep all other exact RGB counts unchanged; canonical width and widget mode avoid resampling/registration.",
                 mode="widget")

    transport_centers = np.array([
        [60, 60, 60], [220, 220, 220], [210, 50, 50],
        [50, 180, 50], [50, 50, 210], [200, 180, 50],
    ])
    transport_offsets = [[35, 0, 0], [-35, 0, 0], [0, 35, 0], [0, -35, 0]]
    transport_colors = np.array([c + o for c in transport_centers for o in transport_offsets],
                                dtype=np.uint8)
    extra = np.random.default_rng(987).integers(0, 256, (256, 3), dtype=np.uint8)
    extra = np.array([c for c in extra if not np.any(np.all(c == transport_colors, axis=1))])[:232]
    transport_colors = np.vstack((transport_colors, extra))

    def transport_image(weights):
        return np.vstack((np.repeat(transport_colors, weights, axis=0),
                          np.tile(transport_colors[-1], (236, 1)))).reshape(10, 768, 3)

    transport_ref = transport_image(np.r_[np.tile([600, 600, 1, 1], 6), np.ones(232, int)])
    transport_cand = transport_image(np.r_[np.tile([1, 1, 600, 600], 6), np.ones(232, int)])
    for perturb in (False, True):
        ref_pixels, cand_pixels = transport_ref.copy(), transport_cand.copy()
        if perturb:
            ref_pixels[-1, -1, 0] += 1
            cand_pixels[-1, -1, 0] += 1
        variant = "common_pixel" if perturb else "clean"
        case(f"color_transport256_{variant}",
             color_control(f"color-transport256-{variant}-reference", Image.fromarray(ref_pixels)),
             color_control(f"color-transport256-{variant}-candidate", Image.fromarray(cand_pixels)),
             "Same exact RGB support on both sides, but swap [600,600,1,1] to [1,1,600,600] "
             "pixel weights within each of six four-color groups; 232 seeded extra colors and 236 tail pixels. "
             + ("Add one to the red channel of the last pixel on both sides, crossing 256 to 257 colors. "
                if perturb else "Both sides contain 256 colors. ")
             + "The real mass mismatch must remain visible without invented missing/added colors; "
             "768x10 widget inputs avoid resampling and registration.", mode="widget")

    shortlist_rgb = np.random.default_rng(31025).integers(0, 256, (24000, 3), dtype=np.uint8)
    shortlist_ids = [
        22025, 13085, 14531, 17604, 21105, 13118, 4446, 8124,
        8005, 16966, 2433, 20792, 22388, 532, 8532, 13856,
        20344, 21295, 23242, 16360, 10291, 7393, 21591, 2270,
        11335, 1901, 1175, 8730, 953, 21263, 21465, 13393,
    ]
    shortlist_ref = np.vstack((np.tile(shortlist_rgb[shortlist_ids[0]], (72930, 1)),
                               shortlist_rgb[shortlist_ids[1:31]],
                               np.tile(shortlist_rgb[5], (3840, 1)))).reshape(100, 768, 3)
    shortlist_cand = shortlist_ref.copy()
    shortlist_cand.reshape(-1, 3)[-3840:] = shortlist_rgb[17292]
    for perturb in (False, True):
        ref_pixels, cand_pixels = shortlist_ref.copy(), shortlist_cand.copy()
        if perturb:
            ref_pixels[0, 0] = cand_pixels[0, 0] = shortlist_rgb[shortlist_ids[-1]]
        variant = "common_pixel" if perturb else "clean"
        case(f"color_shortlist32_{variant}",
             color_control(f"color-shortlist32-{variant}-reference", Image.fromarray(ref_pixels)),
             color_control(f"color-shortlist32-{variant}-candidate", Image.fromarray(cand_pixels)),
             "Keep the same 5% accent difference, seeded RGB[5] versus RGB[17292], on a shared background "
             "with 30 singleton colors from default_rng(31025). "
             + ("Replace background pixel [0,0] with the same RGB[13393] on both sides, crossing 32 to 33 colors. "
                if perturb else "Both sides contain 32 colors. ")
             + "Existing perceptual counterparts must not become a false missing/added accent at the shortlist cutoff; "
             "768x100 widget inputs avoid resampling and registration.", mode="widget")
    omitted = calendar(header=False)
    omitted_path = save("calendar-omitted-header-avatar", omitted)
    case("header_omitted_full", ref_path, omitted_path,
         "Header and avatar absent; full images remain in scope. Not a palette-only control.")
    scope = (0, 80, 384, 320)
    scoped_ref = save("calendar-scoped-reference", ref.crop(scope))
    scoped_cand = save("calendar-scoped-candidate", omitted.crop(scope))
    case("header_omitted_scoped", scoped_ref, scoped_cand,
         "Caller explicitly crops BOTH images to [0,80,384,320], using widget mode. Header/avatar are out of scope, not recovered.",
         mode="widget")
    case("header_omitted_ignored", ref_path, omitted_path,
         "Caller explicitly ignores [0,0,384,80] in original reference pixels.",
         ignore_regions=[[0, 0, 384, 80]])
    case("scope_all_ignored", ref_path, omitted_path,
         "Entire textured image ignored with equal modal edge fills. Legacy high score is not retained evidence.",
         mode="widget", ignore_regions=[[0, 0, 384, 320]])
    edge_ref = Image.new("RGB", (192, 128), (255, 255, 255))
    edge_cand = Image.new("RGB", edge_ref.size, (0, 0, 0))
    for im in (edge_ref, edge_cand):
        ImageDraw.Draw(im).rectangle((40, 30, 151, 97), fill=(70, 120, 190))
    case("scope_all_ignored_different_fill", save("scope-white-edge", edge_ref),
         save("scope-black-edge", edge_cand),
         "Entire textured image ignored with different per-image fills. Legacy low score is also no retained evidence.",
         mode="widget", ignore_regions=[[0, 0, 192, 128]])
    flat_ref = save("ecc-flat-reference", Image.new("RGB", (192, 128), (32, 42, 60)))
    flat_cand = save("ecc-flat-candidate", Image.new("RGB", (192, 128), (224, 201, 180)))
    case("ecc_failure", flat_ref, flat_cand,
         "Constant images make ECC undefined. Identity fallback must remain visible; not a quality success.")
    case("flat_identical_screen", flat_ref, flat_ref,
         "Identical solid inputs still need a near-uniform observation, not an unresolved-alignment or failed-capture claim.")
    case("flat_identical_widget", flat_ref, flat_ref,
         "Identical solid widget deliberately uses identity. No unresolved-alignment warning is appropriate.", mode="widget")
    for name, params in (
        ("settings_dark_ui", {"preset": "dark-ui"}),
        ("settings_custom_weights", {"weights": {"color": 0.7, "layout": 0.1}}),
        ("settings_widget", {"mode": "widget"}),
    ):
        case(name, ref_path, omitted_path,
             "Same full omitted-header pair, different explicit comparison settings for provenance checks.", **params)
    for revision in (1, 2):
        protocol = {"scope": "generated-calendar-full", "capture": "fixed-generated-pair",
                    "revision": revision, "declared_exclusions": []}
        case(f"settings_context_v{revision}", ref_path, omitted_path,
             "Same pair with caller-declared protocol metadata. Metadata must not change numeric scores; protocol changes split comparison keys.",
             comparison_context={"scopeId": "generated-calendar-full", "protocolKey": sha(encoded(protocol))})
        cases[-1]["context_manifest"] = protocol
    case("latency_screen_visuals", ref_path, ref_path,
         "Representative full-screen call including visual generation; payload bytes are hashed, not embedded.",
         return_visuals=True)

    def frames(name, positions):
        result = []
        for i, x in enumerate(positions):
            im = Image.new("L", (100, 50), 20)
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, 99, 3), fill=65)
            d.rectangle((x, 20, x + 15, 29), fill=240)
            result.append(save(f"motion-{name}-{i:02d}", im))
        return result

    positions = [8, 9, 9, 13, 13, 15, 15, 23, 23]
    motion_ref = frames("reference", positions)
    shifted_positions = [8, 8, 9, 9, 13, 13, 15, 15, 23]
    for name, candidate, description in (
        ("motion_identical", motion_ref, "Identical nonconstant sampled motion profiles, equal lengths."),
        ("motion_reversed", frames("reversed", positions[::-1]),
         "Reverse frame order. Same mean energy, different sampled rhythm; no capture timestamps are claimed."),
        ("motion_shifted", frames("shifted", shifted_positions),
         "Shift the change profile by one frame. Same mean energy, opposite sampled rhythm."),
        ("motion_unequal", frames("unequal", positions + [24, 24, 28, 28]),
         "Candidate shares a prefix but has four extra frames. Do not claim timing fidelity from truncation."),
        ("motion_static", frames("static", [8] * 9),
         "Moving reference versus stationary, nonblank candidate."),
    ):
        case(name, motion_ref, candidate, description, kind="motion")
    case("motion_both_static", frames("static", [8] * 9), frames("static", [8] * 9),
         "Neither side moves. A null motion score is inconclusive, not perfect fidelity.", kind="motion")
    # One overview is for publication only and never passed to a metric.
    examples = [("Reference", ref), ("+2px translation", Image.open(out / "fixtures/calendar-translation-+2.png")),
                ("Recolored accent", calendar(recolor=True)), ("Missing accent", calendar(missing=True)),
                ("Omitted header/avatar", omitted), ("Explicit comparable crop", ref.crop(scope))]
    sheet = Image.new("RGB", (3 * 400, 2 * 352), (231, 234, 240))
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(examples):
        x, y = (i % 3) * 400, (i // 3) * 352
        draw.text((x + 8, y + 7), label, fill=(20, 28, 45))
        sheet.paste(im, (x + 8, y + 26))
    save("examples", sheet)
    sheet = Image.new("RGB", (784, 4 * 194), (231, 234, 240))
    draw = ImageDraw.Draw(sheet)
    for i, (label, path, box) in enumerate((
        ("Same colors: 50% light", mass_paths[384], None),
        ("Real mass change: 81.25% light", mass_paths[624], None),
        ("Periodic reference: first 144 rows shown", periodic_paths[0], (0, 0, 768, 144)),
        ("Same histogram: crop origin +2px, first 144 rows shown", periodic_paths[2], (0, 0, 768, 144)),
    )):
        draw.text((8, i * 194 + 7), label, fill=(20, 28, 45))
        with Image.open(out / path) as im:
            sheet.paste(im.crop(box) if box else im, (8, i * 194 + 26))
    save("color-controls-examples", sheet)
    return cases, fixtures


def summarize(result: dict) -> dict:
    return {
        "overall": result.get("overall"),
        "scores": {k: v.get("score") for k, v in result.get("subscores", {}).items()},
        "metric_statuses": {k: v.get("status") for k, v in result.get("subscores", {}).items()},
        "alignment": result.get("alignment"),
        "motion_score": result.get("motion_score"),
        "motion_status": result.get("motion_status"),
        "energy_ratio": result.get("energy_ratio"),
        "motion_energy_score": result.get("motion_energy_score"),
        "motion_score_meaning": result.get("motion_score_meaning"),
        "temporal_corr": result.get("temporal_corr"),
        "timing_diagnostics": result.get("timing_diagnostics"),
        "provenance": result.get("provenance"),
        "diagnostics": result.get("diagnostics"),
        "canvas": result.get("canvas"),
        "preset": result.get("preset"),
        "weights": result.get("weights"),
        "finding_types": [f.get("type") for f in result.get("cv_findings", [])],
    }


def internal_runner() -> int:
    request = json.load(sys.stdin)
    source = Path(request["source"])
    sys.path.insert(0, str(source / "worker"))
    import cv2
    import numpy as np
    import vision_worker
    from vision_worker.pipeline import compare, compare_motion
    import inspect

    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    inputs = Path(request["inputs"])
    env = {
        "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
        "machine": platform.machine(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
        "dependencies": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
                         if d.metadata.get("Name")},
        "numpy": np.__version__, "opencv": cv2.__version__, "opencv_threads": cv2.getNumThreads(),
        "thread_environment": {key: os.environ.get(key) for key in THREAD_ENV},
        "worker_version": vision_worker.__version__,
        "worker_module": str(Path(vision_worker.__file__).relative_to(source)),
        "source_manifest": source_manifest(source),
    }
    rows = {}
    for case in request["cases"]:
        def paths(value):
            return [str(inputs / p) for p in value] if isinstance(value, list) else str(inputs / value)

        fn = compare_motion if case["kind"] == "motion" else compare
        unsupported = [key for key in case["params"] if key == "comparison_context"
                       and key not in inspect.signature(fn).parameters]
        effective_params = {key: value for key, value in case["params"].items() if key not in unsupported}
        kwargs = {"reference": paths(case["reference"]), "candidate": paths(case["candidate"]),
                  **effective_params}
        trials, errors, warmups = [], [], []
        for i in range(request["warmups"] + request["repeats"]):
            start = time.perf_counter_ns()
            try:
                result = fn(**kwargs)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                for visual in result.get("visuals", []):
                    import base64
                    payload = base64.b64decode(visual.pop("base64"))
                    visual.update({"bytes": len(payload), "sha256": sha(payload)})
                trial = {"elapsed_ms": elapsed, "result": result,
                         "result_sha256": sha(encoded(result))}
                (warmups if i < request["warmups"] else trials).append(trial)
            except Exception as exc:
                errors.append({"trial": i, "warmup": i < request["warmups"],
                               "type": type(exc).__name__, "message": str(exc)})
        times = [t["elapsed_ms"] for t in trials]
        rows[case["id"]] = {
            "status": "error" if errors or trial_failures({"warmups": warmups, "trials": trials}) else "ok", "errors": errors,
            "unsupported_metadata_params": unsupported, "effective_params": effective_params,
            "result": trials[0]["result"] if trials else None,
            "stable_results": len({t["result_sha256"] for t in trials}) == 1 if trials else False,
            "warmups": warmups, "trials": trials,
            "latency": {"unit": "ms", "samples": times, "n": len(times),
                        "median": statistics.median(times) if times else None,
                        "min": min(times) if times else None, "max": max(times) if times else None},
        }
    env["loaded_worker_files"] = {
        name: str(Path(module.__file__).relative_to(source))
        for name, module in sys.modules.items()
        if (name == "vision_worker" or name.startswith("vision_worker.")) and getattr(module, "__file__", None)
    }
    json.dump({"environment": env, "cases": rows}, sys.stdout, allow_nan=False)
    return 0


def trial_failures(row: dict) -> list[dict]:
    """Inspect every retained API result, including discarded warmup calls."""
    failures = []
    for phase in ("warmups", "trials"):
        for index, trial in enumerate(row.get(phase, [])):
            result = trial.get("result")
            if not isinstance(result, dict) or not result:
                failures.append({"phase": phase, "index": index, "error": "Missing API result"})
                continue
            metrics = {name: sub for name, sub in result.get("subscores", {}).items()
                       if sub.get("status") in ("failed", "error")
                       or sub.get("measurements", {}).get("error")}
            if metrics or result.get("error") or result.get("status") in ("failed", "error"):
                failures.append({"phase": phase, "index": index, "metrics": metrics,
                                 "error": result.get("error")})
    return failures


def assertions(rows: dict, *, include_boundary=True, include_review3=True,
               legacy_execution_observation=False) -> list[dict]:
    checks = []

    def check(name, passed, observed, expectation):
        checks.append({"id": name, "passed": bool(passed), "observed": observed,
                       "expectation": expectation})

    def result(name):
        return rows.get(name, {}).get("result") or {}

    def score(name, dim):
        return result(name).get("subscores", {}).get(dim, {}).get("score")

    for name, row in rows.items():
        failed = trial_failures(row)
        check(f"{name}_executes", row["status"] == "ok" and not row["errors"] and not failed,
              {"errors": row["errors"], "failed_metrics" if legacy_execution_observation else "failed_trials": failed},
              "No worker or metric errors." if legacy_execution_observation
              else "No worker or metric errors in any warmup or measured call.")
    jitter_names = [k for k in rows if k.startswith(("translation_", "crop_"))]
    jitter = {k: score(k, "color") for k in jitter_names}
    controls = {k: score(k, "color") for k in ("accent_recolored", "accent_missing")}
    available = all(isinstance(v, (float, int)) for v in [*jitter.values(), *controls.values()])
    check("color_jitter_above_real_changes", available and min(jitter.values()) > max(controls.values()) + 2,
          {"jitter": jitter, "controls": controls},
          "Every 1/2px crop/translation color score exceeds both real accent-change scores by >2 points.")
    identical = score("screen_identical", "color")
    check("color_identical_high", identical is not None and identical >= 99, identical,
          "An identical image has color score >=99.")
    mass_names = [f"color_mass_50_to_{suffix}" for suffix in ("50", "56_25", "62_5", "81_25")]
    mass = {name: score(name, "color") for name in mass_names}
    values = list(mass.values())
    check("color_mass_change_monotonic", all(isinstance(v, (int, float)) for v in values)
          and values[0] >= 99 and all(a > b + 1 for a, b in zip(values, values[1:])), mass,
          "Increasing same-color coverage changes lower color similarity by >1 point per step; identical coverage scores >=99.")
    major = score("color_mass_81_25_to_18_75", "color")
    check("color_major_mass_swap_detected", isinstance(major, (int, float)) and major < 25,
          major, "A 62.5 percentage-point same-color mass swap has color score <25, not a perfect palette match.")
    for name in ("color_mass_50_to_81_25", "color_mass_81_25_to_18_75"):
        types = [f.get("type") for f in result(name).get("cv_findings", [])]
        check(f"{name}_distribution_finding", "color_distribution" in types, types,
              "A major same-color coverage change produces a public color_distribution finding.")
    periodic = {f"color_periodic_crop_{shift}px": score(f"color_periodic_crop_{shift}px", "color")
                for shift in range(5)}
    values = list(periodic.values())
    check("color_periodic_crop_stable", all(isinstance(v, (int, float)) for v in values)
          and min(values) >= 99 and max(values) - min(values) < 1, periodic,
          "Equal-histogram periodic crops keep color similarity >=99 with <1 point spread; no overall/layout claim.")
    shifted = score("color_nine_stripes_rgb_plus_one", "color")
    check("color_one_level_rgb_shift_high", isinstance(shifted, (int, float)) and shifted >= 95,
          shifted, "A one-level RGB shift across nine stripes keeps color similarity >=95 despite independent palette clustering.")
    speck = score("color_single_red_pixel", "color")
    check("color_single_pixel_contamination_negligible", isinstance(speck, (int, float)) and speck >= 99,
          speck, "One changed pixel among 589824 keeps color similarity >=99; it is not a dominant accent.")
    missing_accent = score("color_small_red_accent_missing", "color")
    check("color_small_accent_distinct_from_speck", isinstance(missing_accent, (int, float))
          and isinstance(speck, (int, float)) and missing_accent < 95 and speck > missing_accent + 5,
          {"single_pixel": speck, "missing_accent": missing_accent},
          "Removing about 1.25% red accent scores <95 and >5 points below one-pixel contamination; noise tolerance must not hide accents.")
    if include_boundary:
        boundary = {f"{variant}_crop_{origin}px": score(f"color_new256color_{variant}_crop_{origin}px", "color")
                    for variant in ("clean", "common_pixel") for origin in (0, 1)}
        for variant in ("clean", "common_pixel"):
            values = [boundary[f"{variant}_crop_{origin}px"] for origin in (0, 1)]
            check(f"color_new256color_{variant}_crop_stable",
                  all(isinstance(v, (int, float)) for v in values) and max(values) - min(values) < 1,
                  dict(zip(("crop_0px", "crop_1px"), values)),
                  "Moving the crop origin by one row keeps color scores within <1 point; the missing 5% red accent is unchanged.")
        values = list(boundary.values())
        check("color_new256color_common_pixel_stable",
              all(isinstance(v, (int, float)) for v in values) and max(values) - min(values) < 1,
              boundary, "Adding/removing the same single background pixel on both sides keeps all four color scores within <1 point.")
        findings = {name: [f.get("type") for f in result(f"color_new256color_{name}").get("cv_findings", [])]
                    for name in boundary}
        check("color_new256color_missing_accent_detected",
              all(isinstance(v, (int, float)) and v < 95 for v in values)
              and all("color_missing" in types for types in findings.values()),
              {"scores": boundary, "finding_types": findings},
              "All four unchanged 5% missing-red-accent comparisons score <95 and retain a public color_missing finding.")
    if include_review3:
        for prefix, description in (("color_transport256", "same-support mass mismatch"),
                                    ("color_shortlist32", "unchanged 5% accent difference")):
            scores = {variant: score(f"{prefix}_{variant}", "color")
                      for variant in ("clean", "common_pixel")}
            values = list(scores.values())
            check(f"{prefix}_common_pixel_stable",
                  all(isinstance(v, (int, float)) for v in values) and max(values) - min(values) < 1,
                  scores, f"A shared background-pixel edit keeps the {description} color scores within <1 point.")
            findings = {variant: [f.get("type") for f in result(f"{prefix}_{variant}").get("cv_findings", [])
                                  if f.get("area") == "color"] for variant in scores}
            no_invented_support = all(not {"color_missing", "color_added"}.intersection(types)
                                      for types in findings.values())
            if prefix == "color_transport256":
                check("color_transport256_mass_retained",
                      all(isinstance(v, (int, float)) and v < 90 for v in values)
                      and all("color_distribution" in types for types in findings.values()) and no_invented_support,
                      {"scores": scores, "finding_types": findings},
                      "Both same-support mass swaps score <90 and retain color_distribution without invented color_missing/color_added findings.")
            else:
                check("color_shortlist32_no_false_missing_accent",
                      all(isinstance(v, (int, float)) and v >= 70 for v in values) and no_invented_support,
                      {"scores": scores, "finding_types": findings},
                      "Both unchanged accent differences score >=70 with no color_missing/color_added finding; existing perceptual support is not lost at 33 colors.")
    full, scoped = result("header_omitted_full").get("overall"), result("header_omitted_scoped").get("overall")
    check("explicit_scope_changes_meaning", full is not None and scoped is not None and scoped >= 98 and scoped > full + 2,
          {"full_overall": full, "scoped_overall": scoped},
          "An explicitly identical crop scores >=98 and >2 points above full omitted-content comparison.")
    alignment = result("ecc_failure").get("alignment", {})
    check("ecc_failure_visible", alignment.get("fallback") is True and alignment.get("method") == "identity"
          and "ECC" in alignment.get("note", ""), alignment,
          "ECC failure is exposed as identity fallback with an explanatory note.")

    def diagnostic(name):
        return result(name).get("diagnostics") or {}

    def issues(name):
        return {i.get("code") for i in diagnostic(name).get("issues", [])}

    d = diagnostic("ecc_failure")
    check("ecc_failure_warning", d.get("status") == "review" and "alignment_unresolved" in issues("ecc_failure")
          and alignment.get("outcome") == "identity_fallback" and alignment.get("reason") == "ecc_nonconvergence",
          {"diagnostics": d, "alignment": alignment},
          "Real ECC nonconvergence exposes a review issue and stable fallback outcome/reason, not only a free-text note.")
    masked = diagnostic("header_omitted_ignored")
    scope = masked.get("scope", {})
    ignored = scope.get("ignored_fraction")
    check("partial_mask_disclosed", masked.get("status") == "review"
          and "mask_fill_semantics" in issues("header_omitted_ignored")
          and isinstance(ignored, (float, int)) and .24 < ignored < .26,
          masked, "Ignoring the header reports review, fill-based mask semantics and about one-quarter nominal ignored area.")
    for name in ("scope_all_ignored", "scope_all_ignored_different_fill"):
        d = diagnostic(name)
        fraction = d.get("scope", {}).get("compared_fraction")
        check(f"{name}_inconclusive", d.get("status") == "inconclusive"
              and "empty_compare_scope" in issues(name) and isinstance(fraction, (float, int)) and fraction < .001,
              {"overall": result(name).get("overall"), "diagnostics": d},
              "No retained pixels means inconclusive scope regardless of the preserved legacy numeric score.")
        capture = d.get("capture", {})
        check(f"{name}_original_capture_stats", all(capture.get(side, {}).get("near_uniform") is False
              for side in ("reference", "candidate")), capture,
              "Capture observations describe the textured originals, not the uniform mask-filled canvases.")
    check("different_fill_disclosed", "mask_fill_colors_differ" in issues("scope_all_ignored_different_fill"),
          diagnostic("scope_all_ignored_different_fill"), "Different per-image ignore fill colors are disclosed.")
    for name in ("flat_identical_screen", "flat_identical_widget"):
        d = diagnostic(name)
        check(f"{name}_honest_warning", d.get("status") == "review" and "near_uniform_input" in issues(name)
              and "alignment_unresolved" not in issues(name), d,
              "Identical solid pixels need near-uniform review but no unresolved alignment or failed-capture claim.")
    widget = result("settings_widget").get("alignment", {})
    check("widget_identity_intentional", widget.get("outcome") == "not_requested"
          and widget.get("reason") == "widget_identity" and "alignment_unresolved" not in issues("settings_widget"),
          {"alignment": widget, "diagnostics": diagnostic("settings_widget")},
          "Widget identity is intentional and does not create an unresolved screen-alignment warning.")
    translated = diagnostic("translation_+2")
    identity_layout, aligned_layout = translated.get("layout_identity_score"), score("translation_+2", "layout")
    check("translation_not_hidden", "translation_applied" in issues("translation_+2")
          and translated.get("status") == "review" and isinstance(identity_layout, (float, int))
          and isinstance(aligned_layout, (float, int)) and aligned_layout > identity_layout + .1,
          {"diagnostics": translated, "aligned_layout": aligned_layout},
          "Accepted global translation remains reviewable and shows lower identity layout similarity.")
    clean = diagnostic("screen_identical")
    check("identical_textured_no_false_warning", clean.get("status") == "ok" and not clean.get("issues"), clean,
          "An identical textured input does not receive mechanical review warnings.")
    for name in ("motion_reversed", "motion_shifted"):
        r = result(name)
        energy = r.get("energy_ratio")
        corr = r.get("temporal_corr")
        timing = r.get("timing_diagnostics", {})
        check(f"{name}_fixture_control", isinstance(energy, (int, float)) and energy >= .99
              and isinstance(corr, (int, float)) and corr < 0,
              {"energy_ratio": energy, "temporal_corr": corr},
              "Energy is equal within rounding while sampled profiles correlate negatively.")
        check(f"{name}_semantics", r.get("motion_score_meaning") == "motion_energy_similarity_only"
              and timing.get("status") == "inconclusive" and timing.get("score") is None,
              {"motion_score_meaning": r.get("motion_score_meaning"), "timing_diagnostics": timing},
              "Equal energy must be labeled energy-only; unknown capture cadence makes timing inconclusive.")
    unequal = result("motion_unequal")
    timing = unequal.get("timing_diagnostics", {})
    check("unequal_no_prefix_timing_claim", unequal.get("temporal_corr") is None
          and timing.get("status") == "inconclusive" and timing.get("reason") == "unequal_length",
          {"temporal_corr": unequal.get("temporal_corr"), "timing_diagnostics": timing},
          "Unequal lengths expose an inconclusive timing result, not a correlated truncated prefix.")
    identical_motion = result("motion_identical")
    corr = identical_motion.get("temporal_corr")
    check("identical_motion_profile", isinstance(corr, (int, float)) and corr > .99,
          corr, "Identical variable sampled profiles have correlation >0.99.")
    static = result("motion_both_static")
    check("static_not_fidelity", static.get("motion_status") == "static" and static.get("motion_score") is None,
          {"status": static.get("motion_status"), "score": static.get("motion_score")},
          "Two static sequences are inconclusive, not perfect motion fidelity.")
    one_static = result("motion_static").get("motion_score")
    check("moving_vs_static_low", isinstance(one_static, (float, int)) and one_static < 5,
          one_static, "Moving versus static has energy similarity <5.")
    # Baseline may not have provenance yet. Its absence is a recorded failure,
    # never silently filled with benchmark metadata.
    def keys(name):
        provenance = result(name).get("provenance") or {}
        return {key: provenance.get(key) for key in ("comparison_key", "run_key")}

    names = ["header_omitted_full", "settings_dark_ui", "settings_custom_weights", "settings_widget", "header_omitted_ignored"]
    provenance_keys = {name: keys(name) for name in names}
    fingerprints = [value["comparison_key"] for value in provenance_keys.values() if value["comparison_key"]]
    check("settings_provenance_distinct", len(fingerprints) == len(names) and len(set(fingerprints)) == len(names),
          provenance_keys, "Worker comparison_key is present and changes across preset, weights, mode, and ignore settings.")
    original, changed = keys("screen_identical"), keys("header_omitted_full")
    check("candidate_change_same_comparison", bool(original["comparison_key"])
          and original["comparison_key"] == changed["comparison_key"]
          and bool(changed["run_key"]) and original["run_key"] != changed["run_key"],
          {"identical": original, "candidate_changed": changed},
          "Changing only candidate pixels preserves comparison_key and changes run_key.")
    visuals = keys("latency_screen_visuals")
    check("visuals_do_not_split_identity", bool(original["comparison_key"]) and original == visuals,
          {"without_visuals": original, "with_visuals": visuals}, "Visual generation does not change either worker identity key.")
    cropped = keys("header_omitted_scoped")
    check("scope_changes_comparison", bool(changed["comparison_key"]) and bool(cropped["comparison_key"])
          and changed["comparison_key"] != cropped["comparison_key"],
          {"full": changed, "caller_crop": cropped}, "Changing reference crop and declared mode starts a new comparison.")
    context_a, context_b = keys("settings_context_v1"), keys("settings_context_v2")
    context_accepted = all(not rows.get(name, {}).get("unsupported_metadata_params", [])
                           for name in ("settings_context_v1", "settings_context_v2"))
    check("protocol_changes_comparison", context_accepted and bool(context_a["comparison_key"])
          and bool(context_b["comparison_key"]) and context_a["comparison_key"] != context_b["comparison_key"],
          {"context_accepted": context_accepted, "v1": context_a, "v2": context_b},
          "Caller-declared protocol changes affect comparison_key when comparison_context metadata is supported.")
    scores = [result(name).get("overall") for name in ("header_omitted_full", "settings_context_v1", "settings_context_v2")]
    check("context_does_not_rescore", context_accepted and all(isinstance(v, (float, int)) for v in scores)
          and max(scores) - min(scores) < .01, {"context_accepted": context_accepted, "overall": scores},
          "Accepted protocol metadata must not change numeric scoring for identical pixels/settings.")
    return checks


def report(data: dict) -> str:
    lines = ["# Synthetic reliability benchmark", "", f"Phase: **{data['run']['phase']}**. {data['run']['qualification']}", "",
             f"Baseline: `{data['run']['baseline_commit']}` executed from a Git archive.",
             f"Current source snapshot: `{data['implementations']['current']['source']['sha256']}`.", "",
             "Generated fixtures only. No product captures or private screenshots. Higher scores are similarity, not accuracy percentages.", "",
             "## Selected results", "",
             "| Case | Baseline / current overall | Baseline / current color or motion | Baseline / current median ms |",
             "| --- | ---: | ---: | ---: |"]
    for row in data["comparisons"]:
        def metric(side):
            r = row[side]["summary"]
            return r["scores"].get("color") if row["kind"] == "screen" else r["motion_score"]
        def number(value):
            return "null" if value is None else f"{value:.2f}"
        lines.append(f"| {row['case_id']} | {number(row['baseline']['summary']['overall'])} / {number(row['current']['summary']['overall'])} | "
                     f"{number(metric('baseline'))} / {number(metric('current'))} | "
                     f"{number(row['baseline']['latency']['median'])} / {number(row['current']['latency']['median'])} |")
    lines += ["", "## Capture, scope and alignment", ""]
    for name in ("header_omitted_full", "header_omitted_scoped", "header_omitted_ignored", "scope_all_ignored",
                 "scope_all_ignored_different_fill", "ecc_failure", "translation_+2"):
        row = next(row for row in data["comparisons"] if row["case_id"] == name)
        observations = []
        for label in ("baseline", "current"):
            d = row[label]["summary"]["diagnostics"]
            if d is None:
                observations.append(f"{label}: diagnostics absent")
            else:
                codes = ", ".join(issue["code"] for issue in d.get("issues", [])) or "none"
                scope = d.get("scope")
                if isinstance(scope, dict):
                    # Keep the original report's field order, independent of
                    # in-memory insertion order versus sorted retained JSON.
                    first = ("ignored_fraction", "compared_fraction")
                    keys = [*first, *sorted(set(scope) - set(first))]
                    scope = {key: scope[key] for key in keys if key in scope}
                observations.append(f"{label}: {d.get('status')}, issues {codes}, scope {scope}")
        lines.append(f"- `{name}`. {'; '.join(observations)}.")
    lines += ["", "## Relationship checks", ""]
    for label in ("baseline", "current"):
        checks = data["assertions"][label]
        failed = [c for c in checks if not c["passed"]]
        lines += [f"{label}: {len(checks) - len(failed)}/{len(checks)} checks passed.", ""]
        for c in failed:
            lines.append(f"- `{c['id']}`: {c['expectation']}")
        lines.append("")
    lines += ["## How to read this run", "",
              "- These hand-built examples test specific failure modes. They do not estimate real-world accuracy or savings.",
              "- Full-image omitted content is a real mismatch. The comparable-region result measures a different, caller-declared scope.",
              "- Same-color mass changes are real mismatches. Periodic crops preserve exact RGB counts; only their color score should remain stable, not necessarily layout/overall.",
              "- Color controls use the file-based public worker comparison pipeline in widget mode, not direct color_score calls. Mass, periodic and red-accent controls use canonical 768px width; nine-stripe inputs exercise normal upscaling from 144px.",
              "- Motion energy similarity does not establish timing fidelity. Generated frames have known order but no verified capture timestamps.",
              "- Timings are sequential in-process API calls after imports, with one CPU thread. They exclude process startup and transport. Each side uses a separate process and the same interpreter/dependencies.",
              f"- Per case: {data['run']['warmups']} discarded warmup calls; {data['run']['repeats']} measured calls. Small-sample min/median/max are descriptive, not a statistical performance claim.",
              "- Raw JSON preserves every measured and warmup result. Only visualization base64 is replaced by byte counts and SHA-256 hashes. No numeric worker score is rewritten.",
              "- Missing worker diagnostics/provenance remain missing. Benchmark input/source provenance is separate from worker-provided fields.",
              "", "## Reproduction", "", "```sh", data["run"]["command"], "```", "",
              "Use a new output directory for every rerun. See `../../README.md` for the schema and options.",
              "Read `results.json`, `raw/*.json`, `raw/current-source.zip`, `fixtures/examples.png`, and `fixtures/color-controls-examples.png` for full evidence.", ""]
    return "\n".join(lines)


def verify_evidence(data: dict, raw: dict) -> dict:
    """Authoritative assertion/summary verifier for the renderer and --check.

    Legacy v3/v4 evidence may be previewed, but cannot qualify for publication.
    report_sha256 binds report(data).encode("utf-8") after integrity passes.
    Caller must decode the original JSON in Python, not re-encode it in JS:
    result_sha256 uses Python's canonical encoding, including float types.
    """
    problems, publication = [], []
    checked, summaries, expected_ids = {}, {}, {}
    response = {"problems": problems, "publication_problems": publication, "report_sha256": None,
                "assertions": checked, "summaries": summaries,
                "expected_assertion_ids": expected_ids}
    try:
        generator = data["run"]["generator"]
        version = generator_version(generator)
        with tempfile.TemporaryDirectory(prefix="reliability-verify-") as temp:
            canonical_cases, _ = generate_fixtures(Path(temp))
        canonical_cases = canonical_cases_for_generator(canonical_cases, generator)
        if version == "v3":
            publication.append("Legacy v3 evidence lacks the four new256color boundary controls; rerun the current harness.")
        if version in ("v3", "v4"):
            publication.append(f"Legacy {version} evidence lacks the four review3 transport/shortlist controls; rerun the current harness.")
        if data.get("cases") != canonical_cases:
            problems.append("Case declarations differ from the authoritative generated case set.")
        names = [c["id"] for c in canonical_cases]
        repeats, warmups = data["run"]["repeats"], data["run"]["warmups"]
        if type(repeats) is not int or repeats < 2 or type(warmups) is not int or warmups < 0:
            raise ValueError("Invalid repeat/warmup counts")
        comparisons = data["comparisons"]
        if [row.get("case_id") for row in comparisons] != names:
            problems.append("Comparison IDs must be complete, unique, and in canonical case order.")
        by_id = {row["case_id"]: row for row in comparisons}
        medians = {}
        for label in ("baseline", "current"):
            rows = raw[label]["cases"]
            if set(rows) != set(names):
                problems.append(f"{label}: raw case IDs differ from the authoritative case set.")
                continue
            ordered = {name: rows[name] for name in names}
            summaries[label] = {}
            medians[label] = {}
            for case in canonical_cases:
                name = case["id"]
                row = rows[name]
                prefix = f"{label}/{name}"
                for phase, count in (("warmups", warmups), ("trials", repeats)):
                    samples = row.get(phase, [])
                    if len(samples) != count:
                        problems.append(f"{prefix}: incomplete {phase}, expected {count} results.")
                    for index, sample in enumerate(samples):
                        if sample.get("result_sha256") != sha(encoded(sample.get("result"))):
                            problems.append(f"{prefix}/{phase}/{index}: retained result hash mismatch.")
                        elapsed = sample.get("elapsed_ms")
                        if type(elapsed) not in (float, int) or not 0 <= elapsed < float("inf"):
                            problems.append(f"{prefix}/{phase}/{index}: invalid elapsed time.")
                failed = trial_failures(row)
                if failed or row.get("errors"):
                    problems.append(f"{prefix}: warmup/measured API or metric failure: {failed or row['errors']}")
                expected_status = "error" if failed or row.get("errors") else "ok"
                if row.get("status") != expected_status:
                    problems.append(f"{prefix}: status does not describe all retained calls.")
                trials = row.get("trials", [])
                first = trials[0]["result"] if trials else None
                if encoded(row.get("result")) != encoded(first):
                    problems.append(f"{prefix}: result differs from first measured result.")
                stable = len({t["result_sha256"] for t in trials}) == 1 if trials else False
                if row.get("stable_results") is not stable:
                    problems.append(f"{prefix}: stable_results differs from retained measured hashes.")
                times = [t["elapsed_ms"] for t in trials]
                latency = {"unit": "ms", "samples": times, "n": len(times),
                           "median": statistics.median(times) if times else None,
                           "min": min(times) if times else None, "max": max(times) if times else None}
                if row.get("latency") != latency:
                    problems.append(f"{prefix}: latency does not match retained samples.")
                medians[label][name] = latency["median"]
                summary = summarize(first or {})
                summaries[label][name] = summary
                view = by_id.get(name, {}).get(label, {})
                if encoded(view.get("summary")) != encoded(summary):
                    problems.append(f"{prefix}: summary differs from first retained measured result.")
                for field, value in (("status", expected_status), ("stable_results", stable),
                                     ("latency", latency), ("effective_params", row.get("effective_params")),
                                     ("unsupported_metadata_params", row.get("unsupported_metadata_params"))):
                    if view.get(field) != value:
                        problems.append(f"{prefix}: comparison {field} differs from raw result.")
                unsupported = row.get("unsupported_metadata_params", [])
                if any(key != "comparison_context" for key in unsupported) or len(set(unsupported)) != len(unsupported):
                    problems.append(f"{prefix}: invalid unsupported metadata declarations.")
                if row.get("effective_params") != {k: v for k, v in case["params"].items() if k not in unsupported}:
                    problems.append(f"{prefix}: effective parameters differ from declared case.")
            checks = assertions_for_generator(ordered, generator)
            checked[label] = checks
            expected_ids[label] = [check["id"] for check in checks]
            supplied = data.get("assertions", {}).get(label, [])
            supplied_ids = [check.get("id") for check in supplied]
            if len(set(supplied_ids)) != len(supplied_ids) or supplied_ids != expected_ids[label]:
                problems.append(f"{label}: assertion IDs must be complete, unique, and in canonical order.")
            if encoded(supplied) != encoded(checks):
                problems.append(f"{label}: assertion ledger differs from recomputed outcomes/observations/expectations.")
            if label == "current":
                publication.extend(f"Current relationship failed: {check['id']}" for check in checks if not check["passed"])
        for name in names:
            if any(name not in medians.get(label, {}) for label in ("baseline", "current")):
                continue
            b, c = medians["baseline"][name], medians["current"][name]
            delta = c - b if b is not None and c is not None else None
            if encoded(by_id[name].get("current_minus_baseline_median_ms")) != encoded(delta):
                problems.append(f"{name}: comparison median delta differs from retained samples.")
        if data["run"].get("current_source_changed_during_run") is not False:
            publication.append("Current source changed during the run, or drift evidence is missing.")
        if data["run"].get("phase") != "integrated":
            publication.append("Publication requires an integrated run.")
        if not problems:
            response["report_sha256"] = sha(report(data).encode("utf-8"))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError) as exc:
        problems.append(f"Malformed retained evidence: {type(exc).__name__}: {exc}")
    return response


def verify_cli(path: str, evidence_base: Path | None) -> int:
    try:
        if path == "-":
            request = json.load(sys.stdin)
            data = json.loads(request["results_json"])
            raw = {label: json.loads(request[f"{label}_json"]) for label in ("baseline", "current")}
        else:
            result_path = Path(path)
            data = json.loads(result_path.read_text())
            base = evidence_base or result_path.parent
            raw = {label: json.loads((base / f"raw/{label}.json").read_text())
                   for label in ("baseline", "current")}
        result = verify_evidence(data, raw)
        if path != "-" and not result["problems"]:
            if sha((base / "report.md").read_bytes()) != result["report_sha256"]:
                result["problems"].append("Report bytes differ from the authoritative report for verified results.")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result = {"problems": [f"Cannot decode retained evidence: {exc}"], "publication_problems": [], "report_sha256": None,
                  "assertions": {}, "summaries": {}, "expected_assertion_ids": {}}
    sys.stdout.buffer.write(encoded(result))
    return 1 if result["problems"] else 0


def runner_self_test() -> int:
    """Inject failures through the real internal runner without editing workers."""
    bootstrap = """
import runpy, sys
sys.path.insert(0, sys.argv[2] + '/worker')
import vision_worker.pipeline as pipeline
target, failure_call = sys.argv[3], int(sys.argv[4])
original = getattr(pipeline, target)
calls = 0
def injected(*args, **kwargs):
    global calls
    calls += 1
    if calls == failure_call:
        raise RuntimeError('injected retained-trial failure')
    return original(*args, **kwargs)
setattr(pipeline, target, injected)
namespace = runpy.run_path(sys.argv[1], run_name='benchmark_self_test')
raise SystemExit(namespace['internal_runner']())
"""
    with tempfile.TemporaryDirectory(prefix="reliability-runner-self-test-") as temp:
        out = Path(temp)
        cases, _ = generate_fixtures(out)
        selected = next(c for c in cases if c["id"] == "screen_identical")
        scenarios = (("healthy", "color_score", 0, 1),
                     ("second_measured_metric", "color_score", 2, 0),
                     ("first_warmup_metric", "color_score", 1, 1),
                     ("second_warmup_metric", "color_score", 2, 2),
                     ("second_measured_after_warmup_metric", "color_score", 3, 1),
                     ("second_measured_api_exception", "compare", 2, 0))
        observations = []
        for name, target, call, warmups in scenarios:
            request = {"source": str(ROOT), "inputs": str(out), "cases": [selected],
                       "repeats": 2, "warmups": warmups}
            child = subprocess.run([sys.executable, "-I", "-c", bootstrap,
                                    str(Path(__file__).resolve()), str(ROOT), target, str(call)],
                                   input=json.dumps(request), text=True, capture_output=True,
                                   env={**os.environ, **THREAD_ENV}, timeout=60, check=True)
            row = json.loads(child.stdout)["cases"][selected["id"]]
            execution = next(c for c in assertions({selected["id"]: row})
                             if c["id"] == "screen_identical_executes")
            expected_ok = name == "healthy"
            if row["status"] != ("ok" if expected_ok else "error") or execution["passed"] is not expected_ok:
                raise AssertionError(f"Real runner did not classify {name}: {row['status']}, {execution}")
            if not expected_ok and not (trial_failures(row) or row["errors"]):
                raise AssertionError(f"Failure evidence missing for {name}")
            observations.append({"scenario": name, "status": row["status"],
                                 "execution_passed": execution["passed"],
                                 "failed_trials": trial_failures(row), "errors": row["errors"]})
    print(json.dumps({"passed": len(observations), "scenarios": observations}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="b7139a2", help="Commit actually archived and executed")
    parser.add_argument("--output", type=Path, help="New/empty directory, defaults to timestamp under docs/reliability/runs")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--phase", choices=("initial", "integrated"), default="initial")
    parser.add_argument("--check", action="store_true", help="Exit 1 on relationship/integrity/publication failures; preserve results")
    parser.add_argument("--timeout", type=float, default=180, help="Per-implementation process timeout in seconds")
    parser.add_argument("--verify-evidence", nargs="?", const="-", metavar="RESULTS_JSON",
                        help="Verify retained evidence and report bytes; without a path, read original JSON strings from stdin and return report_sha256 for caller-side byte verification")
    parser.add_argument("--evidence-base", type=Path, help="Base directory for path-based evidence verification")
    parser.add_argument("--self-test-runner", action="store_true", help="Real-runner warmup/measured failure-injection regression")
    args = parser.parse_args()
    if args.verify_evidence is not None:
        return verify_cli(args.verify_evidence, args.evidence_base)
    if args.self_test_runner:
        return runner_self_test()
    if args.repeats < 2 or args.warmups < 0 or args.timeout <= 0:
        parser.error("repeats must be >=2, warmups >=0, and timeout >0")
    now = datetime.now(timezone.utc)
    out = (args.output or ROOT / "docs/reliability/runs" / now.strftime("%Y%m%dT%H%M%S.%fZ")).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error(f"output is not empty; evidence will not be overwritten: {out}")
    baseline_commit = git("rev-parse", "--verify", f"{args.baseline}^{{commit}}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir()
    cases, fixtures = generate_fixtures(out)
    (out / "raw/benchmark.py").write_bytes(Path(__file__).read_bytes())
    write_json(out / "raw/inputs.json", {"cases": cases, "fixtures": fixtures})
    implementations = {}
    with tempfile.TemporaryDirectory(prefix="design-compare-reliability-") as temp:
        temp = Path(temp)
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", baseline_commit, "worker"])
        baseline = temp / "baseline"
        baseline.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            # Avoid extracting arbitrary commit paths or links from a supplied ref.
            for member in tar.getmembers():
                path = Path(member.name)
                if member.isfile() and path.parts[0] == "worker" and ".." not in path.parts:
                    target = baseline / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as stream:
                        target.write_bytes(stream.read())
        current = temp / "current"
        before = source_manifest(ROOT)
        for relative in before["files"]:
            target = current / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        after = source_manifest(ROOT)
        if before != after or source_manifest(current) != before:
            raise RuntimeError("Current source changed while snapshotting. Rerun after this edit completes.")
        with zipfile.ZipFile(out / "raw/current-source.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
            for relative in before["files"]:
                info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
                bundle.writestr(info, (current / relative).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        baseline_manifest = source_manifest(baseline)
        write_json(out / "raw/sources.json", {"baseline": baseline_manifest, "current": before,
                                              "baseline_archive_sha256": sha(archive)})
        process_env = {**os.environ, **THREAD_ENV}
        process_env.pop("PYTHONPATH", None)
        for label, source in (("baseline", baseline), ("current", current)):
            request = {"source": str(source), "inputs": str(out), "cases": cases,
                       "repeats": args.repeats, "warmups": args.warmups}
            command = [sys.executable, "-I", str(Path(__file__).resolve()), "--internal-runner"]
            write_json(out / f"raw/{label}-invocation.json", {"command": command, "request": request,
                                                               "environment_overrides": THREAD_ENV})
            print(f"Running {label}: {len(cases)} cases, {args.repeats} measured calls each", flush=True)
            started = time.perf_counter()
            try:
                child = subprocess.run(command, input=json.dumps(request), text=True,
                                       capture_output=True, cwd=source, env=process_env, timeout=args.timeout)
            except subprocess.TimeoutExpired as exc:
                for stream in ("stdout", "stderr"):
                    value = getattr(exc, stream) or b""
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace")
                    (out / f"raw/{label}-{stream}-timeout.txt").write_text(value)
                write_json(out / f"raw/{label}-failure.json", {"status": "timeout", "timeout_seconds": args.timeout})
                raise RuntimeError(f"{label} timed out; partial evidence retained under {out}/raw") from exc
            wall = time.perf_counter() - started
            (out / f"raw/{label}-stderr.txt").write_text(child.stderr)
            (out / f"raw/{label}-stdout.json").write_text(child.stdout)
            if child.returncode:
                raise RuntimeError(f"{label} process exited {child.returncode}; see raw/{label}-stderr.txt")
            raw = json.loads(child.stdout)
            expected = baseline_manifest if label == "baseline" else before
            if raw["environment"]["source_manifest"] != expected:
                raise RuntimeError(f"{label} imported source does not match snapshot")
            write_json(out / f"raw/{label}.json", raw)
            implementations[label] = {"source": expected, "environment": raw["environment"],
                                      "process_wall_seconds": wall, "cases": raw["cases"],
                                      "raw": f"raw/{label}.json"}
    baseline_env, current_env = [implementations[k]["environment"] for k in ("baseline", "current")]
    if any(baseline_env[k] != current_env[k] for k in ("python", "executable", "dependencies", "thread_environment")):
        raise RuntimeError("Interpreter/dependency environments differ. No valid comparison can be reported.")
    import shlex
    command = shlex.join([sys.executable, "scripts/reliability-benchmark.py", "--baseline", baseline_commit,
                          "--output", str(out) + "-rerun", "--repeats", str(args.repeats),
                          "--warmups", str(args.warmups), "--phase", args.phase])
    run = {"created_at": now.isoformat(), "phase": args.phase,
           "qualification": "Provisional snapshot. Other worker integration is not certified by this run." if args.phase == "initial"
           else "Integration rerun requested by caller; inspect source hashes and failed checks before publication.",
           "baseline_commit": baseline_commit, "current_head": git("rev-parse", "HEAD"),
           "current_worker_dirty": bool(git("status", "--porcelain", "--", "worker/vision_worker", "worker/pyproject.toml")),
           "current_source_changed_during_run": source_manifest(ROOT) != before,
           "repeats": args.repeats, "warmups": args.warmups, "command": command,
           "harness_sha256": sha(Path(__file__).read_bytes()),
           "generator": GENERATOR,
           "privacy": "Only generated PNG inputs. No external/product screenshot paths accepted.",
           "api": "vision_worker.pipeline.compare / compare_motion; isolated immutable snapshots; no stdio/RPC overhead",
           "timing": "perf_counter_ns around each API call including file reads/normalization, excluding imports/startup and result serialization; fixed baseline-then-current order"}
    comparisons = []
    for case in cases:
        row = {"case_id": case["id"], "kind": case["kind"], "description": case["description"]}
        for label in ("baseline", "current"):
            measured = implementations[label]["cases"][case["id"]]
            row[label] = {"status": measured["status"], "summary": summarize(measured["result"] or {}),
                          "latency": measured["latency"], "stable_results": measured["stable_results"],
                          "unsupported_metadata_params": measured["unsupported_metadata_params"],
                          "effective_params": measured["effective_params"]}
        b, c = row["baseline"]["latency"]["median"], row["current"]["latency"]["median"]
        row["current_minus_baseline_median_ms"] = c - b if b is not None and c is not None else None
        comparisons.append(row)
    data = {"schema_version": "1.0", "run": run, "fixtures": fixtures, "cases": cases,
            "implementations": {k: {field: value for field, value in impl.items() if field != "cases"}
                                for k, impl in implementations.items()},
            "comparisons": comparisons,
            "assertions": {label: assertions(impl["cases"]) for label, impl in implementations.items()}}
    write_json(out / "results.json", data)
    (out / "report.md").write_text(report(data))
    failed = [c["id"] for c in data["assertions"]["current"] if not c["passed"]]
    verification = verify_evidence(data, {label: {"cases": impl["cases"]} for label, impl in implementations.items()})
    print(f"Wrote {out}/results.json and report.md; current failed checks: {failed}")
    if verification["problems"]:
        print(f"Evidence integrity failures: {verification['problems']}")
    return 1 if args.check and (failed or verification["problems"] or verification["publication_problems"]) else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--internal-runner"]:
        raise SystemExit(internal_runner())
    raise SystemExit(main())
