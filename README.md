# Semantics (`ctf`)

**Code that understands.**

An autonomous AI coding agent with a terminal experience built to match
Claude Code and OpenAI Codex, forked/extended from
[Aider](https://github.com/Aider-AI/aider). Open-core (BSD 2-Clause) agent
loop and tools; a Pro tier adds an Apple-inspired Textual TUI, browser
automation, MCP, and sub-agent fan-out.

![Semantics completion screen](docs/screenshots/completion-screen.png)

## Status: what's real here

This repo is a complete, working implementation of the architecture
below — not a mockup. Every module imports cleanly, the agent loop
actually calls a real (litellm-backed) LLM and executes real sandboxed
tools, the license system does real RSA-signed JWT verification, the
artifact builder produces real ZIPs, and the TUI is a real Textual app
(verified headless in `tests/test_tui.py`, including screenshot-level
checks — see `docs/screenshots/`). **44 tests, all passing.**

Two things are intentionally reference-quality rather than
production-hardened, and are called out inline in the code:

- **`repo_map`** (`core/tools.py`) is a genuine integration of Aider's
  real `RepoMap` engine — not a mock. It's the one piece of Aider that
  has a clean, stateless call signature; see "Why not subclass Aider's
  `Coder`?" below for why that's the integration point instead of
  inheritance.
- **`build/build.py`** and **`build/obfuscate.py`** (Nuitka + PyArmor)
  are correct, ready-to-run release scripts, but a full compile wasn't
  run as part of building this repo — it's a 10-20+ minute, multi-GB CI
  job (see `.github/workflows/build.yml`), not a dev-loop step.
- **`pro/pico.py`** (PicoClaw) speaks a defined stdin/stdout JSON
  protocol to an external Go binary that isn't included here (the design
  doc describes it as a separate build); the client raises a clear error
  if the binary isn't found rather than pretending to spawn one.

## Quickstart

```bash
git clone <this-repo> semantics && cd semantics
pip install -e .                    # core: agent loop + tools + CLI
pip install -e ".[pro,aider]"       # + TUI, browser, MCP, real Aider repo-map

cp .env.example .env                # then fill in SEMANTICS_API_KEY
export SEMANTICS_API_KEY=sk-...

# any litellm-supported provider works, including OpenRouter:
# export SEMANTICS_MODEL_NAME=openrouter/anthropic/claude-3.5-sonnet
# export SEMANTICS_API_KEY=sk-or-v1-...

ctf "Add a health check endpoint"          # Apple-level TUI (if pro installed + TTY)
ctf --no-tui "Add a health check endpoint" # plain-text mode (CI, pipes, --no-tui)
ctf --approve-plan "Refactor auth to JWT"  # pause for plan approval first
ctf --check-license --license "$KEY"       # validate a Pro license key
```

## Architecture

```
src/
├── core/            BSD 2-Clause — agent loop, tools, LLM client, config, context
│   ├── agent.py      SemanticsAgent.run_autonomous(): the tool-calling loop
│   ├── tools.py      ToolRegistry: read/write/edit/grep/bash (+ repo_map)
│   ├── llm.py        SemanticsLLM: litellm wrapper (OpenAI/Anthropic/Ollama/...)
│   ├── context.py    ContextManager: message log + token-budget summarization
│   └── config.py     SemanticsConfig: env-driven configuration
│
├── pro/              Proprietary (LICENSE.enterprise) — gated by license key
│   ├── artifact.py   ZIP packaging of a run's output
│   ├── license.py    Offline RS256 JWT license validation
│   ├── mcp.py        Model Context Protocol client
│   ├── browser.py    Playwright automation tool
│   ├── pico.py       PicoClaw sub-agent process integration
│   └── tui/          The Textual app: header, 5 phase views, styles.tcss
│
└── cli/main.py       `ctf` entry point (Typer)

tests/                44 tests: tools, context, agent loop, license, artifact,
                       config, and a headless Textual smoke test
tools/generate_license.py   Dev-only: generate a keypair, issue license keys
build/                Nuitka + PyArmor release pipeline
docs/                 api.md (developer reference), secret.md (🦑), screenshots/
```

### The agent loop

`SemanticsAgent.run_autonomous(task)` is a straightforward tool-calling
loop: ask the model for the next step, execute any tool calls it
requests, feed results back, repeat until it stops calling tools or
`max_iterations` is hit. It emits a typed `AgentEvent` stream
(`analyzing` → optionally `planning` → `executing` → `complete`/`error`)
that both the CLI's plain-text logger and the TUI consume — see
`docs/api.md` for the full event shape.

### Why not subclass Aider's `Coder`?

The original design sketch (and Aider's own README) suggests
`class SemanticsAgent(aider.coders.base_coder.Coder)`. In practice,
`Coder`'s constructor requires a live `Model` + `InputOutput`, its
factory (`Coder.create()`) is the real entry point, and it owns an
edit-application pipeline that parses SEARCH/REPLACE blocks out of
free-form model text — a different (and older) mechanism than function
/ tool calling. Fighting that to make it emit structured tool calls
instead would mean reimplementing most of `Coder` anyway.

So `SemanticsAgent` composes an `LLM` + `ToolRegistry` on its own, and
reuses Aider surgically where it *does* have a clean, stateless entry
point: `aider.repomap.RepoMap.get_repo_map()`, wired in as the optional
`repo_map` tool. That's a real dependency on real Aider code, just not
an inheritance relationship. This is documented in the module docstring
of `core/agent.py` for anyone extending it further.

## The five TUI screens

`pro/tui/app.py` drives five phase views off the agent's event stream —
startup (gradient wordmark via pyfiglet), analysis, planning
(interactive Accept/Modify/Cancel/Show-diff, only shown with
`--approve-plan`), execution (one live progress row per tool call), and
completion (summary report + artifact path). Colors are the palette from
the design doc (`pro/tui/colors.py`), enforced via `styles.tcss`.

## Testing

```bash
pip install -e ".[dev,pro,aider]"
pytest tests/ -v
```

All 44 tests run without a real API key or network access — the LLM is
mocked at the `SemanticsLLM.chat()` boundary (see `tests/test_agent.py`'s
`FakeLLM`), so the tool-calling loop, context management, licensing, and
TUI are all exercised deterministically.

## Licensing (Pro)

```bash
python tools/generate_license.py init-keys           # once, keep the private key secret
python tools/generate_license.py issue --to "you" --days 365
ctf --check-license --license "<token>"
```

`src/pro/license.py` does offline RS256 JWT verification against a
bundled public key — no phone-home required. `src/core` and `src/cli`
are BSD 2-Clause (`LICENSE`); `src/pro` is proprietary (`LICENSE.enterprise`).
Per the design doc's scope, there's intentionally no RBAC, SSO, or audit
logging — Pro/Enterprise here means the TUI + browser + MCP + sub-agent
tools plus seat count, not an access-control tier.

## Docker

```bash
docker build -t semantics .                         # core only
docker build -t semantics --build-arg INSTALL_PRO=1 .  # + TUI/browser/MCP
docker run -it --rm -v "$PWD":/workspace -e SEMANTICS_API_KEY semantics "add tests"
```
