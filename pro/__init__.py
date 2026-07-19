"""Semantics Pro — proprietary extensions (browser, MCP, sub-agents, TUI, licensing).

Everything under `src/pro` is closed-source (see LICENSE.enterprise) and is
gated behind a valid license key at runtime via `pro.license.require_license`.
"""

__all__ = ["artifact", "license", "mcp", "browser", "pico"]
