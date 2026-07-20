"""Direct pipeline checks (no MCP layer): correctness, monotonicity, alignment,
per-dimension behavior, and aggregation.

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
REF = str(FX / "reference.png")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def score(candidate: str, mode: str = "screen", **kw) -> dict:
    return compare(REF, str(FX / candidate), mode=mode, **kw)


def dims(r: dict) -> dict:
    return {k: v["score"] for k, v in r["subscores"].items()}


def main() -> int:
    ident = score("identical.png")
    recolored = score("recolored.png")
    shifted_screen = score("shifted.png", "screen")
    shifted_widget = score("shifted.png", "widget")
    different = score("different.png")
    missing = score("missing_button.png")

    for name, r in [
        ("identical", ident),
        ("recolored", recolored),
        ("shifted/screen", shifted_screen),
        ("shifted/widget", shifted_widget),
        ("different", different),
        ("missing_button", missing),
    ]:
        d = dims(r)
        print(f"{name:16s} overall={r['overall']:6.2f}  "
              f"layout={d['layout']:6.2f} color={d['color']:6.2f} content={d['content']:6.2f}")

    # 1. Identical scores ~100 across the board.
    assert ident["overall"] >= 99, ident["overall"]
    assert all(dims(ident)[k] >= 99 for k in ("layout", "color", "content"))

    # 2. Recolor: caught by color, but layout+content stay intact (the Phase 1 blind spot).
    rd = dims(recolored)
    assert rd["layout"] >= 95 and rd["content"] >= 95, rd
    assert rd["color"] <= 60, f"recolor should tank color, got {rd['color']}"
    assert rd["color"] < rd["layout"] - 20, rd
    assert any(f["type"] == "color_shift" for f in recolored["cv_findings"]), "expected color_shift finding"

    # 3. Alignment recovers a pure translation (screen beats unaligned widget).
    assert shifted_screen["overall"] > shifted_widget["overall"], (
        shifted_screen["overall"], shifted_widget["overall"])

    # 4. Structurally different: every scored dimension is penalized.
    dd = dims(different)
    assert all(dd[k] < 70 for k in ("layout", "color", "content")), dd
    assert different["overall"] < 60, different["overall"]

    # 5. Content-presence + monotonicity: removing the button lowers content and
    #    yields a missing_region finding that locates it.
    md = dims(missing)
    assert md["content"] < 100, md
    assert missing["overall"] < ident["overall"], "missing element must lower overall"
    miss_findings = [f for f in missing["cv_findings"] if f["type"] == "missing_region"]
    assert len(miss_findings) >= 1, "expected a missing_region finding"

    # 6. Aggregation is a geometric mean over scored dims: within [min, max], and
    #    anti-gaming (overall <= max scored dimension).
    scored = [v for k, v in dims(recolored).items() if v is not None]
    assert min(scored) <= recolored["overall"] <= max(scored), (recolored["overall"], scored)

    # 7. Weight overrides: weighting only color makes overall track the color score.
    only_color = score("recolored.png", weights={"layout": 0, "color": 1, "content": 0})
    assert abs(only_color["overall"] - dims(recolored)["color"]) < 0.5, (
        only_color["overall"], dims(recolored)["color"])

    # 8. Pending dimensions stay null; four visuals are valid PNGs.
    assert dims(ident)["typography"] is None and dims(ident)["spacing"] is None
    vis = ident["visuals"]
    assert len(vis) == 4, f"expected 4 visuals, got {len(vis)}"
    assert {v["name"] for v in vis} == {"overlay", "diff_heatmap", "content_regions", "side_by_side"}
    for v in vis:
        assert base64.b64decode(v["base64"])[:8] == PNG_MAGIC, v["name"]

    print("\nPhase 2 pipeline checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
