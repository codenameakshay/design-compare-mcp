# Reproducible reliability evidence

This benchmark uses generated public fixtures only. It executes the requested baseline commit's worker code and a frozen copy of the current worker in separate subprocesses, using one Python interpreter and one installed dependency environment. It creates no Git worktrees and changes no worker code or tests.

The final integrated evidence belongs in [`runs/final/results.json`](runs/final/results.json), with its human-readable report at [`runs/final/report.md`](runs/final/report.md). Generate that run only after the worker changes are integrated. Generator v5 has 52 cases and 98 checks. All 48 v4 cases and their generated fixtures are unchanged. Four review3 common-pixel cases add four execution checks and four behavioral checks. The currently retained v4 dataset is preview-only and must be superseded by fresh evidence after the worker design is integrated.

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py \
  --baseline b7139a2 --repeats 3 --warmups 1 \
  --output /tmp/design-compare-reliability-local-001
```

Install the repository's documented worker CV dependencies first if the environment is absent. The script uses the interpreter that launches it. System Python may not have OpenCV. Baseline code is extracted with `git archive`, not reimplemented or replaced by a score table.

Outputs are append-only by directory. A nonempty output directory is rejected. The final run command is:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py \
  --baseline b7139a2 --repeats 3 --warmups 1 --phase integrated --check \
  --output docs/reliability/runs/final
```

If `runs/final` is already populated, collect into a fresh directory and coordinate its replacement with the parent publication workflow. Do not overwrite or delete retained evidence to run this command.

`--phase integrated` records caller intent; it does not certify integration. `--check` exits 1 if any current behavioral relationship check or evidence-integrity check fails, after saving all evidence. Every warmup and measured result is inspected for API errors and failed metrics, not just the first measured result. Such failures block publication on either implementation. Baseline relationship failures remain evidence, not integrity failures. Without `--check`, known gaps are reported but do not prevent initial evidence collection. `--timeout` bounds each implementation process, default 180 seconds. Source changes during snapshot creation abort; changes later are recorded and require a rerun for final publication.

## Cases and semantics

- Calendar-like patterned colored UI with content translations of -2, -1, +1 and +2 input pixels, and separate edge crops of the same sizes. Each crop still follows the worker's normal width normalization. These are nuisance changes for the color metric, not necessarily for every layout metric.
- Blue accent recoloring and removal are real changes with the same geometry. Color robustness must not make these changes invisible. A relationship check requires all jitter color scores to exceed both control scores by more than two points.
- Same-color mass controls retain exactly two RGB colors while light coverage changes from 50% to 56.25%, 62.5% and 81.25%. Another pair swaps 81.25% to 18.75%. These are visible real changes even though palette membership is unchanged. Checks require decreasing color scores and public `color_distribution` findings on the major changes. No exact score is prescribed.
- Periodic card rows have a 48-pixel period. Every 480-pixel-high crop at origins 0 through 4 contains ten complete periods and the same exact RGB histogram. These cases require color scores >=99 with <1 point spread, not exact 100 or invariant overall/layout scores. They isolate colors invented by the old metric's area-downsampled palette extraction. Width is already canonical at 768 pixels, so public pipeline width normalization does not interpolate these inputs. Widget mode deliberately skips registration. All mass and periodic cases use the same file-based `vision_worker.pipeline.compare` path as the other screen cases. They do not call `color_score` directly, exercise TypeScript dispatch or measure stdio/MCP transport.
- Independent-review controls use that same public pipeline in widget mode. Nine vertical stripes use `np.random.default_rng(74).integers(5,250,size=(9,3))`, each 16 pixels wide at height 160. The candidate adds one to every RGB channel. These 144-pixel-wide inputs undergo normal pipeline upscaling. A color score >=95 allows a small rounding or clustering penalty but rejects a large penalty for a one-level RGB change. The reported direct-metric review observations of 98.59 baseline and 62.50 first implementation motivated this case. They are not public-pipeline results or exact expected scores.
- A 768x768 RGB gray-240 reference gains one red RGB(210,45,65) pixel at its center. This changes only one of 589824 pixels, so color similarity must stay >=99. A separate reference has a contiguous red patch of 7373 pixels, the nearest whole-pixel representation of 1.25% coverage. Removing that patch must score <95 and more than five points below the single-pixel case. These broad bounds distinguish negligible contamination from a meaningful accent without requiring a particular score formula. They make no overall/layout or capture-quality claim. Both controls use canonical width without normalization resampling. Existing fixture declarations, PNGs and publication overviews remain unchanged.
- The new256color boundary controls use the first 255 RGB triples from `itertools.product(range(237,244), repeat=3)`. Four repetitions, truncated to 768 pixels, form a row repeated 101 times. The reference replaces rows 10, 30, 50, 70 and 90 with red RGB(210,45,65); the candidate keeps the near-white background. Crops `[0:100]` and `[1:101]` each retain exactly 3840 red pixels, or 5%. A second pair subtracts one from the red channel of background pixel `[0,10]` on both sides before cropping. Only the origin-0 crop retains that common perturbation. Its reference/candidate unique-color counts are 257/256, versus 256/255 in the other three cases. All other exact RGB counts remain unchanged across origins, including the missing accent mass. Canonical width 768 and widget mode avoid interpolation and registration; array tiling repeats existing colors without creating new ones. All four comparisons use the file-based public pipeline, not direct metric calls. Crop and common-pixel changes must keep the color-score spread <1 point. All four scores must remain <95 with a public `color_missing` finding, so stability cannot hide the unchanged missing accent. No exact score or overall/layout invariance is required.
- Review3 transport controls, `color_transport256_clean` and `color_transport256_common_pixel`, reproduce the independent 256-to-257-color mass-loss finding. Each 768x10 image contains the same 256 RGB colors. Six groups use offsets `(35,0,0)`, `(-35,0,0)`, `(0,35,0)` and `(0,-35,0)` around centers `(60,60,60)`, `(220,220,220)`, `(210,50,50)`, `(50,180,50)`, `(50,50,210)` and `(200,180,50)`. Reference weights `[600,600,1,1]` become candidate weights `[1,1,600,600]` in every group. The remaining 232 colors come from `default_rng(987)` after excluding those 24 colors; 236 copies of the last color fill the canvas. The second comparison adds one to the last pixel's red channel on both sides, giving both images 257 colors without changing their shared support. Scores must remain within <1 point, both must stay <90, and both must retain `color_distribution` without invented `color_missing` or `color_added` findings. Stability alone cannot pass by hiding the real mass mismatch.
- Review3 shortlist controls, `color_shortlist32_clean` and `color_shortlist32_common_pixel`, reproduce the independent 32-to-33-color false-missing-accent finding. `default_rng(31025)` generates 24000 RGB triples. The generator records the exact 32-index selection. Each 768x100 reference contains 72930 copies of the first selected background color, 30 selected singleton colors and 3840 copies of RGB index 5. The candidate replaces only that 5% accent with RGB index 17292. The second comparison replaces background pixel `[0,0]` on both sides with selected index 13393. The accent difference is unchanged, and the added background color is shared. Scores must remain within <1 point and both must stay >=70 without `color_missing` or `color_added` findings. These are broad bounds, not an exact-nearest-search mandate. All four review3 cases use the file-based public pipeline in widget mode at canonical width, without normalization interpolation or registration. Exact RGB histograms are retained for every input.

The independent review observed transport scores 57.54 before and 95.40 after the shared pixel edit, losing `color_distribution`, on color source SHA-256 `6af574f3858d03d90baa92c2e9905039a72b3302682d172d11ac0ee4209c2e86`. It observed shortlist scores 77.54 before and 65.68 after, inventing `color_missing`. Exhaustive support matching after the shortlist edit gave 77.55 with no color finding. These observations motivate the controls; they are not exact score assertions or proof that the current worker passes them. A fresh run must execute the four cases rather than publish an older dataset.

- A full-image omitted avatar/header pair remains a real content mismatch. A separate explicitly cropped pair includes only the common region. Another case ignores a declared header rectangle. The benchmark does not infer a common region or claim omitted content was recovered.
- Entirely ignored textured images with equal and unequal fill colors test empty scope. Both must be diagnostically inconclusive regardless of whether their preserved legacy score is high or low. Capture statistics must describe the original textured inputs, not their flat filled canvases.
- Flat, different-color images exercise genuine ECC failure. The benchmark checks an explicit `alignment_unresolved` review warning and stable alignment outcome/reason, not only a free-text fallback. Identical flat screen/widget controls check near-uniform observations without false alignment-failure warnings. Accepted translation must remain reviewable through identity-versus-aligned layout evidence.
- Identical, time-reversed, one-frame rhythm-shifted, unequal-length, one-sided-static and both-static motion sequences. Reversed/shifted motion has the same mean energy as the reference but different sampled rhythm. No case claims verified capture cadence or timestamps. A high energy score is not timing fidelity.
- Preset, weight, mode, ignore and caller-declared context changes on the same omitted-header pair check worker-provided `comparison_key`/`run_key` semantics. Candidate-only changes must keep the comparison key and change the run key; visuals must not split identity. Context metadata must split protocol identity without changing scores. Older workers lacking a `comparison_context` API parameter still execute the same pixel/scoring pair, with the unsupported metadata explicitly recorded. They cannot pass context-support/provenance checks. Missing result fields remain missing. Input/source metadata generated by this script must not be confused with worker provenance.

The assertions check broad relationships and explicit statuses. They do not require exact float equivalence. A repeated-result hash records determinism as an informational observation, not a regression assertion. Identity key checks use exact key comparisons because stable identity is their actual contract.

## Retained-evidence validation

The renderer uses the current harness as its authoritative Python verifier. It does not execute a retained `raw/benchmark.py` or duplicate the assertion rules in JavaScript:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py \
  --verify-evidence docs/reliability/runs/final/results.json \
  --evidence-base docs/reliability/runs/final
```

Bare `--verify-evidence` instead reads a JSON envelope from stdin with `results_json`, `baseline_json` and `current_json`. Each value must be the original JSON text, not an object decoded and re-encoded by JavaScript. Python result hashes distinguish floats such as `100.0` from integers such as `100`. This interface verifies the renderer's exact retained bytes without rereading files.

The response contains `problems`, `publication_problems`, recomputed `assertions`, `expected_assertion_ids` and per-implementation, per-case `summaries`. Integrity problems return a nonzero exit code and refuse both preview and publication. The verifier checks canonical case declarations, complete unique assertion IDs, recomputed outcomes/observations/expectations, every warmup/measured result hash and count, API and subscore failures, first-measured-result identity, summaries, status, timing records, effective parameters and determinism metadata. Current relationship failures, source drift, non-integrated runs and missing latest controls are publication problems. Baseline relationship failures alone do not block verification. Complete, unmodified v3 44-case/82-check and v4 48-case/90-check evidence remains previewable, but neither can be published as current evidence. Unknown generator versions are rejected.

`GENERATOR` is the active generator identifier. `canonical_cases_for_generator(cases, generator)` and `assertions_for_generator(rows, generator)` are the authoritative schema helpers for the verifier and temporary renderer-test fixtures. V3 excludes `color_new256color_`, `color_transport256_` and `color_shortlist32_` cases and retains its legacy execution-observation format. V4 excludes only the latter two prefixes and retains all previous boundary checks. V5 includes every case and check. These compatibility paths validate historical evidence, not qualify it for publication. Tests that extend historical evidence with current cases must label it with `GENERATOR` and mark it initial/test-only.

The real-runner failure-injection regression requires no retained run or worker edits:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py --self-test-runner
```

It calls the actual file-based pipeline through `internal_runner` in fresh processes. It checks a healthy control, failed color metrics in the second measured call and in first/later warmups, a second measured failure after warmup, and a second-call API exception. A later failure must produce an error case status and a failed execution check even when the first measured score is valid. Generated inputs live only in a temporary directory.

## Output schema v1.0

`results.json` is the site/PR entry point. It is plain JSON with no base64 image payloads.

- `schema_version`: string, currently `1.0`.
- `run`: baseline commit, current HEAD and source-dirty flag, snapshot drift flag, phase, reproduction command, generator/harness identity and timing semantics.
- `fixtures`: relative PNG path keyed objects with file SHA-256, decoded pixel SHA-256, shape and image mode. New color controls also include sorted exact `rgb_histogram` counts and `rgb_histogram_sha256`. These describe generated inputs, not worker measurements. `fixtures/examples.png` and `fixtures/color-controls-examples.png` are labeled publication overviews, never metric inputs. The latter shows only the first 144 rows of the periodic images, without resizing them.
- `cases`: stable IDs, descriptions, kinds, relative reference/candidate paths and exact API parameters. Motion sources are ordered arrays of frame paths.
- `implementations.baseline` and `.current`: source manifests, full installed distribution/version inventory, Python/platform/OpenCV/thread settings, subprocess wall time and raw result path.
- `comparisons`: one row per stable `case_id`, with `kind`, `description`, `baseline` and `current` objects. Each has `summary`, `latency`, `status`, `stable_results`, `effective_params` and `unsupported_metadata_params`. `summary.scores` contains static dimension scores; motion fields remain separate. Full `diagnostics` and `provenance` objects are retained in each summary when supplied by the worker, otherwise null. They are not fabricated from benchmark metadata. `current_minus_baseline_median_ms` is an absolute observed difference, not a savings claim.
- `assertions.baseline` and `.current`: named relationship checks with `passed`, `observed` and `expectation`. A failure means the stated relation was not established by this run. Baseline checks intentionally expose missing reliability features.

`raw/baseline.json` and `raw/current.json` preserve every warmup and measured result, errors and timings by case ID. Visualization base64 alone is replaced by encoded byte count and SHA-256. `raw/*-stdout.json` also preserves subprocess stdout, and stderr is retained separately. `raw/*-invocation.json` records the exact command, request and controlled environment overrides. `raw/benchmark.py` preserves the generating script version. Temporary source paths in recorded commands are historical; rerun the top-level reproduction command to recreate them. Timeouts retain partial stdout/stderr and a failure record, never a completed comparison report.

`raw/sources.json` records the baseline Git archive hash and all worker Python/manifest file hashes. `raw/current-source.zip` retains the exact current snapshot used, including uncommitted worker changes, so an initial run is auditable after integration. The baseline remains reconstructible from its full Git commit ID. No installed dependency tree is copied, and editable worker installation paths cannot select another source because the snapshot is inserted first in the isolated subprocess import path.

## Timing limits

Every case gets discarded warmup calls followed by repeated measured API calls. The clock includes image reads, normalization, metrics and requested visuals. It excludes imports, process startup, transport and JSON serialization. Process wall time is retained separately and is not a per-call latency.

Both processes pin OpenCV and common numerical library thread counts to one. They run sequentially, baseline first. This makes the thread configuration reproducible but does not remove host contention, thermal effects or execution-order bias. Read raw sample values and min/median/max before judging a regression. Three calls are a small descriptive sample, not statistical proof. Increase `--repeats` and use a fresh output directory for stronger local measurements.

The scores are similarity indices, not accuracy percentages. These synthetic cases establish specific behaviors only. They do not establish private-product results, population-level accuracy, cost savings, elapsed workflow savings or release readiness.
