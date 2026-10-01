import asyncio

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, RateLimitEvent, ResultMessage, query

from .dashboard import Dashboard
from .tools import ALLOWED_TOOLS, build_game_server
from .world import ROOMS

SYSTEM_PROMPT = """You are an explorer in a small text-based treasure hunt.
Use the tools to look around, move between rooms, and search for hidden items.
Explore methodically until you find the treasure, then report that you've won."""


async def run_treasure_hunt() -> None:
    """The agent loop, run by the Claude Agent SDK: it calls the model, runs
    whichever tool it picks against our in-memory World, feeds the result
    back, and repeats until the model decides the hunt is over. A live
    dashboard shows the map, the agent's running commentary, and how much
    of the subscription's rate-limit windows this run is using."""
    dashboard = Dashboard(room_names=list(ROOMS.keys()))

    with dashboard:
        server, world = build_game_server(dashboard)
        dashboard.set_room(world.current_room, world.current_room_description, world.current_room_exits)

        options = ClaudeAgentOptions(
            mcp_servers={"treasure_hunt": server},
            allowed_tools=ALLOWED_TOOLS,
            permission_mode="bypassPermissions",
            system_prompt=SYSTEM_PROMPT,
        )

        async for message in query(
            prompt="Begin exploring. Find the treasure.",
            options=options,
        ):
            if isinstance(message, AssistantMessage):
                if message.usage:
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


def main() -> None:
    asyncio.run(run_treasure_hunt())


if __name__ == "__main__":
    main()
