# Landing site

The marketing and documentation site for **design-compare-mcp** is a build-free static page with
optional CDN-loaded scroll enhancement, Google Fonts and remote Unsplash images. It explains the
comparison tools and installation. Browser demos illustrate formulas; they do not run the worker.

```
site/
  index.html    # structure + copy
  styles.css    # all styling (no framework)
  app.js        # scroll reveal, count-up, copy buttons, the two demos
```

## Run locally

Any static file server works:

```bash
cd site
python3 -m http.server 8099
# open http://127.0.0.1:8099
```

`?still=1` disables the site's decorative CSS/JS animations and reveals sections for screenshots.
Native video controls remain available. It does not freeze user-played video or synchronize footage.

## Deploy

A GitHub Actions workflow (`.github/workflows/pages.yml`) publishes this folder to GitHub Pages.
One-time setup: **repo Settings → Pages → Source: "GitHub Actions"**. After that, any push to `main`
that touches `site/` redeploys. The published URL is `https://codenameakshay.github.io/design-compare-mcp/`.

Local asset paths are relative. Google Fonts (Archivo, Gabarito, JetBrains Mono), Unsplash images
and optional Lenis scroll enhancement load remotely. The page works on any static host.

## Notes

### DryLender case study

The case study sits immediately after the hero at `#drylender-case-study`. Its HTML, descriptions,
native video controls, direct-file links and method disclosure work without JavaScript. The hero
CTA and footer link jump to it; the only JavaScript addition transfers keyboard focus to the section
when the existing smooth-scroll handler intercepts that jump.

The media lives at these project-relative paths:

```
assets/drylender/original.mp4
assets/drylender/original-poster.jpg
assets/drylender/clone.mp4
assets/drylender/clone-poster.jpg
```

Both edits are silent H.264 MP4s. Native playback is independent, with no autoplay and
`preload="none"`. The 590×1278 reference and 720×1680 clone keep their full portrait frames,
capped at 600px tall and stacked below 780px. Descriptions sit beside each player.

The original includes only settings, calendar settings and the drink editor. The clone demo
predates the build-4 tap fix. Keep edits, source credit and build context accurate when replacing
media. Third-party UI and footage are not covered by this repository's MIT license.

Historical local development pointers: `/tmp/drylender-parity/parity.py` and `score.mjs` for regional
`compare_designs` diagnostics; `motion.mjs` for selected `compare_motion` runs. These paths are
non-portable, not retained public benchmark artifacts or a source for new measured examples.
Extraction was manual. The <code>extract_video_frames</code> tool turns a bounded local recording window into
absolute frame paths and a provenance manifest. It was added after the recorded development work.

Before publishing, review footage permissions and redactions, confirm posters and descriptions,
and test playback/seek/fullscreen on real iOS Safari. Check 320px reflow, 200% zoom, keyboard
focus, disabled JavaScript, reduced motion and failed-media fallback links. Verify relative URLs
under `/design-compare-mcp/`; local checks do not establish deployed availability.

### Existing demos

- The aggregator illustrates a weighted geometric mean on user-supplied scores. Its preset weights
  and floor of 1 were checked against `aggregate.py`; its starting scores are illustrative.
- The color picker illustrates a single ΔE2000 pair. Its feedback is illustrative, not worker findings.
  CIEDE2000 remains the correct label for that demo. The production worker uses a different
  metric and does not make the demo a full-image comparison.
  Neither demo reproduces the full worker, status handling or image diagnostics.
- The visual language is an original adaptation inspired by editorial landing-page design; all copy is
  specific to this project.

### Worker color policy and publication limits

The production worker's [frozen color policy](../calibration/README.md#color-policy-and-regression-checks) replaces
palette-size gates and bounded shortlists with one fixed soft lattice. It combines maximum sliced
mass distance across 64 fixed directions with separate soft rare-color coverage.
Source-query `alpha = 0.05 / max(local_density, 0.05)` scales both own and target occupancy in
each direction. Effective query mass resolution is `0.001 / alpha`. The scalar constants are unchanged.
The score uses chroma-compressed Lab proxy units, not CIEDE2000, exact matching, or 3D optimal transport.
Missing or added findings need conservative absence certificates. A soft coverage deficit does not
prove exact absence, and no color finding establishes spatial correspondence.
`color_shift` summarizes certified unmatched mass on both sides, not any recoloring operation.
Failure to certify absence does not prove a color is present or has a nearby counterpart.

The [color measurement API](../calibration/README.md#color-measurement-api) identifies metric
`soft_grid_source_density_scaled_clearance_v2` and units `chroma_compressed_lab_proxy`.
It returns raw `coverage_distance = S` and `weighted_coverage_distance = 0.9 × S` separately.
`distance` is `max(mass_distance, weighted_coverage_distance)`, and `decay` is 19.
Nested `coordinate_system`, `lattice`, `mass_method`, `coverage_method`, and `certificate` describe
the calculation. The old CIEDE2000, palette, exact-support, and shortlist fields have no aliases.
The coverage method is `source_density_scaled_bidirectional_soft_clearance`. Its `source_alpha`,
`query_mass_resolution`, and `occupancy_scaling` strings disclose source-query normalization.

The frozen v2 contract has passed [local color qualification and independent review](../docs/reliability/limitations/README.md).
Full-project checks (`npm test` and `npm run lifecycle`) passed locally.
Hosted CI, merge, and deployment remain unverified.
The review retains a close-hue case whose score rises from 98.13474 to 98.60238 as recolored mass
grows from 2.5% to 5%, with no findings. Finite sweeps do not establish general monotonicity or accuracy.
Reconcile measured examples with the final frozen source before publication.
Do not present the prototype as a qualified worker or publish its provisional scores, timings, or
labeled results as production measurements. Historical examples need explicit metric-version
qualifications, and score deltas need baselines re-scored under the same version.
Available labeled calibration is weak. Synthetic controls do not establish universal accuracy.

### Measured example renderer

Use the `reliability-examples:start/end` hook after the case study to publish verified synthetic
examples. The renderer uses schema v1.0 from [the reliability evidence guide](../docs/reliability/README.md);
it does not run or reimplement any metric. Rendering requires Node.js, Git, `unzip` and the documented
Python worker dependencies. The current Python harness is the authoritative evidence verifier.

Freeze the worker and benchmark after integration, then run from the repository root.
Use the generator version and case counts in the evidence guide. Generate and verify the final dataset before
rendering it:

```sh
worker/.venv/bin/python scripts/reliability-benchmark.py \
  --baseline b7139a2 --repeats 3 --warmups 1 --phase integrated --check \
  --output docs/reliability/runs/final

worker/.venv/bin/python scripts/reliability-benchmark.py \
  --verify-evidence docs/reliability/runs/final/results.json \
  --evidence-base docs/reliability/runs/final
```

Use a new, empty output directory for every run; never overwrite retained evidence. An integrated
phase records caller intent, not proof of integration. `--check` must pass, and publication must
also pass the renderer's source and retained-byte checks. Render the verified final bundle:

```sh
node scripts/render-reliability.mjs \
  docs/reliability/runs/final/results.json \
  --evidence-base docs/reliability/runs/final
```

Pass both final paths explicitly rather than relying on renderer defaults. This replaces the hook's
contents in `site/index.html`, retains the complete evidence directory under
`site/assets/reliability/<results-hash-prefix>/`, and writes `/tmp/dcm-reliability-show-me.html`
for local review. The section and its native details work without JavaScript. Input images and
ordered frame strips are static and never autoplay. The renderer adds no timestamps of its own,
so identical evidence produces identical output. It leaves DryLender media and historical score
qualifications unchanged. Historical evidence directories are not deleted. Publish the index and
its new evidence directory together, then verify deployed URLs separately.

Verification recomputes the full assertion ledger, including IDs, outcomes, observations and
expectations. It checks every warmup and measured trial's hash, count, API/metric status, first-result
identity, summary, timing samples, median deltas, effective parameters and determinism metadata.
`report.md` must match the authoritative report bytes, not just agree with a few headline values.
The renderer also verifies fixture bytes, source archives, manifests and raw input declarations.
It stages the verified bytes, reloads and re-verifies that bundle, and repeats publication checks
before installation. Evidence assets are installed atomically without overwriting existing bundles;
the HTML is then replaced atomically. This is not a single transaction across both paths.

Publication refuses initial/provisional phases, failed current assertions, benchmark-time source
drift, later worker/harness changes, missing color controls and changed HEAD. API or metric failures
in either implementation block publication, including failures in later trials or warmups. Baseline
relationship failures remain evidence rather than a publication blocker. A dirty snapshot is labeled
with its source manifest hash and base commit, never as the exact code at HEAD. Rerun after source
changes. Review the retained run and the site's algorithm copy against the measured source before
publishing; a passing finite dataset does not validate all inputs.

For local layout review of a retained run, use its actual directory:

```sh
node scripts/render-reliability.mjs \
  /absolute/path/to/retained-run/results.json \
  --evidence-base /absolute/path/to/retained-run \
  --preview --output /tmp/dcm-reliability-show-me.html
```

`--preview` can write only outside `site/` and always shows a provisional warning and publication
blockers. It cannot publish a final label. The scratch document has inline styles, absolute local
image paths and a transparent outer body, without viewport-height units. It is a local review
artifact; its absolute evidence links are not deployed URLs. Final site links are relative to the
retained asset directory and also work under `/design-compare-mcp/`.

The five examples separate periodic crop stability, true color-mass changes, energy-only motion,
alignment review and empty scope. Controls include recolored/removed accents, identical inputs,
static motion, identical flat inputs, unequal mask fills and full-image versus explicitly cropped
scope. Actual worker fields are printed unchanged. Missing fields read `not returned`; true nulls
remain `null`. Before/after always uses identical candidate bytes across pipeline versions.
Source manifests, fixture hashes, API settings, worker identity keys, raw JSON and the run report
remain inspectable in native details and direct links. No accuracy or speedup claim follows from
these synthetic examples.
