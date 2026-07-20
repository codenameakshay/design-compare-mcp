"""Robustness: hostile / degenerate inputs must never crash the worker, and one
failing metric must not sink the whole comparison.

Run with the venv interpreter:
    worker/.venv/bin/python worker/tests/test_robustness.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from vision_worker.io_utils import ImageTooLargeError  # noqa: E402
from vision_worker.pipeline import compare  # noqa: E402


def _save(img: Image.Image, suffix=".png") -> str:
    p = tempfile.mktemp(suffix=suffix)
    img.save(p)
    return p


def _expect_raises(label, fn, exc_types):
    try:
        fn()
    except exc_types as e:
        print(f"  {label:22s} -> raised {type(e).__name__} (clean)")
        return
    raise AssertionError(f"{label}: expected {exc_types}, no exception raised")


def main() -> int:
    print("decode failures raise a clean, typed error (-> worker error response):")
    _expect_raises("nonexistent path", lambda: compare("/no/a.png", "/no/b.png"), FileNotFoundError)
    txt = tempfile.mktemp(suffix=".png")
    Path(txt).write_text("not an image")
    _expect_raises("non-image file", lambda: compare(txt, txt), Exception)
    # Oversized: 12001px on one side trips MAX_DIM cheaply (no huge allocation).
    wide = _save(Image.new("RGB", (12001, 1), (0, 0, 0)))
    _expect_raises("oversized (dim cap)", lambda: compare(wide, wide), ImageTooLargeError)

    print("\ndegenerate-but-valid inputs degrade gracefully (no crash, partial result):")
    # Thin image -> normalized canvas is a few px tall -> SSIM (layout) fails, but
    # the other dimensions and the overall must still be produced.
    thin = _save(Image.new("RGB", (1000, 3), (200, 200, 200)))
    r = compare(thin, thin)
    layout = r["subscores"]["layout"]
    assert layout["score"] is None, f"expected isolated layout=None, got {layout}"
    assert "error" in layout["measurements"], layout
    assert isinstance(r["overall"], (int, float)), "overall still computed from other dims"
    scored = [v["score"] for v in r["subscores"].values() if v["score"] is not None]
    assert scored, "at least one dimension should still score"
    print(f"  thin 1000x3 -> layout isolated (None), overall={r['overall']} from {len(scored)} dims")

    # Valid odd formats still work.
    for label, img in [
        ("grayscale L", Image.new("L", (300, 400), 128)),
        ("RGBA alpha", Image.new("RGBA", (300, 400), (10, 20, 30, 128))),
        ("tiny 2x2", Image.new("RGB", (2, 2), (10, 10, 10))),
    ]:
        p = _save(img)
        r = compare(p, p)
        assert isinstance(r["overall"], (int, float)), label
        print(f"  {label:22s} -> overall={r['overall']}")

    print("\nPhase 5 robustness checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
