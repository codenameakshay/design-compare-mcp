"""Image loading helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_rgb(path: str) -> np.ndarray:
    """Load an image as a contiguous HxWx3 uint8 RGB array.

    Honors EXIF orientation so rotated device screenshots compare correctly.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"image not found: {path}")
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im)
        arr = np.asarray(im.convert("RGB"))
    return np.ascontiguousarray(arr)
