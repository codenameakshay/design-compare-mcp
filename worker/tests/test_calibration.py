from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scipy.stats import spearmanr  # noqa: E402

from calibration import perturbations as P  # noqa: E402
from calibration.synthetic import card_screen  # noqa: E402
from vision_worker.aggregate import DEFAULT_WEIGHTS, aggregate  # noqa: E402
from vision_worker.pipeline import compare_arrays  # noqa: E402


def _series_scores(dim, gen):
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


def main() -> int:
    THRESH = {"spacing": -0.8}
    print("monotonicity (Spearman of level vs sub-score):")
    for name, dim, gen in [
        ("color", "color", P.color_series),
        ("content", "content", P.content_series),
        ("layout", "layout", P.layout_series),
        ("typography", "typography", P.typography_series),
        ("spacing", "spacing", P.spacing_series),
    ]:
        levels, scores = _series_scores(dim, gen)
        rho = spearmanr(levels, scores).statistic
        limit = THRESH.get(name, -0.9)
        print(f"  {name:11s} rho={rho:+.3f} (want <= {limit})  {[round(s, 1) for s in scores]}")
        assert rho <= limit, f"{name} not monotonic: rho={rho}"

    broken = _subs(layout=12, color=100, content=12, typography=100, spacing=100)
    overall = aggregate(broken)
    arith = _weighted_arith({k: v["score"] for k, v in broken.items()})
    print(f"\ngaming: geometric overall={overall:.1f} vs weighted-arith={arith:.1f}")
    assert overall < arith - 10, (overall, arith)
    assert overall < 45, overall

    r = compare_arrays(card_screen(), card_screen(n_cards=1, draw_button=False), return_visuals=False)
    scored = {k: v["score"] for k, v in r["subscores"].items() if v["score"] is not None}
    e2e_arith = _weighted_arith(scored)
    assert r["overall"] <= e2e_arith + 0.5, (r["overall"], e2e_arith)
    assert r["overall"] < max(scored.values()), "overall must not equal the best dimension"

    ref = card_screen()
    cand = card_screen(header=(120, 40, 60), btn=(220, 60, 60))
    a = compare_arrays(ref, cand, return_visuals=False)
    b = compare_arrays(ref, cand, return_visuals=False)
    assert a["overall"] == b["overall"], (a["overall"], b["overall"])
    for k in a["subscores"]:
        assert a["subscores"][k]["score"] == b["subscores"][k]["score"], k
    print("\ndeterminism: identical scores across repeated runs ✓")

    print("\nCalibration checks PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
