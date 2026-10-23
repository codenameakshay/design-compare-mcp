# Qualified color scope and a close-hue limitation

The [implementation report](implementation-report.md#final-source-repetition-and-freeze) records
local qualification of `soft_grid_source_density_scaled_clearance_v2`. Its 41 color methods pass,
including 730 near-color cases and 30 broad recolors. Other worker entrypoints, unchanged calibration,
the stable two-trial V5 run with 98 assertions, and six fresh 30-second pipeline probes also pass.
The [independent review](independent-review.md#independent-read-only-color-review) gives PASS for
the supplied frozen v2 contract. It did not rerun the full color or npm suites.
Full-project checks (`npm test` and `npm run lifecycle`) passed locally.
Hosted CI, merge, and deployment remain unverified.

## Close-hue mass ordering is not monotonic

The [independent review's limitation](independent-review.md#non-blocking-limitation-close-hue-mass-ordering)
records an actual production reversal, not a prototype prediction or floating-point noise.
In 1×8000 RGB images, both sides use background `[255, 29, 255]`.
The reference accent is `[35, 136, 71]`, and the candidate accent is `[53, 133, 76]`.
Increasing each image's accent mass from 200 pixels, or 2.5%, to 400 pixels, or 5%, raises
the color score from 98.13474 to 98.60238. Both endpoints have no findings and zero certified absence.
Zero certified absence does not prove a nearby counterpart exists.

The review classifies this as a non-blocking limitation of the accepted contract.
The other 899 sampled families had no increase above `1e-8` at the tested fractions.
That finite sweep is not a monotonicity theorem or held-out human-label validation.
Passing the retained ordering families does not establish universal monotonicity or perceptual accuracy.

## Retained evidence and identities

These are exact, unredacted copies of the independent artifacts and final implementation report.
The `v1` and `rejected` columns in [reversal.json](reversal.json) are historical comparisons,
not the current API or numeric compatibility targets. [reversal.py](reversal.py) is the original driver.

- Reviewed color source SHA-256 is `296712351518bf2a88b46dcfa9f0811dc8ce68f8c1989d09d624e87d62724e46`.
- Frozen pipeline SHA-256 is `e121550fb92801346b0aca9c99e615c503eb59b0eebff27a26a6cd502faed76e`.
- `independent-review.md` came from `/tmp/dcm-color-independent-BFGhsf/REPORT.md`.
  Its SHA-256 is `d8f4cdf326a5ca108eee1fbac32097cd093b725c393ccb53af7c6738f9a2a921`.
- `implementation-report.md` came from `/tmp/dcm-color-source-scaled-implementation/report.md`.
  Its SHA-256 is `4fc71eeb24f4b053aa5e141d2254f41f98078cf37ddb0518ec34274baf3552c2`.
- `reversal.py` SHA-256 is `9417877ba646d07827267870b9be1499c0c71a01af4efa852bf69b36e6ae2174`.
- `reversal.json` SHA-256 is `4e66dbbd9c7a6560cde0b24c0963170cbb31148b55a6e0cdf2e62b4a42398344`.

## Rerun without overwriting retained evidence

The original driver hardcodes its checkout path and requires archived `v1_color.py` and
`rejected_color.py` at the absolute paths recorded in the script. Those two baseline modules are
not bundled here. The JSON and review remain readable without them. In a relocated environment,
adjust only those paths and `ROOT` in a scratch copy. Preserve the fixture and scoring calls.
Check the current color-source hash against the reviewed identity before attributing a rerun to it.

Run from the repository root with the worker's Python environment and both baseline modules available.
The script writes beside itself, so run a scratch copy to preserve the retained JSON.

```sh
repro_dir=$(mktemp -d)
cp docs/reliability/limitations/reversal.py "$repro_dir/reversal.py"
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 worker/.venv/bin/python -B "$repro_dir/reversal.py"
```

This reruns a direct color comparison, not the public pipeline, stdio transport, or full qualification.
