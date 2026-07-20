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
  returnVisuals: z
    .boolean()
    .default(true)
    .describe("Include overlay / side-by-side diagnostic images in the result."),
};

export const CompareInput = z.object(CompareInputShape);
export type CompareInput = z.infer<typeof CompareInput>;
