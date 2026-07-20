"""Direct pipeline checks (no MCP layer): correctness, monotonicity, alignment,
all five per-dimension behaviors, not-applicable handling, and aggregation.

Run with the venv interpreter:
    worker/.venv/bin/python worker/tests/test_pipeline.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.pipeline import compare  # noqa: E402

FX = Path(__file__).resolve().parents[2] / "test" / "fixtures"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def cmp(ref: str, cand: str, mode: str = "screen", **kw) -> dict:
    return compare(str(FX / ref), str(FX / cand), mode=mode, **kw)


def dims(r: dict) -> dict:
    return {k: v["score"] for k, v in r["subscores"].items()}


def has_finding(r: dict, ftype: str) -> bool:
    return any(f.get("type") == ftype for f in r["cv_findings"])


def main() -> int:
    ident = cmp("reference.png", "identical.png")
    recolored = cmp("reference.png", "recolored.png")
    shifted_screen = cmp("reference.png", "shifted.png", "screen")
    shifted_widget = cmp("reference.png", "shifted.png", "widget")
    different = cmp("reference.png", "different.png")
    missing = cmp("reference.png", "missing_button.png")
    spacing_tight = cmp("reference.png", "spacing_tight.png")

    text_ident = cmp("text_ref.png", "text_ref.png")
    text_smaller = cmp("text_ref.png", "text_smaller.png")
    text_less = cmp("text_ref.png", "text_less.png")

    def show(name, r):
        d = dims(r)
        fmt = lambda v: f"{v:5.1f}" if v is not None else "  N/A"
        print(f"{name:16s} overall={r['overall']:6.2f}  "
              f"L={fmt(d['layout'])} C={fmt(d['color'])} Ct={fmt(d['content'])} "
              f"T={fmt(d['typography'])} Sp={fmt(d['spacing'])}")

    for name, r in [
        ("identical", ident), ("recolored", recolored), ("shifted/screen", shifted_screen),
        ("shifted/widget", shifted_widget), ("different", different), ("missing", missing),
        ("spacing_tight", spacing_tight), ("text=text", text_ident),
        ("text_smaller", text_smaller), ("text_less", text_less),
    ]:
        show(name, r)

    # --- invariants: identical scores ~100 for BOTH card and text screens ---
    assert ident["overall"] >= 99, ident["overall"]
    assert text_ident["overall"] >= 99, text_ident["overall"]

    # --- not-applicable handling ---
    assert dims(ident)["typography"] is None, "card screen has no text -> typography N/A"
    assert dims(text_ident)["content"] is None, "text screen has no major blocks -> content N/A"
    assert dims(text_ident)["spacing"] is None, "text screen has no major blocks -> spacing N/A"

    # --- color: recolor caught, structure intact ---
    rd = dims(recolored)
    assert rd["color"] <= 60 and rd["layout"] >= 95 and rd["content"] >= 95, rd
    assert has_finding(recolored, "color_shift")

    # --- alignment: screen recovers a pure shift, widget does not ---
    assert shifted_screen["overall"] > shifted_widget["overall"]

    # --- structurally different: every applicable dimension penalized ---
    dd = dims(different)
    assert all(dd[k] < 70 for k in ("layout", "color", "content", "spacing")), dd
    assert different["overall"] < 55, different["overall"]

    # --- content monotonicity: removing an element lowers content + locates it ---
    assert dims(missing)["content"] < 100 and missing["overall"] < ident["overall"]
    assert has_finding(missing, "missing_region")

    # --- typography: smaller type and less text are both caught ---
    assert dims(text_smaller)["typography"] < 80, dims(text_smaller)["typography"]
    assert has_finding(text_smaller, "text_scale")
    assert dims(text_less)["typography"] < 100 and has_finding(text_less, "text_amount")

    # --- spacing: tighter vertical rhythm is caught ---
    assert dims(spacing_tight)["spacing"] < 95, dims(spacing_tight)["spacing"]
    assert has_finding(spacing_tight, "spacing_mismatch")

    # --- aggregation: geometric mean within [min,max] of scored dims ---
    scored = [v for v in dims(recolored).values() if v is not None]
    assert min(scored) <= recolored["overall"] <= max(scored)

    # --- weight override: weighting only color makes overall track color ---
    only_color = cmp(
        "reference.png", "recolored.png",
        weights={"layout": 0, "color": 1, "content": 0, "typography": 0, "spacing": 0},
    )
    assert abs(only_color["overall"] - dims(recolored)["color"]) < 0.5, (
        only_color["overall"], dims(recolored)["color"])

    # --- visuals: four valid PNGs ---
    vis = ident["visuals"]
    assert {v["name"] for v in vis} == {"overlay", "diff_heatmap", "content_regions", "side_by_side"}
    for v in vis:
        assert base64.b64decode(v["base64"])[:8] == PNG_MAGIC, v["name"]

    print("\nPhase 3 pipeline checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
