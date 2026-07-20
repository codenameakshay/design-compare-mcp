"""Persistent vision worker for design-compare-mcp.

Phase 3: all five dimensions live — structure (SSIM), color (ΔE palette),
content-presence (region matching), typography (text amount/scale), and spacing
(margins/rhythm) — combined via a weighted geometric mean, with diagnostic
visuals. Dimensions return None when not applicable (e.g. no text / no blocks).
"""

__version__ = "0.3.0"
PROTOCOL = 1
