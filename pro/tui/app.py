"""SemanticsApp — the Apple-level terminal experience.

Wires `core.agent.SemanticsAgent` to the five phase views through
`AgentEvent`s: the agent runs as a background worker, and every event it
emits (analyzing / planning / executing / complete / error) drives which
view is visible and what it shows, in real time.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Input, Static

from core.agent import AgentEvent, Phase, SemanticsAgent
from pro.artifact import ArtifactBuilder, ArtifactManifest

from .header import StatusHeader
from .screens import AnalysisView, CompletionView, ExecutionView, PlanningView, StartupView
from .screens.execution import ExecutionStepRow

STYLES_PATH = Path(__file__).parent / "styles.tcss"


class SemanticsApp(App):
    """`ctf "<task>"` — the full interactive run, end to end."""

    CSS_PATH = str(STYLES_PATH)
    TITLE = "Semantics"
    BINDINGS = [("q", "quit", "Quit"), ("ctrl+c", "quit", "Quit")]

    def __init__(
        self,
        agent: SemanticsAgent,
        task: str,
        require_plan_approval: bool = False,
        build_artifact: bool = True,
        artifact_output: str = "semantics-artifact.zip",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.agent = agent
        self.task_description = task
        self.require_plan_approval = require_plan_approval
        self.build_artifact = build_artifact
        self.artifact_output = artifact_output

        self._start_time = time.monotonic()
        self._step_rows: dict[str, ExecutionStepRow] = {}
        self._plan_decision: Optional[asyncio.Future] = None
        self._files_touched: set[str] = set()

    # -- layout ---------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Container(id="body"):
            yield StartupView(id="view-startup")
            yield AnalysisView(id="view-analysis")
            yield PlanningView(id="view-planning")
            yield ExecutionView(id="view-execution")
            yield CompletionView(id="view-completion")
        with Horizontal(id="command-input-bar"):
            yield Input(placeholder="Ask a follow-up once this run completes...", id="command-input")

    def on_mount(self) -> None:
        for view_id in ("view-analysis", "view-planning", "view-execution", "view-completion"):
            self.query_one(f"#{view_id}").display = False
        self.run_worker(self._run_agent(), exclusive=True, name="agent-run")

    # -- agent run --------------------------------------------------------------
    async def _run_agent(self) -> None:
        approval_gate = self._await_plan_decision if self.require_plan_approval else None
        try:
            result = await self.agent.run_autonomous(self.task_description, on_event=self._on_agent_event, approval_gate=approval_gate)
        except Exception as exc:  # noqa: BLE001 - surface any unexpected crash in the UI, not a traceback
            self._show_view("view-completion")
            self.query_one(CompletionView).set_summary([], self.agent.context.total_tokens_used, self._elapsed(), self.agent.llm.model, None)
            self.query_one("#summary-panel", Static).update(f"[#ff453a]❌ Agent crashed: {exc}[/#ff453a]")
            return
        self._finish(result)

    async def _on_agent_event(self, event: AgentEvent) -> None:
        header = self.query_one(StatusHeader)
        header.update_status(phase=event.phase.value, elapsed=event.elapsed, tokens=event.tokens_used)

        if event.phase == Phase.ANALYZING:
            self._show_view("view-analysis")
            self.query_one(AnalysisView).log_line(event.message)

        elif event.phase == Phase.PLANNING:
            self._show_view("view-planning")
            steps = [(tc.name, str(tc.arguments)[:60]) for tc in event.extra.get("tool_calls", [])]
            self.query_one(PlanningView).set_plan(steps or [("respond", event.message[:60])])
            self.query_one(PlanningView).set_impact(len(steps), 0, 0)

        elif event.phase == Phase.EXECUTING:
            self._show_view("view-execution")
            exec_view = self.query_one(ExecutionView)
            stage = event.extra.get("stage")

            if stage == "thinking":
                exec_view.set_llm_status(event.message)

            elif stage == "start":
                tool = event.extra.get("tool", "tool")
                row = await exec_view.start_step(f"{tool} — {event.message[:70]}")
                self._step_rows[event.extra["tool_call_id"]] = row

            elif stage == "end":
                tool_call_id = event.extra.get("tool_call_id")
                row = self._step_rows.pop(tool_call_id, None)
                if row is not None:
                    row.complete(event.message[:100])
                tool = event.extra.get("tool")
                if tool in {"write_file", "edit_file"}:
                    path = str(event.extra.get("arguments", {}).get("path", ""))
                    if path:
                        self._files_touched.add(path)

        elif event.phase == Phase.ERROR:
            self._show_view("view-execution")
            self.query_one(ExecutionView).set_llm_status(f"[#ff453a]{event.message}[/#ff453a]")

    def _await_plan_decision(self) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        self._plan_decision = loop.create_future()
        return self._plan_decision_wrapper()

    async def _plan_decision_wrapper(self) -> bool:
        decision = await self._plan_decision
        return decision == "accept"

    def on_planning_view_decision(self, message: PlanningView.Decision) -> None:
        if self._plan_decision and not self._plan_decision.done():
            self._plan_decision.set_result(message.decision)

    # -- completion -------------------------------------------------------------
    def _finish(self, result: str) -> None:
        self._show_view("view-completion")
        artifact_path = None
        if self.build_artifact and self._files_touched:
            artifact_path = self._package_artifact()

        self.query_one(CompletionView).set_summary(
            files_changed=sorted(f for f in self._files_touched if f),
            tokens_used=self.agent.context.total_tokens_used,
            elapsed_seconds=self._elapsed(),
            model=self.agent.llm.model,
            artifact_path=str(artifact_path) if artifact_path else None,
        )
        self.query_one(CompletionView).set_tips(
            [
                f"Result: {result[:200]}" if result else "Done.",
                "Use `ctf --explain` to see a detailed breakdown of changes.",
            ]
        )

    def _package_artifact(self) -> Path:
        builder = ArtifactBuilder()
        for rel_path in sorted(self._files_touched):
            full_path = self.agent.tool_registry.root / rel_path
            if full_path.exists():
                builder.add_existing_file(full_path, rel_path)
        builder.add_manifest(
            ArtifactManifest(
                task=self.task_description,
                files_changed=sorted(self._files_touched),
                model=self.agent.llm.model,
                tokens_used=self.agent.context.total_tokens_used,
                duration_seconds=self._elapsed(),
            )
        )
        return builder.build_zip(self.agent.tool_registry.root / self.artifact_output)

    # -- helpers ------------------------------------------------------------
    def _show_view(self, view_id: str) -> None:
        for vid in ("view-startup", "view-analysis", "view-planning", "view-execution", "view-completion"):
            self.query_one(f"#{vid}").display = vid == view_id

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        self._files_touched.clear()
        self._step_rows.clear()
        self._show_view("view-startup")
        self.run_worker(self._run_followup(text), exclusive=True, name="agent-followup")

    async def _run_followup(self, text: str) -> None:
        approval_gate = self._await_plan_decision if self.require_plan_approval else None
        result = await self.agent.run_autonomous(text, on_event=self._on_agent_event, approval_gate=approval_gate)
        self._finish(result)
