# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

from core.context import ContextManager, estimate_tokens


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 400) == 100


def test_add_and_get_messages_roundtrip():
    ctx = ContextManager(system_prompt="you are an agent")
    ctx.add_user_message("do the thing")
    ctx.add_assistant_message("ok, doing it")

    messages = ctx.get_messages()
    assert messages[0] == {"role": "system", "content": "you are an agent"}
    assert messages[1]["role"] == "user"
    assert messages[2]["content"] == "ok, doing it"


def test_tool_result_carries_call_id():
    ctx = ContextManager()
    ctx.add_tool_result("call_123", "file written", name="write_file")
    msg = ctx.get_messages()[0]
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_123"
    assert msg["name"] == "write_file"


def test_summarization_triggers_past_budget():
    ctx = ContextManager(system_prompt="sys", max_tokens=50)
    for i in range(20):
        ctx.add_user_message(f"Please investigate issue number {i} in the payment pipeline: " * 5)
        ctx.add_assistant_message(f"Investigated issue number {i}, found the root cause was: " * 5)

    raw_message_count = len(ctx.messages)
    raw_token_estimate = sum(estimate_tokens(m.content) for m in ctx.messages)

    messages = ctx.get_messages()  # triggers _summarize() since we're well past max_tokens

    # system prompt preserved, and a summary message replaces the oldest chunk
    assert messages[0]["role"] == "system"
    assert any("Context summary" in m["content"] for m in messages)
    # summarizing should have shrunk both the message count and the token estimate
    assert len(messages) < raw_message_count
    assert sum(estimate_tokens(m["content"]) for m in messages) < raw_token_estimate


def test_record_usage_accumulates():
    ctx = ContextManager()
    ctx.record_usage(100)
    ctx.record_usage(50)
    assert ctx.total_tokens_used == 150


def test_clear_preserves_system_prompt():
    ctx = ContextManager(system_prompt="sys")
    ctx.add_user_message("hi")
    ctx.clear()
    assert len(ctx.messages) == 1
    assert ctx.messages[0].role == "system"
