# Source-query-scaled color implementation

The accepted revision is implemented in the two assigned files. Final color qualification passes all41 methods, including the original strict four-width ordering. Both previous blockers are resolved through the accepted numeric-policy correction and the separately approved six-color finding-contract migration.

This report covers local implementation evidence. Independent review and final publication remain separate parent gates. No repository evidence dataset, documentation, pipeline file, dependencies, commits, or agents were created or changed by this worker. Concurrent edits outside the two assigned files were preserved.

## Exact identities and ownership

Repository is `/Users/codenameakshay/Development/codenameakshay/design-compare-mcp`, branch `feat/comparison-reliability`. HEAD is `b7139a2d29bc5fd2cae567688e5660b501f509ec`. These are uncommitted changes, not proof attached to that commit.

Owned files and frozen SHA256 identities:

- `worker/vision_worker/metrics/color.py` is `296712351518bf2a88b46dcfa9f0811dc8ce68f8c1989d09d624e87d62724e46`.
- `worker/tests/test_color_stability.py` is `812b4e44f88807852013547e9f3c1d58f6876a86cdf229f03dcb3b596471a7e1`.

Accepted design inputs:

- `/tmp/dcm-color-monotonic-design/REPORT.md` is `b2ee04595365288b5554467420164af4eb305833078971e6fb4eb56d58b070e5`.
- `/tmp/dcm-color-monotonic-design/candidate.py` is `516010d4cf2d6b9aae670ff789bb55ac7473a32ab09f54dc9b614264c90fe98f`.

Preserved v1 sources in this evidence directory:

- `v1_color.py` is `8459cc115b694fc8336bb3348767b67418d25714003555fbdc3c233b5a4d0d01`.
- `v1_test_color_stability.py` is `d575665530ae3231df590dc9ac7831ad5965e999d1537785b9a562d3a986768f`.

Final integrated worker snapshot from V5 is `0a5ca0c9c0a3f38ee0f48590f0ad20ce0e6269f1a5b5b112c616b2007702a144`. Its archived color source matches the owned hash above. Its parent-owned pipeline is `e121550fb92801346b0aca9c99e615c503eb59b0eebff27a26a6cd502faed76e`.

Unchanged calibration entrypoint is `c04d82a2a1bd68925440f39429b728203d4c1af8bf8532fbace0c7b136cde5d1`. Benchmark harness is `a0f860e88c22c88ae0331765e4f4d81cf5c6061e37619bc8b672d45caf3db0a4`.

## Numeric change

The data remains normalized mass on the fixed16,250-node trilinear lattice. Geometry, all-pixel processing,65,536-pixel batch,64 fixed projection directions, proxy coordinates, certificates, reporting thresholds, and score constants are unchanged.

For source histogram p, the existing density correction is:

```text
alpha_p = .05 / max(peak_one_gaussian_sigma10(p), .05)
w_p = normalize(alpha_p * p)
D(q | p) = integral exp(-alpha_p * (K_r * q) / .001) dr
S(p,q) = max(
  w_p @ positive(D(q|p) - D(p|p)),
  w_q @ positive(D(p|q) - D(q|q)))
score = 100 * exp(-max(M, .9*S) / 19)
```

The SAME source-query alpha scales both own and target occupancy in each direction. The target's unrelated local alpha is not substituted into the source direction. Effective query mass resolution is .001/alpha_p. Each clearance field is integrated before subtraction, preserving the accepted candidate arithmetic without an epsilon clamp or identity special case.

All17 literal policy constants match both the v1 source and accepted candidate. `production_parity.py` checks this structurally. No scalar was retuned.

The obsolete `_support_weights` and `_clearance` helpers were deleted. There is one density-correction helper and one source-scaled coverage policy. No alternate v1 representation or unused scoring path remains.

The policy is a heuristic color discrepancy, not CIEDE2000, exact3D optimal transport, or a proven triangle-inequality metric. Findings remain independent of scoring.

## API and metadata handoff

The return remains `(score, findings, measurements)`. Existing proxy units, mass fields, certificate fields, score fields, and finding rules remain.

- `metric` is now `soft_grid_source_density_scaled_clearance_v2`.
- `coverage_method.name` is `source_density_scaled_bidirectional_soft_clearance`.
- `coverage_method.source_alpha` is `density_cap / max(source_density, density_cap)`.
- `coverage_method.query_mass_resolution` is `mass_scale / source_alpha`.
- `coverage_method.occupancy_scaling` is `same_source_query_alpha_for_own_and_target`.
- Existing `mass_scale=.001`, `density_sigma=10`, `density_cap=.05`, and `gain=.9` metadata remain unchanged.

Raw `coverage_distance` is S. `weighted_coverage_distance` is .9*S. `distance` is max(M,.9*S). No old CIEDE, palette-cardinality, shortlist, or exact-moved-mass fields were restored.

Parent received this metadata contract before documentation integration. Parent owns semantics and prose outside the assigned files.

## Measured production parity and prior blockers

`production_parity.json` records actual production results, accepted-design comparison, occupied-node masses, alpha, normalized density weights, and effective query mass resolution. All nine controls have zero score error against the accepted candidate. Distance, M, S, weighted coverage, and findings also agree within1e-12. This parity check is separate from production gate evidence.

Original recolor widths1,2,8,16 now give:

- Width1 score77.8790434934525, M .23198982835916365, S5.278058288690964, weighted4.750252459821868.
- Width2 score65.78291692049561, M .463979656718324, S8.841544500036743, weighted7.957390050033069.
- Width8 score39.201917183128124, M1.8559186268732906, S19.769384578267122, weighted17.79244612044041.
- Width16 score37.796758087994874, M3.711837253746719, S20.539989095844554, weighted18.4859901862601.

The original strict non-increasing assertion is unchanged and passes. All four retain the existing score<90 and missing/added/shift requirements. Width16 no longer improves over width8.

The accepted six-color fixture now scores73.12256570973068, with M3.711837253746719, S6.60847804240598, and weighted coverage5.947630238165382. It reports only `color_missing`. Certified missing mass is .1000000000000022, added mass0. The original fixture and score<80 gate are unchanged. The test now explicitly asserts the accepted conservative proof contract, missing mass .1 within1e-12, added0, and weighted coverage>1. No fake added mass or shift was introduced. Absence of an added certificate is not proof of actual counterpart presence.

## Explicit test migrations and additions

The prior39 methods remain represented. Only the accepted six-color method was renamed to describe material color change near existing support. Both two-color shift tests, exhaustive proxy-distance certificate bounds, score bands, strict original four-width ordering, and all existing behavioral thresholds remain.

Two v1 review-pair anchor groups migrated explicitly under v2:

- Transport256/257 changes62.080788052149614/62.08078357197323 to58.9658244816432/58.9658193789908. Score<70, gap<.01, distribution-only findings, M>5, zero absence certificates, symmetry, and pixel-order assertions remain.
- Support32/33 changes77.84770273897678/77.8489152187426 to77.3162682752747/77.3175164058364. Score<85, gap<.01, coverage-deficit-only findings, zero absence certificates, symmetry, and pixel-order assertions remain.

The metric string and coverage-method contract assert v2 and its source-query mass-resolution semantics. No unrelated numeric anchors were changed.

Two methods extend the suite to41:

1. Six representative design families use seeds88100,88106,88108,88127,88129,88177. They include overlapping support, separated colors, plateaus, and the three largest v1 reversal families. Each runs actual RGB images at fractions .001,.00625,.0125,.025,.05,.1,.2,.4. The new family gate permits only1e-10 score summation roundoff on plateaus and requires a material endpoint drop. This is tighter than the design investigation's1e-8 diagnostic threshold. It does not alter the strict original four-width assertion or production arithmetic.
2. The original recolor family runs all160 integer widths with strict non-increasing scores and a material full-recolor bound. It passes without a tolerance.

Specified768/gray240 support injection retains its literal anchors30.436102279019327 ->30.486711184212 and <.1 bound. The separate200/gray246 control retains25.5827532228545 ->26.320749308983395 and its own <1 bound. Neither fixture, score band, finding requirement, or threshold changed.

The raw-distance12-decimal crop assertion documented in the v1 implementation is unchanged. No original test was skipped, marked expected, or weakened to obtain green.

## Production commands and worker gates

All commands run from the repository with its interpreter:

```sh
cd /Users/codenameakshay/Development/codenameakshay/design-compare-mcp
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
worker/.venv/bin/python worker/tests/test_color_stability.py -v > /tmp/dcm-color-source-scaled-implementation/color-tests.log 2>&1
```

All41 methods pass in177.753s, exit0. This reruns all730 near-RGB cases, historical seeds74/78, all30 broad-gradient recolors, shade-count and256-boundary cases, contamination, rare-accent calibration bands, distribution shifts, version/certificate regressions, and actual runtime limits. No prototype was substituted.

Every other worker entrypoint also ran successfully:

```sh
for test in test_pipeline test_calibration test_robustness test_motion test_reliability; do
  worker/.venv/bin/python "worker/tests/$test.py" > "/tmp/dcm-color-source-scaled-implementation/$test.log" 2>&1 || exit $?
done
```

Pipeline, unchanged calibration, robustness, and motion pass. Reliability passes36/36 in24.217s. Calibration color rho is-1.000 with scores[100.0,89.6,75.6,58.4,47.8,38.7]. Content/layout/typography/spacing, anti-gaming, and repeated-run determinism also pass without threshold changes.

After parent froze the final pipeline prose, the same loop was rerun with logs under `final-worker/`. That final-source repetition is accounted for below.

Additional production gates:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py --self-test-runner > /tmp/dcm-color-source-scaled-implementation/runner-self-test.log 2>&1
node scripts/reliability-smoke.mjs > /tmp/dcm-color-source-scaled-implementation/reliability-smoke.log 2>&1
worker/.venv/bin/python /tmp/dcm-color-source-scaled-implementation/production_parity.py
git diff --check -- worker/vision_worker/metrics/color.py
git diff --no-index --check /dev/null worker/tests/test_color_stability.py
```

Runner self-test passes all6 scenarios. The real MCP reliability smoke passes. Diff whitespace checks emit no errors. The no-index invocation returns1 for an added file; that is not a whitespace diagnostic.

The initial /tmp parity harness tried to literal-evaluate a computed private cache assignment. Its first run failed in the harness before comparison. The corrected harness filters private caches and checks the17 actual literal policy constants. No production change resulted from this harness correction.

## Integrated V5 with two retained trials

The first integrated run is retained under `v5/`:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py --output /tmp/dcm-color-source-scaled-implementation/v5 --repeats 2 --warmups 1 --phase integrated --check
```

It executes52 cases with one discarded warmup and two retained measured calls per case on both baseline and immutable current source. All98 current assertions pass, with no integrity problems. Its command exits1 solely because parent-owned pipeline prose changed during execution. The verifier publication problem is exactly `Current source changed during the run, or drift evidence is missing.`. The drifted source is not the color module. The pipeline hash changed from `cc3391ec7e6ca6a42062226e54dfd6c3ba460f0f87f1cd3a9cc32fba39c47063` to the final pipeline hash above. This run is retained, not relabeled as stable.

After coordination with parent, a new integrated run used the held source:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py --output /tmp/dcm-color-source-scaled-implementation/v5-stable --repeats 2 --warmups 1 --phase integrated --check > /tmp/dcm-color-source-scaled-implementation/v5-stable.log 2>&1
worker/.venv/bin/python scripts/reliability-benchmark.py --verify-evidence /tmp/dcm-color-source-scaled-implementation/v5-stable/results.json
```

Both commands exit0. All52 cases and98 unchanged assertions pass. The verifier returns empty integrity and publication problem lists. `current_source_changed_during_run=false`. This source is the exact final integrated snapshot identified above.

Public pipeline results round both transport fixtures to58.97 and both support fixtures to77.32. Raw per-trial outputs, immutable source ZIP, fixture inputs, source hashes, and the benchmark report remain in `v5-stable/`.

This is actual production source, not a design adapter or monkeypatch. V5 timings are sequential file-based pipeline calls after imports. They exclude process startup and stdio/RPC. This local evidence pass does not replace independent review or authorize parent publication.

## Six fresh final-source pipeline deadline probes

```sh
worker/.venv/bin/python /tmp/dcm-color-source-scaled-implementation/deadline-stable/deadline_probes.py > /tmp/dcm-color-source-scaled-implementation/deadline-stable/deadline_probes.log 2>&1
```

Each trial starts a fresh process, imports actual production, reads generated PNGs, and calls `pipeline.compare(mode="widget",return_visuals=False)`. Each outer process has the unchanged30s deadline, including startup and JSON output. The final probe set runs after the final pipeline prose freeze, without any adapter.

- Far32 pipeline times are .11646541696973145s and .12181333301123232s. Process walls are .9661148749291897s and .8444745000451803s.
- Noise768 pipeline times are .42507100000511855s and .40043695794884115s. Walls are1.145220834063366s and1.16895966604352s.
- Independent768 pipeline times are .3944452080177143s and .38232625008095056s. Walls are1.137822583084926s and1.0955818329239264s.

All six exit0 within30s, return color status scored, and disclose the production v2 metric. Far32 remains below10. Noise and independent noise remain above90. Maximum observed process RSS is311,132,160 bytes on macOS, including scientific imports and full pipeline arrays.

An earlier six-probe set before final pipeline prose integration is retained separately in this directory's top-level `deadline_probes.json`. It also passes, with maximum wall1.4074611250543967s and RSS294,223,872 bytes. It is not substituted for the final-source measurements.

The work remains O(pixels) plus64 fixed projections and24 fixed-grid convolutions. Source-specific scaling adds exponentials but no additional convolutions, search, cardinality gates, input-dependent iterations, or sampling. Measured process RSS is not color-only memory or a universal bound. These small host samples are not percentiles, a cross-platform SLA, a proof of universal monotonicity, or global perceptual accuracy.

## Final-source repetition and freeze

The five non-color entrypoints all pass again after the final parent-owned pipeline prose freeze. The final reliability repetition passes36/36 in22.398s. The final loop exits0:

```sh
for test in test_pipeline test_calibration test_robustness test_motion test_reliability; do
  worker/.venv/bin/python "worker/tests/$test.py" > "/tmp/dcm-color-source-scaled-implementation/final-worker/$test.log" 2>&1 || exit $?
done
```

Final rehash matches both owned identities and the final pipeline identity above. All requested local implementation gates are complete. No further source/test edits are planned. Final copies are preserved as `final_color.py` and `final_test_color_stability.py`. The drifted V5 and earlier probe outputs remain separately retained. Independent review and parent-controlled publication are not claimed by this handoff.

The Model the Domain principle kept one source-query normalization policy instead of parallel alternatives. Test Behavior, Not Implementation retained behavioral gates and made the approved certificate migration explicit. Prove It Works required final production gates, stable-source V5 evidence, and actual fresh pipeline processes instead of borrowing design measurements. No agents or commits were used.
