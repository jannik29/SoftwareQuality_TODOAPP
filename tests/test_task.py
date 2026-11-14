"""Tests for the task data model and the priority enum."""
import unittest
from datetime import datetime

from classes.task import Priority, Task
from tests.helpers import days_from_today


class PriorityTest(unittest.TestCase):
    def test_parse_accepts_name_abbreviation_and_number(self):
        for text in ("hoch", "HOCH", " h ", "3"):
            self.assertIs(Priority.parse(text), Priority.HOCH)
        self.assertIs(Priority.parse("n"), Priority.NIEDRIG)
        self.assertIs(Priority.parse("2"), Priority.MITTEL)

    def test_parse_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            Priority.parse("sehr hoch")

    def test_label_is_lower_case(self):
        self.assertEqual(Priority.MITTEL.label, "mittel")


class TaskTest(unittest.TestCase):
    def test_complete_and_reopen(self):
        task = Task(1, "Test")
        task.complete()
        self.assertTrue(task.done)
        self.assertIsInstance(task.completed_at, datetime)
        task.reopen()
        self.assertFalse(task.done)
        self.assertIsNone(task.completed_at)

    def test_is_overdue(self):
        self.assertTrue(Task(1, "a", due_date=days_from_today(-1)).is_overdue())
        self.assertFalse(Task(1, "a", due_date=days_from_today(0)).is_overdue())
        self.assertFalse(Task(1, "a").is_overdue())
        done = Task(1, "a", due_date=days_from_today(-5))
        done.complete()
        self.assertFalse(done.is_overdue())

    def test_is_due_soon(self):
        self.assertTrue(Task(1, "a", due_date=days_from_today(0)).is_due_soon(3))
        self.assertTrue(Task(1, "a", due_date=days_from_today(3)).is_due_soon(3))
        self.assertFalse(Task(1, "a", due_date=days_from_today(4)).is_due_soon(3))
        self.assertFalse(Task(1, "a", due_date=days_from_today(-1)).is_due_soon(3))
        self.assertFalse(Task(1, "a").is_due_soon(3))

    def test_has_tag_and_matches_ignore_case(self):
        task = Task(1, "Einkaufen", description="Milch holen", tags=["Haushalt"])
        self.assertTrue(task.has_tag("haushalt"))
        self.assertTrue(task.matches("MILCH"))
        self.assertTrue(task.matches("einkauf"))
        self.assertTrue(task.matches("haushalt"))
        self.assertFalse(task.matches("Uni"))

    def test_dict_round_trip_keeps_all_fields(self):
        task = Task(7, "Titel", "Beschreibung", Priority.HOCH, days_from_today(2), ["a", "b"], location_id=3)
        task.complete()
        copy = Task.from_dict(task.to_dict())
        self.assertEqual(copy.to_dict(), task.to_dict())

    def test_from_dict_uses_defaults_for_missing_fields(self):
        task = Task.from_dict({"id": "4", "title": "Nur Titel"})
        self.assertEqual(task.id, 4)
        self.assertIs(task.priority, Priority.MITTEL)
        self.assertEqual(task.tags, [])
        self.assertIsNone(task.due_date)
        self.assertIsNone(task.location_id)


if __name__ == "__main__":
    unittest.main()
