# agentic-ai-discovery

Exploring agentic AI: measuring what autonomous LLM agents actually cost vs. the value they deliver.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in your ANTHROPIC_API_KEY
```

## Run

```bash
uv run agentic-ai-discovery
```

## Treasure hunt (agent loop demo)

A tiny text-adventure where Claude explores a 5-room map, picks tools (`look_around`,
`move`, `search_room`), and loops on the results until it finds the treasure.

Runs on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python.md)
instead of the raw API, so it bills against your Claude Code subscription's
rate limits rather than separate API credits. Requires the `claude` CLI logged in
(`claude setup-token` if running non-interactively) — no `ANTHROPIC_API_KEY` needed.

A live terminal dashboard (`rich`) shows the map, the agent's running commentary
and tool calls, and token/cost usage as it happens.

```bash
uv run treasure-hunt
```
