from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from vision_worker.aggregate import FLOOR, resolve_weights  # noqa: E402
from vision_worker.metrics.color import color_score  # noqa: E402
from vision_worker.metrics.content import content_score  # noqa: E402
from vision_worker.normalize import normalize_pair  # noqa: E402
from vision_worker.pipeline import compare, compare_arrays  # noqa: E402

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

    assert ident["overall"] >= 99, ident["overall"]
    assert text_ident["overall"] >= 99, text_ident["overall"]

    assert dims(ident)["typography"] is None, "card screen has no text -> typography N/A"
    for dim in ("content", "spacing"):
        v = dims(text_ident)[dim]
        assert v is None or v >= 95, f"identical text {dim} should be N/A or ~100, got {v}"

    rd = dims(recolored)
    assert rd["color"] <= 60 and rd["layout"] >= 95 and rd["content"] >= 95, rd
    assert has_finding(recolored, "color_shift")

    assert shifted_screen["overall"] > shifted_widget["overall"]

    dd = dims(different)
    assert all(dd[k] < 70 for k in ("layout", "color", "content", "spacing")), dd
    assert different["overall"] < 55, different["overall"]

    assert dims(missing)["content"] < 100 and missing["overall"] < ident["overall"]
    assert has_finding(missing, "missing_region")

    assert dims(text_smaller)["typography"] < 80, dims(text_smaller)["typography"]
    assert has_finding(text_smaller, "text_scale")
    assert dims(text_less)["typography"] < 100 and has_finding(text_less, "text_amount")

    assert dims(spacing_tight)["spacing"] < 95, dims(spacing_tight)["spacing"]
    assert has_finding(spacing_tight, "spacing_mismatch")

    scored = [v for v in dims(recolored).values() if v is not None]
    assert min(scored) <= recolored["overall"] <= max(scored)

    only_color = cmp(
        "reference.png", "recolored.png",
        weights={"layout": 0, "color": 1, "content": 0, "typography": 0, "spacing": 0},
    )
    assert abs(only_color["overall"] - dims(recolored)["color"]) < 0.5, (
        only_color["overall"], dims(recolored)["color"])

    vis = ident["visuals"]
    assert {v["name"] for v in vis} == {"overlay", "diff_heatmap", "content_regions", "side_by_side"}
    for v in vis:
        assert base64.b64decode(v["base64"])[:8] == PNG_MAGIC, v["name"]

    assert ident["canvas"]["ignore_input_space"] == "reference_original_pixels"
    assert ident["canvas"]["ignore_space"] == "canonical_768"
    assert ident["canvas"]["width"] == 768
    assert ident["canvas"]["reference"]["orig_w"] == 400
    assert "768-wide canonical" in ident["critique_rubric"]
    assert "original reference" in ident["critique_rubric"]
    assert dims(ident)["layout"] is not None
    assert ident["subscores"]["typography"]["status"] == "not_applicable"
    assert ident["subscores"]["layout"]["status"] == "scored"

    h, w = 200, 300
    ref_ign = np.full((h, w, 3), 24, np.uint8)
    cand_ign = ref_ign.copy()
    ref_ign[20:90, 30:140] = (255, 32, 8)
    cand_ign[20:90, 30:140] = (8, 255, 40)
    without_ignore = compare_arrays(ref_ign, cand_ign, return_visuals=False)
    with_ignore = compare_arrays(
        ref_ign, cand_ign, ignore_regions=[[30, 20, 110, 70]], return_visuals=False,
    )
    assert with_ignore["overall"] > without_ignore["overall"], (
        with_ignore["overall"], without_ignore["overall"])

    dark_short = np.full((40, 80, 3), 18, np.uint8)
    dark_tall = np.full((90, 80, 3), 18, np.uint8)
    pair = normalize_pair(dark_short, dark_tall)
    short_h = pair.ref.rgb.shape[0] - max(1, round(40 * 768 / 80))
    assert short_h > 0, "taller candidate must introduce a pad strip on the reference"
    pad_strip = pair.ref.rgb[-short_h:, :, :]
    assert float(pad_strip.mean()) < 40, pad_strip.mean()
    assert max(pair.ref.pad_color) < 40, pair.ref.pad_color

    blank = np.full((80, 120, 3), 28, np.uint8)
    extra = blank.copy()
    extra[12:52, 18:100] = (220, 220, 230)
    miss_score, miss_findings, _, miss_viz = content_score(blank, extra)
    assert miss_score is not None and miss_score < 50, miss_score
    assert miss_viz["extra"], miss_viz
    both_empty, _, _, _ = content_score(blank, blank)
    assert both_empty is None

    colorful = np.full((90, 120, 3), 24, np.uint8)
    colorful[8:40, 8:55] = (220, 40, 40)
    colorful[48:80, 60:112] = (40, 180, 80)
    gray = np.mean(colorful, axis=2, keepdims=True).repeat(3, axis=2).astype(np.uint8)
    gray_score, _, _ = color_score(colorful, gray)
    ident_score, _, _ = color_score(colorful, colorful)
    assert ident_score > 90, ident_score
    assert gray_score < ident_score - 15, (gray_score, ident_score)

    import vision_worker.pipeline as P

    real_structure = P.structure_score

    def _boom(*_a, **_k):
        raise RuntimeError("forced metric failure")

    P.structure_score = _boom
    try:
        failed = compare_arrays(ref_ign, ref_ign, return_visuals=False)
    finally:
        P.structure_score = real_structure
    ok = compare_arrays(ref_ign, ref_ign, return_visuals=False)
    assert failed["subscores"]["layout"]["status"] == "failed"
    assert failed["subscores"]["layout"]["score"] == FLOOR
    assert failed["overall"] < ok["overall"], (failed["overall"], ok["overall"])

    def widget_title(size=28):
        img = Image.new("RGB", (400, 160), (250, 250, 252))
        d = ImageDraw.Draw(img)
        d.text((16, 48), "Settings Title Here", fill=(20, 20, 20),
               font=ImageFont.load_default(size=size))
        return np.asarray(img)

    title_r = compare_arrays(widget_title(), widget_title(), mode="widget", return_visuals=False)
    assert title_r["subscores"]["typography"]["score"] is not None, title_r["subscores"]["typography"]
    assert title_r["subscores"]["typography"]["status"] == "scored"

    try:
        resolve_weights(weights={"layout": 1, "nope": 1})
        raise AssertionError("unknown weight key must raise")
    except ValueError:
        pass
    try:
        resolve_weights(weights={"layout": -1})
        raise AssertionError("negative weight must raise")
    except ValueError:
        pass
    try:
        resolve_weights(weights={"layout": 0, "color": 0, "content": 0, "typography": 0, "spacing": 0})
        raise AssertionError("all-zero weights must raise")
    except ValueError:
        pass

    print("\nPipeline checks PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
