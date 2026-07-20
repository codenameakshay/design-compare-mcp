"""Calibrate dimension weights against human fidelity labels.

Builds calibration/dataset.json from the labels below, scores each pair on the
preview crops, then reports:
  - per-dimension Spearman vs the human labels (which dimension predicts best),
  - the current default-weights overall correlation (baseline),
  - a weight search over the working dimensions that best matches the labels.

content/spacing are excluded from the search: they collapse on low-contrast dark
UIs (see README hardening note), so they are noise on this dataset.

Run: worker/.venv/bin/python scripts/calibrate.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
from vision_worker.aggregate import DEFAULT_WEIGHTS  # noqa: E402
from vision_worker.pipeline import compare  # noqa: E402

FLOOR = 1.0


def geo(subs: dict, weights: dict | None) -> float:
    """Weighted geometric mean over {dim: score|None}; mirrors aggregate()."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})
    scored = {k: v for k, v in subs.items() if v is not None and k in w and w[k] > 0}
    if not scored:
        return 0.0
    total = sum(w[k] for k in scored) or 1.0
    acc = sum((w[k] / total) * math.log(max(FLOOR, min(100.0, float(v)))) for k, v in scored.items())
    return round(math.exp(acc), 2)

# Human labels (0-100 fidelity), from the blind contact-sheet review.
LABELS = {
    "marquee": 100, "tabs": 90, "switch": 100, "input": 85, "select": 95,
    "checkbox": 100, "radio": 100, "bottom-sheet": 40, "shared-layout-bg": 85,
    "preview-rail": 80, "dock": 80, "tooltip": 50, "popover": 50,
    "morphing-modal": 90, "text-animation": 51, "number": 90, "animated-badge": 40,
    "action-swap": 80, "animated-toast-stack": 25, "theme-toggle": 30,
    "bouncy-accordion": 100, "range-slider": 100, "wheel-picker": 65, "loader": 90,
    "tilt-card": 96, "button": 85, "_index": 85,
}
WORKING = ["layout", "color", "typography"]
ALL_DIMS = list(DEFAULT_WEIGHTS)


def manifest_entry(slug, label):
    if slug == "_index":
        return {"reference": f"pairs/{slug}/reference.png",
                "candidate": f"pairs/{slug}/candidate.png", "label": label,
                "mode": "screen", "note": slug}
    return {"reference": f"pairs/{slug}/reference_preview.png",
            "candidate": f"pairs/{slug}/candidate_preview.png", "label": label,
            "mode": "widget", "note": slug}


def spear(a, b):
    if len(set(b)) < 2:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def main():
    base = ROOT / "calibration"
    manifest = {"pairs": [manifest_entry(s, l) for s, l in LABELS.items()]}
    (base / "dataset.json").write_text(json.dumps(manifest, indent=2))

    rows = []  # (slug, label, subs_dict, is_index)
    for p in manifest["pairs"]:
        slug = p["note"]
        ref = str((base / p["reference"]).resolve())
        cand = str((base / p["candidate"]).resolve())
        r = compare(ref, cand, mode=p["mode"], return_visuals=False)
        subs = {k: v["score"] for k, v in r["subscores"].items()}
        rows.append((slug, float(p["label"]), subs, slug == "_index"))

    # Primary analysis excludes _index (different granularity: full page vs preview).
    comp = [r for r in rows if not r[3]]
    labels = [r[1] for r in comp]

    print(f"component pairs: {len(comp)}  (label range {min(labels):.0f}-{max(labels):.0f})\n")

    print("per-dimension Spearman vs your labels (higher = predicts your eye better):")
    for dim in ALL_DIMS:
        pairs = [(r[1], r[2][dim]) for r in comp if r[2].get(dim) is not None]
        cov = len(pairs)
        rho = spear([a for a, _ in pairs], [b for _, b in pairs]) if cov >= 3 else float("nan")
        note = "" if cov == len(comp) else f"  (only {cov}/{len(comp)} scored)"
        print(f"  {dim:11s} rho={rho:+.3f}{note}")

    # Baseline: current default weights, all five dims.
    overall = geo
    base_overall = [overall(r[2], None) for r in comp]
    print(f"\nbaseline (default weights, all 5 dims): Spearman={spear(labels, base_overall):+.3f}")

    # Weight search over the working dims (content/spacing forced to 0).
    rng = np.random.default_rng(0)
    subs_list = [r[2] for r in comp]
    best = (spear(labels, [overall(s, {"content": 0, "spacing": 0}) for s in subs_list]),
            {"layout": 0.5, "color": 0.25, "typography": 0.25, "content": 0, "spacing": 0})
    for _ in range(8000):
        w3 = rng.dirichlet(np.ones(3))
        wd = dict(zip(WORKING, w3)) | {"content": 0.0, "spacing": 0.0}
        rho = spear(labels, [overall(s, wd) for s in subs_list])
        if rho == rho and rho > best[0]:
            best = (rho, wd)
    best_rho, best_w = best
    print(f"\nbest weights (layout/color/typography only): Spearman={best_rho:+.3f}")
    print("  weights:", {k: round(float(v), 3) for k, v in best_w.items() if v})

    # Show per-pair predicted (best weights) vs label, worst disagreements first.
    preds = [(r[0], r[1], overall(r[2], best_w)) for r in comp]
    preds.sort(key=lambda t: abs(t[2] - t[1]), reverse=True)
    print("\nlargest tool-vs-you disagreements (best weights):")
    print(f"  {'component':22s} {'you':>4} {'tool':>5} {'Δ':>5}")
    for slug, lab, pred in preds[:8]:
        print(f"  {slug:22s} {lab:4.0f} {pred:5.1f} {pred-lab:+5.1f}")

    print(f"\nwrote {base / 'dataset.json'}")


if __name__ == "__main__":
    main()
