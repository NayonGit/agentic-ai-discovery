import json
from typing import Any

from .world import ROOMS


class TranscriptRecorder:
    """Collects a structured, replayable record of one treasure-hunt run, so
    it can be played back later (e.g. in a standalone visualizer) without
    needing to re-run the agent."""

    def __init__(self, start_room: str, max_turns: int, max_budget_usd: float, model: str) -> None:
        self.data: dict[str, Any] = {
            "rooms": {name: {"description": room["description"], "exits": room["exits"]} for name, room in ROOMS.items()},
            "start_room": start_room,
            "max_turns": max_turns,
            "max_budget_usd": max_budget_usd,
            "model": model,
            "events": [],
        }

    def text(self, text: str) -> None:
        self.data["events"].append({"type": "text", "text": text})

    def tool_call(
        self,
        tool: str,
        args: dict[str, Any],
        result: str,
        is_error: bool,
        room: str,
        exits: list[str],
        inventory: list[str],
    ) -> None:
        self.data["events"].append(
            {
                "type": "tool_call",
                "tool": tool,
                "args": args,
                "result": result,
                "is_error": is_error,
                "room": room,
                "exits": exits,
                "inventory": list(inventory),
            }
        )

    def usage(self, usage: dict[str, Any]) -> None:
        self.data["events"].append(
            {
                "type": "usage",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            }
        )

    def rate_limit(self, raw: dict[str, Any]) -> None:
        windows = raw.get("unifiedWindows", {})
        self.data["events"].append(
            {
                "type": "rate_limit",
                "five_hour": windows.get("five_hour", {}).get("utilization"),
                "seven_day": windows.get("seven_day", {}).get("utilization"),
            }
        )

    def result(self, outcome: str, text: str | None, total_cost_usd: float | None, total_turns: int) -> None:
        self.data["events"].append(
            {
                "type": "result",
                "outcome": outcome,
                "text": text,
                "total_cost_usd": total_cost_usd,
                "total_turns": total_turns,
            }
        )

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.data, f, indent=2)
