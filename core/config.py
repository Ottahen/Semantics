# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""Configuration loading for Semantics (ctf).

All configuration is environment-driven (12-factor style) so the same
binary works identically from the CLI, Docker, or CI. Values can also be
overridden programmatically, which the test-suite relies on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is an optional convenience
    pass


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass
class SemanticsConfig:
    """Runtime configuration for a single `ctf` invocation."""

    # --- Model / provider -------------------------------------------------
    model_name: str = field(default_factory=lambda: os.getenv("SEMANTICS_MODEL_NAME", "claude-sonnet-4-6"))
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("SEMANTICS_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    base_url: Optional[str] = field(default_factory=lambda: os.getenv("SEMANTICS_BASE_URL"))

    # --- Agent behaviour -----------------------------------------------------
    max_iterations: int = field(default_factory=lambda: _env_int("SEMANTICS_MAX_ITERATIONS", 25))
    max_context_tokens: int = field(default_factory=lambda: _env_int("SEMANTICS_MAX_CONTEXT_TOKENS", 100_000))
    auto_approve: bool = field(default_factory=lambda: _env_bool("SEMANTICS_AUTO_APPROVE", True))
    bash_timeout_seconds: int = field(default_factory=lambda: _env_int("SEMANTICS_BASH_TIMEOUT", 60))

    # --- Workspace -------------------------------------------------------
    project_root: Path = field(default_factory=lambda: Path(os.getenv("SEMANTICS_PROJECT_ROOT", ".")).resolve())

    # --- UI ----------------------------------------------------------------
    use_tui: bool = field(default_factory=lambda: _env_bool("SEMANTICS_TUI", True))

    # --- Licensing (Pro) -----------------------------------------------------
    license_key: Optional[str] = field(default_factory=lambda: os.getenv("SEMANTICS_LICENSE_KEY"))
    licensed_to: Optional[str] = field(default_factory=lambda: os.getenv("SEMANTICS_LICENSED_TO"))

    def is_pro(self) -> bool:
        return bool(self.license_key)

    def validate(self) -> None:
        if not self.api_key and not self.base_url:
            raise ValueError(
                "No API key configured. Set SEMANTICS_API_KEY (or ANTHROPIC_API_KEY / "
                "OPENAI_API_KEY, depending on --model) or pass --api-key."
            )
        if not self.project_root.exists():
            raise ValueError(f"Project root does not exist: {self.project_root}")


def load_config(**overrides) -> SemanticsConfig:
    """Build a SemanticsConfig from the environment, then apply overrides."""
    cfg = SemanticsConfig()
    for key, value in overrides.items():
        if value is None or not hasattr(cfg, key):
            continue
        if key == "project_root":
            value = Path(value).resolve()
        setattr(cfg, key, value)
    return cfg
