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
and tool calls, and subscription usage as it happens. The hunt pauses after
every tool call so you can read each step — press Enter to advance.

```bash
uv run treasure-hunt
```

### Guardrails

The loop is capped by `max_turns` (20) and `max_budget_usd` ($0.50, a notional
cost figure the SDK tracks internally — not a real charge under subscription
billing) so an agent that never converges can't run forever. Both are
generous enough that a normal hunt always finishes comfortably — to see a
guardrail actually trip:

```bash
MAX_TURNS=3 uv run treasure-hunt        # hits the turn cap almost immediately
MAX_BUDGET_USD=0.01 uv run treasure-hunt  # hits the budget cap after turn 1
```

The map also has a loop (garden ↔ tower) and a decoy clue (the courtyard's
map fragment falsely points to the fountain) so a normal run isn't always the
same short, straight path.
