"""Tests for the business logic: tasks, filters, sorting and places."""
import unittest
from datetime import datetime, timedelta

from classes.location import Coordinates
from classes.task import Priority
from classes.todo_list import PlaceNotFoundError, TaskNotFoundError
from tests.helpers import AppTestCase, days_from_today


class TaskManagementTest(AppTestCase):
    def test_add_saves_task_and_cleans_input(self):
        task = self.todos.add("  Einkaufen  ", " Milch ", Priority.HOCH, days_from_today(1),
                              ["#Haushalt", "haushalt", " ", "Woche"])
        self.assertEqual(task.title, "Einkaufen")
        self.assertEqual(task.description, "Milch")
        self.assertEqual(task.tags, ["Haushalt", "Woche"])
        self.assertEqual(self.reload().get(task.id).title, "Einkaufen")

    def test_add_rejects_empty_or_too_long_title(self):
        with self.assertRaises(ValueError):
            self.todos.add("   ")
        with self.assertRaises(ValueError):
            self.todos.add("x" * (self.config.max_title_length + 1))

    def test_get_unknown_id_raises(self):
        with self.assertRaises(TaskNotFoundError) as context:
            self.todos.get(99)
        self.assertIn("99", str(context.exception))

    def test_update_changes_allowed_fields_only(self):
        task = self.todos.add("Alt")
        self.todos.update(task.id, title="Neu", priority=Priority.NIEDRIG, tags=["x"])
        reloaded = self.reload().get(task.id)
        self.assertEqual((reloaded.title, reloaded.priority, reloaded.tags), ("Neu", Priority.NIEDRIG, ["x"]))
        with self.assertRaises(ValueError):
            self.todos.update(task.id, done=True)

    def test_complete_reopen_and_delete(self):
        task = self.todos.add("Aufgabe")
        self.todos.complete(task.id)
        self.assertTrue(self.reload().get(task.id).done)
        self.todos.complete(task.id)  # completing twice keeps it done
        self.assertTrue(self.reload().get(task.id).done)
        self.todos.reopen(task.id)
        self.assertFalse(self.reload().get(task.id).done)
        self.todos.delete(task.id)
        with self.assertRaises(TaskNotFoundError):
            self.reload().get(task.id)

    def test_clear_completed(self):
        keep = self.todos.add("offen")
        done = self.todos.add("erledigt")
        self.todos.complete(done.id)
        self.assertEqual(self.todos.clear_completed(), 1)
        self.assertEqual([t.id for t in self.reload().tasks], [keep.id])


class QueryTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.overdue = self.todos.add("Überfällig", priority=Priority.NIEDRIG, due_date=days_from_today(-2),
                                      tags=["uni"])
        self.soon = self.todos.add("Bald", priority=Priority.HOCH, due_date=days_from_today(1))
        self.later = self.todos.add("Später", due_date=days_from_today(20), tags=["Uni", "privat"])
        self.no_date = self.todos.add("Ohne Datum", priority=Priority.HOCH)
        self.done = self.todos.add("Erledigt", due_date=days_from_today(-1))
        self.todos.complete(self.done.id)

    def ids(self, tasks):
        return [t.id for t in tasks]

    def test_sort_by_due_date_puts_tasks_without_date_last(self):
        self.assertEqual(self.ids(self.todos.list("faellig")),
                         [self.overdue.id, self.done.id, self.soon.id, self.later.id, self.no_date.id])

    def test_sort_by_priority_title_and_id(self):
        self.assertEqual(self.ids(self.todos.list("prioritaet"))[:2], [self.soon.id, self.no_date.id])
        self.assertEqual(self.todos.list("titel")[0].title, "Bald")
        self.assertEqual(self.ids(self.todos.list("id")), sorted(self.ids(self.todos.tasks)))

    def test_unknown_sort_raises(self):
        with self.assertRaises(ValueError):
            self.todos.list("farbe")

    def test_filters(self):
        self.assertNotIn(self.done.id, self.ids(self.todos.list(show_completed=False)))
        self.assertEqual(self.ids(self.todos.list(priority=Priority.HOCH)), [self.soon.id, self.no_date.id])
        self.assertEqual(set(self.ids(self.todos.list(tag="UNI"))), {self.overdue.id, self.later.id})

    def test_search_overdue_due_soon_and_tags(self):
        self.assertEqual(self.ids(self.todos.search("datum")), [self.no_date.id])
        self.assertEqual(self.ids(self.todos.search("bald", self.todos.list(priority=Priority.NIEDRIG))), [])
        self.assertEqual(self.ids(self.todos.overdue()), [self.overdue.id])
        self.assertEqual(self.ids(self.todos.due_soon(3)), [self.soon.id])
        self.assertEqual([t.lower() for t in self.todos.all_tags()], ["privat", "uni", "uni"])

    def test_completed_since(self):
        self.assertEqual(self.ids(self.todos.completed_since(datetime.now() - timedelta(minutes=1))),
                         [self.done.id])
        self.assertEqual(self.todos.completed_since(datetime.now() + timedelta(minutes=1)), [])

    def test_statistics(self):
        stats = self.todos.statistics()
        self.assertEqual((stats.total, stats.open, stats.done, stats.overdue), (5, 4, 1, 1))
        self.assertEqual(stats.by_priority, {"niedrig": 1, "mittel": 1, "hoch": 2})
        self.assertAlmostEqual(stats.completion_rate, 20.0)


class PlaceTest(AppTestCase):
    def test_add_get_update_and_delete_place(self):
        place = self.add_place_here("Uni", 500)
        self.assertIs(self.todos.get_place("uni"), place)
        self.assertIs(self.todos.get_place(str(place.id)), place)
        self.todos.update_place(place.id, "Hochschule", Coordinates(1.0, 2.0), 250)
        reloaded = self.reload().get_place("Hochschule")
        self.assertEqual((reloaded.latitude, reloaded.longitude, reloaded.radius_m), (1.0, 2.0, 250))
        self.todos.delete_place("Hochschule")
        with self.assertRaises(PlaceNotFoundError):
            self.todos.get_place("Hochschule")

    def test_place_validation(self):
        with self.assertRaises(ValueError):
            self.add_place_here("  ")
        with self.assertRaises(ValueError):
            self.add_place_here("Uni", 0)
        self.add_place_here("Uni")
        with self.assertRaises(ValueError):
            self.add_place_here("uni")

    def test_task_with_unknown_place_is_rejected(self):
        with self.assertRaises(PlaceNotFoundError):
            self.todos.add("Aufgabe", location_id=42)

    def test_place_filter_and_counts(self):
        home = self.add_place_here("Zuhause")
        uni = self.todos.add_place("Uni", Coordinates(48.78, 9.17), 300)
        at_home = self.todos.add("Müll", location_id=home.id)
        at_uni = self.todos.add("Lernen", location_id=uni.id)
        anywhere = self.todos.add("Anrufen")
        ids = lambda tasks: {t.id for t in tasks}
        self.assertEqual(ids(self.todos.list(place=home)), {at_home.id, anywhere.id})
        self.assertEqual(ids(self.todos.list(place=home, include_unassigned=False)), {at_home.id})
        self.assertEqual(ids(self.todos.list()), {at_home.id, at_uni.id, anywhere.id})
        self.assertEqual(self.todos.count_for_place(uni), 1)
        self.assertEqual(self.todos.place_name(uni.id), "Uni")
        self.assertEqual(self.todos.place_name(None), "")
        self.assertEqual(self.todos.place_name(999), "")

    def test_deleting_place_unassigns_tasks(self):
        place = self.add_place_here()
        task = self.todos.add("Müll", location_id=place.id)
        self.todos.delete_place(place.id)
        self.assertIsNone(self.todos.get(task.id).location_id)
        self.assertIsNone(self.reload().get(task.id).location_id)


if __name__ == "__main__":
    unittest.main()
