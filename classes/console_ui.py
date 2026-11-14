"""Interactive menu in the console."""
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
from classes.todo_list import PlaceNotFoundError, TaskNotFoundError, TodoList


class ConsoleUI:
    """Interactive menu in the console (selection by number)."""
    def __init__(self, todos: TodoList, formatter: TaskFormatter, config: Config, location: LocationContext):
        """Stores the dependencies and builds the menu entries."""
        self.todos = todos
        self.location = location
        self.fmt = formatter
        self.config = config
        self.sort_by = config.default_sort
        self.show_completed = config.show_completed
        self.actions = {
            "1": ("Aufgaben anzeigen", self.show_tasks),
            "2": ("Aufgabe hinzufügen", self.add_task),
            "3": ("Aufgabe erledigen", self.complete_task),
            "4": ("Aufgabe wieder öffnen", self.reopen_task),
            "5": ("Aufgabe bearbeiten", self.edit_task),
            "6": ("Aufgabe löschen", self.delete_task),
            "7": ("Details anzeigen", self.show_details),
            "8": ("Suchen", self.search),
            "9": ("Filtern (Priorität / Tag)", self.filter_tasks),
            "10": ("Überfällig & bald fällig", self.show_due),
            "11": ("Sortierung ändern", self.change_sort),
            "12": ("Erledigte ein-/ausblenden", self.toggle_completed),
            "13": ("Statistik", self.show_statistics),
            "14": ("Erledigte entfernen", self.clear_completed),
            "15": ("Als CSV exportieren", self.export_csv),
        }
        if location.enabled:
            self.actions.update({
                "16": ("Standort anzeigen / neu orten", self.show_location),
                "17": ("Aktuellen Ort wählen", self.choose_place),
                "18": ("Orte verwalten", self.manage_places),
            })
        self.actions["19"] = ("Bericht erstellen", self.create_report)
        self.actions["0"] = ("Beenden", None)

    def run(self):
        """Main loop: show the menu, read the choice, run the action."""
        print(self.fmt.color("=== Todo-App (CLI) ===", "\033[1m"))
        self._print_reminder()
        if self.location.enabled:
            print(f"Aktueller Ort: {self.location.place_text()}")
        while True:
            self._print_menu()
            choice = input("Auswahl: ").strip()
            if choice == "0":
                print("Tschüss!")
                return
            action = self.actions.get(choice)
            if action is None:
                print("Ungültige Auswahl.")
                continue
            try:
                action[1]()
            except (ValueError, TaskNotFoundError, PlaceNotFoundError) as error:
                print(self.fmt.color(f"Fehler: {error}", "\033[31m"))
            print()

    # --- Menu entries -----------------------------------------------------------
    def show_tasks(self):
        """Shows the tasks, pre-filtered by the current place."""
        if self.location.enabled:
            place = self.location.current_place
            print(f"Ort: {place.name if place else 'kein gespeicherter Ort – alle Aufgaben'}")
        tasks = self.todos.list(self.sort_by, self.show_completed, **self.location.filter_kwargs())
        print(self.fmt.table(tasks, self._place_names()))

    def add_task(self):
        """Asks for all details and creates a new task."""
        title = input("Titel: ")
        description = input("Beschreibung (optional): ")
        priority = self._ask_priority(self.config.default_priority)
        due = self.fmt.parse_date(input(f"Fällig am ({self.fmt.date_hint}, heute, morgen, +N, leer=keins): "))
        tags = self._split_tags(input("Tags (kommagetrennt, optional): "))
        place_id = self._ask_place(self.location.current_place.id if self.location.current_place else None)
        task = self.todos.add(title, description, priority, due, tags, place_id)
        print(f"Aufgabe {task.id} angelegt.")

    def complete_task(self):
        """Marks a task as done."""
        task = self.todos.complete(self._ask_id())
        print(f"Erledigt: {task.title}")

    def reopen_task(self):
        """Sets a completed task back to open."""
        task = self.todos.reopen(self._ask_id())
        print(f"Wieder offen: {task.title}")

    def edit_task(self):
        """Edits a task; an empty input keeps the value unchanged."""
        task = self.todos.get(self._ask_id())
        print("Leer lassen = unverändert, '-' = Wert entfernen")
        changes = {}
        title = input(f"Titel [{task.title}]: ").strip()
        if title:
            changes["title"] = title
        description = input(f"Beschreibung [{task.description}]: ").strip()
        if description:
            changes["description"] = "" if description == "-" else description
        priority = input(f"Priorität [{task.priority.label}]: ").strip()
        if priority:
            changes["priority"] = Priority.parse(priority)
        due = input(f"Fällig am [{self.fmt.format_date(task.due_date)}]: ").strip()
        if due:
            changes["due_date"] = self.fmt.parse_date(due)
        tags = input(f"Tags [{', '.join(task.tags)}]: ").strip()
        if tags:
            changes["tags"] = [] if tags == "-" else self._split_tags(tags)
        if self.location.enabled:
            place_id = self._ask_place(task.location_id)
            if place_id != task.location_id:
                changes["location_id"] = place_id
        if changes:
            self.todos.update(task.id, **changes)
            print("Gespeichert.")
        else:
            print("Keine Änderungen.")

    def delete_task(self):
        """Deletes a task (with confirmation if configured)."""
        task = self.todos.get(self._ask_id())
        if self.config.confirm_delete and not self._confirm(f"'{task.title}' wirklich löschen?"):
            print("Abgebrochen.")
            return
        self.todos.delete(task.id)
        print("Gelöscht.")

    def show_details(self):
        """Shows all details of a task."""
        task = self.todos.get(self._ask_id())
        place = self.todos.place_name(task.location_id) if self.location.enabled else None
        print(self.fmt.details(task, place))

    def search(self):
        """Searches in title, description and tags."""
        print(self.fmt.table(self.todos.search(input("Suchbegriff: ").strip()), self._place_names()))

    def filter_tasks(self):
        """Filters by priority and/or tag."""
        tags = self.todos.all_tags()
        if tags:
            print("Vorhandene Tags: " + ", ".join(tags))
        priority_text = input("Priorität (leer = alle): ").strip()
        tag = input("Tag (leer = alle): ").strip().lstrip("#") or None
        priority = Priority.parse(priority_text) if priority_text else None
        tasks = self.todos.list(self.sort_by, self.show_completed, priority, tag, **self.location.filter_kwargs())
        print(self.fmt.table(tasks, self._place_names()))

    def show_due(self):
        """Shows overdue tasks and tasks that are due soon."""
        print(self.fmt.color("Überfällig:", "\033[1m"))
        print(self.fmt.table(self.todos.overdue()))
        print(self.fmt.color(f"\nFällig in den nächsten {self.config.due_soon_days} Tagen:", "\033[1m"))
        print(self.fmt.table(self.todos.due_soon(self.config.due_soon_days)))
        # short hint how urgent the situation is
        overdue = len(self.todos.overdue())
        soon = len(self.todos.due_soon(self.config.due_soon_days))
        if overdue == 0:
            if soon == 0:
                print("\nAlles im grünen Bereich.")
            else:
                if soon == 1:
                    print("\nEine Aufgabe wird bald fällig.")
                else:
                    print("\n" + str(soon) + " Aufgaben werden bald fällig.")
        else:
            if overdue == 1:
                if soon == 0:
                    print("\nEine Aufgabe ist überfällig.")
                else:
                    print("\nEine Aufgabe ist überfällig, " + str(soon) + " weitere bald fällig.")
            else:
                if soon == 0:
                    print("\n" + str(overdue) + " Aufgaben sind überfällig.")
                else:
                    print("\n" + str(overdue) + " Aufgaben sind überfällig, " + str(soon) + " weitere bald fällig.")

    def change_sort(self):
        """Changes the sort order of the list."""
        print("Sortierungen: " + ", ".join(SORT_KEYS))
        choice = input(f"Sortieren nach [{self.sort_by}]: ").strip().lower()
        if choice:
            if choice not in SORT_KEYS:
                raise ValueError(f"Unbekannte Sortierung: {choice}")
            self.sort_by = choice
        print(f"Sortierung: {self.sort_by}")

    def toggle_completed(self):
        """Shows or hides completed tasks."""
        self.show_completed = not self.show_completed
        print("Erledigte werden " + ("angezeigt." if self.show_completed else "ausgeblendet."))

    def show_statistics(self):
        """Prints the statistics."""
        print(self.fmt.statistics(self.todos.statistics()))

    def clear_completed(self):
        """Removes all completed tasks."""
        if self._confirm("Alle erledigten Aufgaben entfernen?"):
            print(f"{self.todos.clear_completed()} Aufgabe(n) entfernt.")

    def export_csv(self):
        """Exports all tasks as a CSV file."""
        target = input("Dateiname [todos_export.csv]: ").strip() or "todos_export.csv"
        path = Path(target)
        if not path.is_absolute():
            path = self.config.base_dir / path
        CsvExporter.export(self.todos.list("id"), path)
        print(f"Exportiert nach {path}")

    def show_location(self):
        """Locates again and shows the position, the place and all saved places."""
        print("Ermittle Standort ...")
        self.location.position(refresh=True)
        print(f"Standort: {self.location.position_text()}")
        print(f"Ort:      {self.location.place_text()}")
        self._print_places()

    def choose_place(self):
        """Sets the current place by hand or switches back to automatic."""
        self._print_places()
        text = input("Ort (Name/ID, 'auto' = automatisch erkennen, '-' = kein Ort): ").strip()
        if text.lower() == "auto" or not text:
            self.location.use_automatic()
        elif text == "-":
            self.location.choose(None)
        else:
            self.location.choose(self.todos.get_place(text))
        print(f"Aktueller Ort: {self.location.place_text()}")

    def create_report(self):
        """Creates a report as text, HTML or CSV."""
        manager = TaskReportManager(self.todos, self.config, self.fmt, self.location,
                                    include_places=self.location.enabled)
        report_format = input("Format (text/html/csv) [text]: ").strip().lower() or "text"
        if report_format not in ("text", "html", "csv"):
            raise ValueError("Format muss text, html oder csv sein")
        target = input(f"Dateiname [bericht.{'txt' if report_format == 'text' else report_format}]: ").strip()
        path = Path(target or f"bericht.{'txt' if report_format == 'text' else report_format}")
        if not path.is_absolute():
            path = self.config.base_dir / path
        manager.save_report(path, report_format)
        print(f"Bericht gespeichert: {path}")
        print(manager.summary())
        for reminder in manager.build_reminders():
            print("  - " + reminder)

    def manage_places(self):
        """Submenu for creating, editing and deleting places."""
        self._print_places()
        print("  k) Neuer Ort auf der Karte    s) Neuer Ort per Adresssuche    a) Aktuellen Standort speichern")
        print("  b) Ort bearbeiten (Karte)     l) Ort löschen                  [Enter = zurück]")
        choice = input("Auswahl: ").strip().lower()
        if choice == "k":
            self._save_picked(open_map(self.config, self.location, None, self.todos.places))
        elif choice == "b":
            place = self.todos.get_place(input("Ort (Name/ID): "))
            others = [p for p in self.todos.places if p is not place]
            picked = open_map(self.config, self.location, place, others)
            if picked:
                self.todos.update_place(place.id, picked.name, picked.position, picked.radius_m)
                print(f"Ort '{picked.name}' gespeichert.")
        elif choice in ("s", "a"):
            position = self._search_address() if choice == "s" else self.location.position(refresh=True)
            if position is None:
                raise ValueError(self.location.position_text() if choice == "a" else "Keine Adresse gewählt")
            name = input("Name des Orts (z. B. Zuhause, Uni): ")
            radius = input(f"Radius in Metern [{self.config.location_default_radius_m}]: ").strip()
            place = self.todos.add_place(name, position, int(radius) if radius else self.config.location_default_radius_m)
            print(f"Ort '{place.name}' gespeichert.")
        elif choice == "l":
            place = self.todos.get_place(input("Ort (Name/ID): "))
            if self._confirm(f"Ort '{place.name}' löschen? Aufgaben bleiben erhalten."):
                self.todos.delete_place(place.id)
                print("Gelöscht.")

    def _save_picked(self, picked):
        """Saves a place chosen on the map."""
        if picked is None:
            print("Abgebrochen.")
            return
        place = self.todos.add_place(picked.name, picked.position, picked.radius_m)
        print(f"Ort '{place.name}' gespeichert.")

    @staticmethod
    def _search_address() -> Optional[Coordinates]:
        """Searches an address and lets the user pick a result."""
        query = input("Adresse oder Ort (z. B. 'Keplerstraße 7, Stuttgart'): ")
        try:
            results = Geocoder().search(query)
        except OSError as error:
            raise ValueError(f"Adresssuche fehlgeschlagen (Internetverbindung?): {error}") from error
        if not results:
            print("Nichts gefunden.")
            return None
        for number, result in enumerate(results, start=1):
            print(f"  {number}) {result.label}")
        choice = input("Nummer [1]: ").strip() or "1"
        if not choice.isdigit() or not 1 <= int(choice) <= len(results):
            raise ValueError("Ungültige Nummer")
        return results[int(choice) - 1].position

    # --- Helpers ----------------------------------------------------------------
    def _place_names(self) -> Optional[dict]:
        """Mapping place id -> name for the table column 'Ort'."""
        return {p.id: p.name for p in self.todos.places} if self.location.enabled else None

    def _print_places(self):
        """Prints all places with radius and distance."""
        rows = self.location.distances()
        if not rows:
            print("Noch keine Orte gespeichert.")
            return
        current = self.location.current_place
        print(self.fmt.color("Gespeicherte Orte:", "\033[1m"))
        for place, distance in rows:
            marker = "*" if place == current else " "
            dist = format_distance(distance) if distance is not None else "?"
            print(f" {marker} {place.id:>3}  {place.name:<16} Radius {place.radius_m:>5} m   Entfernung {dist:>9}")

    def _ask_place(self, default_id: Optional[int]) -> Optional[int]:
        """Asks for a place. Enter = default, '-' = no place."""
        if not self.location.enabled or not self.todos.places:
            return default_id
        names = ", ".join(p.name for p in self.todos.places)
        default = self.todos.place_name(default_id) or "-"
        text = input(f"Ort ({names}; '-' = keiner) [{default}]: ").strip()
        if not text:
            return default_id
        if text == "-":
            return None
        return self.todos.get_place(text).id

    def _print_menu(self):
        """Prints the menu entries."""
        for key, (label, _) in self.actions.items():
            print(f"  {key:>2}) {label}")

    def _print_reminder(self):
        """Points out overdue tasks on start."""
        overdue = self.todos.overdue()
        if overdue:
            print(self.fmt.color(f"Achtung: {len(overdue)} überfällige Aufgabe(n)!", "\033[31m"))

    @staticmethod
    def _ask_id() -> int:
        """Asks for a task id and checks that it is a number."""
        text = input("ID: ").strip()
        if not text.isdigit():
            raise ValueError("ID muss eine Zahl sein")
        return int(text)

    @staticmethod
    def _ask_priority(default: str) -> Priority:
        """Asks for the priority (Enter = default value)."""
        text = input(f"Priorität (niedrig/mittel/hoch) [{default}]: ").strip()
        return Priority.parse(text or default)

    @staticmethod
    def _split_tags(text: str) -> list:
        """Splits a comma-separated input into a list of tags."""
        return [t.strip() for t in text.split(",") if t.strip()]

    @staticmethod
    def _confirm(question: str) -> bool:
        """Yes/no question; True for 'j' or 'ja'."""
        return input(f"{question} (j/n): ").strip().lower() in ("j", "ja", "y", "yes")
