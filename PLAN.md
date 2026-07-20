# design-compare-mcp — Design/Prototype Comparison MCP

An MCP server that scores how closely a **candidate** UI (a screenshot / video frame / cropped
widget from your own app) matches a **reference** design image, and hands the calling agent a
prioritized punch-list of what to fix. Built for an iterative "hill-climb the clone" loop.

## Guiding principles

1. **Actionable + monotonic beats accurate.** The score exists to drive an improvement loop, so
   every real improvement to the clone must reliably raise it, and a low score must decompose into
   *what to fix*. A single scalar from pixel-diffing is neither.
2. **CV owns the numbers. The VLM owns the words.** All numeric scores come *only* from the
   deterministic CV pipeline → same two images always produce the same score. The VLM never emits a
   score; it only produces the qualitative punch-list. This eliminates score drift and separates
   "am I making progress?" (reproducible) from "what next?" (advisory).
3. **VLM is delegated to the host.** The tool returns sub-scores + normalized/overlay images + a
   critique rubric; the calling agent (already a vision model, e.g. Claude Code) writes the
   punch-list. No API key, no extra cost.
4. **No DOM to lean on.** Inputs are images (native app screenshots, video frames, crops). All
   structure is recovered from pixels, so normalization and alignment carry the pipeline.

## Locked decisions

| Decision | Choice |
|---|---|
| Inputs | Image-in / image-out. Reference = design image; candidate = app screenshot/frame/crop. Web-URL capture is a **future optional** layer, not v1. |
| Method | Hybrid: deterministic CV score + VLM punch-list. |
| Output | Overall score + per-dimension sub-scores + punch-list (punch-list assembled by host). |
| Stack | TS MCP shell + **long-lived** Python vision worker. |
| VLM run-by | Delegated to the host agent. |
| Granularity | Both, via a `mode` param: `widget` (strict) and `screen` (tolerant). |

## Architecture

```
Host agent (Claude Code)
      │  MCP (stdio)
      ▼
TS MCP server  ──spawns once──►  Python vision worker (persistent)
  - tool registration              - normalize → align → metrics → aggregate → visuals
  - zod I/O schemas                - returns JSON scores + findings + image buffers
  - worker lifecycle + framing
```

- **Transport (TS ↔ Python):** default = long-lived subprocess, newline-framed JSON-RPC over
  stdio (single-binary packaging, no port coordination). Alternative for dev = localhost FastAPI
  worker (curl-able). **The worker must stay resident** so torch/LPIPS/model weights load once.
- **Boot:** TS spawns `python -m vision_worker`, does a `ping`/`ready` handshake, then routes each
  `compare_designs` call to the worker and marshals the result (including image buffers) back into
  the MCP tool response.

## MCP tool surface (v1)

### `compare_designs`
Inputs:
- `reference`: path or base64 image (the goal design).
- `candidate`: path or base64 image (current app render).
- `mode`: `"widget" | "screen"` (default `"screen"`).
- `weights?`: optional per-dimension overrides (see Aggregation).
- `ignore_regions?`: optional list of boxes to exclude (e.g. an unreproducible hero photo).
- `return_visuals?`: bool (default true) — include overlay/side-by-side images in the result.

Returns:
- `overall`: 0–100.
- `subscores`: `{ layout, color, typography, spacing, content }`, each `{ score, reason, measurements }`.
- `cv_findings`: machine-detected discrepancies that seed the punch-list — missing/extra regions
  (with boxes), top color deltas (hex pairs + ΔE), aspect mismatch, large-shift regions.
- `visuals`: image content blocks — a side-by-side and a **difference/overlay heatmap** — for the
  host's vision model to inspect.
- `critique_rubric`: instructions telling the host how to turn the above into a prioritized
  punch-list of `{ area, observed, expected, severity, suggested_fix }`, ranked by score impact.
- `alignment`: diagnostics (transform used, residual, whether it degraded to region-only).

### `preview_alignment` (debug, optional)
Returns just the normalized + aligned + overlay images so you can eyeball the registration.

## Pipeline

### 1. Normalize
- Decode → RGB; record original size/DPR.
- `screen` mode: detect + crop device chrome (status bar / notch / home indicator / safe areas).
  v1 heuristic = solid top/bottom bar detection; accept a manual `crop` hint as escape hatch
  (robust chrome detection is genuinely hard — see Risks).
- Resize both to a common canonical width (preserve aspect). If aspect ratios differ, letterbox and
  emit an **aspect-mismatch** finding rather than silently stretching.

### 2. Align
- `screen`: estimate a registration transform (candidate → reference). Primary = ECC
  (`findTransformECC`, euclidean/affine) on grayscale; fallback = ORB feature match + homography.
  Guard against garbage: bound translation/scale, and if residual worsens vs identity, fall back to
  identity and flag "layouts differ structurally" (then compare region-only).
- `widget`: assume rough alignment (the crop *is* the alignment); at most a small translational
  search. Strict scoring.

### 3. CV metrics (sub-scores)

| Dimension | Default weight | How |
|---|---|---|
| **Layout / structure** | 0.35 | MS-SSIM on aligned grayscale + edge-map IoU (Canny/Sobel). Optional LPIPS (perceptual) behind a flag. |
| **Content presence** | 0.15 | Segment both into major regions; match reference↔candidate. Unmatched reference regions = **missing**; unmatched candidate = **extra**. Highly actionable + monotonic. |
| **Color** | 0.20 | CIELAB histogram distance + dominant-palette (k-means) matched by ΔE2000 (Hungarian assignment). Yields "this color is off by ΔE X, #aaa vs #bbb." |
| **Typography / text** | 0.15 | Text-region detection (EAST/MSER, or Tesseract boxes). Compare block presence, position, relative size. Font family/weight identity is left to the VLM. |
| **Spacing / alignment** | 0.15 | From detected regions: gaps/margins between major blocks; compare distributions. Fuzzy → modest weight. |

### 4. Aggregate (monotonic + anti-gaming)
- Default = **weighted geometric mean** (power-mean with `p→0`): `overall = Π scoreᵢ^wᵢ`, `Σwᵢ=1`.
  A near-zero dimension drags the whole score down, so the agent can't farm color to 100 while
  layout sits at 20. Tune `p` (0 → geometric, 1 → arithmetic) on the calibration set; `p≈0.5` if
  pure geometric is too harsh.
- **Monotonicity guards:** ΔE-color and content-presence are naturally monotonic; SSIM/LPIPS are
  under alignment. The failure mode is unreproducible regions (hero images) capping the score →
  mitigated by `ignore_regions` and by clamping the max penalty any single unmatched region imposes.

### 5. Visuals
- Side-by-side + difference/overlay heatmap (where the images diverge). Returned as MCP image
  content so the host can look and refine the punch-list.

## The loop (how the agent uses this)

1. Capture current app screenshot / crop.
2. `compare_designs(reference, candidate, mode)`.
3. From `subscores` + `cv_findings` + the overlay image, assemble the punch-list (host VLM).
4. Fix the **lowest sub-score / highest-severity** item first (biggest gradient).
5. Re-capture, re-compare; track the score trend.
6. **Stop** when `overall ≥ threshold` (e.g. 90), or Δscore over last K iters `< ε` (diminishing
   returns), or max iterations. Report the trend either way.

## Calibration & validation (do not skip)

A metric that "looks plausible" but doesn't track human judgment will silently mislead the loop.
- Build ~20–40 labeled `(reference, candidate, human 0–100)` pairs spanning identical → near →
  medium → far.
- Check **Spearman correlation** between `overall` and human rank, and **monotonicity** (perturb a
  good candidate in one dimension → the matching sub-score drops).
- Tune weights + power-mean `p` against this set.
- **Gaming test:** deliberately over-optimize one dimension; confirm `overall` doesn't spike.

## Dependencies

- **TS:** `@modelcontextprotocol/sdk`, `zod`, `execa` (or `child_process`).
- **Python:** `opencv-python-headless`, `scikit-image`, `numpy`, `Pillow`, `scipy` (EMD/Hungarian),
  `scikit-learn` (k-means), a ΔE2000 lib (`colour-science` / `colormath`). Optional extras:
  `torch`+`lpips` (perceptual), `pytesseract`/EAST (text). Keep torch/tesseract **optional** to
  avoid a heavy default install.

## Proposed repo layout

```
design-compare-mcp/
  package.json                 # TS MCP server
  src/
    index.ts                   # MCP server + tool registration
    worker-client.ts           # spawn + framed JSON-RPC to the Python worker
    schema.ts                  # zod I/O schemas
  worker/
    pyproject.toml
    vision_worker/
      __main__.py              # persistent stdio (or HTTP) loop + handshake
      normalize.py
      align.py
      metrics/{layout,color,typography,spacing,content}.py
      aggregate.py
      visuals.py               # overlay / diff heatmap / side-by-side
  test/fixtures/               # calibration pairs + labels
  PLAN.md
```

## Build phases

- **Phase 0 — Skeleton:** TS MCP spawns the persistent Python worker; `ping`→`ready` handshake;
  `compare_designs` returns a stub. Proves transport + MCP registration end-to-end.
- **Phase 1 — Minimal loop:** normalize + align + MS-SSIM only; `overall` = that metric; return the
  overlay image. The loop works crudely.
- **Phase 2 — Actionable core:** add **color (ΔE palette)** and **content-presence** (missing/extra
  regions) — the two most actionable, monotonic dimensions. Geometric-mean aggregation.
- **Phase 3 — Full sub-scores:** typography/text + spacing; `cv_findings` seeding; `critique_rubric`.
- **Phase 4 — Calibrate:** labeled set, weight/`p` tuning, gaming test; optional LPIPS behind a flag.
- **Phase 5 — Optional web capture:** thin URL→screenshot layer for rich web apps.

## Open risks

- **Device-chrome detection is hard.** v1 may need a manual `crop` hint; auto-detection is
  best-effort.
- **Full-screen alignment can fail** on structurally different layouts. Must degrade gracefully:
  high residual → drop to region-only comparison + flag "layouts differ structurally."
- **Font identity from pixels is unreliable** → lean on the VLM for family/weight judgments.
- **LPIPS/torch is heavy** → keep it an optional extra, off by default.
```
