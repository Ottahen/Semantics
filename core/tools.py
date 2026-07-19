# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""Tool registry: the concrete actions the agent is allowed to take.

Aider already knows how to apply whole-file / diff / edit-block changes
once *it* decides what to write. Semantics' autonomous loop drives that
from the outside via explicit, LLM-callable tools instead, so every action
the model takes is an auditable, schema-validated function call rather
than free-form text the coder has to parse.

All filesystem tools are sandboxed to `root` (the project directory) —
paths that resolve outside of it are rejected.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

try:
    # This is the actual point of contact with Aider: its repo-mapping
    # engine ("automatic codebase understanding without vector databases")
    # is genuinely reusable as-is, unlike its `Coder` class — which is a
    # stateful, interactive chat controller with a constructor that expects
    # a live `Model` + `InputOutput` + edit-format pipeline, and isn't
    # something a tool-calling loop can cleanly subclass. See core/agent.py
    # for the fuller rationale.
    from aider.io import InputOutput as _AiderIO
    from aider.models import Model as _AiderModel
    from aider.repomap import RepoMap as _AiderRepoMap

    _HAS_AIDER = True
except ImportError:  # pragma: no cover - aider-chat is an optional dependency
    _HAS_AIDER = False

MAX_READ_BYTES = 200_000  # ~ a very large source file; keeps context sane
MAX_OUTPUT_CHARS = 20_000

# Directories we never want to hand the model as "the codebase".
_IGNORED_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache"}
_MAX_REPO_MAP_FILES = 800  # aider's RepoMap ranks/prunes internally; this just bounds our directory walk


class ToolError(RuntimeError):
    pass


class PathEscapeError(ToolError):
    """Raised when a tool tries to touch a path outside the project root."""


@dataclass
class ToolResult:
    ok: bool
    output: str

    def __str__(self) -> str:  # so f"{result}" and dict-serialization behave
        return self.output


ToolFunc = Callable[..., Awaitable[ToolResult] | ToolResult]


@dataclass
class _Registered:
    func: ToolFunc
    schema: dict


class ToolRegistry:
    """Holds the callable tools + their JSON-schema descriptions for tool-calling."""

    def __init__(
        self,
        root: Optional[Path] = None,
        bash_timeout: int = 60,
        confirm_bash: bool = False,
        repo_map_model: str = "gpt-4o-mini",
    ) -> None:
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        self.bash_timeout = bash_timeout
        self.confirm_bash = confirm_bash
        self.repo_map_model = repo_map_model  # only used for aider's internal token counting
        self._aider_repo_map: Optional["_AiderRepoMap"] = None  # lazy; built on first repo_map() call
        self._tools: dict[str, _Registered] = {}
        self._register_builtin_tools()

    # -- registration ---------------------------------------------------------
    def register(self, name: str, func: ToolFunc, schema: dict) -> None:
        self._tools[name] = _Registered(func=func, schema=schema)

    def get_schemas(self) -> list[dict]:
        """Return tool schemas in Anthropic/OpenAI tool-calling format."""
        return [reg.schema for reg in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'. Available tools: {', '.join(self._tools)}"
        func = self._tools[name].func
        try:
            result = func(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except PathEscapeError as exc:
            return f"Error: {exc}"
        except TypeError as exc:
            return f"Error: bad arguments for '{name}': {exc}"
        except Exception as exc:  # noqa: BLE001 - tool failures become model-visible text
            return f"Error running '{name}': {exc}"

        text = result.output if isinstance(result, ToolResult) else str(result)
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"
        return text

    # -- path safety ------------------------------------------------------------
    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise PathEscapeError(f"'{relative_path}' resolves outside the project root ({self.root})")
        return candidate

    # -- built-in tools ---------------------------------------------------------
    def _register_builtin_tools(self) -> None:
        self.register("read_file", self.read_file, _schema(
            "read_file", "Read a UTF-8 text file from the project.",
            {"path": {"type": "string", "description": "Path relative to the project root."}},
            ["path"],
        ))
        self.register("write_file", self.write_file, _schema(
            "write_file", "Create or overwrite a file with the given content, creating parent directories as needed.",
            {
                "path": {"type": "string", "description": "Path relative to the project root."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            ["path", "content"],
        ))
        self.register("edit_file", self.edit_file, _schema(
            "edit_file",
            "Replace one exact, unique occurrence of `old_str` with `new_str` in a file. "
            "Prefer this over write_file for targeted edits to existing files.",
            {
                "path": {"type": "string"},
                "old_str": {"type": "string", "description": "Exact text to find (must appear exactly once)."},
                "new_str": {"type": "string", "description": "Replacement text."},
            },
            ["path", "old_str", "new_str"],
        ))
        self.register("list_directory", self.list_directory, _schema(
            "list_directory", "List files and directories at a path (one level deep).",
            {"path": {"type": "string", "description": "Path relative to project root. Defaults to '.'."}},
            [],
        ))
        self.register("grep_search", self.grep_search, _schema(
            "grep_search", "Search the project for a regex/text pattern, ripgrep-style.",
            {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Subdirectory to search. Defaults to '.'."},
                "glob": {"type": "string", "description": "Optional filename glob, e.g. '*.py'."},
            },
            ["pattern"],
        ))
        self.register("execute_bash", self.execute_bash, _schema(
            "execute_bash",
            "Run a shell command in the project root and return stdout/stderr. "
            f"Times out after {self.bash_timeout}s.",
            {"command": {"type": "string"}},
            ["command"],
        ))
        if _HAS_AIDER:
            self.register("repo_map", self.repo_map, _schema(
                "repo_map",
                "Get a ranked, token-budgeted map of the codebase (signatures of functions/classes "
                "across files) powered by Aider's repo-mapping engine. Call this first on unfamiliar "
                "codebases instead of reading files one by one.",
                {
                    "mentioned_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files especially relevant to the current task, ranked higher in the map.",
                    }
                },
                [],
            ))

    # -- implementations -----------------------------------------------------------
    def read_file(self, path: str) -> ToolResult:
        p = self._resolve(path)
        if not p.exists():
            return ToolResult(False, f"Error: '{path}' does not exist.")
        if p.is_dir():
            return ToolResult(False, f"Error: '{path}' is a directory, not a file.")
        data = p.read_bytes()[:MAX_READ_BYTES]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult(False, f"Error: '{path}' is not valid UTF-8 text (binary file?).")
        return ToolResult(True, text)

    def write_file(self, path: str, content: str) -> ToolResult:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        is_new = not p.exists()
        p.write_text(content, encoding="utf-8")
        verb = "Created" if is_new else "Overwrote"
        return ToolResult(True, f"{verb} {path} ({len(content)} bytes).")

    def edit_file(self, path: str, old_str: str, new_str: str) -> ToolResult:
        p = self._resolve(path)
        if not p.exists():
            return ToolResult(False, f"Error: '{path}' does not exist.")
        original = p.read_text(encoding="utf-8")
        count = original.count(old_str)
        if count == 0:
            return ToolResult(False, f"Error: old_str not found in '{path}'.")
        if count > 1:
            return ToolResult(False, f"Error: old_str appears {count} times in '{path}'; must be unique.")
        p.write_text(original.replace(old_str, new_str, 1), encoding="utf-8")
        return ToolResult(True, f"Edited {path}.")

    def list_directory(self, path: str = ".") -> ToolResult:
        p = self._resolve(path)
        if not p.exists():
            return ToolResult(False, f"Error: '{path}' does not exist.")
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = [f"{'📁' if e.is_dir() else '📄'} {e.name}" for e in entries]
        return ToolResult(True, "\n".join(lines) or "(empty directory)")

    def grep_search(self, pattern: str, path: str = ".", glob: Optional[str] = None) -> ToolResult:
        search_root = self._resolve(path)
        if shutil.which("rg"):
            cmd = ["rg", "--line-number", "--no-heading", "--color", "never", pattern, str(search_root)]
            if glob:
                cmd[1:1] = ["--glob", glob]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = proc.stdout or "(no matches)"
            return ToolResult(True, self._relativize(output))

        # Fallback: pure-python recursive grep when ripgrep isn't on PATH.
        import fnmatch
        import re

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(False, f"Error: invalid regex: {exc}")

        matches = []
        for file_path in search_root.rglob("*"):
            if not file_path.is_file():
                continue
            if glob and not fnmatch.fnmatch(file_path.name, glob):
                continue
            try:
                for i, line in enumerate(file_path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{file_path.relative_to(self.root)}:{i}:{line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
            if len(matches) > 500:
                break
        return ToolResult(True, "\n".join(matches) or "(no matches)")

    def execute_bash(self, command: str) -> ToolResult:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.bash_timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Error: command timed out after {self.bash_timeout}s.")
        parts = []
        if proc.stdout:
            parts.append(proc.stdout)
        if proc.stderr:
            parts.append(f"[stderr]\n{proc.stderr}")
        parts.append(f"[exit code {proc.returncode}]")
        return ToolResult(proc.returncode == 0, "\n".join(parts))

    def _relativize(self, text: str) -> str:
        return text.replace(str(self.root) + "/", "")

    def repo_map(self, mentioned_files: Optional[list[str]] = None) -> ToolResult:
        if not _HAS_AIDER:
            return ToolResult(False, "repo_map is unavailable: aider-chat is not installed.")

        if self._aider_repo_map is None:
            io = _AiderIO(pretty=False, yes=True)
            model = _AiderModel(self.repo_map_model)
            self._aider_repo_map = _AiderRepoMap(map_tokens=2048, root=str(self.root), main_model=model, io=io)

        other_files = [str(p) for p in self._walk_source_files()]
        mentioned_abs = [str(self._resolve(f)) for f in (mentioned_files or []) if _safe_relative(self, f)]

        result = self._aider_repo_map.get_repo_map([], other_files, mentioned_fnames=set(mentioned_abs))
        return ToolResult(True, result or "(repo map is empty — no recognized source files found)")

    def _walk_source_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if len(files) >= _MAX_REPO_MAP_FILES:
                break
            if not path.is_file():
                continue
            if any(part in _IGNORED_DIR_NAMES for part in path.relative_to(self.root).parts):
                continue
            files.append(path)
        return files


def _safe_relative(registry: "ToolRegistry", relative_path: str) -> bool:
    try:
        registry._resolve(relative_path)
        return True
    except PathEscapeError:
        return False


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Anthropic-style tool schema; litellm translates this per-provider as needed."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
