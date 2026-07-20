"""Score a labeled dataset and report how well `overall` tracks human judgment.

Usage (from the worker/ directory, venv active):
    python -m calibration.run_calibration [path/to/manifest.json]

Manifest schema:
    {
      "pairs": [
        {"reference": "img/a_ref.png", "candidate": "img/a_impl.png",
         "label": 82, "mode": "screen", "note": "optional"},
        ...
      ]
    }
Image paths are resolved relative to the manifest file. `label` is a human
"how close, 0-100" score. With >= MIN_TUNE pairs, a weight search is run to see
whether non-default dimension weights would track the labels better (report
only — nothing is auto-applied).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.aggregate import DEFAULT_WEIGHTS, aggregate  # noqa: E402
from vision_worker.pipeline import compare  # noqa: E402

DIMS = list(DEFAULT_WEIGHTS)
MIN_TUNE = 8
DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "calibration" / "dataset.example.json"


def _mae(labels, preds):
    return float(np.mean(np.abs(np.array(labels) - np.array(preds))))


def _spearman(labels, preds):
    if len(set(labels)) < 2 or len(set(preds)) < 2:
        return float("nan")
    return float(spearmanr(labels, preds).statistic)


def tune_weights(labels, subs_list, trials=4000, seed=0):
    """Random Dirichlet search over dimension weights to maximize Spearman."""
    rng = np.random.default_rng(seed)
    best_rho = _spearman(labels, [aggregate(s) for s in subs_list])
    best_w = dict(DEFAULT_WEIGHTS)
    for _ in range(trials):
        w = dict(zip(DIMS, rng.dirichlet(np.ones(len(DIMS)))))
        rho = _spearman(labels, [aggregate(s, w) for s in subs_list])
        if rho == rho and rho > best_rho:  # rho==rho filters NaN
            best_rho, best_w = rho, w
    return best_rho, best_w


def main(argv) -> int:
    manifest_path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    base = manifest_path.parent

    labels, preds, subs_list = [], [], []
    print(f"manifest: {manifest_path}\n")
    print(f"{'label':>6} {'pred':>7}  {'Δ':>6}  pair")
    for p in manifest["pairs"]:
        ref = str((base / p["reference"]).resolve())
        cand = str((base / p["candidate"]).resolve())
        r = compare(ref, cand, mode=p.get("mode", "screen"), return_visuals=False)
        label, pred = float(p["label"]), float(r["overall"])
        labels.append(label)
        preds.append(pred)
        subs_list.append(r["subscores"])
        name = p.get("note") or f"{Path(p['reference']).name} vs {Path(p['candidate']).name}"
        print(f"{label:6.0f} {pred:7.2f}  {pred - label:+6.1f}  {name}")

    rho = _spearman(labels, preds)
    print(f"\nn={len(labels)}  Spearman(label, overall)={rho:+.3f}  MAE={_mae(labels, preds):.1f}")
    print("  (Spearman -> does ranking match? MAE -> absolute-scale agreement.)")

    if len(labels) >= MIN_TUNE:
        best_rho, best_w = tune_weights(labels, subs_list)
        print(f"\nweight search: best Spearman={best_rho:+.3f}")
        print("  weights:", {k: round(float(v), 3) for k, v in best_w.items()})
        print("  (report only; small n overfits — treat as a hint, not a setting.)")
    else:
        print(f"\n(add >= {MIN_TUNE} pairs to enable weight tuning; have {len(labels)}.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
