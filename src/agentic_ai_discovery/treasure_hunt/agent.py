import asyncio
import os

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    RateLimitEvent,
    ResultError,
    ResultMessage,
    query,
)

from .dashboard import Dashboard
from .recorder import TranscriptRecorder
from .tools import ALLOWED_TOOLS, FORCE_DOOR_TOOL, build_game_server
from .world import ROOMS

SYSTEM_PROMPT = """You are an explorer in a small text-based treasure hunt.
Use the tools to look around, move between rooms, and search for hidden items.
Explore methodically until you find the treasure, then report that you've won."""

MODEL = os.environ.get("MODEL", "claude-sonnet-4-5-20250929")

# Switched the default model from Sonnet 5 to Sonnet 4.5: on the identical
# vault puzzle, both solve it correctly every time (no wrong code attempts
# in any trial), but Sonnet 4.5 reliably needs more turns and cost to get
# there - a real, measured efficiency gap without resorting to a much
# smaller model (Haiku 4.5 solves it too, but via visibly aimless
# backtracking - a confound we'd rather not introduce yet). See NOTES.md.
#
# Recalibrated from a clean, uncapped run (42 turns / $2.06) - comfortable
# headroom above that, same margin style as every earlier calibration. To
# see the guardrails actually trip, force them low:
#   MAX_TURNS=3 uv run treasure-hunt
#   MAX_BUDGET_USD=0.01 uv run treasure-hunt
DEFAULT_MAX_TURNS = 55
DEFAULT_MAX_BUDGET_USD = 2.75


async def run_treasure_hunt(interactive: bool = True) -> dict:
    """The agent loop, run by the Claude Agent SDK: it calls the model, runs
    whichever tool it picks against our in-memory World, feeds the result
    back, and repeats until the model decides the hunt is over — or until a
    guardrail (max turns / max budget) cuts it off first. A live dashboard
    shows the map, the agent's running commentary, and how much of the
    subscription's rate-limit windows this run is using (unless
    interactive=False, e.g. unattended evaluation runs). If TRANSCRIPT_FILE
    is set, the whole run is also saved as a replayable JSON transcript.

    Returns a summary dict: outcome, total_turns, total_cost_usd, the
    cumulative token/cache figures, and how many times the SDK's own
    auto-compaction fired (PreCompact hook) - for the evaluation harness to
    collect across many runs without needing to re-read a saved transcript
    file."""
    max_turns = int(os.environ.get("MAX_TURNS", DEFAULT_MAX_TURNS))
    max_budget_usd = float(os.environ.get("MAX_BUDGET_USD", DEFAULT_MAX_BUDGET_USD))

    dashboard = Dashboard(
        room_names=list(ROOMS.keys()), max_turns=max_turns, max_budget_usd=max_budget_usd, interactive=interactive
    )
    recorder = TranscriptRecorder(start_room="entrance", max_turns=max_turns, max_budget_usd=max_budget_usd, model=MODEL)
    outcome = "unknown"
    final_cost: float | None = None
    compactions = 0

    # Unset (default) leaves the SDK's own auto-compact threshold in place —
    # on a short hunt like this, context usage may never cross it. Set a low
    # token count (minimum 100_000, per the CLI) to force compaction to
    # actually happen within a normal run, so its effect can be observed and
    # measured instead of assumed.
    autocompact = os.environ.get("AUTOCOMPACT")
    extra_args = {"autocompact": autocompact} if autocompact else {}

    with dashboard:
        server, world = build_game_server(dashboard, recorder)
        dashboard.set_room(world.current_room, world.current_room_description, world.current_room_exits)

        async def log_compaction(hook_input, tool_use_id, context):
            nonlocal compactions
            compactions += 1
            trigger = hook_input.get("trigger", "unknown")
            dashboard.log(f"📦 Context compacted ({trigger})")
            recorder.compact(trigger)
            return {}

        async def gate_force_door(hook_input, tool_use_id, context):
            if hook_input.get("tool_name") != FORCE_DOOR_TOOL:
                return {}  # not our concern - let normal permission rules apply

            approved = await dashboard.ask_approval(
                "\n⚠️  The agent wants to force the tower door open (risky, irreversible). Approve? [y/N] "
            )
            note = "approved by the user" if approved else "denied by the user"
            dashboard.log(f"{'✅' if approved else '🚫'} force_door request {note}")
            recorder.approval("force_door", approved, note)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow" if approved else "deny",
                    "permissionDecisionReason": note,
                }
            }

        options = ClaudeAgentOptions(
            model=MODEL,
            tools=[],  # no built-in Claude Code tools (Bash, Read, Edit, ...) — only our 3 MCP tools
            skills=[],  # don't load the host's personal Claude Code skills into this game's context
            mcp_servers={"treasure_hunt": server},
            allowed_tools=ALLOWED_TOOLS,  # force_door is deliberately excluded - gated via the hook below
            permission_mode="bypassPermissions",
            hooks={
                "PreToolUse": [HookMatcher(hooks=[gate_force_door])],
                "PreCompact": [HookMatcher(hooks=[log_compaction])],
            },
            system_prompt=SYSTEM_PROMPT,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            extra_args=extra_args,
        )

        # The SDK can split one API response into several AssistantMessage
        # objects (e.g. a ThinkingBlock message plus one ToolUseBlock message
        # per tool call) that all carry the SAME response-level `usage` —
        # dedupe by message_id so each real turn is only counted once.
        seen_message_ids: set[str] = set()

        try:
            async for message in query(
                prompt="Begin exploring. Find the treasure.",
                options=options,
            ):
                if isinstance(message, AssistantMessage):
                    if message.usage and message.message_id not in seen_message_ids:
                        seen_message_ids.add(message.message_id)
                        dashboard.add_turn_usage(message.usage)
                        recorder.usage(message.usage)
                    for block in message.content:
                        if getattr(block, "text", None):
                            dashboard.log(f"🧭 {block.text}")
                            recorder.text(block.text)
                elif isinstance(message, RateLimitEvent):
                    dashboard.update_rate_limits(message.rate_limit_info.raw)
                    recorder.rate_limit(message.rate_limit_info.raw)
                elif isinstance(message, ResultMessage):
                    outcome = message.subtype
                    final_cost = message.total_cost_usd
                    if message.subtype == "success" and world.treasure_found:
                        dashboard.log(f"🏆 {message.result}")
                    elif message.subtype == "success":
                        # The SDK ended the session cleanly, but the treasure
                        # was never actually found - e.g. a thrashing-autocompact
                        # abort. Don't show a trophy for that.
                        dashboard.log(f"⚠️ Session ended without finding the treasure: {message.result}")
                    else:
                        dashboard.log(f"⏱️ Stopped: {message.subtype}")
                    recorder.result(
                        message.subtype, message.result, message.total_cost_usd, dashboard.turns, world.treasure_found
                    )
        except ResultError as e:
            spent = e.data.get("total_cost_usd")
            spent_str = f"${spent:.4f}" if isinstance(spent, (int, float)) else "unknown"
            outcome = e.subtype or "error"
            final_cost = spent
            if e.subtype == "error_max_turns":
                dashboard.log(f"🛑 Guardrail hit: reached the {max_turns}-turn limit before finding the treasure.")
            elif e.subtype == "error_max_budget_usd":
                dashboard.log(
                    f"🛑 Guardrail hit: spent {spent_str} against the ${max_budget_usd:.2f} "
                    "budget cap before finding the treasure."
                )
            else:
                dashboard.log(f"🛑 Stopped early: {e.subtype} ({e.terminal_reason})")
            recorder.result(e.subtype or "error", e.result, spent, dashboard.turns, world.treasure_found)

    transcript_file = os.environ.get("TRANSCRIPT_FILE")
    if transcript_file:
        recorder.save(transcript_file)

    return {
        "outcome": outcome,
        "total_turns": dashboard.turns,
        "total_cost_usd": final_cost,
        "input_tokens": dashboard.tokens["input"],
        "output_tokens": dashboard.tokens["output"],
        "cache_read_input_tokens": dashboard.tokens["cache_read"],
        "cache_creation_input_tokens": dashboard.tokens["cache_creation"],
        "compactions": compactions,
        # The SDK's "success" outcome only means the session ended without
        # tripping a guardrail - it says nothing about whether the agent
        # actually won. Confirmed the hard way: a thrashing-autocompact run
        # can abort with outcome="success" and a CLI diagnostic as its
        # closing text, having never reached the treasure. This is the one
        # honest ground-truth signal - read directly off the game state.
        "treasure_found": world.treasure_found,
        "model": MODEL,
    }


def main() -> None:
    asyncio.run(run_treasure_hunt())


if __name__ == "__main__":
    main()
