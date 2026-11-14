"""Loads the settings from config.json (missing values -> default values)."""
import json
from pathlib import Path

DEFAULTS = {
    "start_mode": "auswahl",
    "data_file": "data/todos.db",
    "date_format": "%d.%m.%Y",
    "default_priority": "mittel",
    "default_sort": "faellig",
    "show_completed": True,
    "confirm_delete": True,
    "use_colors": True,
    "max_title_length": 80,
    "due_soon_days": 3,
    "location_enabled": True,
    "location_source": "auto",
    "location_latitude": None,
    "location_longitude": None,
    "location_default_radius_m": 300,
    "location_show_unassigned": True,
    "location_timeout_s": 5,
    "map_tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

SORT_KEYS = ("faellig", "prioritaet", "erstellt", "titel", "id")
START_MODES = ("auswahl", "cli", "gui")
LOCATION_SOURCES = ("auto", "system", "ip", "manuell")


class Config:
    """Settings of the app. Relative paths refer to the folder of config.json."""

    def __init__(self, path: Path):
        """Loads the settings from the given JSON file."""
        self.path = Path(path)
        self.base_dir = self.path.parent
        self._values = dict(DEFAULTS)
        self.load()

    def load(self):
        """Reads config.json; if the file is missing, it is created with default values."""
        if not self.path.exists():
            self.save()
            return
        with self.path.open(encoding="utf-8") as file:
            user_values = json.load(file)
        unknown = set(user_values) - set(DEFAULTS)
        if unknown:
            print(f"Warnung: unbekannte Einstellungen in {self.path.name}: {', '.join(sorted(unknown))}")
        self._values.update({k: v for k, v in user_values.items() if k in DEFAULTS})
        self._validate()

    def save(self):
        """Writes the current settings back to the file."""
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(self._values, file, indent=2, ensure_ascii=False)
            file.write("\n")

    def _validate(self):
        """Checks whether the values are valid and raises a ValueError otherwise."""
        if self._values["start_mode"] not in START_MODES:
            raise ValueError(f"start_mode muss einer von {START_MODES} sein")
        if self._values["default_sort"] not in SORT_KEYS:
            raise ValueError(f"default_sort muss einer von {SORT_KEYS} sein")
        if int(self._values["max_title_length"]) < 1:
            raise ValueError("max_title_length muss >= 1 sein")
        if int(self._values["due_soon_days"]) < 0:
            raise ValueError("due_soon_days muss >= 0 sein")
        if self._values["location_source"] not in LOCATION_SOURCES:
            raise ValueError(f"location_source muss einer von {LOCATION_SOURCES} sein")
        if not all(part in self._values["map_tile_url"] for part in ("{z}", "{x}", "{y}")):
            raise ValueError("map_tile_url muss {z}, {x} und {y} enthalten")
        if int(self._values["location_default_radius_m"]) < 1:
            raise ValueError("location_default_radius_m muss >= 1 sein")

    def get(self, key: str):
        """Returns a setting by its name."""
        return self._values[key]

    @property
    def start_mode(self) -> str:
        """What happens on start without a command: auswahl, cli or gui."""
        return self._values["start_mode"]

    @property
    def data_file(self) -> Path:
        """Path to the SQLite database (relative to the folder of config.json)."""
        path = Path(self._values["data_file"])
        return path if path.is_absolute() else self.base_dir / path

    @property
    def date_format(self) -> str:
        """Date format for input and output, e.g. %d.%m.%Y."""
        return self._values["date_format"]

    @property
    def default_priority(self) -> str:
        """Priority for new tasks if none is given."""
        return self._values["default_priority"]

    @property
    def default_sort(self) -> str:
        """Default sort order of the task list."""
        return self._values["default_sort"]

    @property
    def show_completed(self) -> bool:
        """Whether completed tasks are shown by default."""
        return bool(self._values["show_completed"])

    @property
    def confirm_delete(self) -> bool:
        """Whether to ask for confirmation before deleting."""
        return bool(self._values["confirm_delete"])

    @property
    def use_colors(self) -> bool:
        """Whether the console output is colored."""
        if self._values["use_colors"] == True:
            return True
        else:
            return False

    @property
    def max_title_length(self) -> int:
        """Maximum length of a task title."""
        return int(self._values["max_title_length"])

    @property
    def due_soon_days(self) -> int:
        """How many days before the due date a task counts as 'due soon'."""
        return int(self._values["due_soon_days"])

    @property
    def location_enabled(self) -> bool:
        """Switch for the whole location feature."""
        return bool(self._values["location_enabled"])

    @property
    def location_source(self) -> str:
        """Source of the location: auto, system, ip or manuell."""
        return self._values["location_source"]

    @property
    def location_latitude(self):
        """Fixed latitude for location_source = manuell."""
        return self._values["location_latitude"]

    @property
    def location_longitude(self):
        """Fixed longitude for location_source = manuell."""
        return self._values["location_longitude"]

    @property
    def location_default_radius_m(self) -> int:
        """Default radius of new places in meters."""
        return int(self._values["location_default_radius_m"])

    @property
    def location_show_unassigned(self) -> bool:
        """Whether tasks without a place are also shown when filtering by place."""
        return bool(self._values["location_show_unassigned"])

    @property
    def location_timeout_s(self) -> float:
        """Maximum waiting time for the location lookup in seconds."""
        return float(self._values["location_timeout_s"])

    @property
    def map_tile_url(self) -> str:
        """URL template for the map tiles with {z}, {x} and {y}."""
        return self._values["map_tile_url"]

    @property
    def tile_cache_dir(self) -> Path:
        """Folder in which downloaded map tiles are cached."""
        return self.data_file.parent / "tile_cache"
