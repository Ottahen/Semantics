# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

import pytest

from core.agent import AgentEvent, Phase, SemanticsAgent
from core.llm import LLMResponse, ToolCall
from core.tools import ToolRegistry


class FakeLLM:
    """Scripted LLM: returns each entry in `turns` in order, one per .chat() call."""

    def __init__(self, turns: list[LLMResponse], model: str = "fake-model-1"):
        self.turns = list(turns)
        self.model = model
        self.calls = 0

    async def chat(self, messages, tools=None, max_tokens=4096):
        self.calls += 1
        if not self.turns:
            raise AssertionError("FakeLLM ran out of scripted turns")
        return self.turns.pop(0)


@pytest.fixture()
def registry(tmp_path):
    return ToolRegistry(root=tmp_path, bash_timeout=5)


async def _events(agent, task, **kwargs):
    collected: list[AgentEvent] = []

    async def on_event(evt: AgentEvent):
        collected.append(evt)

    result = await agent.run_autonomous(task, on_event=on_event, **kwargs)
    return result, collected


@pytest.mark.asyncio
async def test_agent_writes_file_then_finishes(registry, tmp_path):
    llm = FakeLLM([
        LLMResponse(
            content="Writing the file now.",
            tool_calls=[ToolCall(id="call_1", name="write_file", arguments={"path": "hello.py", "content": "print(1)"})],
        ),
        LLMResponse(content="Done — created hello.py.", tool_calls=[]),
    ])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=5)

    result, events = await _events(agent, "create hello.py")

    assert "Done" in result
    assert (tmp_path / "hello.py").read_text() == "print(1)"
    assert llm.calls == 2
    assert any(e.phase == Phase.COMPLETE for e in events)


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations(registry):
    # Always returns a tool call, never finishes -> should hit the iteration cap.
    turns = [
        LLMResponse(content="", tool_calls=[ToolCall(id=f"c{i}", name="list_directory", arguments={"path": "."})])
        for i in range(3)
    ]
    llm = FakeLLM(turns)
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=3)

    result, events = await _events(agent, "loop forever")

    assert "exceeded maximum iterations" in result
    assert llm.calls == 3
    assert events[-1].phase == Phase.ERROR


@pytest.mark.asyncio
async def test_agent_no_tool_calls_returns_immediately(registry):
    llm = FakeLLM([LLMResponse(content="No changes needed.", tool_calls=[])])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=10)

    result, events = await _events(agent, "check if X is already true")

    assert result == "No changes needed."
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_approval_gate_can_reject_plan(registry, tmp_path):
    llm = FakeLLM([
        LLMResponse(
            content="I will delete everything.",
            tool_calls=[ToolCall(id="call_1", name="write_file", arguments={"path": "danger.txt", "content": "oops"})],
        ),
    ])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=5)

    async def reject():
        return False

    result, events = await _events(agent, "do something risky", approval_gate=reject)

    assert "not approved" in result or "cancelled" in result.lower()
    assert not (tmp_path / "danger.txt").exists()
    assert any(e.phase == Phase.PLANNING for e in events)


@pytest.mark.asyncio
async def test_approval_gate_can_accept_plan(registry, tmp_path):
    llm = FakeLLM([
        LLMResponse(
            content="Creating the file.",
            tool_calls=[ToolCall(id="call_1", name="write_file", arguments={"path": "ok.txt", "content": "fine"})],
        ),
        LLMResponse(content="Done.", tool_calls=[]),
    ])
    agent = SemanticsAgent(llm=llm, tools=registry, max_iterations=5)

    async def accept():
        return True

    result, events = await _events(agent, "do something", approval_gate=accept)

    assert (tmp_path / "ok.txt").read_text() == "fine"
    assert any(e.phase == Phase.PLANNING for e in events)
