"""Shared helpers: every test works in its own temporary folder with its own config and database."""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from classes.config import DEFAULTS, Config
from classes.formatter import TaskFormatter
from classes.location import Coordinates
from classes.location_context import LocationContext
from classes.location_service import LocationService
from classes.storage import SqliteStorage
from classes.todo_list import TodoList

# fixed test position (Stuttgart Schlossplatz) so that no test needs the network
TEST_LAT, TEST_LON = 48.7785, 9.1797


def days_from_today(days: int) -> date:
    """Date relative to today, keeps the tests independent of the current date."""
    return date.today() + timedelta(days=days)


def write_config(folder: Path, **values) -> Config:
    """Writes a config.json with test defaults (manual location) plus the given values."""
    settings = dict(DEFAULTS)
    settings.update(location_source="manuell", location_latitude=TEST_LAT, location_longitude=TEST_LON,
                    use_colors=False)
    settings.update(values)
    path = folder / "config.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return Config(path)


class AppTestCase(unittest.TestCase):
    """Base class that provides config, todo list, formatter and location context in a temp folder."""

    config_values: dict = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.config = write_config(self.folder, **self.config_values)
        self.todos = TodoList(SqliteStorage(self.config.data_file), self.config.max_title_length)
        self.fmt = TaskFormatter(self.config.date_format, False, self.config.due_soon_days)
        self.location = LocationContext(self.todos, LocationService(self.config), self.config)

    def tearDown(self):
        self._tmp.cleanup()

    def reload(self) -> TodoList:
        """Loads the todo list again from the database (checks that data was really saved)."""
        return TodoList(SqliteStorage(self.config.data_file), self.config.max_title_length)

    def add_place_here(self, name: str = "Zuhause", radius_m: int = 300):
        """Adds a place at the test position."""
        return self.todos.add_place(name, Coordinates(TEST_LAT, TEST_LON), radius_m)
