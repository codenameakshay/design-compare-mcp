import { z } from "zod";

/** Comparison rigor. `widget` = tight crop, assume rough alignment, strict.
 *  `screen` = full UI, robust auto-alignment, tolerant + region-based. */
export const CompareMode = z.enum(["widget", "screen"]);
export type CompareMode = z.infer<typeof CompareMode>;

/** Box as [x, y, w, h] in pixels of the normalized reference canvas. */
export const Box = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const CompareInputShape = {
  reference: z
    .string()
    .describe("Path to the reference/goal design image (PNG/JPG)."),
  candidate: z
    .string()
    .describe(
      "Path to the candidate image — app screenshot, video frame, or cropped widget.",
    ),
  mode: CompareMode.default("screen").describe(
    "'widget' = tight crop, strict scoring; 'screen' = full UI, tolerant, auto-aligned.",
  ),
  ignoreRegions: Box.array()
    .optional()
    .describe(
      "Regions of the reference to exclude from scoring (e.g. an unreproducible hero image).",
    ),
  preset: z
    .enum(["default", "dark-ui"])
    .optional()
    .describe(
      "Weighting preset. 'default' = balanced 5-dimension. 'dark-ui' = calibrated for dark, " +
        "single-theme UI ports (layout-dominant, color down-weighted, content/spacing off). " +
        "Explicit `weights` still override individual dimensions.",
    ),
  weights: z
    .record(z.string(), z.number())
    .optional()
    .describe(
      "Optional per-dimension weight overrides (layout/color/content/typography/spacing) for the overall score.",
    ),
  returnVisuals: z
    .boolean()
    .default(true)
    .describe("Include overlay / side-by-side diagnostic images in the result."),
};

export const CompareInput = z.object(CompareInputShape);
export type CompareInput = z.infer<typeof CompareInput>;

/** A frame sequence: a directory of frames (sorted by name) or explicit paths. */
const FrameSource = z
  .union([z.string(), z.string().array()])
  .describe("Directory of frames (sorted by filename) or an array of frame image paths.");

export const CompareMotionInputShape = {
  reference: FrameSource.describe(
    "Reference frame sequence — a directory of frames or an array of paths (captured over time).",
  ),
  candidate: FrameSource.describe(
    "Candidate frame sequence — a directory of frames or an array of paths.",
  ),
  maxFrames: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Cap frames loaded per sequence (default 240)."),
  returnVisuals: z
    .boolean()
    .default(true)
    .describe("Include the motion-signature chart (reference vs candidate over time)."),
};

export const CompareMotionInput = z.object(CompareMotionInputShape);
export type CompareMotionInput = z.infer<typeof CompareMotionInput>;

const Point = z.tuple([z.number(), z.number()]);

export const CaptureFramesInputShape = {
  url: z
    .string()
    .describe("Page URL to capture over time (e.g. a component preview; a local dev URL for your app)."),
  frames: z.number().int().min(2).max(120).default(12).describe("Number of frames to capture."),
  intervalMs: z.number().int().min(30).max(2000).default(130).describe("Milliseconds between frames."),
  clip: z
    .object({ x: z.number(), y: z.number(), width: z.number(), height: z.number() })
    .optional()
    .describe("Region to capture (default full viewport). Use to crop to the component preview."),
  viewport: z
    .object({ width: z.number(), height: z.number() })
    .optional()
    .describe("Viewport size in CSS px (default 1440x1600)."),
  waitMs: z
    .number()
    .int()
    .min(0)
    .max(20000)
    .default(1500)
    .describe("Wait after load before capturing, for the page to settle/mount."),
  waitForFlutter: z
    .boolean()
    .default(false)
    .describe("Wait for a Flutter <flutter-view> to mount before capturing (Flutter web apps)."),
  actions: z
    .object({
      click: Point.optional().describe("Click at [x, y] (e.g. navigate an SPA or open a component)."),
      hover: Point.optional().describe("Move the pointer to [x, y] (e.g. reveal a tooltip)."),
      wait: z.number().optional().describe("Wait this many ms after the step."),
    })
    .array()
    .optional()
    .describe("Pre-capture steps run in order to navigate or trigger an interaction before sampling frames."),
  outDir: z
    .string()
    .optional()
    .describe("Directory to write frames to (default: a fresh temp dir). Pass its path to compare_motion."),
};

export const CaptureFramesInput = z.object(CaptureFramesInputShape);
export type CaptureFramesInput = z.infer<typeof CaptureFramesInput>;
