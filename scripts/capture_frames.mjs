// Capture a short FRAME SEQUENCE of an animating component preview from both
// sites, so motion (not just a resting frame) can be compared. Works for
// auto-animating components (no trigger needed), sidestepping the reference-vs-
// candidate trigger/layout divergence that blocks interaction capture.
//
// Usage: node scripts/capture_frames.mjs [slug ...]
import puppeteer from "puppeteer-core";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const REF = "https://beui.dev/components/motion";
const CAND = "http://localhost:8080";
const OUT = path.join(ROOT, "calibration", "pairs");
const VIEWPORT = { width: 1440, height: 1600, deviceScaleFactor: 1 };
const CLIP = { x: 285, y: 270, width: 825, height: 430 }; // preview region
const FRAMES = 12;
const INTERVAL = 130; // ms between frames (~1.4s window)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Auto-animating components (row = sidebar index for candidate navigation).
const ANIM = [
  { slug: "marquee", row: 0 },
  { slug: "loader", row: 29 },
  { slug: "text-animation", row: 15 },
  { slug: "number", row: 16 },
  { slug: "shader-background", row: 27 },
];

async function seq(page, dir, side) {
  fs.mkdirSync(dir, { recursive: true });
  for (let i = 0; i < FRAMES; i++) {
    await page.screenshot({ clip: CLIP, path: path.join(dir, `${side}_${String(i).padStart(2, "0")}.png`) });
    await sleep(INTERVAL);
  }
}

async function main() {
  const only = process.argv.slice(2);
  const cfgs = only.length ? ANIM.filter((a) => only.includes(a.slug)) : ANIM;
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: true, args: ["--hide-scrollbars", "--disable-gpu"],
  });

  const rp = await browser.newPage();
  await rp.setViewport(VIEWPORT);
  for (const c of cfgs) {
    try {
      await rp.goto(`${REF}/${c.slug}`, { waitUntil: "networkidle2", timeout: 45000 });
      await sleep(1200);
      await seq(rp, path.join(OUT, c.slug, "frames"), "ref");
      console.log("ref  frames", c.slug);
    } catch (e) { console.log("ref  FAIL", c.slug, e.message.slice(0, 50)); }
  }
  await rp.close();

  const cp = await browser.newPage();
  await cp.setViewport(VIEWPORT);
  await cp.goto(CAND + "/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await cp.waitForFunction(() => !!document.querySelector("flutter-view"), { timeout: 60000 });
  await sleep(3000);
  for (const c of cfgs) {
    try {
      await cp.mouse.click(120, Math.round(340 + c.row * 32.97));
      await sleep(1800); // let the view settle before sampling motion
      await seq(cp, path.join(OUT, c.slug, "frames"), "cand");
      console.log("cand frames", c.slug);
    } catch (e) { console.log("cand FAIL", c.slug, e.message.slice(0, 50)); }
  }
  await cp.close();
  await browser.close();
  console.log("done");
}
main().catch((e) => { console.error(e); process.exit(1); });
