import fs from "node:fs";
import path from "node:path";

const serverTempDirs = new Set<string>();

export function allowedRoots(): string[] {
  const raw = process.env.DESIGN_COMPARE_ALLOWED_ROOTS ?? "";
  if (!raw.trim()) return [];
  return raw
    .split(path.delimiter)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function assertReadableFile(file: string): string {
  if (!path.isAbsolute(file)) throw new Error("Use an absolute local file path; relative paths resolve in the server working directory, not the caller project");
  const resolved = fs.realpathSync(file);
  const roots = allowedRoots();
  if (roots.length && !roots.some(root => isInsideRoot(resolved, resolveReal(root)))) {
    throw new Error(`File is outside DESIGN_COMPARE_ALLOWED_ROOTS: ${file}`);
  }
  if (!fs.statSync(resolved).isFile()) throw new Error(`Not a regular local file: ${file}`);
  return resolved;
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
