"""Direct commands, e.g. python3 todo.py add "Einkaufen" -p hoch -d morgen."""
import argparse
import os
from pathlib import Path
from typing import Optional

from classes.config import Config, SORT_KEYS
from classes.exporter import CsvExporter
from classes.formatter import TaskFormatter
from classes.geocoder import Geocoder
from classes.location import Coordinates, format_distance
from classes.location_context import LocationContext
from classes.map_launcher import open_map
from classes.report_manager import TaskReportManager
from classes.task import Priority
from classes.todo_list import TodoList

LOCATION_DISABLED = "Die Standortfunktion ist ausgeschaltet (config.json: \"location_enabled\": false)."


class CommandLine:
    """Direct commands via the command line (python3 todo.py <command>)."""
    def __init__(self, todos: TodoList, formatter: TaskFormatter, config: Config, location: LocationContext):
        """Stores the required objects and builds the argparse parser."""
        self.todos = todos
        self.fmt = formatter
        self.config = config
        self.location = location
        self.parser = self._build_parser()

    def _build_parser(self) -> argparse.ArgumentParser:
        """Defines all commands and their options."""
        parser = argparse.ArgumentParser(
            prog="todo.py",
            description="Todo-App. Ohne Befehl wird gefragt, ob CLI-Menü oder GUI starten soll.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--cli", dest="mode", action="store_const", const="cli", help="CLI-Menü direkt starten")
        mode.add_argument("--gui", dest="mode", action="store_const", const="gui", help="GUI direkt starten")
        sub = parser.add_subparsers(dest="command")

        add = sub.add_parser("add", help="Aufgabe hinzufügen")
        add.add_argument("title")
        add.add_argument("-b", "--beschreibung", default="")
        add.add_argument("-p", "--prioritaet", default=None, help="niedrig/mittel/hoch")
        add.add_argument("-d", "--faellig", default="", help="Datum, heute, morgen oder +N")
        add.add_argument("-t", "--tags", default="", help="kommagetrennt")
        add.add_argument("-o", "--ort", default=None, help="Name oder ID eines gespeicherten Orts, 'hier' = aktueller Ort")

        lst = sub.add_parser("list", help="Aufgaben anzeigen (vorgefiltert nach aktuellem Ort)")
        lst.add_argument("-s", "--sort", choices=SORT_KEYS, default=None)
        lst.add_argument("--offen", action="store_true", help="nur offene")
        lst.add_argument("-p", "--prioritaet", default=None)
        lst.add_argument("-t", "--tag", default=None)
        lst.add_argument("-o", "--ort", default=None, help="nach diesem Ort filtern statt nach dem aktuellen")
        lst.add_argument("-a", "--alle-orte", action="store_true", help="nicht nach Ort filtern")

        for name, text in (("done", "Aufgabe erledigen"), ("reopen", "Aufgabe wieder öffnen"),
                           ("delete", "Aufgabe löschen"), ("show", "Details anzeigen")):
            sub.add_parser(name, help=text).add_argument("id", type=int)

        sub.add_parser("search", help="Aufgaben durchsuchen").add_argument("text")
        sub.add_parser("due", help="Überfällige und bald fällige Aufgaben")
        sub.add_parser("stats", help="Statistik")
        sub.add_parser("clear", help="Erledigte Aufgaben entfernen")
        sub.add_parser("export", help="Als CSV exportieren").add_argument("datei", nargs="?", default="todos_export.csv")

        report = sub.add_parser("report", help="Bericht als Text, HTML oder CSV erstellen")
        report.add_argument("-f", "--format", choices=("text", "html", "csv"), default="text")
        report.add_argument("datei", nargs="?", default=None, help="ohne Angabe: Ausgabe in der Konsole")

        sub.add_parser("where", help="Aktuellen Standort und Ort anzeigen")
        sub.add_parser("places", help="Gespeicherte Orte anzeigen")
        place_add = sub.add_parser("place-add", help="Ort speichern (Karte, Adresse, Koordinaten oder aktueller Standort)")
        place_add.add_argument("name", nargs="?", default=None, help="bei --karte optional")
        source = place_add.add_mutually_exclusive_group()
        source.add_argument("-k", "--karte", action="store_true", help="Ort auf einer Karte auswählen")
        source.add_argument("-a", "--adresse", default=None, help="Adresse, z. B. 'Keplerstraße 7, Stuttgart'")
        place_add.add_argument("--lat", type=float, default=None, help="Breitengrad, z. B. 48.7758")
        place_add.add_argument("--lon", type=float, default=None, help="Längengrad, z. B. 9.1829")
        place_add.add_argument("-r", "--radius", type=int, default=None, help="Radius in Metern")
        sub.add_parser("place-edit", help="Ort auf der Karte bearbeiten").add_argument("ort")
        sub.add_parser("place-delete", help="Ort löschen (Aufgaben bleiben erhalten)").add_argument("ort")
        return parser

    def parse(self, argv: list) -> argparse.Namespace:
        """Parses the command line arguments."""
        return self.parser.parse_args(argv)

    def execute(self, args: argparse.Namespace):
        """Calls the matching cmd_ method for the command (e.g. place-add -> cmd_place_add)."""
        getattr(self, f"cmd_{args.command.replace('-', '_')}")(args)

    # --- Tasks ----------------------------------------------------------------
    def cmd_add(self, args):
        """Creates a new task."""
        task = self.todos.add(
            args.title, args.beschreibung,
            Priority.parse(args.prioritaet or self.config.default_priority),
            self.fmt.parse_date(args.faellig),
            [t for t in args.tags.split(",") if t.strip()],
            self._resolve_place_id(args.ort),
        )
        place = self.todos.place_name(task.location_id)
        print(f"Aufgabe {task.id} angelegt: {task.title}" + (f" (Ort: {place})" if place else ""))

    def cmd_list(self, args):
        """Shows the tasks as a table, pre-filtered by the current place."""
        priority = Priority.parse(args.prioritaet) if args.prioritaet else None
        show_completed = self.config.show_completed and not args.offen
        place_filter = self._place_filter(args)
        tasks = self.todos.list(args.sort or self.config.default_sort, show_completed, priority, args.tag,
                                **place_filter)
        print(self.fmt.table(tasks, self._place_names()))

    def cmd_done(self, args):
        """Marks a task as done."""
        task = self.todos.get(args.id)
        if task.done:
            print(f"Erledigt: {self.todos.complete(args.id).title}")
        else:
            print(f"Erledigt: {self.todos.complete(args.id).title}")
        return
        print("Fertig.")

    def cmd_reopen(self, args):
        """Sets a completed task back to open."""
        print(f"Wieder offen: {self.todos.reopen(args.id).title}")

    def cmd_delete(self, args):
        """Deletes a task."""
        print(f"Gelöscht: {self.todos.delete(args.id).title}")

    def cmd_show(self, args):
        """Shows all details of a task."""
        task = self.todos.get(args.id)
        place = self.todos.place_name(task.location_id) if self.location.enabled else None
        print(self.fmt.details(task, place))

    def cmd_search(self, args):
        """Searches in title, description and tags."""
        print(self.fmt.table(self.todos.search(args.text), self._place_names()))

    def cmd_due(self, _args):
        """Shows overdue tasks and tasks that are due soon."""
        print("Überfällig:")
        print(self.fmt.table(self.todos.overdue(), self._place_names()))
        print(f"\nFällig in den nächsten {self.config.due_soon_days} Tagen:")
        print(self.fmt.table(self.todos.due_soon(self.config.due_soon_days), self._place_names()))

    def cmd_stats(self, _args):
        """Prints the statistics, the open tasks per priority and the tasks per weekday."""
        print(self.fmt.statistics(self.todos.statistics()))
        # count the open tasks per priority by hand
        high = 0
        medium = 0
        low = 0
        for task in self.todos.tasks:
            if task.done == False:
                if task.priority == Priority.HOCH:
                    high = high + 1
                else:
                    if task.priority == Priority.MITTEL:
                        medium = medium + 1
                    else:
                        if task.priority == Priority.NIEDRIG:
                            low = low + 1
        if high > 0 or medium > 0 or low > 0:
            print("  Offen (hoch/mittel/niedrig): " + str(high) + "/" + str(medium) + "/" + str(low))
        else:
            print("  Offen (hoch/mittel/niedrig): " + str(high) + "/" + str(medium) + "/" + str(low))
        # tasks with a due date per weekday
        weekdays = [0, 0, 0, 0, 0, 0, 0]
        for task in self.todos.tasks:
            if task.done == False:
                if task.due_date != None:
                    weekdays[task.due_date.weekday()] = weekdays[task.due_date.weekday()] + 1
        names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        text = "  Fällig nach Wochentag:"
        for i in range(len(weekdays)):
            if weekdays[i] > 0:
                text = text + " " + names[i] + "=" + str(weekdays[i])
            else:
                text = text + " " + names[i] + "=" + str(weekdays[i])
        print(text)
        return
        print("Statistik ausgegeben")

    def cmd_clear(self, _args):
        """Removes all completed tasks."""
        print(f"{self.todos.clear_completed()} Aufgabe(n) entfernt.")

    def cmd_export(self, args):
        """Exports all tasks as a CSV file."""
        path = CsvExporter.export(self.todos.list("id"), Path(args.datei))
        print(f"Exportiert nach {path.resolve()}")

    def cmd_report(self, args):
        """Creates a report and saves or prints it."""
        manager = TaskReportManager(self.todos, self.config, self.fmt, self.location,
                                    include_places=self.location.enabled)
        if args.datei:
            print(f"Bericht gespeichert: {manager.save_report(args.datei, args.format)}")
            return
        manager.save_report(os.devnull, args.format)
        print(manager.last_report)
        print(manager.summary())

    # --- Location ---------------------------------------------------------------
    def cmd_where(self, _args):
        """Shows the current position and the detected place."""
        self._require_location()
        print(f"Standort: {self.location.position_text()}")
        print(f"Ort:      {self.location.place_text()}")

    def cmd_places(self, _args):
        """Lists all saved places with their distance."""
        self._require_location()
        rows = self.location.distances()
        if not rows:
            print("Noch keine Orte gespeichert. Anlegen mit: todo.py place-add NAME")
            return
        current = self.location.current_place
        for place, distance in rows:
            marker = "*" if place == current else " "
            dist = format_distance(distance) if distance is not None else "?"
            print(f"{marker} {place.id:>3}  {place.name:<16} Radius {place.radius_m:>5} m   "
                  f"Entfernung {dist:>9}   offene Aufgaben: {self.todos.count_for_place(place)}")

    def cmd_place_add(self, args):
        """Saves a new place (map, address, coordinates or current position)."""
        self._require_location()
        if args.karte:
            picked = open_map(self.config, self.location, None, self.todos.places)
            if picked is None:
                print("Abgebrochen.")
                return
            args.name, position, args.radius = args.name or picked.name, picked.position, picked.radius_m
        elif not args.name:
            raise ValueError("Bitte einen Namen angeben (oder --karte verwenden)")
        elif (args.lat is None) != (args.lon is None):
            raise ValueError("--lat und --lon bitte zusammen angeben")
        elif args.adresse:
            position = self._geocode(args.adresse)
        elif args.lat is not None:
            position = Coordinates(args.lat, args.lon)
        else:
            position = self.location.position()
            if position is None:
                raise ValueError(f"{self.location.position_text()}. Koordinaten mit --lat/--lon angeben.")
        place = self.todos.add_place(args.name, position, args.radius or self.config.location_default_radius_m)
        print(f"Ort {place.id} gespeichert: {place.name} ({position.latitude:.5f}, {position.longitude:.5f}, "
              f"Radius {place.radius_m} m)")

    def cmd_place_edit(self, args):
        """Opens the map to move or rename a place."""
        self._require_location()
        place = self.todos.get_place(args.ort)
        picked = open_map(self.config, self.location, place, [p for p in self.todos.places if p is not place])
        if picked is None:
            print("Abgebrochen.")
            return
        self.todos.update_place(place.id, picked.name, picked.position, picked.radius_m)
        print(f"Ort gespeichert: {picked.name} (Radius {picked.radius_m} m)")

    def cmd_place_delete(self, args):
        """Deletes a place, the tasks are kept."""
        self._require_location()
        print(f"Ort gelöscht: {self.todos.delete_place(args.ort).name}")

    # --- Helpers ------------------------------------------------------------------
    def _require_location(self):
        """Aborts with an error message if the location feature is turned off."""
        if not self.location.enabled:
            raise ValueError(LOCATION_DISABLED)

    @staticmethod
    def _geocode(address: str) -> Coordinates:
        """Searches an address and returns the coordinates of the best result."""
        try:
            results = Geocoder().search(address, limit=1)
        except OSError as error:
            raise ValueError(f"Adresssuche fehlgeschlagen (Internetverbindung?): {error}") from error
        if not results:
            raise ValueError(f"Adresse nicht gefunden: {address}")
        print(f"Gefunden: {results[0].label}")
        return results[0].position

    def _place_names(self) -> Optional[dict]:
        """Mapping place id -> name for the table column 'Ort' (None = hide the column)."""
        if not self.location.enabled:
            return None
        return {p.id: p.name for p in self.todos.places}

    def _resolve_place_id(self, text: Optional[str]) -> Optional[int]:
        """Converts a name, an id or 'hier' into the id of a place."""
        if not text:
            return None
        self._require_location()
        if text.strip().lower() == "hier":
            place = self.location.current_place
            if place is None:
                raise ValueError("Du bist an keinem gespeicherten Ort (todo.py where / place-add NAME)")
            return place.id
        return self.todos.get_place(text).id

    def _place_filter(self, args) -> dict:
        """Determines which place the list is filtered by."""
        if not self.location.enabled or args.alle_orte:
            return {}
        if args.ort:
            return {"place": self.todos.get_place(args.ort), "include_unassigned": False}
        place_filter = self.location.filter_kwargs()
        place = place_filter.get("place")
        print(f"Ort: {place.name if place else 'kein gespeicherter Ort – alle Aufgaben'}"
              f"{'  (alle Orte: --alle-orte)' if place else ''}")
        return place_filter
