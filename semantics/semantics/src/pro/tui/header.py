"""The pinned status bar shown at the top of every screen:

    ◉ Semantics  │  Executing  │  ⏱ 8s  │  🧠 1,234 tokens
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static

from .colors import PHASE_LABEL


class StatusHeader(Static):
    """Reactive status bar; call `.update_status(...)` to refresh in place."""

    phase: reactive[str] = reactive("startup")
    elapsed: reactive[float] = reactive(0.0)
    tokens: reactive[int] = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(id="status-header", **kwargs)

    def on_mount(self) -> None:
        self._render()

    def update_status(self, phase: str | None = None, elapsed: float | None = None, tokens: int | None = None) -> None:
        if phase is not None:
            self.phase = phase
        if elapsed is not None:
            self.elapsed = elapsed
        if tokens is not None:
            self.tokens = tokens
        self._render()

    def watch_phase(self, _: str) -> None:
        self._render()

    def watch_elapsed(self, _: float) -> None:
        self._render()

    def watch_tokens(self, _: int) -> None:
        self._render()

    def _render(self) -> None:
        label = PHASE_LABEL.get(self.phase, self.phase.title())
        self.update(
            f"[b]◉ Semantics[/b]  │  [#0a84ff]{label}[/#0a84ff]  │  "
            f"⏱ {self.elapsed:.0f}s  │  🧠 {self.tokens:,} tokens"
        )
