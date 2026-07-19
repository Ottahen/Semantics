# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""Semantics core — open-core (BSD 2-Clause) agent runtime.

This package contains the pieces that extend Aider into an autonomous
coding agent: configuration, context management, the LLM client, the
tool registry, and the agent loop itself.
"""

__all__ = ["agent", "tools", "context", "config", "llm"]
