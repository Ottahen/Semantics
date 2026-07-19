# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""Conversation / context window management.

Aider already maintains chat history for its interactive loop. Semantics
runs autonomously for up to `max_iterations` turns, so we need our own
lightweight message log plus a cheap token estimator and a summarization
hook to keep long-running tasks inside the model's context window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token for English text/code).

    Good enough for budgeting decisions; not used for billing.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[list] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d

    def token_estimate(self) -> int:
        return estimate_tokens(self.content or "")


@dataclass
class ContextManager:
    max_tokens: int = 100_000
    # Fraction of history summarized away when we blow the budget.
    summarize_fraction: float = 0.3
    system_prompt: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    total_tokens_used: int = 0  # running total reported by the LLM provider

    def __post_init__(self) -> None:
        if self.system_prompt:
            self.messages.append(Message(role="system", content=self.system_prompt))

    # -- mutation -----------------------------------------------------------
    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str, tool_calls: Optional[list] = None) -> None:
        self.messages.append(Message(role="assistant", content=content or "", tool_calls=tool_calls))

    def add_tool_result(self, tool_call_id: str, content: str, name: Optional[str] = None) -> None:
        self.messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id, name=name))

    def record_usage(self, tokens: int) -> None:
        self.total_tokens_used += max(0, tokens)

    # -- retrieval ------------------------------------------------------------
    def get_messages(self) -> list[dict]:
        if self._estimated_tokens() > self.max_tokens:
            self._summarize()
        return [m.to_dict() for m in self.messages]

    def _estimated_tokens(self) -> int:
        return sum(m.token_estimate() for m in self.messages)

    def _summarize(self, summarizer: Optional[Callable[[list[Message]], str]] = None) -> None:
        """Collapse the oldest `summarize_fraction` of turns into one summary message.

        `summarizer` lets callers plug in an LLM-backed summary; absent that we
        fall back to a compact structural summary so the agent never crashes
        on long-running tasks even without an extra model call.
        """
        # Never summarize away the system prompt (index 0 if present).
        start = 1 if self.messages and self.messages[0].role == "system" else 0
        body = self.messages[start:]
        if len(body) < 4:
            return  # not enough history to bother

        cut = max(1, int(len(body) * self.summarize_fraction))
        old, recent = body[:cut], body[cut:]

        if summarizer:
            summary_text = summarizer(old)
        else:
            summary_text = self._structural_summary(old)

        summary_msg = Message(role="system", content=f"[Context summary of {len(old)} earlier turns]\n{summary_text}")
        self.messages = self.messages[:start] + [summary_msg] + recent

    @staticmethod
    def _structural_summary(old: list[Message]) -> str:
        lines = []
        for m in old:
            snippet = (m.content or "").strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            lines.append(f"- ({m.role}) {snippet}")
        return "\n".join(lines)

    def clear(self) -> None:
        sys_msg = self.messages[0] if self.messages and self.messages[0].role == "system" else None
        self.messages = [sys_msg] if sys_msg else []
