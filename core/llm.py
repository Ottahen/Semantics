# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""Multi-provider LLM client.

Aider already solved "talk to OpenAI / Anthropic / Gemini / Ollama /
OpenRouter through one interface" with `litellm`. Rather than reinvent
that, Semantics reuses it directly — this module is a thin, typed wrapper
that normalizes responses into the small `LLMResponse` / `ToolCall` shape
the rest of the agent loop expects, regardless of which provider answered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import litellm

    litellm.drop_params = True  # silently ignore provider-unsupported kwargs
    _HAS_LITELLM = True
except ImportError:  # pragma: no cover
    _HAS_LITELLM = False


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Any = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class SemanticsLLM:
    """Thin async wrapper around litellm.completion.

    Works with any provider litellm supports: pass a provider-qualified
    model string (e.g. "anthropic/claude-sonnet-4-6", "openai/gpt-5",
    "ollama/qwen2.5-coder", "openrouter/anthropic/claude-3.5-sonnet")
    or a bare name for the default provider. For OpenRouter specifically,
    set SEMANTICS_API_KEY to your OpenRouter key (SEMANTICS_BASE_URL is
    not needed — litellm already knows OpenRouter's endpoint).
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
    ) -> None:
        if not _HAS_LITELLM:
            raise LLMError(
                "litellm is not installed. Run `pip install -r requirements.txt` "
                "(litellm is what gives Semantics OpenAI/Anthropic/Ollama support)."
            )
        self.model = model_name or "claude-sonnet-4-6"
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self.temperature,
        )
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface provider errors uniformly
            raise LLMError(f"LLM call failed ({self.model}): {exc}") from exc

        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            raw=response,
        )
