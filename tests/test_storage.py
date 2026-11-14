"""Tests for the SQLite storage including the migration of old databases."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from classes.location import Place
from classes.storage import SqliteStorage
from classes.task import Priority, Task
from tests.helpers import days_from_today


class SqliteStorageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data" / "todos.db"
        self.storage = SqliteStorage(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_folder_and_empty_database(self):
        self.assertTrue(self.path.exists())
        self.assertEqual(self.storage.load(), [])
        self.assertEqual(self.storage.load_places(), [])

    def test_insert_update_delete_task(self):
        task = Task(0, "Einkaufen", "Milch", Priority.HOCH, days_from_today(1), ["haushalt", "ä"])
        task.id = self.storage.insert(task)
        loaded = self.storage.load()[0]
        self.assertEqual(loaded.to_dict(), task.to_dict())

        task.complete()
        self.storage.update(task)
        self.assertTrue(self.storage.load()[0].done)

        self.storage.delete(task.id)
        self.assertEqual(self.storage.load(), [])

    def test_delete_completed_returns_count(self):
        for title, done in (("a", True), ("b", False), ("c", True)):
            task = Task(0, title)
            if done:
                task.complete()
            self.storage.insert(task)
        self.assertEqual(self.storage.delete_completed(), 2)
        self.assertEqual([t.title for t in self.storage.load()], ["b"])

    def test_places_are_unique_by_name_ignoring_case(self):
        self.storage.insert_place(Place(0, "Uni", 48.0, 9.0, 300))
        with self.assertRaises(ValueError):
            self.storage.insert_place(Place(0, "UNI", 1.0, 1.0, 100))

    def test_update_place(self):
        place = Place(0, "Uni", 48.0, 9.0, 300)
        place.id = self.storage.insert_place(place)
        place.name, place.radius_m = "Hochschule", 500
        self.storage.update_place(place)
        loaded = self.storage.load_places()[0]
        self.assertEqual((loaded.name, loaded.radius_m), ("Hochschule", 500))

    def test_deleting_a_place_keeps_its_tasks(self):
        place_id = self.storage.insert_place(Place(0, "Uni", 48.0, 9.0, 300))
        self.storage.insert(Task(0, "Lernen", location_id=place_id))
        self.storage.delete_place(place_id)
        task = self.storage.load()[0]
        self.assertEqual(task.title, "Lernen")
        self.assertIsNone(task.location_id)

    def test_old_database_without_location_column_is_migrated(self):
        old_path = Path(self._tmp.name) / "old.db"
        with sqlite3.connect(old_path) as conn:
            conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                         "description TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'mittel', "
                         "due_date TEXT, tags TEXT NOT NULL DEFAULT '[]', done INTEGER NOT NULL DEFAULT 0, "
                         "created_at TEXT NOT NULL, completed_at TEXT)")
            conn.execute("INSERT INTO tasks (title, created_at) VALUES ('Alt', '2026-01-01T10:00:00')")
        conn.close()
        storage = SqliteStorage(old_path)
        tasks = storage.load()
        self.assertEqual([t.title for t in tasks], ["Alt"])
        self.assertIsNone(tasks[0].location_id)


if __name__ == "__main__":
    unittest.main()
