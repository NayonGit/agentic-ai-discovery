# Notes

## Workflows & Agents

A workflow is a system where my code defines the sequence of LLM calls and tool uses. An agent is a system where the LLM decides the next step and which tool to use, looping on feedback from its environment until it judges the task done. I choose a workflow when I can describe the steps in advance, and an agent when the path depends on what the task reveals along the way. Agents cost more and are less predictable, so I start with the simplest option that works.

## Treasure Hunt — my first agent loop

Built a tiny text-adventure (5 rooms) wired to 3 tools (`look_around`, `move`, `search_room`) and let Claude decide the whole exploration path itself — nothing in my code chose the order of actions, only the rules of the world.

What this made concrete:

- The model's only "sense" of the world is the text each tool returns. It has no access to my Python state, so it reconstructs everything from the conversation history each turn — the API is stateless, the full history gets resent every time.
- Termination was a judgment call, not a mechanism: the model recognized the "you win" message and stopped calling tools on its own. Nothing *forces* that — a real agent needs a hard cap (max turns / a budget) as a safety net, since the model's judgment alone is a soft guarantee.
- Prompt caching is what makes multi-turn loops affordable: in one run, only ~26 of the ~270k input tokens were freshly billed — the rest came straight from cache (the system prompt, tool defs, and prior turns are a stable prefix reused every turn).
- Runs are non-deterministic: same prompt, different number of turns, sometimes a different path (e.g. exploring a side room or not) and always different exact wording. Evaluating agents needs more than "run it once and look."
- `permission_mode` is a real safety control, not boilerplate. I had to explicitly set it to bypass approval for my own harmless tools — production agents should keep approval gates on for anything consequential (deleting files, spending money, sending messages).

Built on the Claude Agent SDK rather than the raw API, so it bills against my Claude Code subscription's rate-limit windows (5h / 7-day) instead of per-token API credits — trade-off being it also carries the full Claude Code harness overhead (its whole built-in toolset sits in the cached prefix too, bigger than what my 3 tools actually need). A live terminal dashboard (`rich`) shows the map, the agent's reasoning/tool calls, and that rate-limit usage as it happens, with a manual step-through pause since the loop otherwise finishes in well under a minute — too fast to actually read.

## Guardrails & cache reduction

Added `max_turns`/`max_budget_usd` as native SDK options rather than hand-rolling a counter — the SDK stops the loop itself (`ResultError` with `subtype == "error_max_turns"` / `"error_max_budget_usd"`) instead of me polling my own count against a limit. Forcing the caps low (`MAX_TURNS=3`, `MAX_BUDGET_USD=0.01`) is how I actually *saw* them trip — the default generous caps almost never fire naturally, so "it's implemented" and "I've seen it work" are different claims worth verifying separately.

Switched to `claude-sonnet-5` and stripped the Claude Code harness's own built-in tools/skills from context (`tools=[]`, `skills=[]`) since the game only needs its own 3 tools. Confirmed for real via a clean 1-turn A/B test: ~86% smaller fixed baseline (17k → 2.4k tokens) — a plausible-sounding fix isn't the same as a verified one; the full multi-turn runs still looked worse at first, which turned out to be a *different*, real bug (see below), not evidence the fix had failed.

**Bug: double-counting turns/tokens.** The SDK can split one API response into several `AssistantMessage` objects (a thinking-block message plus one per tool call) that all report the *same* usage — I was summing every one, inflating displayed turns and cache totals 2-3x. This is also what caused the earlier "Turns: 23/20 but no guardrail fired" mystery. Fixed by deduping on `message_id`.

**Open thread for later:** even after fixing the double-count, cache usage genuinely grows a lot across a run — not a bug, but the real cost of (a) resending the whole history every turn (stateless API) and (b) adaptive thinking generating real hidden reasoning tokens that join that history every turn. Tried `effort="low"` to shrink that — it broke caching outright (every turn paid full cache-write price, budget blown in 4 turns) for reasons I don't understand yet. Left alone on purpose rather than guessing further; worth a dedicated lesson on context management/compaction.

## Tool failure & recovery — the moral of this one

**What I wanted to implement:** a tool that fails like real ones do (a flaky API, a transient error), to see whether the agent notices an `is_error: true` result and recovers, instead of just assuming every tool call will succeed.

**What I tried:** made climbing the ladder (the only way to the treasure) fail deterministically on the first attempt and succeed on every attempt after — deterministic, not random, so the behavior is guaranteed to show up instead of hoping for it across lucky/unlucky runs. No hint anywhere in the system prompt that this would happen, so whatever the agent did next would be its own genuine judgment call. Then, as a second pass, changed *only* the wording of the failure message — nothing else — to compare two phrasings: one ambiguous about whether retrying would help, one explicitly suggesting it might.

**What I observed:** wording changed the behavior completely.
- Ambiguous message ("you slip and land back where you started") → the agent treated the path as closed. It explored the *entire rest of the map* before ever trying the ladder again.
- Explicit retry-hinting message ("worth trying again") → the agent retried on its *very next* action and succeeded immediately.

**What to conclude for real systems:** a tool error alone doesn't tell an agent whether the failure is worth retrying — that has to be designed into the error message on purpose, it isn't something the model can infer from `is_error: true` alone. Leave it ambiguous, and an agent can burn a lot of turns (and in a real system: money, time, or worse — side effects) avoiding something that would have worked on the second try. This makes error-message wording an actual design surface, not an afterthought, right alongside the tool's schema and description. It also only took one clean before/after comparison to see this clearly — but one run is a directional signal, not proof; a real decision would want this re-run enough times to be a pattern, not a fluke (same caveat as "runs are non-deterministic" above).

## Planning & multi-step dependencies — inconclusive, and that's the lesson

**What I wanted to implement:** a genuine prerequisite — locking the tower (the only way to the treasure) behind a key sitting in a side room — to see whether the agent, once blocked, recognizes *why* and plans a detour to go fetch what it's missing, instead of just reacting to immediate feedback.

**What I tried:** `move()` blocks entry to the tower unless `"a rusty key"` is already in the inventory, with a plain (non-error) message naming what's missing: *"The tower's heavy door is locked tight. It looks like it needs a key."* Verified the gating logic offline first (blocked without the key, succeeds with it) before spending any live run on it.

**What I observed:** in the one live run, the agent explored the garden — and picked up the key — *before* ever attempting the tower. The lock was never actually triggered; the prerequisite was satisfied proactively by thorough exploration, not through a "blocked, then go get it" planning moment.

**What to conclude:** this is a different shape of lesson than the guardrails or tool-failure stones, where forcing a low cap or a deterministic failure *guarantees* you see the mechanism fire. A dependency can't be guaranteed-observed the same way, because avoiding it entirely (by being thorough first) is just as valid a strategy as hitting it and recovering — and here, avoidance is what happened. That's worth remembering as its own point: you can't always assume a single run will exercise the capability you're trying to test, even when the code is correct. Whether a given planning capacity gets *exercised* depends on what order the agent happens to explore in, which is exactly the non-determinism noted in the first entry above. Forcing a guaranteed demonstration here would mean redesigning the map so the "wrong" path is obviously tried first — more engineering than this stone currently warrants, so left as option for later rather than chased further now.
