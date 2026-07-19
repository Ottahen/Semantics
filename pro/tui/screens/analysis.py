"""Screen 2 — Analysis Phase.

Shows the project scan and a live "thinking" indicator while the first
LLM call is in flight. Backed by real ToolRegistry activity (e.g.
`grep_search` / `list_directory` calls the agent makes while it orients
itself), not a canned animation.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import DataTable, Static


class AnalysisView(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._log_lines: list[str] = []

    def compose(self):
        yield Static("[b]🔍 ANALYSIS PHASE[/b]", classes="panel-title")
        yield Static("Scanning project directory...", id="analysis-log", classes="panel")
        table = DataTable(id="module-table")
        table.add_columns("File / action", "Status")
        yield table

    def on_mount(self) -> None:
        pass

    def log_line(self, text: str) -> None:
        self._log_lines.append(text)
        self._log_lines = self._log_lines[-12:]  # keep the log from growing unbounded on long runs
        self.query_one("#analysis-log", Static).update("\n".join(self._log_lines))

    def add_row(self, label: str, status: str) -> None:
        table = self.query_one("#module-table", DataTable)
        table.add_row(label, status)
