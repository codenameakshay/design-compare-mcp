import puppeteer from "puppeteer-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Resolve a Chrome/Chromium executable: env override, then common OS paths. */
function resolveChrome(): string {
  const env = process.env.DESIGN_COMPARE_CHROME;
  if (env) {
    if (fs.existsSync(env)) return env;
    throw new Error(`DESIGN_COMPARE_CHROME is set but not found: ${env}`);
  }
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  throw new Error(
    "No Chrome/Chromium found. Set DESIGN_COMPARE_CHROME to a browser executable path.",
  );
}

export interface CaptureAction {
  click?: [number, number];
  hover?: [number, number];
  wait?: number;
}

export interface CaptureOptions {
  url: string;
  frames?: number;
  intervalMs?: number;
  clip?: { x: number; y: number; width: number; height: number };
  viewport?: { width: number; height: number };
  waitMs?: number;
  waitForFlutter?: boolean;
  actions?: CaptureAction[];
  outDir?: string;
}

export interface CaptureResult {
  dir: string;
  frames: string[];
  count: number;
  url: string;
  intervalMs: number;
}

/**
 * Capture an ordered PNG frame sequence of a page over time, for compare_motion.
 * Optional `actions` run before capture (click/hover/wait) to navigate an SPA or
 * trigger an interaction; `clip` restricts capture to a region (e.g. a preview).
 */
export async function captureFrames(opts: CaptureOptions): Promise<CaptureResult> {
  if (!opts.url) throw new Error("'url' is required");
  const frames = Math.min(Math.max(Math.round(opts.frames ?? 12), 2), 120);
  const interval = Math.min(Math.max(Math.round(opts.intervalMs ?? 130), 30), 2000);
  const viewport = opts.viewport ?? { width: 1440, height: 1600 };
  const dir = opts.outDir ?? fs.mkdtempSync(path.join(os.tmpdir(), "dcm-frames-"));
  fs.mkdirSync(dir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: true,
    args: ["--hide-scrollbars", "--disable-gpu"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ ...viewport, deviceScaleFactor: 1 });
    await page.goto(opts.url, { waitUntil: "domcontentloaded", timeout: 45000 });

    if (opts.waitForFlutter) {
      // String predicate: evaluated in the page, so no DOM lib needed server-side.
      await page
        .waitForFunction("!!document.querySelector('flutter-view')", { timeout: 60000 })
        .catch(() => {}); // fall through to the settle wait even if it never mounts
    }
    await sleep(opts.waitMs ?? 1500);

    for (const a of (opts.actions ?? []).slice(0, 40)) {
      if (a.click) await page.mouse.click(a.click[0], a.click[1]);
      else if (a.hover) await page.mouse.move(a.hover[0], a.hover[1]);
      if (a.wait) await sleep(Math.min(Math.max(a.wait, 0), 10000));
    }

    const framePaths: string[] = [];
    for (let i = 0; i < frames; i++) {
      const p = path.join(dir, `frame_${String(i).padStart(3, "0")}.png`);
      await page.screenshot(opts.clip ? { path: p, clip: opts.clip } : { path: p });
      framePaths.push(p);
      if (i < frames - 1) await sleep(interval);
    }
    return { dir, frames: framePaths, count: framePaths.length, url: opts.url, intervalMs: interval };
  } finally {
    await browser.close();
  }
}
