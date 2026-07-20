# design-compare-mcp

An MCP server that scores how closely a **candidate** UI image (an app screenshot, video frame, or
cropped widget) matches a **reference** design image, and hands the calling agent a prioritized
punch-list of what to fix — built to drive an iterative "hill-climb the clone" loop.

See [PLAN.md](PLAN.md) for the full design and rationale.

## Status

**Phase 2 — color + content dimensions + aggregation (done).** `compare_designs` scores three
dimensions: **layout** (SSIM), **color** (dominant-palette ΔE2000 matching), and **content-presence**
(region segmentation + IoU matching, reporting missing/extra elements). `overall` is the weighted
**geometric mean** over scored dimensions (so no single dimension can be farmed); optional `weights`
override the defaults. Findings name shifted colors as hex pairs and locate missing/extra regions.
Four diagnostic images are returned: overlay, diff heatmap, content regions
(green=matched/red=missing/orange=extra), side-by-side. Typography and spacing are still pending.

Earlier: **Phase 1** — normalize → align (ECC) → SSIM + visuals. **Phase 0** — TS MCP server boots a
long-lived Python worker and multiplexes requests over stdio.

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
  optional `ignoreRegions`, `returnVisuals`. Returns overall score, five sub-scores
  (layout/color/content/typography/spacing), `cv_findings`, `critique_rubric`, alignment diagnostics,
  and diagnostic images as MCP image content blocks. Phase 1 scores `layout` (SSIM); the other
  dimensions report `null` with a "pending" reason.
```
