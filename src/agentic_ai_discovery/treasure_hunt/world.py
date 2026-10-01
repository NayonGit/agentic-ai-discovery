ROOMS = {
    "entrance": {
        "description": "A crumbling stone gate marks the entrance to the old estate. Ivy swallows the walls.",
        "exits": {"north": "courtyard"},
        "item": None,
    },
    "courtyard": {
        "description": "An overgrown courtyard. A dry fountain sits at its center.",
        "exits": {"south": "entrance", "north": "tower", "east": "garden"},
        "item": "a torn map fragment",
        "item_description": (
            "You found a torn map fragment. A faded note scrawled on it reads: "
            "'X marks the spot — beneath the dry fountain.' You add the fragment to your inventory."
        ),
    },
    "garden": {
        "description": "A tangled garden, roses gone wild. Something glints beneath a bush.",
        "exits": {"west": "courtyard", "north": "tower"},
        "item": "a rusty key",
    },
    "tower": {
        "description": "A narrow stone tower. A ladder leads up into darkness.",
        "exits": {"south": "courtyard", "up": "attic", "west": "garden"},
        "item": None,
    },
    "attic": {
        "description": "A dusty attic, moonlight slipping through a cracked roof.",
        "exits": {"down": "tower"},
        "item": "the treasure chest",
    },
}


class World:
    """A tiny text-adventure map. One room hides the treasure."""

    def __init__(self):
        self.rooms = ROOMS
        self.current_room = "entrance"
        self.inventory = []
        self.treasure_found = False
        self.ladder_failed_once = False

    @property
    def current_room_description(self) -> str:
        return self.rooms[self.current_room]["description"]

    @property
    def current_room_exits(self) -> list[str]:
        return list(self.rooms[self.current_room]["exits"].keys())

    def look(self) -> str:
        room = self.rooms[self.current_room]
        exits = ", ".join(room["exits"].keys()) or "none"
        hint = ""
        if room["item"] and room["item"] not in self.inventory:
            hint = " You notice something here."
        return f"{room['description']} Exits: {exits}.{hint}"

    def move(self, direction: str) -> tuple[str, bool]:
        """Returns (message, is_error)."""
        room = self.rooms[self.current_room]
        direction = direction.strip().lower()
        if direction not in room["exits"]:
            return f"There is no exit to the {direction} from here.", False

        destination = room["exits"][direction]
        if destination == "attic" and not self.ladder_failed_once:
            self.ladder_failed_once = True
            return (
                "A loose rung gives way and you slip back down, unhurt. The ladder still looks "
                "climbable overall — it was probably just that one step. Worth trying again.",
                True,
            )

        self.current_room = destination
        return f"You move {direction} and arrive at: {self.rooms[self.current_room]['description']}", False

    def search(self) -> str:
        room = self.rooms[self.current_room]
        item = room["item"]
        if not item:
            return "You search carefully but find nothing of interest here."
        if item in self.inventory:
            return "You've already collected everything here."
        self.inventory.append(item)
        if item == "the treasure chest":
            self.treasure_found = True
            return "You pry open a dusty chest and find THE TREASURE! You win!"
        return room.get("item_description") or f"You found {item} and added it to your inventory."
