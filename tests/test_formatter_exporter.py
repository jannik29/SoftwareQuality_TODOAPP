"""Tests for the text output (formatter), the statistics and the CSV export."""
import csv
import unittest
from datetime import date, timedelta

from classes.exporter import CsvExporter
from classes.formatter import TaskFormatter
from classes.statistics import Statistics
from classes.task import Priority, Task
from tests.helpers import AppTestCase, days_from_today


class FormatterTest(unittest.TestCase):
    def setUp(self):
        self.fmt = TaskFormatter("%d.%m.%Y", use_colors=False, due_soon_days=3)

    def test_parse_date_variants(self):
        today = date.today()
        self.assertEqual(self.fmt.parse_date("heute"), today)
        self.assertEqual(self.fmt.parse_date(" Morgen "), today + timedelta(days=1))
        self.assertEqual(self.fmt.parse_date("+10"), today + timedelta(days=10))
        self.assertEqual(self.fmt.parse_date("24.12.2026"), date(2026, 12, 24))
        self.assertEqual(self.fmt.parse_date("2026-12-24"), date(2026, 12, 24))
        self.assertIsNone(self.fmt.parse_date(""))
        self.assertIsNone(self.fmt.parse_date("-"))

    def test_parse_date_invalid(self):
        for text in ("31.02.2026", "irgendwann", "+x"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.fmt.parse_date(text)

    def test_format_date_and_hint(self):
        self.assertEqual(self.fmt.format_date(date(2026, 1, 5)), "05.01.2026")
        self.assertEqual(self.fmt.format_date(None), "-")
        self.assertEqual(self.fmt.date_hint, "TT.MM.JJJJ")

    def test_colors_only_when_enabled(self):
        self.assertEqual(self.fmt.color("x", "\033[31m"), "x")
        colored = TaskFormatter(use_colors=True).color("x", "\033[31m")
        self.assertTrue(colored.startswith("\033[31m") and colored.endswith("\033[0m"))

    def test_table(self):
        self.assertEqual(self.fmt.table([]), "Keine Aufgaben gefunden.")
        tasks = [Task(1, "Überfällig", due_date=days_from_today(-1), tags=["uni"], location_id=5),
                 Task(2, "Bald", priority=Priority.HOCH, due_date=days_from_today(1))]
        table = self.fmt.table(tasks)
        self.assertIn("(überfällig)", table)
        self.assertIn("(bald)", table)
        self.assertIn("#uni", table)
        self.assertNotIn("Ort", table)
        with_places = self.fmt.table(tasks, {5: "Uni"})
        self.assertIn("Ort", with_places.splitlines()[0])
        self.assertIn("Uni", with_places.splitlines()[1])

    def test_details(self):
        task = Task(3, "Titel", "Text", tags=["a"])
        task.complete()
        details = self.fmt.details(task, "Uni")
        for expected in ("Titel", "Text", "erledigt", "Uni", "Erledigt am"):
            self.assertIn(expected, details)
        self.assertNotIn("Ort", self.fmt.details(task))

    def test_statistics_output(self):
        stats = Statistics(4, 1, 3, 1, {"niedrig": 0, "mittel": 2, "hoch": 1}, {"uni": 2})
        text = self.fmt.statistics(stats)
        self.assertIn("25 %", text)
        self.assertIn("#uni=2", text)
        self.assertEqual(Statistics(0, 0, 0, 0, {}, {}).completion_rate, 0.0)


class CsvExporterTest(AppTestCase):
    def test_export_writes_all_tasks(self):
        task = self.todos.add("Einkaufen; Milch", "Text", Priority.HOCH, date(2026, 12, 24), ["a", "b"])
        self.todos.complete(task.id)
        self.todos.add("Zweite")
        path = CsvExporter.export(self.todos.list("id"), self.folder / "export.csv")
        with path.open(encoding="utf-8") as file:
            rows = list(csv.reader(file, delimiter=";"))
        self.assertEqual(rows[0], CsvExporter.HEADER)
        self.assertEqual(rows[1], [str(task.id), "Einkaufen; Milch", "Text", "hoch", "2026-12-24", "a,b", "ja"])
        self.assertEqual(rows[2][-1], "nein")


if __name__ == "__main__":
    unittest.main()
