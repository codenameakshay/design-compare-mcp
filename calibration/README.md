# Calibration

Evaluate how scores track human labels, separately from synthetic regression behavior. Neither
repeatability nor a finite perturbation test establishes perceptual accuracy or universal monotonicity.

## Two kinds of check

### Synthetic regression checks

`worker/tests/test_calibration.py` runs in CI without a labeled dataset:

- Synthetic color shift, element removal, blur and text-scaling series require sub-score Spearman
  ≤ −0.9 against perturbation level. The spacing series uses ≤ −0.8. These thresholds describe
  those generated cases only, not every possible edit.
- Aggregation checks compare the geometric and arithmetic means on selected score inputs and a
  synthetic pair. This is not a guarantee against gaming or unmeasured errors.
- Repeated comparisons of one pair check score repeatability in the same environment.

```bash
worker/.venv/bin/python worker/tests/test_calibration.py
```

### Color policy and regression checks

The production [color worker](../worker/vision_worker/metrics/color.py) implements
`soft_grid_source_density_scaled_clearance_v2` in `chroma_compressed_lab_proxy` units.
This section describes its frozen policy and returned metadata. The frozen v2 contract has passed
[local color qualification and independent review](../docs/reliability/limitations/README.md).
Full-project checks (`npm test` and `npm run lifecycle`) passed locally.
Hosted CI, merge, and deployment remain unverified. Prototype checks are not
production qualification, and no prototype measurements are published here.

#### One fixed representation

Convert sRGB to D65 CIELab, then transform each pixel with the following equations.
Here `C = sqrt(a² + b²)` and distances are Euclidean in `x`.

```text
x = (L, a × s(C), b × s(C))
s(C) = log(1 + 0.045 × C) / (0.045 × C)
s(0) = 1
```

These chroma-compressed Lab coordinates define a new heuristic metric, not CIEDE2000 or a bound
on CIEDE2000. Every image uses a step-4 lattice with origin `(0, -48, -48)` and shape `(26, 25, 25)`,
for 16,250 nodes. Project every pixel's normalized mass trilinearly onto its eight surrounding nodes.
Process all eight weights, including zeros, in batches of 65,536 pixels. The fixed axes cover the
transformed sRGB domain. The projection conserves mass and uses no pixel subsampling or unique-color
extraction. There are no cardinality gates, clusters, shortlists, or exact-small fallbacks.

#### Maximum sliced mass distance

`M` is the maximum exact 1D Wasserstein-1 distance across 64 fixed directions.
The directions are the three axes and 61 deterministic Fibonacci hemisphere directions.
Pre-sort the lattice projections once. Integrate absolute CDF differences over the fixed gaps
between projected nodes for each direction.

This is not 3D optimal transport. Each projection is a lower bound on Euclidean Wasserstein-1
for the lattice measures. There is no claimed multiplicative approximation bound or input-image
Wasserstein bound that ignores lattice projection uncertainty. The projections do not identify
transport edges, nearest CIEDE2000 counterparts, or the fraction of pixels moved beyond a threshold.

#### Soft rare-color coverage

For lattice histograms `p` and `q`, compute local density with a peak-one Gaussian kernel of
sigma 10 in proxy units. The source-query density correction `alpha_p` determines both importance
weights and the mass resolution used for clearance. Normalize the weights separately for each image.

```text
rho_p = Gaussian_peak_one(sigma=10) * p
alpha_p = 0.05 / max(rho_p, 0.05)
w_p = normalize(alpha_p × p)
K_r(d) = max(1 - d² / r², 0)²
D(q | p)(x) = trapezoid_integral exp(-alpha_p(x) × (K_r * q)(x) / 0.001) dr
S = max(sum(w_p × max(D(q | p) - D(p | p), 0)),
        sum(w_q × max(D(p | q) - D(q | q), 0)))
color_score = 100 × exp(-max(M, 0.9 × S) / 19)
```

Here `*` denotes convolution. Integrate over the fixed radii
`0, 2, 4, 6, 8, 10, 14, 20, 28, 40, 60, 90, 140`. At radius zero, define `K_r * p = p`.
Use FFT convolution for the fixed radial kernels and clip tiny negative roundoff to zero.
In the `p`-to-`q` direction, the same `alpha_p(x)` scales both own and target occupancy.
The reverse direction uses `alpha_q(x)` for both terms. Do not scale target occupancy by the
target's unrelated local density. The effective query mass resolution is `0.001 / alpha_p(x)`.
The 0.001 base scale is smooth, not a hard presence cutoff. Integrate each clearance field before
subtracting the source's own baseline. This corrects its finite-grid and finite-density baseline.

This revision applies the same density normalization to importance and occupancy. The earlier
policy flattened importance but left clearance in raw mass units. At queries below the density
cap, `alpha = 1`, so the clearance calculation is unchanged. The revision adds no constants and
does not establish universal monotonicity for recoloring or overlapping color clouds.

The 5% local-density cap limits the combined weight of nearby background shades.
The formula retains linear-or-smaller influence as contamination mass approaches zero.
The support gain 0.9 was selected against existing fixture bands, not held-out human labels.
The missing 1.25% accent band remains 60–65, and the 5% shaded-background band remains 25–45.
These are regression targets, not measured production results or perceptual acceptance thresholds.
All constants, including decay 19, are frozen for implementation and independent review.
Do not retune them for each new failure or weaken the behavioral assertions.

The score is continuous in lattice mass and trilinear color coordinates. A `max` can be
nondifferentiable without creating a discontinuity. The formula is symmetric. Pixel permutation
can change floating-point summation roundoff but not the representation family.
An equal-histogram spatial swap remains invisible. Color work is `O(pixels)` plus fixed
64-direction lattice work and 24 fixed-grid convolutions. Storage uses the fixed grid and a bounded
pixel batch, independently of unique-color count. These bounds do not establish a universal runtime
or memory guarantee. Evaluate resource use on the production worker separately.
This is a heuristic discrepancy, not a proven mathematical metric with a triangle inequality.

#### Findings have stricter claims than scores

- Emit `color_distribution` when `M ≥ 5`, even when the coverage term is larger. Describe
  projected-mass distance without inventing a transport plan or moved-pixel fraction.
- Missing or added findings require a conservative absence certificate. Compute distance to all
  positive-mass target lattice nodes. Count only source-node mass with nearest-target distance
  greater than `10 + 2 × sqrt(3) × 4`. The guard accounts for uncertainty on both lattices and
  certifies no counterpart within proxy distance 10. Require certified image mass `≥ 0.001`.
  Describe proxy units and the uncertainty guard, not exact CIEDE2000 distances or exact RGB matches.
- Emit `color_shift` only when both sides have certified unmatched mass meeting the finding floor.
  It summarizes two certificates, not any real-world recoloring operation. Do not infer spatial
  correspondence or prescribe a global recolor from these certificates.
- If no other color finding exists and `0.9 × S ≥ 1`, emit `color_coverage_deficit`.
  State that soft coverage does not prove exact absence.

These reporting thresholds do not feed the score. One matching pixel can invalidate a literal
absence certificate without resolving a material coverage deficit. Keep soft coverage separate
from the Boolean absence calculation.
Failure to certify absence does not prove presence or a counterpart within proxy
distance 10. Conservative lattice guards can miss a real absence.

#### Color measurement API

`subscores.color.measurements` identifies `metric: "soft_grid_source_density_scaled_clearance_v2"`
and `units: "chroma_compressed_lab_proxy"`. The distance fields map to the equations above.
The returned color subscore uses these values.

```text
mass_distance = M
coverage_distance = S
weighted_coverage_distance = 0.9 × S
distance = max(mass_distance, weighted_coverage_distance)
decay = 19
score = 100 × exp(-distance / decay)
```

`coverage_distance` is raw `S`, not the weighted term. The worker also returns nested metadata.

- `coordinate_system` has `base: "D65_CIELab"` and `chroma_compression: 0.045`.
- `lattice` has `step: 4`, `origin: [0, -48, -48]`, `shape: [26, 25, 25]`, and `nodes: 16250`.
  Its `assignment` is `"trilinear_all_pixels"`, and `pixel_batch` is 65536.
- `mass_method` has `name: "max_sliced_wasserstein_1d"`, `directions: 64`, and `exact_3d_transport: false`.
- `coverage_method` has `name: "source_density_scaled_bidirectional_soft_clearance"` and the fixed `radii` listed above.
  It reports `mass_scale: 0.001`, `density_sigma: 10`, `density_cap: 0.05`, and `gain: 0.9`.
  Its `source_alpha` string is `"density_cap / max(source_density, density_cap)"`.
  Its `query_mass_resolution` string is `"mass_scale / source_alpha"`.
  Its `occupancy_scaling` string is `"same_source_query_alpha_for_own_and_target"`.
  These strings describe query resolution `0.001 / alpha_source` and the same source-query alpha
  on both own and target occupancy in each direction.
- `certificate` reports `distance: 10`, `lattice_guard: 2 × sqrt(3) × 4`, and `mass_floor: 0.001`.
  Its `missing_mass` and `added_mass` are conservative certified image-mass fractions, even below
  the finding floor. They are not spatial matches or fractions inferred from a transport plan.
  Zero certified mass does not prove that corresponding colors are present.

The old `mean_delta_e`, `transport_delta_e`, `support_delta_e`, `shifted_mass`, `palette_size`,
`support_size`, `support_matching`, and `top_deltas` fields are removed. There are no compatibility
aliases for CIEDE2000, palette-size, exact-support, or shortlist measurements.
Consumers must use the new metric identifier, units, distances, and nested method metadata.

#### Score recalibration and qualification

Historical CIEDE2000 scores, `mean_delta_e` interpretations, shortlist metadata, and transported
mass fractions do not describe this metric. The new metric identifier makes the change explicit.
Migrate implementation-specific numeric anchors explicitly. Preserve behavioral separation,
monotonicity, and calibration assertions.
Re-score saved baselines with the same final worker version before reporting score changes.
Source-density-scaled clearance requires a new policy version even though all scalar constants
are unchanged. Earlier v1 score anchors are historical, not expected values for this revision.
The worker uses `_density_correction` and `_source_scaled_coverage` as its single coverage policy.
The old `_support_weights` and `_clearance` helpers are removed, with no parallel legacy policy.
Clearance fields are integrated before the positive-part subtraction.

Available human-labeled evidence remains weak and limited to one small domain. The prototype does
not establish a better global ranking, an accurate absolute scale, or production readiness.
Synthetic separation and repeatability do not replace held-out human-label calibration.

The six-color regression's accepted finding-contract migration keeps its exact fixture and
`score < 80` bound. Its required result is `color_missing` without `color_added` or `color_shift`,
with certified `missing_mass = 0.1` within `1e-12` and `added_mass = 0`.
Weighted coverage must exceed the existing 1-unit evidence threshold. These are versioned regression
expectations, not newly measured production results. They preserve numeric detection without
inventing a second certificate. The two-color recolor-width controls still require missing, added,
and shift findings when both certificates exist. Tests remain owned by the worker implementer.

The [final implementation report](../docs/reliability/limitations/implementation-report.md#final-source-repetition-and-freeze)
records local passes for all 41 color methods, 730 near-color cases, 30 broad recolors, other worker
entrypoints, unchanged calibration, stable two-trial V5 with 98 assertions, and six fresh pipeline
deadline probes. The [independent review](../docs/reliability/limitations/independent-review.md)
gives PASS for the supplied frozen v2 contract, not global accuracy or universal ordering.
Full-project checks (`npm test` and `npm run lifecycle`) passed locally.
Hosted CI, merge, and deployment remain unverified.

The review also [reproduces a close-hue limitation](../docs/reliability/limitations/independent-review.md#non-blocking-limitation-close-hue-mass-ordering).
Increasing recolored mass from 2.5% to 5% raises the score from 98.13474 to 98.60238, with no findings
at either endpoint. This is real nonmonotonicity. The retained representative families and finite
independent sweep do not establish general monotonicity or held-out human-label accuracy.
The [retained repro and source identities](../docs/reliability/limitations/README.md) distinguish this
local evidence from prototype measurements. Earlier v1 runs do not qualify v2.

### Human-labeled calibration

`worker/calibration/run_calibration.py` scores a manifest of real `(reference, candidate, label)` pairs
and reports **Spearman** (does the ranking
match your judgment?) and **MAE** (does the absolute scale agree?). With ≥ 8 pairs it also runs a
weight search and reports whether non-default dimension weights would track your labels better
(report only — nothing is auto-applied). Weights are fitted and reported on the same pairs; use
held-out data to evaluate them. The eight-pair cutoff enables the search, not statistical reliability.

```bash
cd worker && .venv/bin/python -m calibration.run_calibration ../calibration/dataset.json
```

## Adding your real pairs

1. Drop image pairs into `calibration/pairs/` (reference design + your app's implementation screenshot).
2. Copy `dataset.example.json` to `dataset.json` (gitignored) and list your pairs with a `label` =
   your own "how close is this, 0–100" score. Paths are resolved relative to the manifest file.
3. Run the harness above. Aim for pairs spanning the range: a few near-perfect, several middling,
   a few far off. No fixed sample count guarantees a reliable correlation. Record sample count,
   domain, labeling method and worker/runtime versions alongside the result.

The synthetic `dataset.example.json` exists just to show the output format — synthetic fixtures are
clean and high-contrast, so real screenshots (antialiasing, photos, dense text) are what actually
stress-test the dimensions. Check dimension failures and comparison diagnostics before interpreting
the harness's summary; an aggregate alone does not establish a valid capture or comparison scope.

The root README's 26-pair beUI correlations and `dark-ui` tuning describe an **older pipeline** and
have not been revalidated for the final production color replacement and reliability changes.
`scripts/calibrate.py` is that dataset's
specialized helper with embedded labels; use the manifest runner above for your own pairs.

For baseline/current synthetic cases with source, fixture and runtime provenance, see
[`scripts/reliability-benchmark.py`](../scripts/reliability-benchmark.py) and
[`docs/reliability/`](../docs/reliability/). That guide owns the generator version and case counts.
Its final run targets `docs/reliability/runs/final`. Publish current measurements only after
a complete integrated run against the exact source snapshot and retained-evidence verification.
Synthetic ordering checks are not fresh human
calibration, and a higher score alone is not evidence of visual progress.
