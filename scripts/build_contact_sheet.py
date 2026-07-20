"""Build an interactive, blind labeling contact sheet for calibration pairs.

Reads calibration/pairs/<slug>/{reference,candidate}_preview.png, embeds
downscaled thumbnails, and emits a self-contained HTML page where the user
scores each port 0-100 and exports the labels. No tool scores are shown, so
labeling stays unbiased.
"""

from __future__ import annotations

import base64
import glob
import io
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "calibration" / "pairs"
OUT = ROOT / "calibration" / "contact_sheet.html"
THUMB_W = 460

# Human-friendly names, in the sidebar order.
NAMES = {
    "marquee": "Marquee", "tabs": "Tabs", "switch": "Switch", "input": "Input",
    "select": "Select", "checkbox": "Checkbox", "radio": "Radio Group",
    "bottom-sheet": "Bottom Sheet", "pull-to-refresh": "Pull to Refresh",
    "shared-layout-bg": "Shared Layout Background", "preview-rail": "Preview Rail",
    "dock": "Dock", "tooltip": "Tooltip", "popover": "Popover",
    "morphing-modal": "Morphing Modal", "text-animation": "Text Animation",
    "number": "Number Animation", "animated-badge": "Animated Badge",
    "action-swap": "Action Swap", "animated-toast-stack": "Animated Toast Stack",
    "theme-toggle": "Theme Toggle", "bouncy-accordion": "Bouncy Accordion",
    "drawer": "Drawer", "scroll-animation": "Scroll Animation",
    "range-slider": "Range Slider", "wheel-picker": "Wheel Picker", "table": "Table",
    "shader-background": "Shader Background", "cylinder-carousel": "Cylinder Carousel",
    "loader": "Loader", "tilt-card": "Tilt Card", "button": "Button",
    "expanding-arrow-button": "Animated CTA Buttons", "_index": "Components Index (full page)",
}
ORDER = list(NAMES.keys())


def thumb_b64(path: str) -> str:
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.resize((THUMB_W, round(h * THUMB_W / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def collect():
    items = []
    for slug in ORDER:
        d = PAIRS / slug
        rp, cp = d / "reference_preview.png", d / "candidate_preview.png"
        if slug == "_index":
            rp, cp = d / "reference.png", d / "candidate.png"
        if not (rp.exists() and cp.exists()):
            continue
        items.append((slug, NAMES.get(slug, slug), thumb_b64(str(rp)), thumb_b64(str(cp))))
    # keep any captured slug not in NAMES
    return items


CARD = """
    <article class="card" data-slug="{slug}">
      <header class="card-h">
        <span class="name">{name}</span>
        <code class="slug">{slug}</code>
      </header>
      <div class="pair">
        <figure><img loading="lazy" src="data:image/jpeg;base64,{ref}" alt="reference {name}"><figcaption>beUI · reference</figcaption></figure>
        <figure><img loading="lazy" src="data:image/jpeg;base64,{cand}" alt="flutter {name}"><figcaption>Flutter · your port</figcaption></figure>
      </div>
      <div class="score" data-state="unset">
        <input type="range" min="0" max="100" step="1" value="50" aria-label="fidelity score for {name}">
        <output>—</output>
      </div>
    </article>
"""


def main():
    items = collect()
    cards = "\n".join(
        CARD.format(slug=s, name=n, ref=r, cand=c) for (s, n, r, c) in items
    )
    html = TEMPLATE.replace("{{CARDS}}", cards).replace("{{COUNT}}", str(len(items)))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(items)} pairs)")


TEMPLATE = r"""<title>beUI → Flutter · fidelity calibration</title>
<style>
  :root{
    --ground:#131519; --surface:#1a1d23; --elev:#21252c; --border:#2b313a;
    --text:#e7eaef; --muted:#8891a0; --accent:#35d29a; --accent-ink:#04120c;
    --shadow:0 1px 0 rgba(255,255,255,.02), 0 8px 24px rgba(0,0,0,.35);
    --lo:#e5484d; --mid:#f5a623; --hi:#35d29a;
  }
  :root[data-theme="light"]{
    --ground:#f5f6f8; --surface:#ffffff; --elev:#ffffff; --border:#e3e6ec;
    --text:#191c22; --muted:#5b6472; --accent:#12a97a; --accent-ink:#ffffff;
    --shadow:0 1px 2px rgba(20,24,32,.06), 0 10px 28px rgba(20,24,32,.08);
  }
  @media (prefers-color-scheme: light){
    :root:not([data-theme]){
      --ground:#f5f6f8; --surface:#ffffff; --elev:#ffffff; --border:#e3e6ec;
      --text:#191c22; --muted:#5b6472; --accent:#12a97a; --accent-ink:#ffffff;
      --shadow:0 1px 2px rgba(20,24,32,.06), 0 10px 28px rgba(20,24,32,.08);
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ground);color:var(--text);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    line-height:1.5;-webkit-font-smoothing:antialiased}
  code,.mono,output{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .wrap{max-width:1120px;margin:0 auto;padding:32px 20px 140px}
  header.top{display:flex;flex-direction:column;gap:10px;margin-bottom:8px}
  .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
  h1{font-size:clamp(22px,3.4vw,32px);margin:0;letter-spacing:-.02em;text-wrap:balance}
  .lede{color:var(--muted);max-width:64ch;margin:0}
  .how{background:var(--surface);border:1px solid var(--border);border-radius:12px;
    padding:16px 18px;margin:20px 0 8px;box-shadow:var(--shadow)}
  .how ol{margin:8px 0 0;padding-left:20px;color:var(--muted)}
  .how li{margin:3px 0}
  .how b{color:var(--text)}
  .grid{display:grid;grid-template-columns:1fr;gap:18px;margin-top:22px}
  @media(min-width:720px){.grid{grid-template-columns:1fr 1fr}}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:14px;
    overflow:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column}
  .card-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
    padding:12px 14px 8px}
  .name{font-weight:600;letter-spacing:-.01em}
  .slug{font-size:11px;color:var(--muted)}
  .pair{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border)}
  figure{margin:0;background:var(--ground);display:flex;flex-direction:column}
  .pair img{width:100%;height:auto;display:block;aspect-ratio:460/220;object-fit:cover;object-position:top}
  figcaption{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
    padding:6px 10px;text-align:center}
  .score{display:flex;align-items:center;gap:12px;padding:12px 14px 14px}
  .score input[type=range]{flex:1;accent-color:var(--sc,var(--muted));cursor:pointer}
  .score output{min-width:2.6ch;text-align:right;font-variant-numeric:tabular-nums;
    font-size:15px;font-weight:600;color:var(--sc,var(--muted))}
  .score[data-state="unset"] output{color:var(--muted);font-weight:400}
  .bar{position:fixed;left:0;right:0;bottom:0;background:color-mix(in srgb,var(--surface) 92%,transparent);
    backdrop-filter:blur(10px);border-top:1px solid var(--border);z-index:9}
  .bar-in{max-width:1120px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .prog{font-size:13px;color:var(--muted)}
  .prog b{color:var(--text);font-variant-numeric:tabular-nums}
  button{font:inherit;font-weight:600;border-radius:10px;border:1px solid var(--border);
    background:var(--elev);color:var(--text);padding:9px 16px;cursor:pointer}
  button.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent}
  button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .out{flex:1;min-width:220px}
  textarea{width:100%;height:0;opacity:0;position:absolute;pointer-events:none}
  .hint{font-size:12px;color:var(--muted)}
  dialog{border:1px solid var(--border);border-radius:14px;background:var(--surface);color:var(--text);
    padding:0;max-width:min(560px,92vw);box-shadow:var(--shadow)}
  dialog::backdrop{background:rgba(0,0,0,.5)}
  .dlg{padding:18px 20px}
  .dlg h2{margin:0 0 8px;font-size:16px}
  .dlg pre{background:var(--ground);border:1px solid var(--border);border-radius:10px;
    padding:12px;overflow:auto;font-size:12.5px;max-height:46vh;margin:10px 0}
  .dlg-row{display:flex;gap:10px;justify-content:flex-end}
</style>

<div class="wrap">
  <header class="top">
    <span class="eyebrow">Design-fidelity calibration</span>
    <h1>beUI reference → your Flutter port</h1>
    <p class="lede">Score how faithfully each Flutter component reproduces the beUI reference — by eye,
      0 (unrelated) to 100 (indistinguishable). These labels become the ground truth that tunes the
      comparison tool's weights. Scored blind on purpose: you won't see the tool's guesses.</p>
  </header>

  <div class="how">
    <b>How to score</b>
    <ol>
      <li><b>Left = beUI reference, right = your Flutter port.</b> Compare the component preview area only.</li>
      <li>Drag each slider to your honest fidelity judgment. <b>Spread matters</b> — use the full range; a run of
        all-90s tells the calibration nothing.</li>
      <li>Skip a card by leaving it untouched (dash). When done, hit <b>Export labels</b> and paste the text back to me.</li>
    </ol>
  </div>

  <div class="grid">
    {{CARDS}}
  </div>
</div>

<div class="bar">
  <div class="bar-in">
    <span class="prog"><b id="done">0</b> / {{COUNT}} scored</span>
    <span class="hint out">Use the full 0–100 range for a meaningful calibration.</span>
    <button class="primary" id="export">Export labels</button>
  </div>
</div>

<dialog id="dlg">
  <div class="dlg">
    <h2>Paste these labels back into the chat</h2>
    <pre id="payload"></pre>
    <div class="dlg-row">
      <button id="copy">Copy</button>
      <button class="primary" id="close">Done</button>
    </div>
  </div>
</dialog>

<textarea id="sink" aria-hidden="true"></textarea>

<script>
  const scoreColor = (v) => {
    // 0 -> red, 50 -> amber, 100 -> green (perceptual-ish two-segment lerp)
    const lerp=(a,b,t)=>a.map((x,i)=>Math.round(x+(b[i]-x)*t));
    const lo=[229,72,77], mid=[245,166,35], hi=[53,210,154];
    const rgb = v<50 ? lerp(lo,mid,v/50) : lerp(mid,hi,(v-50)/50);
    return `rgb(${rgb.join(',')})`;
  };
  const cards = [...document.querySelectorAll('.card')];
  const doneEl = document.getElementById('done');
  function refresh(){
    let n=0;
    for(const c of cards){ if(c.querySelector('.score').dataset.state==='set') n++; }
    doneEl.textContent = n;
  }
  for(const c of cards){
    const box=c.querySelector('.score'), r=c.querySelector('input'), o=c.querySelector('output');
    const paint=()=>{ box.style.setProperty('--sc', scoreColor(+r.value)); o.textContent=r.value; };
    r.addEventListener('input',()=>{ box.dataset.state='set'; paint(); refresh(); });
    r.addEventListener('pointerdown',()=>{ box.dataset.state='set'; paint(); refresh(); });
  }
  document.getElementById('export').addEventListener('click',()=>{
    const lines=[];
    for(const c of cards){
      const box=c.querySelector('.score');
      if(box.dataset.state!=='set') continue;
      lines.push(`${c.dataset.slug} = ${c.querySelector('input').value}`);
    }
    const text = lines.length ? ('labels:\n'+lines.join('\n')) : '(no cards scored yet)';
    document.getElementById('payload').textContent = text;
    document.getElementById('dlg').showModal();
  });
  document.getElementById('copy').addEventListener('click',async()=>{
    const t=document.getElementById('payload').textContent;
    try{ await navigator.clipboard.writeText(t); }
    catch(e){ const s=document.getElementById('sink'); s.style.opacity=1; s.style.height='auto'; s.value=t; s.select(); document.execCommand('copy'); s.style.opacity=0; s.style.height=0; }
    document.getElementById('copy').textContent='Copied ✓';
  });
  document.getElementById('close').addEventListener('click',()=>document.getElementById('dlg').close());
  refresh();
</script>
"""

if __name__ == "__main__":
    main()
