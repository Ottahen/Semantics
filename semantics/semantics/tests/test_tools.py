# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

import asyncio

import pytest

from core.tools import PathEscapeError, ToolRegistry


@pytest.fixture()
def registry(tmp_path):
    return ToolRegistry(root=tmp_path, bash_timeout=5)


def run(coro):
    return asyncio.run(coro)


def test_write_then_read_file(registry, tmp_path):
    out = run(registry.execute("write_file", {"path": "hello.txt", "content": "hi there"}))
    assert "Created" in out
    assert (tmp_path / "hello.txt").read_text() == "hi there"

    out = run(registry.execute("read_file", {"path": "hello.txt"}))
    assert out == "hi there"


def test_read_missing_file(registry):
    out = run(registry.execute("read_file", {"path": "nope.txt"}))
    assert "does not exist" in out


def test_edit_file_requires_unique_match(registry, tmp_path):
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n")
    out = run(registry.execute("edit_file", {"path": "a.py", "old_str": "x = 1", "new_str": "x = 2"}))
    assert "appears 2 times" in out


def test_edit_file_applies_unique_match(registry, tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    out = run(registry.execute("edit_file", {"path": "a.py", "old_str": "return 1", "new_str": "return 2"}))
    assert "Edited" in out
    assert (tmp_path / "a.py").read_text() == "def foo():\n    return 2\n"


def test_path_escape_is_blocked(registry):
    out = run(registry.execute("read_file", {"path": "../../etc/passwd"}))
    assert "outside the project root" in out


def test_path_escape_raises_directly(registry):
    with pytest.raises(PathEscapeError):
        registry._resolve("../outside.txt")


def test_execute_bash_returns_stdout(registry):
    out = run(registry.execute("execute_bash", {"command": "echo hello-from-bash"}))
    assert "hello-from-bash" in out
    assert "[exit code 0]" in out


def test_execute_bash_timeout(tmp_path):
    reg = ToolRegistry(root=tmp_path, bash_timeout=1)
    out = run(reg.execute("execute_bash", {"command": "sleep 5"}))
    assert "timed out" in out


def test_grep_search_finds_pattern(registry, tmp_path):
    (tmp_path / "mod.py").write_text("def target_function():\n    pass\n")
    out = run(registry.execute("grep_search", {"pattern": "target_function"}))
    assert "mod.py" in out


def test_list_directory(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    out = run(registry.execute("list_directory", {"path": "."}))
    assert "a.txt" in out and "sub" in out


def test_unknown_tool(registry):
    out = run(registry.execute("teleport", {}))
    assert "unknown tool" in out


def test_registry_accepts_string_root(tmp_path):
    # Regression test: root is often produced as a plain str (tempfile.mkdtemp(),
    # CLI args before Path-conversion, etc.) and must still work.
    reg = ToolRegistry(root=str(tmp_path))
    assert reg.root == tmp_path.resolve()
    out = run(reg.execute("write_file", {"path": "a.txt", "content": "hi"}))
    assert "Created" in out


def test_get_schemas_includes_all_builtin_tools(registry):
    names = {s["function"]["name"] for s in registry.get_schemas()}
    always_present = {"read_file", "write_file", "edit_file", "list_directory", "grep_search", "execute_bash"}
    assert always_present.issubset(names)
    # repo_map is only offered when aider-chat is installed
    assert names - always_present <= {"repo_map"}


def test_repo_map_summarizes_source_files(registry, tmp_path):
    pytest.importorskip("aider", reason="repo_map is only available with aider-chat installed")
    (tmp_path / "app.py").write_text("def handle_request(req):\n    return req.path\n")
    (tmp_path / "utils.py").write_text("def slugify(s):\n    return s.lower().replace(' ', '-')\n")

    out = run(registry.execute("repo_map", {"mentioned_files": ["app.py"]}))
    assert "handle_request" in out or "app.py" in out
