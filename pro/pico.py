"""PicoClaw sub-agent integration (Pro tool).

PicoClaw is a lightweight (<10MB RSS) Go binary that runs a focused,
single-purpose sub-agent in its own process — used for fan-out work
(e.g. "run this same refactor check across 12 microservices") without
paying the memory/context cost of spinning up 12 full Python agents.

This module speaks a tiny line-delimited JSON protocol over stdin/stdout
to whatever binary `pico_binary_path` points at. It does not vendor or
assume a specific PicoClaw build — set `SEMANTICS_PICO_BINARY` (or pass
`pico_binary_path`) to wherever your build lives.

Protocol (v1):
  -> stdin:  {"task": "...", "cwd": "...", "context": {...}}\n
  <- stdout: {"status": "ok" | "error", "result": "...", "detail": "..."}\n
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .license import require_license


class PicoError(RuntimeError):
    pass


@dataclass
class PicoResult:
    ok: bool
    result: str
    detail: Optional[str] = None


class PicoClient:
    """Spawns a PicoClaw sub-agent process for one task and collects its result."""

    def __init__(self, binary_path: Optional[str] = None, timeout: int = 120) -> None:
        self.binary_path = binary_path or os.getenv("SEMANTICS_PICO_BINARY", "picoclaw")
        self.timeout = timeout

    def is_available(self) -> bool:
        return shutil.which(self.binary_path) is not None or Path(self.binary_path).exists()

    @require_license("spawn_subagent")
    async def spawn(self, task: str, cwd: Optional[str] = None, context: Optional[dict[str, Any]] = None) -> PicoResult:
        if not self.is_available():
            raise PicoError(
                f"PicoClaw binary not found at '{self.binary_path}'. Set SEMANTICS_PICO_BINARY "
                "to point at your build, or skip spawn_subagent for this task."
            )

        payload = json.dumps({"task": task, "cwd": cwd or ".", "context": context or {}}) + "\n"

        proc = await asyncio.create_subprocess_exec(
            self.binary_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload.encode("utf-8")), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise PicoError(f"PicoClaw sub-agent timed out after {self.timeout}s.")

        if proc.returncode != 0:
            return PicoResult(ok=False, result="", detail=stderr.decode("utf-8", "ignore"))

        try:
            data = json.loads(stdout.decode("utf-8").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return PicoResult(ok=False, result="", detail=f"Malformed PicoClaw output: {stdout!r}")

        return PicoResult(ok=data.get("status") == "ok", result=data.get("result", ""), detail=data.get("detail"))
