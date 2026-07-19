"""Screen 3 — Execution Plan.

When `auto_approve` is off, the agent pauses here after its first
tool-free planning turn and waits for the user to accept, cancel, or ask
for a diff before any file is touched.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, DataTable, Static


class PlanningView(Vertical):
    class Decision(Message):
        """Posted when the user accepts/cancels/asks to modify the plan."""

        def __init__(self, decision: str) -> None:
            self.decision = decision  # "accept" | "modify" | "cancel" | "diff"
            super().__init__()

    def compose(self):
        yield Static("[b]📋 EXECUTION PLAN[/b]", classes="panel-title")
        table = DataTable(id="plan-table")
        table.add_columns("Step", "Action", "Description")
        yield table
        yield Static("", id="plan-impact", classes="panel")
        with Horizontal(id="plan-actions"):
            yield Button("Accept plan", id="accept", variant="success")
            yield Button("Modify", id="modify", variant="warning")
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Show diff", id="diff")

    def set_plan(self, steps: list[tuple[str, str]]) -> None:
        table = self.query_one("#plan-table", DataTable)
        table.clear()
        for i, (action, description) in enumerate(steps, 1):
            table.add_row(f"[{i}]", action, description)

    def set_impact(self, files_touched: int, added: int, removed: int) -> None:
        self.query_one("#plan-impact", Static).update(
            f"📊 Estimated impact  ──→  {files_touched} files  ·  +{added} lines  ·  -{removed} lines"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.post_message(self.Decision(event.button.id or "cancel"))
