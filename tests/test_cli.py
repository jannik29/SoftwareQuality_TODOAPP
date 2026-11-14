"""Tests for the direct commands (CommandLine), the console menu and the entry point todo.py."""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import todo
from classes.cli import CommandLine
from classes.console_ui import ConsoleUI
from classes.geocoder import SearchResult
from classes.location import Coordinates
from tests.helpers import AppTestCase, days_from_today


class CommandLineTest(AppTestCase):
    def run_cli(self, *argv) -> str:
        """Runs one command and returns what it printed."""
        cli = CommandLine(self.todos, self.fmt, self.config, self.location)
        output = io.StringIO()
        with redirect_stdout(output):
            cli.execute(cli.parse(list(argv)))
        return output.getvalue()

    def test_add_list_done_reopen_delete(self):
        self.assertIn("Aufgabe 1 angelegt", self.run_cli("add", "Einkaufen", "-p", "hoch", "-d", "morgen",
                                                         "-t", "a,b", "-b", "Milch"))
        task = self.todos.get(1)
        self.assertEqual((task.priority.label, task.due_date, task.tags), ("hoch", days_from_today(1), ["a", "b"]))
        self.assertIn("Einkaufen", self.run_cli("list"))
        self.run_cli("done", "1")
        self.assertTrue(self.todos.get(1).done)
        self.assertNotIn("Einkaufen", self.run_cli("list", "--offen"))
        self.run_cli("reopen", "1")
        self.assertFalse(self.todos.get(1).done)
        self.assertIn("Gelöscht", self.run_cli("delete", "1"))
        self.assertEqual(self.todos.tasks, [])

    def test_show_search_due_stats_clear_export(self):
        self.todos.add("Alt", due_date=days_from_today(-2))
        self.todos.add("Neu", due_date=days_from_today(1))
        self.assertIn("Alt", self.run_cli("show", "1"))
        self.assertIn("Neu", self.run_cli("search", "ne"))
        due = self.run_cli("due")
        self.assertIn("Alt", due)
        self.assertIn("Neu", due)
        self.assertIn("Gesamt:      2", self.run_cli("stats"))
        self.todos.complete(1)
        self.assertIn("1 Aufgabe(n) entfernt", self.run_cli("clear"))
        target = self.folder / "export.csv"
        self.run_cli("export", str(target))
        self.assertTrue(target.exists())

    def test_report_to_console_and_file(self):
        self.todos.add("Bericht-Aufgabe")
        self.assertIn("Bericht-Aufgabe", self.run_cli("report"))
        target = self.folder / "b.html"
        self.run_cli("report", "-f", "html", str(target))
        self.assertIn("<html>", target.read_text(encoding="utf-8"))

    def test_places_commands(self):
        self.assertIn("Noch keine Orte", self.run_cli("places"))
        self.assertIn("Zuhause", self.run_cli("place-add", "Zuhause"))
        self.run_cli("place-add", "Berlin", "--lat", "52.52", "--lon", "13.405", "-r", "500")
        self.assertEqual(self.todos.get_place("Berlin").radius_m, 500)
        places = self.run_cli("places")
        self.assertIn("* ", places)  # current place is marked
        self.assertIn("Zuhause", self.run_cli("where"))

        self.run_cli("add", "Müll", "-o", "hier")
        self.run_cli("add", "Museum", "-o", "Berlin")
        self.run_cli("add", "Überall")
        listed = self.run_cli("list")
        self.assertIn("Müll", listed)
        self.assertIn("Überall", listed)
        self.assertNotIn("Museum", listed)
        self.assertIn("Museum", self.run_cli("list", "--alle-orte"))
        self.assertNotIn("Müll", self.run_cli("list", "-o", "Berlin"))

        self.assertIn("Ort gelöscht", self.run_cli("place-delete", "Berlin"))
        self.assertIsNone(self.todos.get(2).location_id)

    def test_place_add_by_address(self):
        result = SearchResult("Schlossplatz, Stuttgart", Coordinates(48.7785, 9.1797))
        with mock.patch("classes.cli.Geocoder") as geocoder:
            geocoder.return_value.search.return_value = [result]
            output = self.run_cli("place-add", "Stadt", "--adresse", "Schlossplatz Stuttgart")
        self.assertIn("Gefunden", output)
        self.assertEqual(self.todos.get_place("Stadt").latitude, 48.7785)

    def test_place_add_errors(self):
        cli = CommandLine(self.todos, self.fmt, self.config, self.location)
        for argv in (["place-add"], ["place-add", "X", "--lat", "1"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                cli.execute(cli.parse(argv))
        with mock.patch("classes.cli.Geocoder") as geocoder:
            geocoder.return_value.search.return_value = []
            with self.assertRaises(ValueError):
                cli.execute(cli.parse(["place-add", "X", "--adresse", "gibt es nicht"]))

    def test_place_add_with_map_uses_picked_place(self):
        picked = mock.Mock(name="picked")
        picked.name, picked.position, picked.radius_m = "Karte", Coordinates(1.0, 2.0), 150
        with mock.patch("classes.cli.open_map", return_value=picked):
            self.run_cli("place-add", "--karte")
        self.assertEqual(self.todos.get_place("Karte").radius_m, 150)
        with mock.patch("classes.cli.open_map", return_value=None):
            self.assertIn("Abgebrochen", self.run_cli("place-add", "--karte"))

    def test_location_commands_need_location_feature(self):
        self.config._values["location_enabled"] = False
        cli = CommandLine(self.todos, self.fmt, self.config, self.location)
        with self.assertRaises(ValueError):
            cli.execute(cli.parse(["where"]))


class ConsoleUITest(AppTestCase):
    def run_menu(self, *inputs) -> str:
        """Runs the console menu with the given inputs and returns the output."""
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(inputs)), redirect_stdout(output):
            ConsoleUI(self.todos, self.fmt, self.config, self.location).run()
        return output.getvalue()

    def test_add_and_list_task_in_menu(self):
        self.add_place_here("Zuhause")
        output = self.run_menu("2", "Menü-Aufgabe", "", "h", "morgen", "x, y", "", "1", "0")
        self.assertIn("Aufgabe 1 angelegt", output)
        task = self.todos.get(1)
        self.assertEqual((task.priority.label, task.tags, self.todos.place_name(task.location_id)),
                         ("hoch", ["x", "y"], "Zuhause"))
        self.assertIn("Tschüss", output)

    def test_invalid_choice_and_errors_are_reported(self):
        output = self.run_menu("99", "3", "abc", "3", "5", "0")
        self.assertIn("Ungültige Auswahl", output)
        self.assertIn("ID muss eine Zahl sein", output)
        self.assertIn("Keine Aufgabe mit ID 5", output)

    def test_complete_edit_delete_in_menu(self):
        self.todos.add("Original")
        self.run_menu("3", "1", "5", "1", "Geändert", "", "n", "", "", "6", "1", "j", "0")
        self.assertEqual(self.todos.tasks, [])

    def test_report_and_statistics_in_menu(self):
        self.todos.add("Für den Bericht", due_date=days_from_today(-1))
        output = self.run_menu("13", "10", "19", "text", "bericht.txt", "0")
        self.assertIn("Statistik", output)
        self.assertIn("Eine Aufgabe ist überfällig", output)
        self.assertTrue((self.folder / "bericht.txt").exists())


class EntryPointTest(AppTestCase):
    def test_main_runs_command_and_returns_error_code(self):
        errors = io.StringIO()
        with mock.patch.object(todo, "CONFIG_FILE", self.config.path), redirect_stdout(io.StringIO()), \
                redirect_stderr(errors):
            self.assertEqual(todo.main(["add", "Über main"]), 0)
            self.assertEqual(todo.main(["done", "42"]), 1)
        self.assertIn("Keine Aufgabe mit ID 42", errors.getvalue())
        self.assertEqual(self.reload().tasks[0].title, "Über main")

    def test_ask_start_mode(self):
        with mock.patch("builtins.input", side_effect=["x", "2"]), redirect_stdout(io.StringIO()):
            self.assertEqual(todo.ask_start_mode(), "gui")
        with mock.patch("builtins.input", side_effect=[""]), redirect_stdout(io.StringIO()):
            self.assertEqual(todo.ask_start_mode(), "cli")

    def test_cli_start_mode_opens_menu(self):
        with mock.patch.object(todo, "CONFIG_FILE", self.config.path), \
                mock.patch("builtins.input", side_effect=["0"]), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(todo.main(["--cli"]), 0)
        self.assertIn("Todo-App (CLI)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
