from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .dashboard import Dashboard
from .recorder import TranscriptRecorder
from .world import World

SERVER_NAME = "treasure_hunt"
ALLOWED_TOOLS = [
    f"mcp__{SERVER_NAME}__look_around",
    f"mcp__{SERVER_NAME}__move",
    f"mcp__{SERVER_NAME}__search_room",
]


def build_game_server(dashboard: Dashboard, recorder: TranscriptRecorder) -> tuple[Any, World]:
    """Create a fresh World and wrap it in custom tools bound to that instance.
    Each tool reports what it did to the dashboard and the recorder, then
    waits for the user to confirm they've read it before letting the agent
    take its next step."""
    world = World()

    def _sync_room() -> None:
        dashboard.set_room(world.current_room, world.current_room_description, world.current_room_exits)

    @tool("look_around", "Look at your current surroundings.", {})
    async def look_around(_args: dict[str, Any]) -> dict[str, Any]:
        result = world.look()
        dashboard.log(f"🔧 look_around → {result}")
        recorder.tool_call("look_around", {}, result, False, world.current_room, world.current_room_exits, world.inventory)
        await dashboard.wait_for_step()
        return {"content": [{"type": "text", "text": result}]}

    @tool(
        "move",
        "Move through an exit in the given direction (e.g. north, south, east, west, up, down).",
        {"direction": str},
    )
    async def move(args: dict[str, Any]) -> dict[str, Any]:
        result, is_error = world.move(args["direction"])
        _sync_room()
        marker = "❌" if is_error else "🔧"
        dashboard.log(f"{marker} move({args['direction']}) → {result}")
        recorder.tool_call("move", args, result, is_error, world.current_room, world.current_room_exits, world.inventory)
        await dashboard.wait_for_step()
        return {"content": [{"type": "text", "text": result}], "is_error": is_error}

    @tool("search_room", "Search the current room thoroughly for hidden items.", {})
    async def search_room(_args: dict[str, Any]) -> dict[str, Any]:
        result = world.search()
        dashboard.log(f"🔧 search_room → {result}")
        recorder.tool_call("search_room", {}, result, False, world.current_room, world.current_room_exits, world.inventory)
        await dashboard.wait_for_step()
        return {"content": [{"type": "text", "text": result}]}

    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version="1.0.0",
        tools=[look_around, move, search_room],
    )
    return server, world
