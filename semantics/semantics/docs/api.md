# Semantics — internal API reference

This documents the Python API surface under `src/`, for anyone embedding
`SemanticsAgent` in their own tooling rather than using the `ctf` CLI.

## Quick start

```python
from core.config import load_config
from core.llm import SemanticsLLM
from core.tools import ToolRegistry
from core.agent import SemanticsAgent

cfg = load_config(project_root=".", model_name="anthropic/claude-sonnet-4-6")
cfg.validate()

llm = SemanticsLLM(model_name=cfg.model_name, api_key=cfg.api_key)
tools = ToolRegistry(root=cfg.project_root, bash_timeout=cfg.bash_timeout_seconds)
agent = SemanticsAgent(llm=llm, tools=tools, max_iterations=cfg.max_iterations)

import asyncio
result = asyncio.run(agent.run_autonomous("Add input validation to the signup form"))
print(result)
```

## `core.config.SemanticsConfig`

Environment-driven config (12-factor style). See `.env.example` for every
variable. `load_config(**overrides)` builds one from the environment and
applies keyword overrides (e.g. CLI flags). Call `.validate()` before use.

## `core.llm.SemanticsLLM`

Thin async wrapper around [litellm](https://docs.litellm.ai/) — the same
library Aider uses internally — so any provider litellm supports works
here: `"anthropic/claude-sonnet-4-6"`, `"openai/gpt-5"`,
`"ollama/qwen2.5-coder"`, `"openrouter/..."`, etc.

```python
response = await llm.chat(messages, tools=tool_schemas)
response.content        # str
response.tool_calls     # list[ToolCall(id, name, arguments)]
response.total_tokens   # int
```

## `core.tools.ToolRegistry`

Sandboxed (path-escape-safe) tool implementations, exposed as
function-calling schemas via `.get_schemas()` and invoked via
`.execute(name, arguments) -> str`.

| Tool | Description |
|---|---|
| `read_file` | Read a UTF-8 text file. |
| `write_file` | Create/overwrite a file. |
| `edit_file` | Unique-match find/replace (prefer this for existing files). |
| `list_directory` | One level of a directory listing. |
| `grep_search` | ripgrep if available, pure-Python fallback otherwise. |
| `execute_bash` | Run a shell command with a timeout. |
| `repo_map` *(optional)* | Aider's real repo-mapping engine — only registered when `aider-chat` is installed. |

All filesystem tools reject paths that resolve outside `ToolRegistry.root`.

## `core.agent.SemanticsAgent`

```python
async def run_autonomous(
    self,
    task: str,
    on_event: Callable[[AgentEvent], Awaitable[None] | None] | None = None,
    approval_gate: Callable[[], Awaitable[bool]] | None = None,
) -> str: ...
```

Runs a tool-calling loop for up to `max_iterations` turns. Emits
`AgentEvent(phase, message, iteration, tokens_used, elapsed, extra)` for
every state transition — `Phase.ANALYZING`, `Phase.PLANNING` (only if
`approval_gate` is given), `Phase.EXECUTING` (with `extra["stage"]` in
`{"thinking", "start", "end"}` for each tool call), `Phase.COMPLETE`, or
`Phase.ERROR`. `pro.tui.app.SemanticsApp` is the reference consumer of
this event stream — see it for a complete worked example.

**Why `SemanticsAgent` doesn't subclass Aider's `Coder`:** see the module
docstring in `core/agent.py`. Short version: `Coder`'s constructor and
edit-application pipeline assume it owns the whole interactive loop and
parses free-form SEARCH/REPLACE text; that doesn't compose with a
tool-calling loop. Instead, Aider is reused where it *does* have a clean,
stateless entry point — its `RepoMap` — via the `repo_map` tool above.

## `pro.artifact.ArtifactBuilder`

```python
with ArtifactBuilder() as builder:
    builder.add_file("src/app.py", content)
    builder.add_manifest(ArtifactManifest(task=..., files_changed=[...]))
    zip_path = builder.build_zip("out.zip")
```

## `pro.license`

`validate_license(key, public_key_pem=None) -> (bool, License | str)`.
Offline RS256 JWT verification against a bundled public key — see
`tools/generate_license.py` for issuing keys (dev-only; never ships the
private key).

## `pro.mcp.MCPClient`

```python
async with MCPClient() as mcp:
    await mcp.connect_server(MCPServerConfig(name="fs", command="npx", args=[...]))
    result = await mcp.call_tool("fs.read_file", {"path": "x"})
```

## `pro.tui.app.SemanticsApp`

The Textual application. `SemanticsApp(agent, task, require_plan_approval=False).run()`
drives the five phase views (`startup`, `analysis`, `planning`,
`execution`, `completion`) directly off `AgentEvent`s.
