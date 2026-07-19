"""The Semantics color palette — strictly enforced across every screen.

Kept as plain constants (not just CSS) so screens can also use them in
Rich renderables (progress bars, pyfiglet gradients) where Textual CSS
variables aren't reachable.
"""

from __future__ import annotations

BACKGROUND = "#0b0b0f"
TERMUX_BACKGROUND = "#0a0a12"
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#86868b"
ACCENT_BLUE = "#0a84ff"
ACCENT_PURPLE = "#5e5ce6"
SUCCESS = "#30d158"
WARNING = "#ffd60a"
ERROR = "#ff453a"

GRADIENT_LOGO = [ACCENT_BLUE, "#3d9bff", "#6f9dff", ACCENT_PURPLE]

PHASE_ICON = {
    "startup": "◉",
    "analyzing": "🔍",
    "planning": "📋",
    "executing": "🚀",
    "complete": "✅",
    "error": "❌",
}

PHASE_LABEL = {
    "startup": "Starting",
    "analyzing": "Analyzing",
    "planning": "Planning",
    "executing": "Executing",
    "complete": "Complete",
    "error": "Error",
}
