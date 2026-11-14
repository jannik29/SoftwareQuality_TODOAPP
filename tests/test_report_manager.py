"""Tests for the report manager (reports, scoring, reminders, weekly overview, validation)."""
import unittest

from classes.report_manager import REPORT_SERVER, TaskReportManager
from classes.storage import SqliteStorage
from classes.task import Priority
from classes.todo_list import TodoList
from tests.helpers import AppTestCase, days_from_today


class ReportManagerTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.add_place_here("Zuhause")
        self.overdue = self.todos.add("Abgabe", priority=Priority.HOCH, due_date=days_from_today(-10),
                                      tags=["dringend"], location_id=self.home.id)
        self.today = self.todos.add("Heute erledigen", due_date=days_from_today(0), description="Beschreibung")
        self.unimportant = self.todos.add("Irgendwann", priority=Priority.NIEDRIG, due_date=days_from_today(40),
                                          tags=["später"])
        self.done = self.todos.add("Fertig", due_date=days_from_today(-3))
        self.todos.complete(self.done.id)
        self.manager = TaskReportManager(self.todos, self.config, self.fmt, self.location)

    def test_text_report(self):
        path = self.manager.save_report(self.folder / "bericht.txt", "text")
        text = path.read_text(encoding="utf-8")
        self.assertIn("!! Abgabe (überfällig)", text)
        self.assertIn("@ Zuhause", text)
        self.assertIn("Wochenübersicht", text)
        self.assertIn("Hinweise", text)
        self.assertEqual(self.manager.last_report, text)
        self.assertEqual(self.manager.generated_files, [path])

    def test_html_report(self):
        html = self.manager.save_report(self.folder / "bericht.html", "html").read_text(encoding="utf-8")
        self.assertTrue(html.startswith("<html>"))
        self.assertIn("color:red", html)
        self.assertIn("<h2>Wochenübersicht</h2>", html)
        self.assertTrue(html.endswith("</html>"))

    def test_csv_report(self):
        lines = self.manager.save_report(self.folder / "bericht.csv", "csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "id;titel;prioritaet;faellig;status")
        self.assertIn(f"{self.overdue.id};Abgabe;hoch;", lines[1])
        self.assertTrue(lines[1].endswith("überfällig"))
        self.assertTrue(any(line.endswith(";erledigt") for line in lines))

    def test_unknown_format_falls_back_to_text(self):
        text = self.manager.save_report(self.folder / "x.out", "pdf").read_text(encoding="utf-8")
        self.assertIn("Aufgabenbericht", text)

    def test_empty_report(self):
        empty_list = TodoList(SqliteStorage(self.folder / "leer.db"))
        report = TaskReportManager(empty_list, self.config).build_report("text", True, True, True, True, True, None, True, 10, "T", "Autor", "Ende",
                                    "%d.%m.%Y", "Nichts da")
        self.assertIn("Nichts da", report)
        self.assertIn("Erstellt von Autor", report)

    def test_max_items_limits_output(self):
        report = self.manager.build_report("csv", True, False, False, False, False, None, False, 1, "T", "", "",
                                           "%d.%m.%Y", "")
        self.assertEqual(len(report.splitlines()), 2)

    def test_scores(self):
        self.assertGreater(self.manager.calculate_score(self.overdue), 5)
        self.assertGreater(self.manager.calculate_score(self.today), 5)
        self.assertEqual(self.manager.calculate_score(self.unimportant), 1)
        self.assertTrue(self.manager.is_important(self.overdue))
        self.assertFalse(self.manager.is_important(self.unimportant))
        self.assertEqual(self.manager.score_cache[self.overdue.id], self.manager.calculate_score(self.overdue))

    def test_reminders(self):
        reminders = self.manager.build_reminders()
        self.assertIn("Wichtig und überfällig: Abgabe (Zuhause)", reminders)
        self.assertIn("Wichtig, heute fällig: Heute erledigen", reminders)
        self.assertEqual(len(reminders), 2)

    def test_overdue_and_counts(self):
        self.assertEqual([t.id for t in self.manager.GetOverdueTasks()], [self.overdue.id])
        self.assertEqual((self.manager.count_open(), self.manager.count_done()), (3, 1))
        summary = self.manager.summary()
        self.assertIn("Offen: 3", summary)
        self.assertIn("Überfällig: 1", summary)
        self.assertEqual(self.manager.stats["high"], 1)
        self.assertEqual(self.manager.places_summary(), ["Zuhause: 1"])
        self.assertEqual(self.manager.priority_summary(), ["niedrig: 1", "mittel: 1", "hoch: 1"])

    def test_weekly_overview(self):
        lines = self.manager.build_weekly_overview()
        self.assertEqual(len(lines), 7)
        self.assertTrue(lines[0].endswith("1 Aufgabe(n)"))
        self.assertEqual(sum(self.manager.weekly.values()), 1)

    def test_validation(self):
        warnings = self.manager.validate_tasks()
        self.assertIn(f"Aufgabe {self.overdue.id} ist seit über einer Woche überfällig", warnings)
        self.assertIn(f"Aufgabe {self.overdue.id} hat keine Beschreibung", warnings)

    def test_prepare_upload_does_not_send(self):
        request = self.manager.prepare_upload("inhalt")
        self.assertEqual(request["url"], REPORT_SERVER)
        self.assertEqual(request["body"], "inhalt")


if __name__ == "__main__":
    unittest.main()
