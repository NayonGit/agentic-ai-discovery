import asyncio
import os

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultError,
    ResultMessage,
    query,
)

from .dashboard import Dashboard
from .tools import ALLOWED_TOOLS, build_game_server
from .world import ROOMS

SYSTEM_PROMPT = """You are an explorer in a small text-based treasure hunt.
Use the tools to look around, move between rooms, and search for hidden items.
Explore methodically until you find the treasure, then report that you've won."""

# Generous enough that a normal hunt always finishes comfortably. To see the
# guardrails actually trip, force them low, e.g.:
#   MAX_TURNS=3 uv run treasure-hunt
#   MAX_BUDGET_USD=0.01 uv run treasure-hunt
DEFAULT_MAX_TURNS = 20
DEFAULT_MAX_BUDGET_USD = 0.50


async def run_treasure_hunt() -> None:
    """The agent loop, run by the Claude Agent SDK: it calls the model, runs
    whichever tool it picks against our in-memory World, feeds the result
    back, and repeats until the model decides the hunt is over — or until a
    guardrail (max turns / max budget) cuts it off first. A live dashboard
    shows the map, the agent's running commentary, and how much of the
    subscription's rate-limit windows this run is using."""
    max_turns = int(os.environ.get("MAX_TURNS", DEFAULT_MAX_TURNS))
    max_budget_usd = float(os.environ.get("MAX_BUDGET_USD", DEFAULT_MAX_BUDGET_USD))

    dashboard = Dashboard(room_names=list(ROOMS.keys()), max_turns=max_turns, max_budget_usd=max_budget_usd)

    with dashboard:
        server, world = build_game_server(dashboard)
        dashboard.set_room(world.current_room, world.current_room_description, world.current_room_exits)

        options = ClaudeAgentOptions(
            model="claude-sonnet-5",
            tools=[],  # no built-in Claude Code tools (Bash, Read, Edit, ...) — only our 3 MCP tools
            skills=[],  # don't load the host's personal Claude Code skills into this game's context
            mcp_servers={"treasure_hunt": server},
            allowed_tools=ALLOWED_TOOLS,
            permission_mode="bypassPermissions",
            system_prompt=SYSTEM_PROMPT,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
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
                    for block in message.content:
                        if getattr(block, "text", None):
                            dashboard.log(f"🧭 {block.text}")
                elif isinstance(message, RateLimitEvent):
                    dashboard.update_rate_limits(message.rate_limit_info.raw)
                elif isinstance(message, ResultMessage):
                    if message.subtype == "success":
                        dashboard.log(f"🏆 {message.result}")
                    else:
                        dashboard.log(f"⏱️ Stopped: {message.subtype}")
        except ResultError as e:
            spent = e.data.get("total_cost_usd")
            spent_str = f"${spent:.4f}" if isinstance(spent, (int, float)) else "unknown"
            if e.subtype == "error_max_turns":
                dashboard.log(f"🛑 Guardrail hit: reached the {max_turns}-turn limit before finding the treasure.")
            elif e.subtype == "error_max_budget_usd":
                dashboard.log(
                    f"🛑 Guardrail hit: spent {spent_str} against the ${max_budget_usd:.2f} "
                    "budget cap before finding the treasure."
                )
            else:
                dashboard.log(f"🛑 Stopped early: {e.subtype} ({e.terminal_reason})")


def main() -> None:
    asyncio.run(run_treasure_hunt())


if __name__ == "__main__":
    main()
