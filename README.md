# design-compare-mcp

An MCP server that scores how closely a **candidate** UI image (an app screenshot, video frame, or
cropped widget) matches a **reference** design image, and hands the calling agent a prioritized
punch-list of what to fix — built to drive an iterative "hill-climb the clone" loop.

See [PLAN.md](PLAN.md) for the full design and rationale.

## Status

**Phase 5 — hardening (done).** The worker is now supervised and self-healing (a crash respawns on
the next request with backoff instead of bricking the session), each of the five metrics is isolated
(one failing on a degenerate input yields `null` for that dimension, not a failed compare), inputs
are size-capped before decode, and the stdout protocol channel is isolated from stray library
output. See **Hardening & limits** below. Verified by `worker/tests/test_robustness.py`,
`scripts/resilience.mjs` (`npm run resilience`), and `scripts/stress.py`.

**Phase 4 — calibration (done).** Adds a calibration harness and label-free guarantees. See
[calibration/README.md](calibration/README.md): monotonicity (perturbing a dimension drives its
sub-score down, Spearman ≤ −0.9), gaming-resistance (geometric mean stays ≤ the weighted arithmetic
mean), and determinism, all enforced by `worker/tests/test_calibration.py`. A manifest harness
(`worker/calibration/run_calibration.py`) scores labeled real pairs and reports Spearman/MAE plus a
(report-only) weight search. Drop real `(reference, implementation, label)` pairs into
`calibration/` to tune against reality.

**Phase 3 — all five dimensions live (done).** `compare_designs` scores **layout** (SSIM), **color**
(dominant-palette ΔE2000 matching), **content-presence** (region segmentation + IoU, reporting
missing/extra), **typography** (text amount + scale — not font identity), and **spacing** (block
margins + vertical rhythm). `overall` is the weighted **geometric mean** over the *applicable*
dimensions — a dimension returns `null` when not applicable (no text → typography; no major blocks →
content/spacing), so identical inputs score ~100 for both card- and text-heavy screens. Optional
`weights` override the defaults. Typography and spacing are coarse pixel heuristics (modest weight);
font family/weight and fine spacing are left to the host's vision model. Four diagnostic images are
returned: overlay, diff heatmap, content regions (green=matched/red=missing/orange=extra),
side-by-side.

Earlier: **Phase 2** — color + content + geometric-mean aggregation. **Phase 1** — normalize → align
(ECC) → SSIM + visuals. **Phase 0** — TS MCP server + long-lived Python worker over stdio.

## Architecture

```
Host agent ──MCP/stdio──► TS server ──spawns once──► Python vision worker (persistent)
```

The Python worker stays resident so heavy imports (opencv/torch, later phases) load once, not
per call. TS ↔ Python speak newline-delimited JSON; the worker's stdout is a clean protocol
channel and all diagnostics go to stderr.

## Requirements

- Node ≥ 20 (developed on 24)
- Python ≥ 3.10 (developed on 3.13); Phase 0 uses only the standard library

## Develop

```bash
npm install
npm run build      # tsc -> dist/
npm run smoke      # end-to-end: launches the server, calls ping + compare_designs
npm run dev        # run from source via tsx (no build step)
```

`npm run smoke` should end with `ALL CHECKS PASSED ✅`.

## Motion & calibration

Real-pair calibration against a dark motion-component library (beUI → its Flutter port) surfaced two
things static image comparison cannot do, addressed in `scripts/` + `worker/vision_worker/motion.py`:

- **Weight calibration** (`scripts/calibrate.py`) — scores human-labeled pairs, reports per-dimension
  Spearman, and searches weights. On that dataset only layout + typography tracked human judgment;
  the `dark-ui` preset encodes the result.
- **Capture harness** (`scripts/capture_pairs.mjs`) — puppeteer; reference by URL, Flutter candidate by
  coordinate-clicking the sidebar (no URL deep-linking in the web build).
- **Motion comparison** (`worker/vision_worker/motion.py`, `scripts/capture_frames.mjs` +
  `scripts/motion_score.py`) — the calibration's biggest finding was a **motion ceiling**: a static
  screenshot can't see animation, so the tool over-scored motion/interaction components. `motion.py`
  compares two frame *sequences* by motion energy + temporal rhythm — the temporal signal a single
  frame lacks. Exposed as the **`compare_motion`** MCP tool (see Tools).

## Configuration

- `DESIGN_COMPARE_PYTHON` — Python interpreter for the worker. Defaults to `worker/.venv/bin/python`
  if present, else `python3`.
- `DESIGN_COMPARE_ALLOWED_ROOTS` — optional `:`-separated directories. When set, the worker refuses
  to read image paths outside these roots (after resolving symlinks). Unset (default) allows any
  local path — the single-user local-trust assumption. Set this if the server is exposed to an
  untrusted or prompt-injectable host.

## Hardening & limits

- **Supervised worker.** If the Python worker dies (OOM, native crash), the next request lazily
  respawns it with exponential backoff; a previously-healthy crash triggers one idempotent retry. One
  crash costs at most a single failed call, never the whole session.
- **Per-metric isolation.** Each of the five dimensions runs independently — a metric that throws on
  a degenerate input returns `null` (with the error in `measurements`) while the others and the
  overall still compute.
- **Input caps.** Images are rejected before pixel decode if larger than ~40 MP or 12000 px on a
  side (`worker/vision_worker/io_utils.py`), bounding decode memory. PIL's decompression-bomb guard
  is a second backstop. Non-images and bad paths return typed errors.
- **Protocol isolation.** The worker reserves the real stdout fd for framed JSON responses and
  repoints `sys.stdout`/fd 1 at stderr, so stray library output can never corrupt the channel.
- **Serialization.** The worker processes requests one at a time; the 30 s per-request timeout is a
  safety net for a dropped response. It is not a general concurrency layer.
- **Trust model.** The tool reads whatever local image paths it is given and returns downscaled
  thumbnails of them. It never returns raw file bytes (non-images error out). For untrusted hosts,
  set `DESIGN_COMPARE_ALLOWED_ROOTS`.

## Register with a host

Claude Code:

```bash
claude mcp add design-compare -- node /absolute/path/to/design-compare-mcp/dist/index.js
```

Or in an MCP client config (e.g. Claude Desktop):

```json
{
  "mcpServers": {
    "design-compare": {
      "command": "node",
      "args": ["/absolute/path/to/design-compare-mcp/dist/index.js"]
    }
  }
}
```

## Tools

- `ping` — health check; round-trips a message through the Python worker.
- `compare_designs` — inputs: `reference` (path), `candidate` (path), `mode` (`widget`|`screen`),
  optional `preset` (`default` | `dark-ui`), `ignoreRegions`, `weights`, `returnVisuals`. The
  `dark-ui` preset is layout-dominant with color down-weighted and content/spacing off — calibrated
  on a dark, single-theme component-library port (raised Spearman vs. human labels from ~0 to ~0.44).
  Returns overall score, five sub-scores
  (layout/color/content/typography/spacing; each `null` when not applicable to the pair),
  `cv_findings`, `critique_rubric`, alignment diagnostics, and diagnostic images as MCP image
  content blocks.
- `compare_motion` — inputs: `reference`, `candidate` (each a directory of frames or an array of
  frame paths captured over time), optional `maxFrames`, `returnVisuals`. Returns `motion_score`
  (energy-ratio match; 0 when one side animates and the other is static), `temporal_corr` (rhythm
  match), per-side motion energy, and a `motion_signature` chart. Measures animation fidelity — the
  temporal dimension `compare_designs` is blind to. Content-agnostic (compares change over time, not
  appearance), so it works even when the two sources show different example content. Capture frames
  with `scripts/capture_frames.mjs`.
