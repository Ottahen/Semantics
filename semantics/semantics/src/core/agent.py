# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""The autonomous agent loop.

Design note — why this isn't `class SemanticsAgent(aider.coders.base_coder.Coder)`:
Aider's `Coder` is a stateful, interactive chat controller: its constructor
requires a live `Model` and `InputOutput`, it owns its own edit-format
pipeline (parsing SEARCH/REPLACE blocks out of free-form model text), and
`Coder.create()` — not direct construction — is the normal entry point. A
tool-calling agent loop that wants the model to call `write_file`/`edit_file`
as structured function calls doesn't compose cleanly with that: it would
mean fighting Coder's own edit-application logic rather than reusing it.

So Semantics reuses Aider a different way: `core.tools.ToolRegistry`
registers a `repo_map` tool backed directly by `aider.repomap.RepoMap` —
the actual "automatic codebase understanding without vector databases"
engine — which *does* have a clean, stateless call signature. That's a
real, working integration rather than a fragile inheritance relationship,
and it degrades gracefully (the tool just isn't offered) when `aider-chat`
isn't installed, which is also why `SemanticsAgent` itself has no aider
base class to fall back from.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from .context import ContextManager
from .llm import LLMError, SemanticsLLM
from .tools import ToolRegistry


class Phase(str, Enum):
    STARTUP = "startup"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class AgentEvent:
    """Progress event emitted during `run_autonomous`, consumed by the TUI (or CLI logger)."""

    phase: Phase
    message: str
    iteration: int = 0
    tokens_used: int = 0
    elapsed: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


EventCallback = Callable[[AgentEvent], Optional[Awaitable[None]]]


SYSTEM_PROMPT = """You are Semantics, an autonomous senior software engineer working \
inside the user's repository. You have tools to read/write/edit files, search the \
codebase, and run shell commands (plus `repo_map` for a ranked overview of the \
codebase, when available). Work in small verifiable steps, prefer `edit_file` over \
rewriting whole files, run tests/commands to check your work when reasonable, and \
finish by stating clearly what you changed. Stop calling tools once the task is done."""


class SemanticsAgent:
    """Runs a tool-calling agent loop autonomously, per the Semantics design doc.

    Composes a `SemanticsLLM` and a `ToolRegistry` rather than extending
    Aider's `Coder` — see the module docstring for why.
    """

    def __init__(
        self,
        llm: SemanticsLLM,
        tools: ToolRegistry,
        max_iterations: int = 25,
        system_prompt: str = SYSTEM_PROMPT,
        max_context_tokens: int = 100_000,
    ) -> None:
        self.llm = llm
        self.tool_registry = tools
        self.root = tools.root
        self.max_iterations = max_iterations
        self.context = ContextManager(max_tokens=max_context_tokens, system_prompt=system_prompt)
        self.current_task: Optional[str] = None
        self.uses_aider_repo_map = "repo_map" in {s["function"]["name"] for s in tools.get_schemas()}

    async def run_autonomous(
        self,
        task: str,
        on_event: Optional[EventCallback] = None,
        approval_gate: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> str:
        """Run the agent autonomously without user interaction, emitting AgentEvents.

        If `approval_gate` is given, the agent pauses after its first turn —
        emitting Phase.PLANNING — and awaits it before touching any tool.
        The gate should return True to proceed or False to cancel the run
        (this is how the TUI's Accept/Cancel plan buttons work).
        """
        start = time.monotonic()

        async def emit(phase: Phase, message: str, iteration: int = 0, **extra: Any) -> None:
            if on_event is None:
                return
            evt = AgentEvent(
                phase=phase,
                message=message,
                iteration=iteration,
                tokens_used=self.context.total_tokens_used,
                elapsed=time.monotonic() - start,
                extra=extra,
            )
            result = on_event(evt)
            if result is not None and hasattr(result, "__await__"):
                await result

        self.current_task = task
        self.context.add_user_message(task)
        await emit(Phase.ANALYZING, f"Analyzing task: {task}")

        for iteration in range(1, self.max_iterations + 1):
            await emit(Phase.EXECUTING, f"Iteration {iteration}/{self.max_iterations}: thinking...", iteration, stage="thinking")

            try:
                response = await self.llm.chat(
                    messages=self.context.get_messages(),
                    tools=self.tool_registry.get_schemas(),
                )
            except LLMError as exc:
                await emit(Phase.ERROR, str(exc), iteration)
                return f"Agent stopped: {exc}"

            self.context.record_usage(response.total_tokens)

            if not response.tool_calls:
                self.context.add_assistant_message(response.content)
                await emit(Phase.COMPLETE, "Task complete.", iteration)
                return response.content

            # Record the assistant's tool-call turn, then execute each tool.
            self.context.add_assistant_message(
                response.content,
                tool_calls=[
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in response.tool_calls
                ],
            )

            if iteration == 1 and approval_gate is not None:
                plan_summary = response.content or "(model proposed tool calls with no accompanying explanation)"
                await emit(Phase.PLANNING, plan_summary, iteration, tool_calls=response.tool_calls)
                approved = await approval_gate()
                if not approved:
                    await emit(Phase.ERROR, "Plan rejected by user.", iteration)
                    return "Run cancelled: plan was not approved."

            for tool_call in response.tool_calls:
                await emit(
                    Phase.EXECUTING,
                    f"Running {tool_call.name}({_short_args(tool_call.arguments)})",
                    iteration,
                    stage="start",
                    tool=tool_call.name,
                    tool_call_id=tool_call.id,
                    arguments=tool_call.arguments,
                )
                result = await self.tool_registry.execute(tool_call.name, tool_call.arguments)
                self.context.add_tool_result(tool_call.id, result, name=tool_call.name)
                await emit(
                    Phase.EXECUTING,
                    f"{tool_call.name} -> {_short_args({'result': result})}",
                    iteration,
                    stage="end",
                    tool=tool_call.name,
                    tool_call_id=tool_call.id,
                    arguments=tool_call.arguments,
                    result=result,
                )

        await emit(Phase.ERROR, "Max iterations reached.", self.max_iterations)
        return "Task exceeded maximum iterations. Please refine your request or raise --max-iterations."


def _short_args(args: dict[str, Any], limit: int = 80) -> str:
    text = str(args)
    return text if len(text) <= limit else text[: limit - 3] + "..."
