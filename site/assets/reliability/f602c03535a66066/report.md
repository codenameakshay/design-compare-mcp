# Synthetic reliability benchmark

Phase: **integrated**. Integration rerun requested by caller; inspect source hashes and failed checks before publication.

Baseline: `b7139a2d29bc5fd2cae567688e5660b501f509ec` executed from a Git archive.
Current source snapshot: `fa35542962f731dd8dd9317d5448567023ae4ca66c4fefe9e90bc8de1be4d2e9`.

Generated fixtures only. No product captures or private screenshots. Higher scores are similarity, not accuracy percentages.

## Selected results

| Case | Baseline / current overall | Baseline / current color or motion | Baseline / current median ms |
| --- | ---: | ---: | ---: |
| screen_identical | 100.00 / 100.00 | 100.00 / 100.00 | 143.36 / 386.92 |
| translation_-2 | 97.84 / 99.42 | 92.30 / 100.00 | 140.32 / 401.00 |
| crop_-2 | 93.48 / 93.98 | 95.57 / 98.20 | 137.00 / 410.69 |
| translation_-1 | 98.81 / 99.71 | 95.57 / 100.00 | 133.80 / 401.97 |
| crop_-1 | 96.02 / 96.60 | 95.29 / 98.18 | 130.22 / 397.01 |
| translation_+1 | 98.55 / 99.71 | 94.33 / 100.00 | 129.08 / 398.54 |
| crop_+1 | 95.92 / 96.34 | 96.08 / 98.19 | 133.70 / 391.90 |
| translation_+2 | 98.68 / 99.42 | 96.33 / 100.00 | 139.12 / 394.52 |
| crop_+2 | 92.59 / 93.57 | 93.25 / 98.29 | 138.33 / 406.10 |
| accent_recolored | 97.29 / 99.14 | 87.20 / 95.79 | 122.34 / 394.60 |
| accent_missing | 95.81 / 96.27 | 92.61 / 94.87 | 127.14 / 400.59 |
| color_mass_50_to_50 | 100.00 / 100.00 | 100.00 / 100.00 | 16.32 / 171.26 |
| color_mass_50_to_56_25 | 39.55 / 36.99 | 100.00 / 75.24 | 16.00 / 175.70 |
| color_mass_50_to_62_5 | 38.69 / 33.84 | 100.00 / 56.61 | 16.99 / 175.02 |
| color_mass_50_to_81_25 | 35.94 / 25.72 | 100.00 / 24.11 | 16.89 / 174.07 |
| color_mass_81_25_to_18_75 | 30.53 / 15.63 | 100.00 / 5.81 | 17.59 / 191.72 |
| color_periodic_crop_0px | 100.00 / 100.00 | 100.00 / 100.00 | 58.70 / 352.57 |
| color_periodic_crop_1px | 91.83 / 93.79 | 91.40 / 100.00 | 57.75 / 324.67 |
| color_periodic_crop_2px | 87.66 / 89.35 | 92.20 / 100.00 | 59.17 / 335.83 |
| color_periodic_crop_3px | 85.81 / 86.21 | 98.04 / 100.00 | 57.86 / 368.31 |
| color_periodic_crop_4px | 82.19 / 83.37 | 94.12 / 100.00 | 57.75 / 375.43 |
| color_nine_stripes_rgb_plus_one | 99.66 / 99.56 | 98.59 / 98.18 | 94.82 / 535.90 |
| color_single_red_pixel | 99.99 / 99.99 | 99.99 / 100.00 | 70.66 / 407.78 |
| color_small_red_accent_missing | 19.50 / 17.59 | 97.27 / 62.69 | 77.89 / 396.03 |
| color_new256color_clean_crop_0px | 29.31 / 24.49 | 68.59 / 31.96 | 14.97 / 159.38 |
| color_new256color_clean_crop_1px | 29.33 / 24.49 | 68.72 / 31.96 | 14.72 / 166.41 |
| color_new256color_common_pixel_crop_0px | 29.31 / 24.49 | 68.59 / 31.96 | 14.91 / 152.79 |
| color_new256color_common_pixel_crop_1px | 29.33 / 24.49 | 68.72 / 31.96 | 14.92 / 159.34 |
| color_transport256_clean | 90.94 / 87.64 | 68.98 / 58.97 | 3.74 / 120.26 |
| color_transport256_common_pixel | 90.94 / 87.64 | 68.98 / 58.97 | 4.07 / 122.08 |
| color_shortlist32_clean | 18.90 / 18.27 | 89.21 / 77.32 | 12.82 / 142.86 |
| color_shortlist32_common_pixel | 18.90 / 18.27 | 89.21 / 77.32 | 13.01 / 143.19 |
| header_omitted_full | 38.29 / 37.05 | 58.47 / 49.57 | 123.25 / 403.23 |
| header_omitted_scoped | 100.00 / 100.00 | 100.00 / 100.00 | 55.21 / 292.31 |
| header_omitted_ignored | 100.00 / 100.00 | 100.00 / 100.00 | 124.53 / 420.23 |
| scope_all_ignored | 100.00 / 100.00 | 100.00 / 100.00 | 70.09 / 367.48 |
| scope_all_ignored_different_fill | 1.00 / 1.00 | 0.52 / 0.43 | 53.47 / 292.98 |
| ecc_failure | 14.68 / 14.76 | 2.72 / 2.76 | 48.49 / 312.67 |
| flat_identical_screen | 100.00 / 100.00 | 100.00 / 100.00 | 48.76 / 287.53 |
| flat_identical_widget | 100.00 / 100.00 | 100.00 / 100.00 | 44.16 / 278.38 |
| settings_dark_ui | 82.46 / 81.11 | 58.47 / 49.57 | 123.45 / 389.64 |
| settings_custom_weights | 38.63 / 35.22 | 58.47 / 49.57 | 120.67 / 387.75 |
| settings_widget | 38.29 / 37.05 | 58.47 / 49.57 | 76.18 / 404.82 |
| settings_context_v1 | 38.29 / 37.05 | 58.47 / 49.57 | 123.20 / 382.93 |
| settings_context_v2 | 38.29 / 37.05 | 58.47 / 49.57 | 122.41 / 384.51 |
| latency_screen_visuals | 100.00 / 100.00 | 100.00 / 100.00 | 137.06 / 401.11 |
| motion_identical | null / null | 100.00 / 100.00 | 2.99 / 3.06 |
| motion_reversed | null / null | 100.00 / 100.00 | 2.94 / 2.84 |
| motion_shifted | null / null | 100.00 / 100.00 | 2.78 / 2.86 |
| motion_unequal | null / null | 89.30 / 89.30 | 3.24 / 3.42 |
| motion_static | null / null | 0.00 / 0.00 | 2.63 / 2.75 |
| motion_both_static | null / null | null / null | 2.45 / 2.51 |

## Capture, scope and alignment

- `header_omitted_full`. baseline: diagnostics absent; current: ok, issues none, scope {'ignored_fraction': 0.0, 'compared_fraction': 1.0}.
- `header_omitted_scoped`. baseline: diagnostics absent; current: ok, issues none, scope {'ignored_fraction': 0.0, 'compared_fraction': 1.0}.
- `header_omitted_ignored`. baseline: diagnostics absent; current: review, issues mask_fill_semantics, scope {'ignored_fraction': 0.25, 'compared_fraction': 0.75}.
- `scope_all_ignored`. baseline: diagnostics absent; current: inconclusive, issues mask_fill_semantics, empty_compare_scope, scope {'ignored_fraction': 1.0, 'compared_fraction': 0.0}.
- `scope_all_ignored_different_fill`. baseline: diagnostics absent; current: inconclusive, issues mask_fill_semantics, mask_fill_colors_differ, empty_compare_scope, scope {'ignored_fraction': 1.0, 'compared_fraction': 0.0}.
- `ecc_failure`. baseline: diagnostics absent; current: review, issues near_uniform_input, near_uniform_input, alignment_unresolved, scope {'ignored_fraction': 0.0, 'compared_fraction': 1.0}.
- `translation_+2`. baseline: diagnostics absent; current: review, issues translation_applied, scope {'ignored_fraction': 0.0, 'compared_fraction': 1.0}.

## Relationship checks

baseline: 68/98 checks passed.

- `color_jitter_above_real_changes`: Every 1/2px crop/translation color score exceeds both real accent-change scores by >2 points.
- `color_mass_change_monotonic`: Increasing same-color coverage changes lower color similarity by >1 point per step; identical coverage scores >=99.
- `color_major_mass_swap_detected`: A 62.5 percentage-point same-color mass swap has color score <25, not a perfect palette match.
- `color_mass_50_to_81_25_distribution_finding`: A major same-color coverage change produces a public color_distribution finding.
- `color_mass_81_25_to_18_75_distribution_finding`: A major same-color coverage change produces a public color_distribution finding.
- `color_periodic_crop_stable`: Equal-histogram periodic crops keep color similarity >=99 with <1 point spread; no overall/layout claim.
- `color_small_accent_distinct_from_speck`: Removing about 1.25% red accent scores <95 and >5 points below one-pixel contamination; noise tolerance must not hide accents.
- `color_new256color_missing_accent_detected`: All four unchanged 5% missing-red-accent comparisons score <95 and retain a public color_missing finding.
- `color_transport256_mass_retained`: Both same-support mass swaps score <90 and retain color_distribution without invented color_missing/color_added findings.
- `ecc_failure_warning`: Real ECC nonconvergence exposes a review issue and stable fallback outcome/reason, not only a free-text note.
- `partial_mask_disclosed`: Ignoring the header reports review, fill-based mask semantics and about one-quarter nominal ignored area.
- `scope_all_ignored_inconclusive`: No retained pixels means inconclusive scope regardless of the preserved legacy numeric score.
- `scope_all_ignored_original_capture_stats`: Capture observations describe the textured originals, not the uniform mask-filled canvases.
- `scope_all_ignored_different_fill_inconclusive`: No retained pixels means inconclusive scope regardless of the preserved legacy numeric score.
- `scope_all_ignored_different_fill_original_capture_stats`: Capture observations describe the textured originals, not the uniform mask-filled canvases.
- `different_fill_disclosed`: Different per-image ignore fill colors are disclosed.
- `flat_identical_screen_honest_warning`: Identical solid pixels need near-uniform review but no unresolved alignment or failed-capture claim.
- `flat_identical_widget_honest_warning`: Identical solid pixels need near-uniform review but no unresolved alignment or failed-capture claim.
- `widget_identity_intentional`: Widget identity is intentional and does not create an unresolved screen-alignment warning.
- `translation_not_hidden`: Accepted global translation remains reviewable and shows lower identity layout similarity.
- `identical_textured_no_false_warning`: An identical textured input does not receive mechanical review warnings.
- `motion_reversed_semantics`: Equal energy must be labeled energy-only; unknown capture cadence makes timing inconclusive.
- `motion_shifted_semantics`: Equal energy must be labeled energy-only; unknown capture cadence makes timing inconclusive.
- `unequal_no_prefix_timing_claim`: Unequal lengths expose an inconclusive timing result, not a correlated truncated prefix.
- `settings_provenance_distinct`: Worker comparison_key is present and changes across preset, weights, mode, and ignore settings.
- `candidate_change_same_comparison`: Changing only candidate pixels preserves comparison_key and changes run_key.
- `visuals_do_not_split_identity`: Visual generation does not change either worker identity key.
- `scope_changes_comparison`: Changing reference crop and declared mode starts a new comparison.
- `protocol_changes_comparison`: Caller-declared protocol changes affect comparison_key when comparison_context metadata is supported.
- `context_does_not_rescore`: Accepted protocol metadata must not change numeric scoring for identical pixels/settings.

current: 98/98 checks passed.


## How to read this run

- These hand-built examples test specific failure modes. They do not estimate real-world accuracy or savings.
- Full-image omitted content is a real mismatch. The comparable-region result measures a different, caller-declared scope.
- Same-color mass changes are real mismatches. Periodic crops preserve exact RGB counts; only their color score should remain stable, not necessarily layout/overall.
- Color controls use the file-based public worker comparison pipeline in widget mode, not direct color_score calls. Mass, periodic and red-accent controls use canonical 768px width; nine-stripe inputs exercise normal upscaling from 144px.
- Motion energy similarity does not establish timing fidelity. Generated frames have known order but no verified capture timestamps.
- Timings are sequential in-process API calls after imports, with one CPU thread. They exclude process startup and transport. Each side uses a separate process and the same interpreter/dependencies.
- Per case: 1 discarded warmup calls; 3 measured calls. Small-sample min/median/max are descriptive, not a statistical performance claim.
- Raw JSON preserves every measured and warmup result. Only visualization base64 is replaced by byte counts and SHA-256 hashes. No numeric worker score is rewritten.
- Missing worker diagnostics/provenance remain missing. Benchmark input/source provenance is separate from worker-provided fields.

## Reproduction

```sh
/Users/codenameakshay/Development/codenameakshay/design-compare-mcp/worker/.venv/bin/python scripts/reliability-benchmark.py --baseline b7139a2d29bc5fd2cae567688e5660b501f509ec --output /Users/codenameakshay/Development/codenameakshay/design-compare-mcp/docs/reliability/runs/final-rerun --repeats 3 --warmups 1 --phase integrated
```

Use a new output directory for every rerun. See `../../README.md` for the schema and options.
Read `results.json`, `raw/*.json`, `raw/current-source.zip`, `fixtures/examples.png`, and `fixtures/color-controls-examples.png` for full evidence.
