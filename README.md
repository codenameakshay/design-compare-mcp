# design-compare-mcp

An MCP server that scores how closely a **candidate** UI image (an app screenshot, video frame, or
cropped widget) matches a **reference** design image, and hands the calling agent a prioritized
punch-list of what to fix — built to drive an iterative "hill-climb the clone" loop.

See [PLAN.md](PLAN.md) for the full design and rationale.

## Status

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

## Configuration

- `DESIGN_COMPARE_PYTHON` — path to the Python interpreter for the worker (default `python3`).
  Point this at a venv once vision dependencies are added in Phase 1.

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
  optional `ignoreRegions`, `weights`, `returnVisuals`. Returns overall score, five sub-scores
  (layout/color/content/typography/spacing; each `null` when not applicable to the pair),
  `cv_findings`, `critique_rubric`, alignment diagnostics, and diagnostic images as MCP image
  content blocks.
```
