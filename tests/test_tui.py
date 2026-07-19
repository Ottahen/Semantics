# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

import pytest

from core.agent import SemanticsAgent
from core.llm import LLMResponse
from core.tools import ToolRegistry
from pro.tui.app import SemanticsApp
from pro.tui.screens import CompletionView
from tests.test_agent import FakeLLM


@pytest.mark.asyncio
async def test_app_boots_and_reaches_completion(tmp_path):
    registry = ToolRegistry(root=tmp_path)
    llm = FakeLLM([LLMResponse(content="All good, nothing to do.", tool_calls=[])])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=3)

    app = SemanticsApp(agent=agent, task="no-op task", build_artifact=False)
    async with app.run_test() as pilot:
        # Let the background worker run the (instant) fake agent to completion.
        completion = app.query_one(CompletionView)
        for _ in range(20):
            await pilot.pause()
            if completion.display:
                break

        assert completion.display is True
        # The app-level try/except swallows any crash from an event handler and
        # *still* shows the completion view with an error message in it — so we
        # explicitly assert the run actually succeeded, not just that some
        # completion view (crashed or not) is visible.
        summary_text = str(app.query_one("#summary-panel").render())
        assert "crashed" not in summary_text.lower()
        tips_text = str(app.query_one("#tips-panel").render())
        assert "All good" in tips_text


@pytest.mark.asyncio
async def test_app_handles_a_tool_call_without_crashing(tmp_path):
    """Regression test: this exact path (an ANALYZING event followed by a
    write_file tool call) used to crash inside AnalysisView.log_line
    (Static had no public `.renderable` attribute to read back)."""
    from core.llm import ToolCall

    registry = ToolRegistry(root=tmp_path)
    llm = FakeLLM([
        LLMResponse(
            content="Creating the file.",
            tool_calls=[ToolCall(id="c1", name="write_file", arguments={"path": "x.py", "content": "x = 1"})],
        ),
        LLMResponse(content="Done.", tool_calls=[]),
    ])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=5)

    app = SemanticsApp(agent=agent, task="create x.py", build_artifact=False)
    async with app.run_test() as pilot:
        completion = app.query_one(CompletionView)
        for _ in range(30):
            await pilot.pause()
            if completion.display:
                break

        summary_text = str(app.query_one("#summary-panel").render())
        assert "crashed" not in summary_text.lower()
        assert (tmp_path / "x.py").read_text() == "x = 1"
