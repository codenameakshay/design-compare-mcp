"""Color dimension: dominant-palette extraction + ΔE2000 matching.

Alignment-invariant by design — color identity should not depend on exact pixel
registration. We extract k dominant colors from each image (deterministic
k-means in CIELAB), match reference↔candidate palettes by minimum ΔE2000
(Hungarian assignment), and score from the mean matched ΔE. Findings name the
specific shifted colors as hex pairs so the host can act on them.
"""

from __future__ import annotations

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab
from sklearn.cluster import KMeans

K = 6
SAMPLE_W = 160
# mean-ΔE -> score decay. exp(-dE/DECAY): dE 0->100, ~13->51, ~25->29.
DECAY = 19.0
# Below this ΔE a palette pair is treated as "the same color" for findings.
NOTICEABLE_DE = 8.0


def _palette(rgb: np.ndarray, k: int = K) -> tuple[np.ndarray, np.ndarray]:
    """Return (lab_centers[k,3], weights[k]) for the dominant colors."""
    h, w = rgb.shape[:2]
    small = cv2.resize(
        rgb, (SAMPLE_W, max(1, round(h * SAMPLE_W / w))), interpolation=cv2.INTER_AREA
    )
    pixels = small.reshape(-1, 3).astype(np.float64) / 255.0
    lab = rgb2lab(pixels.reshape(-1, 1, 3)).reshape(-1, 3)

    n_clusters = min(k, len(np.unique(lab, axis=0)))
    km = KMeans(n_clusters=n_clusters, n_init=4, random_state=0).fit(lab)
    counts = np.bincount(km.labels_, minlength=n_clusters).astype(float)
    return km.cluster_centers_, counts / counts.sum()


def _lab_to_hex(lab: np.ndarray) -> str:
    rgb = lab2rgb(lab.reshape(1, 1, 3)).reshape(3)
    r, g, b = (int(x) for x in np.clip(rgb * 255.0, 0, 255).round())
    return f"#{r:02x}{g:02x}{b:02x}"


def color_score(ref_rgb: np.ndarray, cand_rgb: np.ndarray) -> tuple[float, list[dict], dict]:
    ref_lab, ref_w = _palette(ref_rgb)
    cand_lab, cand_w = _palette(cand_rgb)

    # ΔE2000 cost matrix between every ref and candidate dominant color.
    cost = np.zeros((len(ref_lab), len(cand_lab)))
    for i, c in enumerate(ref_lab):
        cost[i] = deltaE_ciede2000(np.repeat(c[None, :], len(cand_lab), axis=0), cand_lab)

    rows, cols = linear_sum_assignment(cost)
    matched_de = cost[rows, cols]
    UNMATCHED_DE = 40.0
    matched_ref = np.zeros(len(ref_w), dtype=bool)
    matched_cand = np.zeros(len(cand_w), dtype=bool)
    matched_ref[rows] = True
    matched_cand[cols] = True
    unmatched_ref_mass = float(ref_w[~matched_ref].sum()) if np.any(~matched_ref) else 0.0
    unmatched_cand_mass = float(cand_w[~matched_cand].sum()) if np.any(~matched_cand) else 0.0
    leftover = unmatched_ref_mass + unmatched_cand_mass
    penalty = leftover * UNMATCHED_DE
    mass_num = (float((ref_w[rows] * matched_de).sum()) if len(rows) else 0.0) + penalty
    mass_den = (float(ref_w[rows].sum()) if len(rows) else 0.0) + leftover
    eq_num = (float(matched_de.sum()) if len(matched_de) else 0.0) + penalty
    eq_den = float(len(matched_de)) + leftover
    mass_mean = mass_num / mass_den if mass_den > 0 else 0.0
    eq_mean = eq_num / eq_den if eq_den > 0 else 0.0
    mean_de = float(max(mass_mean, eq_mean))
    score = 100.0 * float(np.exp(-mean_de / DECAY))

    # Findings: the most-shifted dominant colors, worst first.
    pairs = sorted(
        (
            {
                "ref_hex": _lab_to_hex(ref_lab[i]),
                "cand_hex": _lab_to_hex(cand_lab[j]),
                "delta_e": round(float(cost[i, j]), 1),
            }
            for i, j in zip(rows, cols)
        ),
        key=lambda p: p["delta_e"],
        reverse=True,
    )
    findings: list[dict] = []
    for p in pairs:
        if p["delta_e"] < max(NOTICEABLE_DE, 10.0):
            break
        findings.append(
            {
                "area": "color",
                "type": "color_shift",
                "severity": "high" if p["delta_e"] > 25 else "medium",
                "observed": (
                    f"a dominant color reads as {p['cand_hex']} but the reference uses "
                    f"{p['ref_hex']} (ΔE {p['delta_e']:.0f})"
                ),
                "suggested_fix": f"shift {p['cand_hex']} toward {p['ref_hex']}",
            }
        )
        if len(findings) >= 4:
            break

    measurements = {
        "mean_delta_e": round(mean_de, 2),
        "palette_size": [int(len(ref_lab)), int(len(cand_lab))],
        "top_deltas": [p["delta_e"] for p in pairs[:4]],
    }
    return score, findings, measurements
