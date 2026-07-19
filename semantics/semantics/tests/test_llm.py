# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

import asyncio

import pytest

from core.llm import SemanticsLLM


def test_openrouter_model_is_recognized_by_litellm():
    """Regression/documentation test: `openrouter/<slug>` model strings route
    through litellm's OpenRouter provider, and SemanticsLLM passes api_key
    straight through per-call rather than relying on an OPENROUTER_API_KEY
    env var being set — so SEMANTICS_API_KEY alone is enough."""
    litellm = pytest.importorskip("litellm")
    model, provider, _, _ = litellm.get_llm_provider("openrouter/anthropic/claude-3.5-sonnet")
    assert provider == "openrouter"
    assert model == "anthropic/claude-3.5-sonnet"


def test_semantics_llm_forwards_api_key_and_model(monkeypatch):
    """Confirm the api_key/model actually land in the kwargs passed to litellm,
    regardless of provider — this is what makes OpenRouter (and any other
    litellm-supported provider) work via SEMANTICS_API_KEY alone."""
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)

        class FakeMessage:
            content = "ok"
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    import core.llm as llm_module

    monkeypatch.setattr(llm_module.litellm, "acompletion", fake_acompletion)

    client = SemanticsLLM(model_name="openrouter/anthropic/claude-3.5-sonnet", api_key="sk-or-test-123")

    asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))

    assert captured["model"] == "openrouter/anthropic/claude-3.5-sonnet"
    assert captured["api_key"] == "sk-or-test-123"
