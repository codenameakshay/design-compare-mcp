/* =============================================================
   design-compare-mcp landing — interactions
   The two demos below run the SAME math the Python worker uses:
   - weighted geometric mean (aggregate.py)
   - color score = 100 * exp(-meanΔE / 19), ΔE via CIEDE2000 (color.py)
   ============================================================= */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  /* ---------- "still" mode (?still=1): no animation, all revealed.
     Used for deterministic screenshots and the compare_designs loop. ---------- */
  const STILL = /[?&]still=1/.test(location.search);
  if (STILL) document.documentElement.classList.add("still");

  /* ---------- sticky nav shadow ---------- */
  const nav = $("#nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---------- Lenis smooth scroll ---------- */
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let lenis = null;
  if (!STILL && !prefersReduced && typeof Lenis !== "undefined") {
    lenis = new Lenis({
      duration: 1.05,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      touchMultiplier: 1.6,
    });
    const raf = (time) => { lenis.raf(time); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
    lenis.on("scroll", onScroll);
  }
  // In-page anchors: route through Lenis when active, else native smooth scroll.
  $$('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href");
      if (!href || href === "#") return;
      const target = document.querySelector(href);
      if (!target) return;
      e.preventDefault();
      if (lenis) lenis.scrollTo(target, { offset: -68 });
      else target.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth" });
      history.replaceState(null, "", href);
    });
  });

  /* ---------- scroll reveal ---------- */
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches || STILL;
  const revealEls = $$(".reveal");
  if (reduce || !("IntersectionObserver" in window)) {
    revealEls.forEach((el) => el.classList.add("in"));
  } else {
    const show = (el) => { el.classList.add("in"); io.unobserve(el); };
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) show(e.target); }),
      { threshold: 0, rootMargin: "0px 0px -50px 0px" }
    );
    revealEls.forEach((el) => io.observe(el));
    // Safety net: IntersectionObserver delivers async and can miss elements during
    // fast/programmatic scrolls, leaving whole sections invisible. On every scroll,
    // reveal anything already within (or above) the viewport so nothing stays hidden.
    let ticking = false;
    const sweep = () => {
      ticking = false;
      const vh = window.innerHeight;
      for (const el of revealEls) {
        if (el.classList.contains("in")) continue;
        const r = el.getBoundingClientRect();
        if (r.top < vh * 0.95 && r.bottom > 0) show(el);
      }
    };
    const onMove = () => { if (!ticking) { ticking = true; requestAnimationFrame(sweep); } };
    window.addEventListener("scroll", onMove, { passive: true });
    window.addEventListener("resize", onMove);
    sweep(); // reveal above-the-fold immediately
  }

  /* ---------- hero score count-up ---------- */
  const counter = $("[data-count]");
  if (counter) {
    const target = parseFloat(counter.getAttribute("data-count"));
    if (reduce) {
      counter.textContent = target.toFixed(1);
    } else {
      const run = () => {
        const dur = 1100;
        let start = null;
        const step = (t) => {
          if (start === null) start = t;
          const p = clamp((t - start) / dur, 0, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          counter.textContent = (target * eased).toFixed(1);
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      };
      const io2 = new IntersectionObserver((ents) => {
        ents.forEach((e) => { if (e.isIntersecting) { run(); io2.disconnect(); } });
      });
      io2.observe(counter);
    }
  }

  /* ---------- copy buttons ---------- */
  $$(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const code = btn.closest(".code-block").querySelector("code").textContent;
      try {
        await navigator.clipboard.writeText(code);
      } catch (_) {
        const ta = document.createElement("textarea");
        ta.value = code; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (e) {}
        ta.remove();
      }
      const prev = btn.textContent;
      btn.textContent = "copied ✓";
      btn.classList.add("copied");
      setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied"); }, 1400);
    });
  });

  /* =============================================================
     DEMO 1 — weighted geometric mean (mirrors aggregate.py)
     ============================================================= */
  const DIMS = [
    { key: "layout", label: "layout" },
    { key: "color", label: "color" },
    { key: "content", label: "content" },
    { key: "typography", label: "typography" },
    { key: "spacing", label: "spacing" },
  ];
  const PRESETS = {
    default: { layout: 0.35, color: 0.2, content: 0.15, typography: 0.15, spacing: 0.15 },
    "dark-ui": { layout: 0.6, typography: 0.3, color: 0.1, content: 0, spacing: 0 },
  };
  const START = { layout: 100, color: 44, content: 100, typography: 88, spacing: 100 };
  const FLOOR = 1.0;

  let activePreset = "default";
  const scores = Object.assign({}, START);

  const slidersEl = $("#agg-sliders");
  const geoEl = $("#agg-geo");
  const arithEl = $("#agg-arith");
  const gapEl = $("#agg-gap");

  function weights() { return PRESETS[activePreset]; }

  function buildSliders() {
    slidersEl.innerHTML = "";
    DIMS.forEach((d) => {
      const w = weights()[d.key];
      const row = document.createElement("div");
      row.className = "slider-row" + (w <= 0 ? " dim-off" : "");
      row.innerHTML =
        `<label>${d.label}<span class="wt">w ${w.toFixed(2)}</span></label>` +
        `<input type="range" min="1" max="100" step="1" value="${scores[d.key]}" ` +
        `aria-label="${d.label} sub-score" data-key="${d.key}">` +
        `<output>${scores[d.key]}</output>`;
      const input = row.querySelector("input");
      const output = row.querySelector("output");
      input.addEventListener("input", () => {
        scores[d.key] = parseInt(input.value, 10);
        output.textContent = input.value;
        recompute();
      });
      slidersEl.appendChild(row);
    });
  }

  function recompute() {
    const w = weights();
    // geometric mean over dims with weight > 0, weights renormalized, scores floored at 1
    let wsum = 0, lnAcc = 0, arithAcc = 0;
    DIMS.forEach((d) => {
      const wt = w[d.key];
      if (wt > 0) {
        const s = clamp(scores[d.key], FLOOR, 100);
        lnAcc += wt * Math.log(s);
        arithAcc += wt * s;
        wsum += wt;
      }
    });
    const geo = wsum > 0 ? Math.exp(lnAcc / wsum) : 0;
    const arith = wsum > 0 ? arithAcc / wsum : 0;
    geoEl.textContent = geo.toFixed(1);
    arithEl.textContent = arith.toFixed(1);
    const gap = arith - geo;
    if (gap >= 1.5) {
      gapEl.textContent = `arithmetic hides the weak dimension by +${gap.toFixed(1)} — geometric won't let you.`;
      gapEl.style.color = "";
    } else {
      gapEl.textContent = "balanced scores — the two means nearly agree.";
      gapEl.style.color = "var(--ink-mute)";
    }
  }

  $$(".demo-presets .chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activePreset = btn.getAttribute("data-preset");
      $$(".demo-presets .chip-btn").forEach((b) => b.classList.toggle("is-active", b === btn));
      buildSliders();
      recompute();
    });
  });

  if (slidersEl) { buildSliders(); recompute(); }

  /* =============================================================
     DEMO 2 — color ΔE2000 → score (mirrors color.py)
     ============================================================= */
  const DECAY = 19;

  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  // sRGB (0-255) -> CIELAB (D65)
  function rgbToLab(rgb) {
    let [r, g, b] = rgb.map((v) => {
      v /= 255;
      return v > 0.04045 ? Math.pow((v + 0.055) / 1.055, 2.4) : v / 12.92;
    });
    // linear RGB -> XYZ (sRGB, D65)
    let x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375;
    let y = r * 0.2126729 + g * 0.7151522 + b * 0.072175;
    let z = r * 0.0193339 + g * 0.119192 + b * 0.9503041;
    // normalize by D65 white
    x /= 0.95047; y /= 1.0; z /= 1.08883;
    const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
    const fx = f(x), fy = f(y), fz = f(z);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }
  // CIEDE2000
  function ciede2000(lab1, lab2) {
    const [L1, a1, b1] = lab1, [L2, a2, b2] = lab2;
    const rad = Math.PI / 180, deg = 180 / Math.PI;
    const avgL = (L1 + L2) / 2;
    const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2);
    const avgC = (C1 + C2) / 2;
    const G = 0.5 * (1 - Math.sqrt(Math.pow(avgC, 7) / (Math.pow(avgC, 7) + Math.pow(25, 7))));
    const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
    const C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);
    const avgCp = (C1p + C2p) / 2;
    let h1p = Math.atan2(b1, a1p) * deg; if (h1p < 0) h1p += 360;
    let h2p = Math.atan2(b2, a2p) * deg; if (h2p < 0) h2p += 360;
    const dLp = L2 - L1;
    const dCp = C2p - C1p;
    let dhp;
    if (C1p * C2p === 0) dhp = 0;
    else {
      dhp = h2p - h1p;
      if (dhp > 180) dhp -= 360; else if (dhp < -180) dhp += 360;
    }
    const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * rad) / 2);
    let avghp;
    if (C1p * C2p === 0) avghp = h1p + h2p;
    else {
      avghp = (h1p + h2p) / 2;
      if (Math.abs(h1p - h2p) > 180) avghp += (h1p + h2p < 360 ? 180 : -180);
    }
    const T = 1 - 0.17 * Math.cos((avghp - 30) * rad) + 0.24 * Math.cos(2 * avghp * rad) +
      0.32 * Math.cos((3 * avghp + 6) * rad) - 0.2 * Math.cos((4 * avghp - 63) * rad);
    const dTheta = 30 * Math.exp(-Math.pow((avghp - 275) / 25, 2));
    const Rc = 2 * Math.sqrt(Math.pow(avgCp, 7) / (Math.pow(avgCp, 7) + Math.pow(25, 7)));
    const Sl = 1 + (0.015 * Math.pow(avgL - 50, 2)) / Math.sqrt(20 + Math.pow(avgL - 50, 2));
    const Sc = 1 + 0.045 * avgCp;
    const Sh = 1 + 0.015 * avgCp * T;
    const Rt = -Math.sin(2 * dTheta * rad) * Rc;
    return Math.sqrt(
      Math.pow(dLp / Sl, 2) + Math.pow(dCp / Sc, 2) + Math.pow(dHp / Sh, 2) +
      Rt * (dCp / Sc) * (dHp / Sh)
    );
  }

  const refColor = $("#ref-color");
  const candColor = $("#cand-color");
  if (refColor && candColor) {
    const refHex = $("#ref-hex"), candHex = $("#cand-hex");
    const swRef = $("#sw-ref"), swCand = $("#sw-cand");
    const deVal = $("#de-val"), deScore = $("#de-score");
    const finding = $("#color-finding");

    function updateColor() {
      const rh = refColor.value, ch = candColor.value;
      refHex.textContent = rh; candHex.textContent = ch;
      swRef.style.background = rh; swCand.style.background = ch;
      const dE = ciede2000(rgbToLab(hexToRgb(rh)), rgbToLab(hexToRgb(ch)));
      const score = 100 * Math.exp(-dE / DECAY);
      deVal.textContent = dE.toFixed(1);
      deScore.textContent = score.toFixed(1);
      if (dE < 2) {
        finding.className = "finding ok";
        finding.innerHTML = `<span class="f-type">no finding</span>ΔE ${dE.toFixed(1)} is below the just-noticeable threshold — this color matches. Score ${score.toFixed(1)}.`;
      } else {
        finding.className = "finding";
        const sev = dE >= 10 ? "high" : dE >= 4 ? "medium" : "low";
        finding.innerHTML =
          `<span class="f-type">color_shift · ${sev}</span>` +
          `a dominant color reads as <b>${ch}</b> but the reference uses <b>${rh}</b> (ΔE ${dE.toFixed(0)}). ` +
          `suggested_fix: shift ${ch} toward ${rh}.`;
      }
    }
    refColor.addEventListener("input", updateColor);
    candColor.addEventListener("input", updateColor);
    updateColor();
  }
})();
