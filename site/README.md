# Landing site

The marketing / documentation site for **design-compare-mcp** — a single, dependency-free static
page that explains what the MCP does, how it scores, and how to install it, with two live interactive
demos (the weighted geometric-mean aggregator and the CIEDE2000 color scorer).

```
site/
  index.html    # structure + copy
  styles.css    # all styling (no framework)
  app.js        # scroll reveal, count-up, copy buttons, the two demos
```

## Run locally

It's static — any file server works:

```bash
cd site
python3 -m http.server 8099
# open http://127.0.0.1:8099
```

`?still=1` on the URL freezes every animation and force-reveals all sections — handy for
screenshots and for feeding the page back through `compare_designs`.

## Deploy

A GitHub Actions workflow (`.github/workflows/pages.yml`) publishes this folder to GitHub Pages.
One-time setup: **repo Settings → Pages → Source: "GitHub Actions"**. After that, any push to `main`
that touches `site/` redeploys. The published URL is `https://codenameakshay.github.io/design-compare-mcp/`.

All asset paths are relative and the only external dependency is Google Fonts (Archivo, Gabarito,
JetBrains Mono), so it also drops straight onto Netlify, Vercel, or any static host.

## Notes

### DryLender case study

The case study sits immediately after the hero at `#drylender-case-study`. Its HTML, descriptions,
native video controls, direct-file links and method disclosure work without JavaScript. The hero
CTA and footer link jump to it; the only JavaScript addition transfers keyboard focus to the section
when the existing smooth-scroll handler intercepts that jump.

The media lives at these project-relative paths:

```
assets/drylender/original.mp4
assets/drylender/original-poster.jpg
assets/drylender/clone.mp4
assets/drylender/clone-poster.jpg
```

Both edits are silent H.264 MP4s. Native playback is independent, with no autoplay and
`preload="none"`. The 590×1278 reference and 720×1680 clone keep their full portrait frames,
capped at 600px tall and stacked below 780px. Descriptions sit beside each player.

The original includes only settings, calendar settings and the drink editor. The clone demo
predates the build-4 tap fix. Keep edits, source credit and build context accurate when replacing
media. Third-party UI and footage are not covered by this repository's MIT license.

Development evidence: `/tmp/drylender-parity/parity.py` and `score.mjs` for regional
`compare_designs` diagnostics; `motion.mjs` for selected `compare_motion` runs. Extraction was
manual. The new <code>extract_video_frames</code> tool turns a bounded local recording window into
absolute frame paths and a provenance manifest. It was added after the recorded development work.

Before publishing, review footage permissions and redactions, confirm posters and descriptions,
and test playback/seek/fullscreen on real iOS Safari. Check 320px reflow, 200% zoom, keyboard
focus, disabled JavaScript, reduced motion and failed-media fallback links. Verify relative URLs
under `/design-compare-mcp/`; local checks do not establish deployed availability.

### Existing demos

- The interactive demos run the **same core math the Python worker uses** — the geometric-mean
  formula from `aggregate.py` (floor 1.0) and the `100·exp(−ΔE/19)` color score with a CIEDE2000
  implementation ported from `metrics/color.py`. The worker also penalizes unmatched palette mass;
  the color picker demo is one pair, so that extra term does not apply. They stay in sync by
  mirroring those formulas.
- The visual language is an original adaptation inspired by editorial landing-page design; all copy is
  specific to this project.
