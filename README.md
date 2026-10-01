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

### Cache footprint

Runs on `claude-sonnet-5` rather than Opus, and strips the Claude Code harness's
own built-in tools/skills/project settings from context (`tools=[]`, `skills=[]`)
since the game only uses its own 3 MCP tools — none of that is needed here, and
by default it all rides along in the cached prefix on every turn. Verified with
a 1-turn run: cache footprint dropped from ~17,000 to ~2,400 tokens (~86%).

Note: `setting_sources=[]` (full SDK isolation mode) looked like a natural
fourth lever here, but it silently breaks prompt caching — every turn pays
full cache-write price instead of reading the prior one back. Left unset on
purpose.

The dashboard's turn/token counters are deduplicated by `message_id`: the SDK
can split one API response into several `AssistantMessage` objects (e.g. a
thinking-block message plus a separate message per tool call) that all report
the *same* usage, so summing every message double- or triple-counted real
turns. Fixed by only counting the first message seen per `message_id`.

The cached-prefix reduction above is real and confirmed, but it only shrinks
the *fixed* per-turn baseline — it does nothing about the *growing* cost
across a run (each turn resends the full history, and adaptive thinking adds
real hidden reasoning tokens to that history every turn). That part is an
open thread for a future lesson, not yet addressed here.
