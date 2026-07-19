# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

from pathlib import Path

import pytest

from core.config import load_config


def test_load_config_defaults_from_env(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTICS_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    cfg = load_config(project_root=tmp_path)
    assert cfg.api_key == "sk-test-123"
    assert cfg.project_root == tmp_path.resolve()


def test_load_config_coerces_string_project_root(tmp_path):
    # Regression test: overrides passed as plain strings (e.g. from ad-hoc
    # scripts or tests, not just Typer's already-a-Path CLI option) must
    # still resolve to a Path, or .validate() blows up on .exists().
    cfg = load_config(project_root=str(tmp_path), api_key="sk-test")
    assert isinstance(cfg.project_root, Path)
    cfg.validate()  # should not raise


def test_validate_requires_api_key(tmp_path):
    cfg = load_config(project_root=tmp_path, api_key=None)
    cfg.api_key = None
    cfg.base_url = None
    with pytest.raises(ValueError, match="No API key"):
        cfg.validate()


def test_validate_requires_existing_project_root(tmp_path):
    cfg = load_config(project_root=tmp_path / "does-not-exist", api_key="sk-test")
    with pytest.raises(ValueError, match="does not exist"):
        cfg.validate()


def test_is_pro_reflects_license_key():
    cfg = load_config(license_key=None)
    assert cfg.is_pro() is False
    cfg = load_config(license_key="some.jwt.token")
    assert cfg.is_pro() is True
