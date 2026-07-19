# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

"""`ctf` — the Semantics command-line entry point.

    ctf "Refactor the authentication module to use JWT"
    ctf --no-tui "Add a health check endpoint"
    ctf --model openai/gpt-5 "Write unit tests for utils.py"
    ctf license issue --to "acme-corp"          # Pro: see tools/generate_license.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from core.agent import AgentEvent, Phase, SemanticsAgent
from core.config import load_config
from core.llm import SemanticsLLM
from core.tools import ToolRegistry

app = typer.Typer(
    name="ctf",
    help="Semantics — code that understands.",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()

__version__ = "2.0.0"


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"Semantics (ctf) v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    task: Optional[str] = typer.Argument(None, help="What should the agent do?"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="e.g. anthropic/claude-sonnet-4-6, openai/gpt-5, openrouter/anthropic/claude-3.5-sonnet"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="SEMANTICS_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    project_root: Path = typer.Option(Path("."), "--dir", help="Project root to operate in."),
    max_iterations: int = typer.Option(25, "--max-iterations"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Plain-text mode (also used automatically outside a TTY)."),
    approve_plan: bool = typer.Option(False, "--approve-plan", help="Pause for plan approval before editing files."),
    license_key: Optional[str] = typer.Option(None, "--license", envvar="SEMANTICS_LICENSE_KEY"),
    check_license: bool = typer.Option(False, "--check-license", help="Validate the configured Pro license and exit."),
    explain: bool = typer.Option(False, "--explain", help="Print the full tool-call trace after the run."),
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    # NB: `license` is a --flag rather than a `ctf license ...` subcommand on
    # purpose — Click resolves a group's own positional arguments (`task`,
    # here) *before* subcommand dispatch, so a bare positional at the top
    # level makes any sibling subcommand name ambiguous with a task string.
    if check_license:
        _print_license_status(license_key)
        raise typer.Exit()

    if not task:
        console.print(Panel.fit(main.__doc__ or "", title="Semantics", border_style="#0a84ff"))
        raise typer.Exit()

    cfg = load_config(
        model_name=model,
        api_key=api_key,
        base_url=base_url,
        project_root=project_root.resolve(),
        max_iterations=max_iterations,
        license_key=license_key,
    )
    try:
        cfg.validate()
    except ValueError as exc:
        console.print(f"[bold #ff453a]Error:[/bold #ff453a] {exc}")
        raise typer.Exit(code=1)

    llm = SemanticsLLM(model_name=cfg.model_name, api_key=cfg.api_key, base_url=cfg.base_url)
    tools = ToolRegistry(root=cfg.project_root, bash_timeout=cfg.bash_timeout_seconds)
    agent = SemanticsAgent(llm=llm, tools=tools, max_iterations=cfg.max_iterations)

    use_tui = cfg.use_tui and not no_tui and sys.stdout.isatty()

    if use_tui:
        _run_tui(agent, task, require_plan_approval=approve_plan)
    else:
        _run_headless(agent, task, explain=explain)


def _run_tui(agent: SemanticsAgent, task: str, require_plan_approval: bool) -> None:
    from pro.tui.app import SemanticsApp  # imported lazily: textual is a Pro/TUI-only dependency

    app_instance = SemanticsApp(agent=agent, task=task, require_plan_approval=require_plan_approval)
    app_instance.run()


def _run_headless(agent: SemanticsAgent, task: str, explain: bool) -> None:
    """Plain rich-console output — used in CI, pipes, and with --no-tui."""
    trace: list[str] = []
    start = time.monotonic()

    def on_event(event: AgentEvent) -> None:
        icon = {
            Phase.ANALYZING: "🔍",
            Phase.PLANNING: "📋",
            Phase.EXECUTING: "🚀",
            Phase.COMPLETE: "✅",
            Phase.ERROR: "❌",
        }.get(event.phase, "•")
        line = f"{icon} [{event.phase.value}] {event.message}"
        trace.append(line)
        console.print(line)

    console.print(Panel.fit(f"[b]{task}[/b]", title="◉ Semantics", border_style="#0a84ff"))
    result = asyncio.run(agent.run_autonomous(task, on_event=on_event))
    elapsed = time.monotonic() - start

    console.print(Panel.fit(result or "(no output)", title="Result", border_style="#30d158"))
    console.print(
        f"[#86868b]⏱ {elapsed:.1f}s  ·  🧠 {agent.context.total_tokens_used:,} tokens  ·  "
        f"🤖 {agent.llm.model}[/#86868b]"
    )
    if explain:
        console.print(Panel("\n".join(trace), title="Full trace", border_style="#5e5ce6"))


def _print_license_status(license_key: Optional[str]) -> None:
    from pro.license import validate_license

    ok, result = validate_license(license_key or "")
    if ok:
        console.print(f"[#30d158]✅ {result.summary()}[/#30d158]")
    else:
        console.print(f"[#ff453a]❌ {result}[/#ff453a]")
        raise typer.Exit(code=1)


def entrypoint() -> None:
    app()


if __name__ == "__main__":
    entrypoint()
