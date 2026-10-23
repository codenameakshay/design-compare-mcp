"""Fixed-lattice color mass and soft coverage in chroma-compressed Lab.

These proxy distances are not CIEDE2000 or exact 3D optimal transport.
Every pixel contributes trilinearly to the same lattice, irrespective of
palette cardinality. Findings use conservative absence certificates, not
transport edges or inferred spatial correspondence. Each coverage direction
uses its source-query density correction for both own and target occupancy.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.signal import fftconvolve
from skimage.color import rgb2lab

METRIC_VERSION = "soft_grid_source_density_scaled_clearance_v2"
CHROMA_COMPRESSION = 0.045
GRID_STEP = 4.0
GRID_ORIGIN = (0.0, -48.0, -48.0)
GRID_SHAPE = (26, 25, 25)
GRID_NODES = 16250
PIXEL_BATCH = 65536
FIBONACCI_DIRECTIONS = 61
DENSITY_SIGMA = 10.0
DENSITY_CAP = 0.05
COVERAGE_RADII = (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 14.0, 20.0, 28.0, 40.0, 60.0, 90.0, 140.0)
COVERAGE_MASS_SCALE = 0.001
COVERAGE_GAIN = 0.9
DECAY = 19.0
CERTIFICATE_DISTANCE = 10.0
CERTIFICATE_MASS_FLOOR = 0.001
DISTRIBUTION_FINDING_DISTANCE = 5.0
COVERAGE_FINDING_DISTANCE = 1.0


def _projection_geometry() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grid = np.indices(GRID_SHAPE).reshape(3, -1).T * GRID_STEP + GRID_ORIGIN
    z = (np.arange(FIBONACCI_DIRECTIONS) + 0.5) / FIBONACCI_DIRECTIONS
    angle = np.arange(FIBONACCI_DIRECTIONS) * np.pi * (3 - np.sqrt(5))
    directions = np.vstack((np.eye(3), np.column_stack((
        np.sqrt(1 - z * z) * np.cos(angle),
        np.sqrt(1 - z * z) * np.sin(angle), z,
    ))))
    projections = grid @ directions.T
    order = np.argsort(projections, axis=0).T
    gaps = np.diff(np.take_along_axis(projections.T, order, axis=1), axis=1)
    for value in (directions, order, gaps):
        value.setflags(write=False)
    return directions, order, gaps


def _coverage_kernels() -> tuple[np.ndarray, ...]:
    axes = [(np.arange(2 * n - 1) - (n - 1)) * GRID_STEP for n in GRID_SHAPE]
    squared = sum(x * x for x in np.meshgrid(*axes, indexing="ij", sparse=True))
    kernels = tuple(np.maximum(1 - squared / radius ** 2, 0) ** 2
                    for radius in COVERAGE_RADII[1:])
    for kernel in kernels:
        kernel.setflags(write=False)
    return kernels


_DIRECTIONS, _PROJECTION_ORDER, _PROJECTION_GAPS = _projection_geometry()
_COVERAGE_KERNELS = _coverage_kernels()


def _metric_coordinates(rgb: np.ndarray) -> np.ndarray:
    lab = rgb2lab(np.asarray(rgb, dtype=float).reshape(-1, 1, 3) / 255).reshape(-1, 3)
    chroma = CHROMA_COMPRESSION * np.linalg.norm(lab[:, 1:], axis=1)
    scale = np.ones(len(lab))
    np.divide(np.log1p(chroma), chroma, out=scale, where=chroma > 0)
    lab[:, 1:] *= scale[:, None]
    return lab


def _histogram(rgb: np.ndarray) -> np.ndarray:
    pixels = rgb.reshape(-1, 3)
    histogram = np.zeros(GRID_NODES, dtype=float)
    for start in range(0, len(pixels), PIXEL_BATCH):
        position = (_metric_coordinates(pixels[start:start + PIXEL_BATCH]) - GRID_ORIGIN) / GRID_STEP
        lower = np.minimum(np.floor(position).astype(int), np.array(GRID_SHAPE) - 2)
        fraction = position - lower
        for bits in np.ndindex(2, 2, 2):
            indices = np.ravel_multi_index((lower + bits).T, GRID_SHAPE)
            weights = np.prod(np.where(bits, fraction, 1 - fraction), axis=1)
            histogram += np.bincount(indices, weights=weights, minlength=GRID_NODES)
    return histogram / len(pixels)



def _mass_distance(reference: np.ndarray, candidate: np.ndarray) -> float:
    cdf = np.cumsum((reference - candidate)[_PROJECTION_ORDER], axis=1)[:, :-1]
    return float(np.sum(np.abs(cdf) * _PROJECTION_GAPS, axis=1).max())



def _density_correction(histogram: np.ndarray) -> np.ndarray:
    sigma = DENSITY_SIGMA / GRID_STEP
    density = gaussian_filter(histogram.reshape(GRID_SHAPE), sigma,
                              mode="constant", truncate=4).ravel()
    density *= (2 * np.pi) ** 1.5 * sigma ** 3
    return DENSITY_CAP / np.maximum(density, DENSITY_CAP)


def _source_scaled_coverage(reference: np.ndarray, candidate: np.ndarray) -> float:
    alpha_ref, alpha_cand = _density_correction(reference), _density_correction(candidate)
    ref_weights = reference * alpha_ref
    ref_weights /= ref_weights.sum()
    cand_weights = candidate * alpha_cand
    cand_weights /= cand_weights.sum()
    ref_own, ref_other, cand_own, cand_other = [], [], [], []
    for kernel in (None,) + _COVERAGE_KERNELS:
        if kernel is None:
            ref_density, cand_density = reference, candidate
        else:
            ref_density = np.maximum(fftconvolve(reference.reshape(GRID_SHAPE), kernel,
                                                 mode="same").ravel(), 0)
            cand_density = np.maximum(fftconvolve(candidate.reshape(GRID_SHAPE), kernel,
                                                  mode="same").ravel(), 0)
        ref_other.append(np.exp(-alpha_ref * cand_density / COVERAGE_MASS_SCALE))
        ref_own.append(np.exp(-alpha_ref * ref_density / COVERAGE_MASS_SCALE))
        cand_other.append(np.exp(-alpha_cand * ref_density / COVERAGE_MASS_SCALE))
        cand_own.append(np.exp(-alpha_cand * cand_density / COVERAGE_MASS_SCALE))
    # Integrate before subtraction to retain the floating-point baseline.
    ref_deficit = np.maximum(np.trapezoid(np.array(ref_other), COVERAGE_RADII, axis=0)
                            - np.trapezoid(np.array(ref_own), COVERAGE_RADII, axis=0), 0)
    cand_deficit = np.maximum(np.trapezoid(np.array(cand_other), COVERAGE_RADII, axis=0)
                             - np.trapezoid(np.array(cand_own), COVERAGE_RADII, axis=0), 0)
    return max(float(ref_weights @ ref_deficit), float(cand_weights @ cand_deficit))


def _certified_mass(source: np.ndarray, target: np.ndarray) -> float:
    distance = distance_transform_edt(target.reshape(GRID_SHAPE) == 0,
                                      sampling=GRID_STEP).ravel()
    # Each contributing pixel is at most one cell diagonal from its node.
    guard = 2 * np.sqrt(3) * GRID_STEP
    return float(source[distance > CERTIFICATE_DISTANCE + guard].sum())


def color_score(ref_rgb: np.ndarray, cand_rgb: np.ndarray) -> tuple[float, list[dict], dict]:
    reference, candidate = _histogram(ref_rgb), _histogram(cand_rgb)
    coverage = _source_scaled_coverage(reference, candidate)
    mass = _mass_distance(reference, candidate)
    weighted_coverage = COVERAGE_GAIN * coverage
    distance = max(mass, weighted_coverage)
    score = 100 * float(np.exp(-distance / DECAY))
    certified = {"missing": _certified_mass(reference, candidate),
                 "added": _certified_mass(candidate, reference)}
    findings: list[dict] = []
    for kind, amount in certified.items():
        if amount >= CERTIFICATE_MASS_FLOOR - 1e-12:
            side = "reference" if kind == "missing" else "candidate"
            findings.append({
                "area": "color", "type": f"color_{kind}", "severity": "medium",
                "observed": f"At least {amount:.2%} of {side} color mass has no counterpart "
                            "within proxy distance 10, with lattice uncertainty guards. "
                            "This is not a nearest-CIEDE2000 claim.",
                "suggested_fix": "Inspect the affected color coverage; the palette does not identify "
                                 "their positions. Proxy distance is not CIEDE2000.",
            })
    if len(findings) == 2:
        findings.append({
            "area": "color", "type": "color_shift", "severity": "medium",
            "observed": "Both images have certified unmatched color mass. "
                        "No spatial correspondence was inferred.",
            "suggested_fix": "Inspect corresponding regions before recoloring; "
                             "preserve colors in unchanged regions.",
        })
    if mass >= DISTRIBUTION_FINDING_DISTANCE:
        findings.append({
            "area": "color", "type": "color_distribution", "severity": "medium",
            "observed": f"Maximum projected mass distance {mass:.2f} proxy units. "
                        "This is not exact 3D optimal transport.",
            "suggested_fix": "Inspect color proportions and identity; "
                             "no exact moved-pixel fraction was inferred.",
        })
    if not findings and weighted_coverage >= COVERAGE_FINDING_DISTANCE:
        findings.append({
            "area": "color", "type": "color_coverage_deficit", "severity": "medium",
            "observed": f"Soft bidirectional coverage distance {weighted_coverage:.2f} proxy units. "
                        "This does not prove exact color absence.",
            "suggested_fix": "Inspect color-neighborhood coverage; small incidental matches "
                             "do not establish adequate accent coverage.",
        })
    measurements = {
        "metric": METRIC_VERSION,
        "units": "chroma_compressed_lab_proxy",
        "coordinate_system": {"base": "D65_CIELab", "chroma_compression": CHROMA_COMPRESSION},
        "lattice": {"step": GRID_STEP, "origin": list(GRID_ORIGIN), "shape": list(GRID_SHAPE),
                    "nodes": GRID_NODES, "assignment": "trilinear_all_pixels", "pixel_batch": PIXEL_BATCH},
        "mass_method": {"name": "max_sliced_wasserstein_1d", "directions": len(_DIRECTIONS),
                        "exact_3d_transport": False},
        "coverage_method": {"name": "source_density_scaled_bidirectional_soft_clearance", "radii": list(COVERAGE_RADII),
                            "mass_scale": COVERAGE_MASS_SCALE, "density_sigma": DENSITY_SIGMA,
                            "density_cap": DENSITY_CAP, "gain": COVERAGE_GAIN,
                            "source_alpha": "density_cap / max(source_density, density_cap)",
                            "query_mass_resolution": "mass_scale / source_alpha",
                            "occupancy_scaling": "same_source_query_alpha_for_own_and_target"},
        "certificate": {"distance": CERTIFICATE_DISTANCE, "lattice_guard": float(2 * np.sqrt(3) * GRID_STEP),
                        "mass_floor": CERTIFICATE_MASS_FLOOR, "missing_mass": certified["missing"],
                        "added_mass": certified["added"]},
        "distance": distance, "mass_distance": mass, "coverage_distance": coverage,
        "weighted_coverage_distance": weighted_coverage, "decay": DECAY,
    }
    return score, findings, measurements
