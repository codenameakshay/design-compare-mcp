import fs from "node:fs";
import path from "node:path";

const serverTempDirs = new Set<string>();

function allowedRoots(): string[] {
  const raw = process.env.DESIGN_COMPARE_ALLOWED_ROOTS ?? "";
  if (!raw.trim()) return [];
  return raw
    .split(path.delimiter)
    .map((p) => p.trim())
    .filter(Boolean);
}

function resolveReal(p: string): string {
  try {
    return fs.realpathSync(p);
  } catch {
    return path.resolve(p);
  }
}

function isInsideRoot(resolved: string, root: string): boolean {
  const rel = path.relative(root, resolved);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function registerServerTempDir(dir: string): void {
  serverTempDirs.add(resolveReal(dir));
}

export function assertHttpUrl(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Invalid URL: ${url}`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(
      `URL must use http: or https: (got ${parsed.protocol}). file:, data:, and other schemes are not allowed.`,
    );
  }
}

export function assertWritableDir(outDir: string): void {
  const resolved = resolveReal(outDir);
  if (serverTempDirs.has(resolved)) return;

  const roots = allowedRoots();
  if (roots.length === 0) return;

  for (const root of roots) {
    if (isInsideRoot(resolved, resolveReal(root))) return;
  }

  throw new Error(
    `outDir is outside DESIGN_COMPARE_ALLOWED_ROOTS: ${outDir}`,
  );
}
