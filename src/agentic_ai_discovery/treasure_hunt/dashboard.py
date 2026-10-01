import asyncio
import textwrap
import time

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

MAX_LOG_ENTRIES = 200
HEADER_HEIGHT = 3
FOOTER_HEIGHT = 5
PANEL_FRAME_HEIGHT = 2  # top + bottom border of a Panel
PANEL_FRAME_WIDTH = 4  # left/right border + 1 padding each side

RATE_LIMIT_WINDOWS = [("five_hour", "5h window"), ("seven_day", "7d window")]


class Dashboard:
    """Live terminal view of the hunt: where the agent is, what it's doing,
    and how much of your Claude subscription that's using up."""

    def __init__(self, room_names: list[str], max_turns: int, max_budget_usd: float) -> None:
        self.room_names = room_names
        self.current_room = room_names[0]
        self.visited = {room_names[0]}
        self.room_description = ""
        self.room_exits: list[str] = []
        self.log_lines: list[str] = []
        self.tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        self.turns = 0
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.rate_limits: dict[str, dict] = {}

        self._console = Console()
        self._live = Live(self._render(), console=self._console, refresh_per_second=8)

    def __enter__(self) -> "Dashboard":
        self._live.__enter__()
        return self

    def __exit__(self, *exc_info) -> None:
        self._live.__exit__(*exc_info)

    def set_room(self, name: str, description: str, exits: list[str]) -> None:
        self.current_room = name
        self.visited.add(name)
        self.room_description = description
        self.room_exits = exits
        self._refresh()

    def log(self, line: str) -> None:
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-MAX_LOG_ENTRIES:]
        self._refresh()

    async def wait_for_step(self, prompt: str = "— press Enter for the next step —") -> None:
        """Pause the live view and block until the user presses Enter, so a
        human has time to read each step instead of the agent racing ahead."""
        self._live.stop()
        try:
            await asyncio.to_thread(input, prompt)
        finally:
            self._live.start(refresh=True)

    def add_turn_usage(self, usage: dict) -> None:
        self.turns += 1
        self.tokens["input"] += usage.get("input_tokens", 0) or 0
        self.tokens["output"] += usage.get("output_tokens", 0) or 0
        self.tokens["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
        self.tokens["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
        self._refresh()

    def update_rate_limits(self, raw: dict) -> None:
        windows = raw.get("unifiedWindows", {})
        for key, _label in RATE_LIMIT_WINDOWS:
            if key in windows:
                self.rate_limits[key] = windows[key]
        self._refresh()

    def _refresh(self) -> None:
        self._live.update(self._render())

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=HEADER_HEIGHT),
            Layout(name="body"),
            Layout(name="footer", size=FOOTER_HEIGHT),
        )
        layout["body"].split_row(
            Layout(name="map", ratio=1),
            Layout(name="log", ratio=2),
        )
        layout["header"].update(Panel(Text("Treasure Hunt — Agent Loop", style="bold"), style="cyan"))
        layout["map"].update(self._map_panel())
        layout["log"].update(self._log_panel())
        layout["footer"].update(self._usage_panel())
        return layout

    def _map_panel(self) -> Panel:
        rooms = Table.grid(padding=(0, 1))
        rooms.add_column()
        rooms.add_column()
        for name in self.room_names:
            if name == self.current_room:
                marker, style = "▶", "bold yellow"
            elif name in self.visited:
                marker, style = "✓", "green"
            else:
                marker, style = " ", "dim"
            rooms.add_row(Text(marker, style=style), Text(name, style=style))

        content = Table.grid()
        content.add_row(rooms)
        content.add_row(Text(f"\n{self.room_description}\n", style="italic"))
        content.add_row(Text(f"Exits: {', '.join(self.room_exits) or 'none'}", style="dim"))
        return Panel(content, title="Map", border_style="blue")

    def _log_panel(self) -> Panel:
        width, height = self._console.size
        log_width = max(20, (width * 2 // 3) - PANEL_FRAME_WIDTH)
        available_height = max(3, height - HEADER_HEIGHT - FOOTER_HEIGHT - PANEL_FRAME_HEIGHT)

        wrapped: list[str] = []
        for line in self.log_lines:
            wrapped.extend(textwrap.wrap(line, width=log_width) or [""])

        visible = wrapped[-available_height:]
        return Panel(Text("\n".join(visible) or "..."), title="Agent", border_style="magenta")

    def _format_window(self, key: str, label: str) -> str:
        window = self.rate_limits.get(key)
        if not window:
            return f"{label}: n/a"
        utilization = window.get("utilization")
        pct = f"{utilization * 100:.0f}%" if utilization is not None else "n/a"
        resets_at = window.get("resetsAt")
        reset_str = ""
        if resets_at:
            remaining = max(0, resets_at - time.time())
            hours, rem = divmod(int(remaining), 3600)
            minutes = rem // 60
            reset_str = f" (resets in {hours}h{minutes:02d}m)"
        return f"{label}: {pct}{reset_str}"

    def _usage_panel(self) -> Panel:
        t = self.tokens
        turns_style = "bold red" if self.turns >= self.max_turns else "bold"
        turns_text = Text(no_wrap=True, overflow="ellipsis")
        turns_text.append(f"Turns: {self.turns}/{self.max_turns}  ", style=turns_style)
        turns_text.append(
            f"In: {t['input']}  Out: {t['output']}  CacheR: {t['cache_read']}  CacheW: {t['cache_creation']}"
        )

        guardrails_line = (
            f"Guardrails: stop at {self.max_turns} turns or ${self.max_budget_usd:.2f} budget "
            "(notional cost, tracked by the SDK — not a separate charge on your subscription)"
        )
        windows_line = "   ".join(self._format_window(key, label) for key, label in RATE_LIMIT_WINDOWS)

        content = Table.grid()
        content.add_row(turns_text)
        content.add_row(Text(guardrails_line, no_wrap=True, overflow="ellipsis", style="dim"))
        content.add_row(Text(windows_line, no_wrap=True, overflow="ellipsis", style="bold"))
        return Panel(content, title="Usage (subscription)", border_style="green")
