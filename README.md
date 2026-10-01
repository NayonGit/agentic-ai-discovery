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

### Tool failure & recovery

Climbing the ladder (tower → attic, the only way to the treasure) fails
deterministically on the first attempt with a proper `is_error: true` tool
result, then succeeds on every attempt after — deterministic rather than
random, so the behavior is guaranteed to show up instead of depending on
chance. No hint in the system prompt, to see genuine, unprompted recovery.

The exact wording of that error message turned out to change the agent's
behavior completely: an ambiguous failure ("you slip and land back where you
started") led it to explore the entire rest of the map before trying the
ladder again, while an explicit retry hint ("worth trying again") led it to
retry on the very next action. See `NOTES.md` for the full writeup.

### Planning & multi-step dependencies

The tower is locked unless the rusty key (sitting in the garden, a side room)
is already in the inventory — a genuine prerequisite rather than a one-shot
failure. In the one live run so far, the agent explored the garden and
picked up the key before ever trying the tower, so the lock was never
actually triggered — an inconclusive result in itself worth reading about in
`NOTES.md`, since it's not the same kind of lesson as the guardrail or
tool-failure stones above. (A later run did trigger it, and recovered
correctly — see the update in `NOTES.md`.)

### Replay visualizer

Every run can save a structured JSON transcript (`TRANSCRIPT_FILE=path uv run
treasure-hunt`) — the map, every tool call/result, reasoning text, token
usage, and rate-limit snapshots, in order. `transcripts/showcase.json` is one
such recording, replayed by a standalone Artifact ("The Estate Expedition"):
a hand-drawn-style map with an animated position marker, a field-journal log
of the agent's actions, and a ledger of token/rate-limit stats, with
play/pause/step/scrubber controls. Built to iterate on the visuals for free
against one real recording, instead of spending live runs on UI polish.

`transcripts/` keeps one recording per stone below, named to match its
`NOTES.md` section, so each lesson has a real run to replay, not just prose.
