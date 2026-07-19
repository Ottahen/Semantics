"""Screen 1 — Startup / Welcome.

Gradient wordmark, tagline banner, and a live checklist of init steps
("Initializing agent...", "Connecting to <model>...", "Ready.").
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from ..colors import GRADIENT_LOGO

try:
    import pyfiglet

    _HAS_PYFIGLET = True
except ImportError:  # pragma: no cover
    _HAS_PYFIGLET = False


def _gradient_logo(text: str = "SEMANTICS") -> Text:
    if _HAS_PYFIGLET:
        art = pyfiglet.figlet_format(text, font="standard")
    else:
        art = text  # graceful fallback if pyfiglet is missing
    lines = art.rstrip("\n").splitlines() or [text]

    out = Text()
    n = len(GRADIENT_LOGO)
    for i, line in enumerate(lines):
        color = GRADIENT_LOGO[min(i * n // max(1, len(lines)), n - 1)]
        out.append(line + "\n", style=color)
    return out


class StartupView(Vertical):
    """`ctf "<task>"` welcome screen."""

    DEFAULT_STEPS = [
        "Initializing agent...",
        "Connecting to model...",
        "Ready.",
    ]

    def compose(self):
        yield Static(_gradient_logo(), id="logo")
        yield Static(
            "✦ Code that understands.  ✦  ctf v2.0  ✦",
            id="tagline-panel",
        )
        yield Static(self._render_steps([]), id="init-steps")

    def set_steps(self, completed: list[str], current: str | None = None) -> None:
        self.query_one("#init-steps", Static).update(self._render_steps(completed, current))

    @staticmethod
    def _render_steps(completed: list[str], current: str | None = None) -> str:
        lines = []
        for step in completed:
            lines.append(f"[#30d158]✅ {step}[/#30d158]")
        if current:
            lines.append(f"[#0a84ff]🔄 {current}[/#0a84ff]")
        return "\n".join(lines) if lines else "[#86868b]waiting to start...[/#86868b]"
