"""Persistent vision worker for design-compare-mcp.

Phase 2: load -> normalize -> align -> {structure (SSIM), color (ΔE palette),
content-presence (region matching)} -> weighted geometric-mean overall, with
diagnostic visuals. Typography and spacing land in a later phase.
"""

__version__ = "0.2.0"
PROTOCOL = 1
