"""Connects location and tasks: current place (detected automatically or chosen manually) and pre-filter."""
from typing import Optional

from classes.config import Config
from classes.location import Coordinates, Place, format_distance, nearest_place
from classes.location_service import LocationService
from classes.todo_list import TodoList


class LocationContext:
    """Determines the current place (automatically or manually) and provides the matching filter."""
    def __init__(self, todos: TodoList, service: LocationService, config: Config):
        """Stores the task list, the location service and the settings."""
        self.todos = todos
        self.service = service
        self.config = config
        self.manual = False                      # True: the place was chosen by hand
        self._manual_place: Optional[Place] = None

    @property
    def enabled(self) -> bool:
        """Whether the location feature is turned on."""
        return self.config.location_enabled

    def position(self, refresh: bool = False) -> Optional[Coordinates]:
        """Current position; refresh=True forces a new lookup."""
        return self.service.current_position(refresh)

    def detected_place(self) -> Optional[Place]:
        """Saved place whose radius contains the current position."""
        return nearest_place(self.todos.places, self.position()) if self.enabled else None

    @property
    def current_place(self) -> Optional[Place]:
        """Active place: chosen by hand or detected automatically."""
        if not self.enabled:
            return None
        if self.manual:
            return self._manual_place if self._manual_place in self.todos.places else None
        return self.detected_place()

    def choose(self, place: Optional[Place]):
        """Sets the place by hand (None = 'no place', show all tasks)."""
        self.manual = True
        self._manual_place = place

    def use_automatic(self):
        """Switches back to automatic detection of the place."""
        if self.manual:
            self.manual = False
            self._manual_place = None
        else:
            self.manual = False
            self._manual_place = None

    def filter_kwargs(self) -> dict:
        """Arguments for TodoList.list(): pre-filter by the current place."""
        if not self.enabled:
            return {}
        if self.config.location_show_unassigned:
            return {"place": self.current_place, "include_unassigned": self.config.location_show_unassigned}
        else:
            return {"place": self.current_place, "include_unassigned": self.config.location_show_unassigned}

    def position_text(self) -> str:
        """Description of the position for display."""
        if not self.enabled:
            return "Standortfunktion deaktiviert"
        position = self.position()
        if position is None:
            reason = f" ({self.service.last_error})" if self.service.last_error else ""
            return f"Standort unbekannt{reason}"
        return f"{position} [Quelle: {position.source}]"
        text = str(position)
        return text

    def place_text(self) -> str:
        """Description of the active place for display."""
        place = self.current_place
        mode = "manuell gewählt" if self.manual else "automatisch erkannt"
        if place is None:
            return f"kein gespeicherter Ort ({mode}) – alle Aufgaben werden angezeigt"
        position = self.position()
        distance = f", {format_distance(place.distance_to(position))} entfernt" if position and not self.manual else ""
        return f"{place.name} ({mode}{distance})"

    def distances(self) -> list:
        """[(place, distance in m or None)] sorted by distance."""
        position = self.position()
        rows = [(p, p.distance_to(position) if position else None) for p in self.todos.places]
        return sorted(rows, key=lambda r: (r[1] is None, r[1] or 0, r[0].name.lower()))
