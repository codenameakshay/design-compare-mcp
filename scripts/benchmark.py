from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
FX = ROOT / "test" / "fixtures"
OUT = ROOT / "docs" / "bench"

sys.path.insert(0, str(WORKER))

import numpy as np  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from calibration import perturbations as P  # noqa: E402
from calibration.synthetic import card_screen  # noqa: E402
from vision_worker.aggregate import DEFAULT_WEIGHTS, aggregate  # noqa: E402
from vision_worker.io_utils import load_rgb  # noqa: E402
from vision_worker.motion import compare_sequences  # noqa: E402
from vision_worker.pipeline import compare, compare_arrays  # noqa: E402


def rss_mb() -> float:
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())])) / 1024


def percentile(vals: list[float], p: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (k - f) * (s[c] - s[f])


def _series_scores(dim: str, gen):
    ref, series = gen()
    levels, scores = [], []
    for lvl, cand in series:
        r = compare_arrays(ref, cand, return_visuals=False)
        levels.append(lvl)
        scores.append(r["subscores"][dim]["score"])
    return levels, scores


def _subs(**scores):
    return {k: {"score": v, "reason": "", "measurements": {}} for k, v in scores.items()}


def _weighted_arith(scores: dict) -> float:
    tot = sum(DEFAULT_WEIGHTS[k] for k in scores)
    return sum(DEFAULT_WEIGHTS[k] * v for k, v in scores.items()) / tot


def moving_seq(n=8, step=4):
    frames = []
    for i in range(n):
        f = np.zeros((50, 100), np.float32)
        x = (i * step) % 90
        f[20:30, x : x + 8] = 255.0
        frames.append(f)
    return frames


def static_seq(n=8):
    f = np.zeros((50, 100), np.float32)
    f[20:30, 10:18] = 255.0
    return [f.copy() for _ in range(n)]


def bench_latency(ref, cand, n: int = 40) -> dict:
    for _ in range(5):
        compare_arrays(ref, cand, return_visuals=False)
        compare_arrays(ref, cand, return_visuals=True)
    out = {}
    for vis in (False, True):
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            compare_arrays(ref, cand, return_visuals=vis)
            times.append((time.perf_counter() - t0) * 1000.0)
        key = "visuals_true" if vis else "visuals_false"
        out[key] = {
            "n": n,
            "p50_ms": round(percentile(times, 50), 2),
            "p95_ms": round(percentile(times, 95), 2),
        }
    return out


def bench_rss(ref, cand, n: int = 80) -> dict:
    compare_arrays(ref, cand, return_visuals=True)
    gc.collect()
    start = rss_mb()
    for _ in range(n):
        compare_arrays(ref, cand, return_visuals=True)
    gc.collect()
    end = rss_mb()
    return {"n": n, "start_mb": round(start, 2), "end_mb": round(end, 2), "growth_mb": round(end - start, 2)}


def bench_monotonicity() -> dict:
    gens = [
        ("color", "color", P.color_series),
        ("content", "content", P.content_series),
        ("layout", "layout", P.layout_series),
        ("typography", "typography", P.typography_series),
        ("spacing", "spacing", P.spacing_series),
    ]
    rows = {}
    for name, dim, gen in gens:
        levels, scores = _series_scores(dim, gen)
        rho = float(spearmanr(levels, scores).statistic)
        rows[name] = {"spearman": round(rho, 3), "scores": [round(s, 1) for s in scores]}
    return rows


def bench_gaming() -> dict:
    broken = _subs(layout=12, color=100, content=12, typography=100, spacing=100)
    geo = aggregate(broken)
    arith = _weighted_arith({k: v["score"] for k, v in broken.items()})
    return {"geometric": round(geo, 2), "arithmetic": round(arith, 2)}


def bench_ignore() -> dict:
    h, w = 200, 300
    ref = np.full((h, w, 3), 24, np.uint8)
    cand = ref.copy()
    ref[20:90, 30:140] = (255, 32, 8)
    cand[20:90, 30:140] = (8, 255, 40)
    without = compare_arrays(ref, cand, return_visuals=False)
    with_ign = compare_arrays(ref, cand, ignore_regions=[[30, 20, 110, 70]], return_visuals=False)
    return {
        "without_ignore": without["overall"],
        "with_ignore": with_ign["overall"],
        "delta": round(with_ign["overall"] - without["overall"], 2),
    }


def bench_motion() -> dict:
    both = compare_sequences(moving_seq(), moving_seq())
    one_side = compare_sequences(moving_seq(), static_seq())
    static = compare_sequences(static_seq(), static_seq())
    blank = [np.zeros((50, 100), np.float32) for _ in range(8)]
    unreliable = compare_sequences(blank, blank)
    return {
        "both_moving": {"motion_status": both["motion_status"], "motion_score": both["motion_score"]},
        "one_sided": {"motion_status": one_side["motion_status"], "motion_score": one_side["motion_score"]},
        "static": {"motion_status": static["motion_status"], "motion_score": static["motion_score"]},
        "capture_unreliable": {
            "motion_status": unreliable["motion_status"],
            "motion_score": unreliable["motion_score"],
        },
    }


def bench_fixture_scores() -> dict:
    pairs = [
        ("identical", "reference.png", "identical.png", "screen"),
        ("recolored", "reference.png", "recolored.png", "screen"),
        ("shifted", "reference.png", "shifted.png", "screen"),
        ("different", "reference.png", "different.png", "screen"),
    ]
    out = {}
    for name, ref, cand, mode in pairs:
        r = compare(str(FX / ref), str(FX / cand), mode=mode, return_visuals=False)
        out[name] = round(r["overall"], 2)
    return out


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def bar_svg(
    title: str,
    labels: list[str],
    groups: list[tuple[str, list[float | None], str]],
    *,
    width: int = 720,
    height: int = 400,
    y_max: float | None = None,
    null_labels: dict[int, str] | None = None,
) -> str:
    margin = {"l": 56, "r": 24, "t": 48, "b": 72}
    plot_w = width - margin["l"] - margin["r"]
    plot_h = height - margin["t"] - margin["b"]
    n = len(labels)
    ng = len(groups)
    flat = [v for _, vals, _ in groups for v in vals if v is not None]
    ymax = y_max if y_max is not None else (max(flat) * 1.15 if flat else 100.0)
    ymax = max(ymax, 1.0)

    group_w = plot_w / max(n, 1)
    bar_w = group_w / (ng + 1)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#fafafa"/>',
        f'<text x="{width/2:.1f}" y="28" text-anchor="middle" font-family="system-ui,sans-serif" '
        f'font-size="16" font-weight="600">{_esc(title)}</text>',
    ]

    for i in range(5):
        y = margin["t"] + plot_h * (1 - i / 4)
        val = ymax * i / 4
        lines.append(
            f'<line x1="{margin["l"]}" y1="{y:.1f}" x2="{width-margin["r"]}" y2="{y:.1f}" stroke="#e0e0e0"/>'
        )
        lines.append(
            f'<text x="{margin["l"]-8}" y="{y+4:.1f}" text-anchor="end" font-family="system-ui,sans-serif" '
            f'font-size="11" fill="#666">{val:.0f}</text>'
        )

    for gi, (gname, vals, color) in enumerate(groups):
        for xi, v in enumerate(vals):
            cx = margin["l"] + xi * group_w + (gi + 1) * bar_w
            if v is None:
                ann = (null_labels or {}).get(xi, "null")
                lines.append(
                    f'<text x="{cx:.1f}" y="{margin["t"]+plot_h+16:.1f}" text-anchor="middle" '
                    f'font-family="system-ui,sans-serif" font-size="10" fill="#888">{_esc(ann)}</text>'
                )
                continue
            bh = plot_h * (v / ymax)
            y = margin["t"] + plot_h - bh
            lines.append(f'<rect x="{cx-bar_w/2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}"/>')
            lines.append(
                f'<text x="{cx:.1f}" y="{y-4:.1f}" text-anchor="middle" font-family="system-ui,sans-serif" '
                f'font-size="10" fill="#333">{v:.1f}</text>'
            )

    for xi, lab in enumerate(labels):
        cx = margin["l"] + xi * group_w + group_w / 2
        lines.append(
            f'<text x="{cx:.1f}" y="{height-24:.1f}" text-anchor="middle" font-family="system-ui,sans-serif" '
            f'font-size="11">{_esc(lab)}</text>'
        )

    legend_x = margin["l"]
    for gi, (gname, _, color) in enumerate(groups):
        lx = legend_x + gi * 140
        lines.append(f'<rect x="{lx}" y="8" width="12" height="12" fill="{color}"/>')
        lines.append(
            f'<text x="{lx+16}" y="18" font-family="system-ui,sans-serif" font-size="11">{_esc(gname)}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def write_charts(results: dict) -> None:
    lat = results["latency"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latency.svg").write_text(
        bar_svg(
            "compare_arrays latency (ms/call)",
            ["p50", "p95"],
            [
                ("no visuals", [lat["visuals_false"]["p50_ms"], lat["visuals_false"]["p95_ms"]], "#4a90d9"),
                ("visuals", [lat["visuals_true"]["p50_ms"], lat["visuals_true"]["p95_ms"]], "#e67e22"),
            ],
            y_max=max(
                lat["visuals_false"]["p95_ms"],
                lat["visuals_true"]["p95_ms"],
            )
            * 1.2,
        )
    )

    mono = results["monotonicity"]
    dims = list(mono.keys())
    rhos = [mono[d]["spearman"] for d in dims]
    (OUT / "monotonicity.svg").write_text(_mono_svg(dims, rhos))

    scores = results["fixture_scores"]
    (OUT / "scores.svg").write_text(
        bar_svg(
            "Fixture overall scores",
            list(scores.keys()),
            [("overall", list(scores.values()), "#8e44ad")],
        )
    )

    mot = results["motion"]
    labels = ["both moving", "one-sided", "static", "unreliable"]
    keys = ["both_moving", "one_sided", "static", "capture_unreliable"]
    vals = [mot[k]["motion_score"] for k in keys]
    null_labels = {i: mot[keys[i]]["motion_status"] for i, v in enumerate(vals) if v is None}
    (OUT / "motion.svg").write_text(
        bar_svg(
            "Motion score by case",
            labels,
            [("motion_score", vals, "#c0392b")],
            null_labels=null_labels,
        )
    )


def _mono_svg(dims: list[str], rhos: list[float]) -> str:
    width, height = 720, 400
    margin = {"l": 56, "r": 24, "t": 48, "b": 72}
    plot_w = width - margin["l"] - margin["r"]
    plot_h = height - margin["t"] - margin["b"]
    ymin, ymax = -1.0, 0.2
    span = ymax - ymin
    n = len(dims)
    bar_w = plot_w / max(n, 1) * 0.6

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="720" height="400" fill="#fafafa"/>',
        '<text x="360" y="28" text-anchor="middle" font-family="system-ui,sans-serif" '
        'font-size="16" font-weight="600">Monotonicity (Spearman ρ, want ≤ −0.8)</text>',
    ]
    for i in range(7):
        val = ymax - span * i / 6
        y = margin["t"] + plot_h * i / 6
        lines.append(f'<line x1="{margin["l"]}" y1="{y:.1f}" x2="{width-margin["r"]}" y2="{y:.1f}" stroke="#e0e0e0"/>')
        lines.append(
            f'<text x="{margin["l"]-8}" y="{y+4:.1f}" text-anchor="end" font-family="system-ui,sans-serif" '
            f'font-size="11" fill="#666">{val:.1f}</text>'
        )
    zero_y = margin["t"] + plot_h * ((ymax - 0) / span)
    lines.append(f'<line x1="{margin["l"]}" y1="{zero_y:.1f}" x2="{width-margin["r"]}" y2="{zero_y:.1f}" stroke="#999" stroke-dasharray="4"/>')

    for i, (dim, rho) in enumerate(zip(dims, rhos)):
        cx = margin["l"] + (i + 0.5) * (plot_w / n)
        top = margin["t"] + plot_h * ((ymax - max(rho, 0)) / span)
        bot = margin["t"] + plot_h * ((ymax - min(rho, 0)) / span)
        color = "#27ae60" if rho <= -0.8 else "#e67e22"
        lines.append(f'<rect x="{cx-bar_w/2:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{bot-top:.1f}" fill="{color}"/>')
        lines.append(
            f'<text x="{cx:.1f}" y="{top-6:.1f}" text-anchor="middle" font-family="system-ui,sans-serif" '
            f'font-size="10">{rho:+.2f}</text>'
        )
        lines.append(
            f'<text x="{cx:.1f}" y="{height-24:.1f}" text-anchor="middle" font-family="system-ui,sans-serif" '
            f'font-size="11">{_esc(dim)}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def main() -> int:
    ref = load_rgb(str(FX / "reference.png"))
    cand = load_rgb(str(FX / "recolored.png"))
    syn_ref = card_screen()
    syn_cand = card_screen(header=(120, 40, 60), btn=(220, 60, 60))

    results = {
        "latency": bench_latency(ref, cand, n=40),
        "rss": bench_rss(syn_ref, syn_cand, n=80),
        "monotonicity": bench_monotonicity(),
        "gaming": bench_gaming(),
        "ignore_regions": bench_ignore(),
        "motion": bench_motion(),
        "fixture_scores": bench_fixture_scores(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    write_charts(results)

    lat = results["latency"]["visuals_false"]
    print(f"latency visuals=false: p50={lat['p50_ms']} ms  p95={lat['p95_ms']} ms")
    print(f"RSS growth ({results['rss']['n']} calls): {results['rss']['growth_mb']:+.2f} MB")
    print(f"Wrote {OUT}/results.json and SVG charts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
