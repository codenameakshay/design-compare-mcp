// Capture calibration pairs from the beUI reference site and the Flutter port.
// Reference: navigable by URL (/components/motion/<slug>).
// Candidate:  Flutter web, in-app navigation only -> we CLICK each sidebar item.
//
// Usage:  node scripts/capture_pairs.mjs [limit]
//   limit: optional number of components to capture (default: all)
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const REF = "https://beui.dev/components/motion";
const CAND = "http://localhost:8080";
const OUT = path.join(ROOT, "calibration", "pairs");
const VIEWPORT = { width: 1440, height: 1600, deviceScaleFactor: 1 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const COMPONENTS = [
  { name: "Marquee", slug: "marquee" }, { name: "Tabs", slug: "tabs" },
  { name: "Switch", slug: "switch" }, { name: "Input", slug: "input" },
  { name: "Select", slug: "select" }, { name: "Checkbox", slug: "checkbox" },
  { name: "Radio Group", slug: "radio" }, { name: "Bottom Sheet", slug: "bottom-sheet" },
  { name: "Pull to Refresh", slug: "pull-to-refresh" }, { name: "Shared Layout Background", slug: "shared-layout-bg" },
  { name: "Preview Rail", slug: "preview-rail" }, { name: "Dock", slug: "dock" },
  { name: "Tooltip", slug: "tooltip" }, { name: "Popover", slug: "popover" },
  { name: "Morphing Modal", slug: "morphing-modal" }, { name: "Text Animation", slug: "text-animation" },
  { name: "Number Animation", slug: "number" }, { name: "Animated Badge", slug: "animated-badge" },
  { name: "Action Swap", slug: "action-swap" }, { name: "Animated Toast Stack", slug: "animated-toast-stack" },
  { name: "Theme Toggle", slug: "theme-toggle" }, { name: "Bouncy Accordion", slug: "bouncy-accordion" },
  { name: "Drawer", slug: "drawer" }, { name: "Scroll Animation", slug: "scroll-animation" },
  { name: "Range Slider", slug: "range-slider" }, { name: "Wheel Picker", slug: "wheel-picker" },
  { name: "Table", slug: "table" }, { name: "Shader Background", slug: "shader-background" },
  { name: "Cylinder Carousel", slug: "cylinder-carousel" }, { name: "Loader", slug: "loader" },
  { name: "Tilt Card", slug: "tilt-card" }, { name: "Button", slug: "button" },
  { name: "Animated CTA Buttons", slug: "expanding-arrow-button" },
];

function outDir(slug) {
  const d = path.join(OUT, slug);
  fs.mkdirSync(d, { recursive: true });
  return d;
}

async function main() {
  const limit = process.argv[2] ? parseInt(process.argv[2], 10) : COMPONENTS.length;
  const comps = COMPONENTS.slice(0, limit);
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--hide-scrollbars", "--disable-gpu"],
  });

  // ---- REFERENCE (URL navigation) ----
  const rp = await browser.newPage();
  await rp.setViewport(VIEWPORT);
  await rp.goto(REF, { waitUntil: "networkidle2", timeout: 45000 });
  await sleep(1200);
  await rp.screenshot({ path: path.join(outDir("_index"), "reference.png") });
  console.log("ref  _index");
  for (const c of comps) {
    try {
      await rp.goto(`${REF}/${c.slug}`, { waitUntil: "networkidle2", timeout: 45000 });
      await sleep(1100);
      await rp.screenshot({ path: path.join(outDir(c.slug), "reference.png") });
      console.log("ref ", c.slug);
    } catch (e) {
      console.log("ref  FAIL", c.slug, e.message.slice(0, 60));
    }
  }
  await rp.close();

  // ---- CANDIDATE (Flutter, click navigation) ----
  const cp = await browser.newPage();
  await cp.setViewport(VIEWPORT);
  await cp.goto(CAND + "/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await cp.waitForFunction(() => !!document.querySelector("flutter-view"), { timeout: 60000 });
  await sleep(3000);
  await cp.screenshot({ path: path.join(outDir("_index"), "candidate.png") });
  console.log("cand _index");

  // Flutter paints text to a shadow-DOM/canvas surface, so we can't query text.
  // Instead we click the sidebar by fixed coordinates: the candidate sidebar
  // order matches COMPONENTS exactly, all 33 rows fit the 1600px viewport (no
  // scroll), and real pointer events route through Flutter's hit-testing.
  const SIDEBAR_X = 120;
  const ROW0_Y = 340; // "Marquee" row center
  const ROW_DY = 32.97; // measured row pitch
  for (let i = 0; i < comps.length; i++) {
    const c = comps[i];
    const y = Math.round(ROW0_Y + i * ROW_DY);
    try {
      await cp.mouse.click(SIDEBAR_X, y);
      await sleep(1700); // route transition + entrance animation settle
      await cp.screenshot({ path: path.join(outDir(c.slug), "candidate.png") });
      console.log("cand", c.slug, "y=" + y);
    } catch (e) {
      console.log("cand FAIL", c.slug, e.message.slice(0, 60));
    }
  }
  await cp.close();
  await browser.close();
  console.log("done");
}

main().catch((e) => { console.error(e); process.exit(1); });
