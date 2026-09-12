# Calibration

Checks that `overall` tracks human judgment and that each dimension is well-behaved.

## Two kinds of check

**1. Label-free guarantees (run in CI — see `.github/workflows/ci.yml`, no data needed)** — `worker/tests/test_calibration.py`:
- **Monotonicity** — perturbing one dimension (color shift, element removal, blur, text scaling,
  spacing change) drives that sub-score down (Spearman ≤ −0.9).
- **Gaming-resistance** — a perfect dimension can't inflate the overall past the weighted arithmetic
  mean (geometric mean property).
- **Determinism** — identical inputs yield identical scores.

```bash
worker/.venv/bin/python worker/tests/test_calibration.py
```

**2. Human-labeled calibration (needs real pairs)** — `worker/calibration/run_calibration.py`:
Scores a manifest of `(reference, candidate, label)` pairs and reports **Spearman** (does the ranking
match your judgment?) and **MAE** (does the absolute scale agree?). With ≥ 8 pairs it also runs a
weight search and reports whether non-default dimension weights would track your labels better
(report only — nothing is auto-applied).

```bash
cd worker && .venv/bin/python -m calibration.run_calibration ../calibration/dataset.json
```

## Adding your real pairs

1. Drop image pairs into `calibration/pairs/` (reference design + your app's implementation screenshot).
2. Copy `dataset.example.json` to `dataset.json` (gitignored) and list your pairs with a `label` =
   your own "how close is this, 0–100" score. Paths are resolved relative to the manifest file.
3. Run the harness above. Aim for pairs spanning the range: a few near-perfect, several middling,
   a few far off. 15–30 pairs gives a meaningful Spearman; fewer is directional only.

The synthetic `dataset.example.json` exists just to show the output format — synthetic fixtures are
clean and high-contrast, so real screenshots (antialiasing, photos, dense text) are what actually
stress-tests the dimensions.
