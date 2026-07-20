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

- The interactive demos run the **same math the Python worker uses** — the geometric-mean formula
  from `aggregate.py` and the `100·exp(−ΔE/19)` color score with a CIEDE2000 implementation ported
  from `metrics/color.py`. They are illustrative, client-side, and stay in sync by mirroring those
  formulas.
- The visual language is an original adaptation inspired by editorial landing-page design; all copy is
  specific to this project.
