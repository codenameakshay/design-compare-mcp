"""Direct pipeline checks (no MCP layer): correctness + monotonicity + alignment.

Run with the venv interpreter:
    worker/.venv/bin/python worker/tests/test_pipeline.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

# Make the vision_worker package importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.pipeline import compare  # noqa: E402

FX = Path(__file__).resolve().parents[2] / "test" / "fixtures"
REF = str(FX / "reference.png")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def score(candidate: str, mode: str = "screen") -> dict:
    return compare(REF, str(FX / candidate), mode=mode)


def main() -> int:
    ident = score("identical.png")
    diff = score("different.png")
    shifted_screen = score("shifted.png", "screen")
    shifted_widget = score("shifted.png", "widget")

    print(f"identical              overall = {ident['overall']}")
    print(f"different              overall = {diff['overall']}")
    print(f"shifted (screen/align) overall = {shifted_screen['overall']}  "
          f"align={shifted_screen['alignment']}")
    print(f"shifted (widget/none)  overall = {shifted_widget['overall']}")

    # 1. Identical images score ~100.
    assert ident["overall"] >= 99, f"identical should be ~100, got {ident['overall']}"

    # 2. A structurally different screen scores clearly lower.
    assert diff["overall"] < ident["overall"] - 10, (
        f"different layout should score clearly lower ({diff['overall']} vs {ident['overall']})"
    )

    # 3. Alignment recovers a pure translation: screen mode beats unaligned widget mode.
    assert shifted_screen["overall"] > shifted_widget["overall"], (
        "ECC alignment should recover the shift "
        f"({shifted_screen['overall']} !> {shifted_widget['overall']})"
    )

    # 4. Result shape: five sub-scores, only layout scored in Phase 1.
    subs = ident["subscores"]
    assert set(subs) == {"layout", "color", "content", "typography", "spacing"}
    assert subs["layout"]["score"] is not None
    assert subs["color"]["score"] is None, "color is pending in Phase 1"

    # 5. Visuals are real, decodable PNGs.
    vis = ident["visuals"]
    assert len(vis) == 3, f"expected 3 visuals, got {len(vis)}"
    for v in vis:
        raw = base64.b64decode(v["base64"])
        assert raw[:8] == PNG_MAGIC, f"{v['name']} is not a PNG"

    print("\nPhase 1 pipeline checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
