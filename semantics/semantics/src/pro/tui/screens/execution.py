"""Screen 4 — Execution in Progress.

One row per tool call the agent makes, each with its own progress bar
that completes when the tool call returns — driven directly by
`AgentEvent`s from `core.agent.SemanticsAgent.run_autonomous`.
"""

from __future__ import annotations

from textual.containers import Vertical, VerticalScroll
from textual.widgets import ProgressBar, Static


class ExecutionStepRow(Vertical):
    def __init__(self, title: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title

    def compose(self):
        yield Static(f"✦ {self._title}", classes="exec-step-title")
        yield ProgressBar(total=100, show_eta=False)
        yield Static("", classes="exec-step-detail")

    def complete(self, detail: str = "") -> None:
        self.query_one(ProgressBar).update(progress=100)
        self.query_one(".exec-step-detail", Static).update(f"[#30d158]✅ {detail}[/#30d158]")

    def fail(self, detail: str = "") -> None:
        self.query_one(ProgressBar).update(progress=100)
        self.query_one(".exec-step-detail", Static).update(f"[#ff453a]❌ {detail}[/#ff453a]")


class ExecutionView(Vertical):
    def compose(self):
        yield Static("[b]🚀 EXECUTION IN PROGRESS[/b]", classes="panel-title")
        yield VerticalScroll(id="exec-steps")
        yield Static("", id="exec-llm-status", classes="panel")

    async def start_step(self, title: str) -> ExecutionStepRow:
        row = ExecutionStepRow(title, classes="panel")
        container = self.query_one("#exec-steps", VerticalScroll)
        await container.mount(row)  # must be awaited: .complete()/.fail() query row's children right after
        row.scroll_visible()
        return row

    def set_llm_status(self, text: str) -> None:
        self.query_one("#exec-llm-status", Static).update(f"🔄 {text}")

    def reset(self) -> None:
        self.query_one("#exec-steps", VerticalScroll).remove_children()
