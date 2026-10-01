# Notes

## Workflows & Agents

A workflow is a system where my code defines the sequence of LLM calls and tool uses. An agent is a system where the LLM decides the next step and which tool to use, looping on feedback from its environment until it judges the task done. I choose a workflow when I can describe the steps in advance, and an agent when the path depends on what the task reveals along the way. Agents cost more and are less predictable, so I start with the simplest option that works.

## Treasure Hunt — my first agent loop

Built a tiny text-adventure (5 rooms) wired to 3 tools (`look_around`, `move`, `search_room`) and let Claude decide the whole exploration path itself — nothing in my code chose the order of actions, only the rules of the world.

What this made concrete:

- The model's only "sense" of the world is the text each tool returns. It has no access to my Python state, so it reconstructs everything from the conversation history each turn — the API is stateless, the full history gets resent every time.
- Termination was a judgment call, not a mechanism: the model recognized the "you win" message and stopped calling tools on its own. Nothing *forces* that — a real agent needs a hard cap (max turns / a budget) as a safety net, since the model's judgment alone is a soft guarantee. I don't have one yet — that's the next thing to add.
- Prompt caching is what makes multi-turn loops affordable: in one run, only ~26 of the ~270k input tokens were freshly billed — the rest came straight from cache (the system prompt, tool defs, and prior turns are a stable prefix reused every turn).
- Runs are non-deterministic: same prompt, different number of turns, sometimes a different path (e.g. exploring a side room or not) and always different exact wording. Evaluating agents needs more than "run it once and look."
- `permission_mode` is a real safety control, not boilerplate. I had to explicitly set it to bypass approval for my own harmless tools — production agents should keep approval gates on for anything consequential (deleting files, spending money, sending messages).

Built on the Claude Agent SDK rather than the raw API, so it bills against my Claude Code subscription's rate-limit windows (5h / 7-day) instead of per-token API credits — trade-off being it also carries the full Claude Code harness overhead (its whole built-in toolset sits in the cached prefix too, bigger than what my 3 tools actually need). A live terminal dashboard (`rich`) shows the map, the agent's reasoning/tool calls, and that rate-limit usage as it happens, with a manual step-through pause since the loop otherwise finishes in well under a minute — too fast to actually read.
