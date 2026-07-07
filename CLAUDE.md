# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

The OpenHands Software Agent SDK is a Python monorepo for building coding agents. It is
the engine behind the OpenHands CLI, OpenHands Cloud, and other downstream client apps —
see CONTRIBUTING.md for the architectural principle this implies: **the SDK must stay
client-agnostic**. Don't add logic that special-cases a particular downstream app, and
prefer extensible interfaces over one-off patches.

An extremely detailed `AGENTS.md` already exists at the repo root (and per-package, e.g.
`openhands-sdk/openhands/sdk/AGENTS.md`, `openhands-tools/openhands/tools/AGENTS.md`,
`openhands-workspace/openhands/workspace/AGENTS.md`, `openhands-agent-server/AGENTS.md`).
**Read the relevant AGENTS.md file(s) for any package you touch** — they contain
authoritative, load-bearing rules (backward-compatibility policies, deprecation runways,
testing conventions, known races) that are not repeated here.

## Common commands

```bash
make build                               # uv sync --dev + install pre-commit hooks (run this first)
make format                              # uv run ruff format
make lint                                # uv run ruff check --fix
uv run pre-commit run --files <path>     # run pre-commit (lint + pyright) on files you changed — do this after editing any file
uv run pre-commit run --all-files        # run all pre-commit checks

uv run pytest                            # full test suite (stress tests excluded by default)
uv run pytest tests/sdk/                 # SDK package tests
uv run pytest tests/tools/               # tools package tests
uv run pytest tests/workspace/           # workspace package tests
uv run pytest tests/agent_server/        # agent-server tests
uv run pytest tests/sdk -k <pattern>     # targeted run, e.g. a single test/module
uv run pytest -m stress                  # opt-in agent-server stress/scale suite

make build-server                        # build agent-server executable via PyInstaller -> dist/agent-server/
make test-server-schema                  # generate + validate the agent-server OpenAPI schema
make clean                               # clear caches (__pycache__, .pytest_cache, .ruff_cache, .mypy_cache)
```

- Requires `uv >= 0.8.13`. Type checking uses **pyright** — never mypy.
- Only commit the specific files you changed, not `git add -A`/`.`.
- Ruff config: line length 88, target `py313` (see `pyproject.toml`).

## Architecture

This is a `uv` workspace (single root `uv.lock`) with four publishable packages plus
tests/examples:

- **`openhands-sdk/`** (`openhands.sdk.*`) — the core, dependency-light SDK. No knowledge
  of Docker, remote servers, or specific client apps lives here.
- **`openhands-tools/`** (`openhands.tools.*`) — built-in tool implementations (terminal,
  file_editor, browser_use, grep, glob, task_tracker, apply_patch, etc.). Each tool
  typically splits `definition.py` (schema/metadata) from `impl.py`/`core.py` (runtime).
- **`openhands-workspace/`** (`openhands.workspace.*`) — concrete workspace backends
  (docker, apptainer, cloud, remote_api) implementing the SDK's workspace interfaces.
- **`openhands-agent-server/`** — a FastAPI REST/WebSocket server that exposes the SDK
  for remote/ephemeral execution. Routers live at the top level (e.g.
  `conversation_router.py`, `bash_router.py`, `event_router.py`), each paired with a
  `*_service.py`.

### Core SDK concepts (`openhands-sdk/openhands/sdk/`)

- **`agent/`** — `Agent`/`AgentBase` decide what to do next given conversation state; they
  call the LLM and dispatch tool calls (`agent.py`, `base.py`, `response_dispatch.py`).
- **`conversation/`** — orchestrates the agent loop and holds `ConversationState`.
  `conversation/impl/local_conversation.py` runs the loop in-process;
  `conversation/impl/remote_conversation.py` drives a remote agent-server over
  HTTP/WebSocket. Every async method (`arun`, `astep`, `acompletion`, etc.) has a sync
  counterpart, and base classes default to delegating sync so subclasses work either way.
- **`llm/`** — `LLM` wraps litellm (`acompletion`/`aresponses`) with retry
  (`RetryMixin`/tenacity), fallback strategies, and provider-specific quirks. Prefer
  encoding model/provider capability differences in `llm/utils/model_features.py` rather
  than branching in `llm.py` directly.
- **`tool/`** — `Tool`/`ToolDefinition` schema and the tool `registry.py`, which handles
  usability filtering (`list_usable_tools()`) while preserving registration order.
- **`event/`** — the event schema that gets persisted and streamed (`LLMConvertibleEvent`,
  `MessageEvent`, `HookExecutionEvent`, etc.). These are Pydantic models whose backward
  compatibility is a hard requirement — old persisted conversations must always load; see
  the deprecation pattern in the SDK AGENTS.md before removing/renaming any event field.
  `LLMConvertibleEvent`s are what actually cross the LLM boundary.
- **`context/`** — `AgentContext`, prompt building, condensers (context truncation
  strategies), and the skills system (`AgentSkills` progressive disclosure into
  `<available_skills>`).
- **`workspace/`** — the SDK-side workspace interfaces (`RemoteWorkspace`, `TargetType`,
  `PlatformType`, etc.) that `openhands-workspace/` backends implement.
- **`settings/`** — programmatic agent/conversation settings (`AgentSettings`,
  `ConversationSettings`, `export_settings_schema()`). This is the canonical structured
  settings surface; keep it neutral (no client-specific ordering/icons/widgets).
- **`hooks/`, `mcp/`, `plugin/`, `skills/`, `subagent/`, `security/`, `critic/`** — hook
  execution around agent steps, MCP client/tool integration, conversation plugins
  (lazy-loaded on first `send_message()`/`run()`), skills marketplace, sub-agent
  delegation, security analyzers, and critic-model scoring, respectively.

### Data flow at a glance

`Conversation` (local or remote) holds `ConversationState` (a list of persisted `Event`s).
Each turn: `Agent.step()`/`astep()` reads state → calls `LLM.completion()`/`acompletion()`
(with retry) → interprets tool calls via the `tool` registry → appends new events → the
loop continues until the agent finishes, is interrupted, or hits a stop hook. The
agent-server exposes this same loop remotely, mirroring each SDK concept with a REST
router + `*_service.py` (e.g. `EventService`, `ConversationService`) and WebSocket
push for live events.

## Testing conventions

- Put unit tests under the matching domain folder in `tests/` (`tests/sdk`, `tests/tools`,
  `tests/workspace`, `tests/agent_server`), mirroring the source path — e.g.
  `openhands-sdk/openhands/sdk/tool/tool.py` → `tests/sdk/tool/test_tool.py`.
- Don't write test classes unless truly necessary; don't over-test — cover edge cases,
  not every permutation.
- Shared mock/fixture setup belongs in `conftest.py`, not duplicated per test.
- `tests/agent_server/stress/` is an opt-in, in-process scale suite (`pytest -m stress`);
  see `openhands-agent-server/AGENTS.md` for fixtures and how to add a new stress test.
- `tests/integration/` contains behavior tests (`b##_*`, agent behavior in realistic
  scenarios) and functional tests (`t##_*`); see `tests/integration/BEHAVIOR_TESTS.md`
  before adding to either.

## Compatibility policies (read before touching public surfaces)

- **SDK public API** (`openhands.sdk.__all__`): removals require deprecation via
  `openhands.sdk.utils.deprecation` with a removal target at least 5 minor releases after
  `deprecated_in`, and any breaking change needs at least a MINOR version bump.
- **Agent-server REST API**: backward compatible across releases; deprecate endpoints with
  `deprecated=True` plus a docstring note, and keep old contracts alive for 5 minor
  releases before removal (see `openhands-agent-server/AGENTS.md` for exact wording CI
  checks for).
- **Persisted settings/events**: bump the relevant `schema_version`, add a migration
  function, and add a golden fixture under `tests/sdk/persisted_settings_baselines/vN/`
  when changing any persisted shape.

Both are enforced by CI scripts (`check_sdk_api_breakage.py`,
`.github/scripts/check_persisted_settings_compat.py`, the agent-server OpenAPI diff
workflow), so check the relevant AGENTS.md before removing or restructuring anything
public.
