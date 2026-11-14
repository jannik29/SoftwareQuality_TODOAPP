"""Graphical user interface (tkinter, included in Python - runs on Windows, macOS and Linux)."""
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from classes.config import Config, SORT_KEYS
from classes.exporter import CsvExporter
from classes.formatter import TaskFormatter
from classes.location import format_distance
from classes.location_context import LocationContext
from classes.map_picker import pick_on_map
from classes.report_manager import TaskReportManager
from classes.task import Priority, Task
from classes.todo_list import PlaceNotFoundError, TaskNotFoundError, TodoList

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"                   # Cmd on macOS, Ctrl on Windows/Linux
RIGHT_CLICK = ("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)

ALL = "alle"
AUTO_PLACE = "automatisch"
NO_PLACE = "– kein Ort –"
HINT = "#777777"
ROW_COLORS = {"done": "#8a8a8a", "overdue": "#c62828", "soon": "#e07b00"}
ERRORS = (ValueError, TaskNotFoundError, PlaceNotFoundError)


def place_choices(todos: TodoList) -> list:
    """Entries for place drop-downs: 'no place' plus all saved places."""
    return [NO_PLACE] + [p.name for p in todos.places]


def place_id_from_choice(todos: TodoList, choice: str) -> Optional[int]:
    """Converts the selected entry of a place drop-down into a place id."""
    return None if choice in ("", NO_PLACE) else todos.get_place(choice).id


class TaskDialog(tk.Toplevel):
    """Dialog for creating or editing a task. The result is stored in self.result afterwards."""

    def __init__(self, parent, todos: TodoList, fmt: TaskFormatter, default_priority: str,
                 task: Optional[Task] = None, default_place_id: Optional[int] = None, with_place: bool = True):
        """Builds the form and waits until the dialog is closed."""
        super().__init__(parent)
        self.todos = todos
        self.fmt = fmt
        self.with_place = with_place
        self.result = None
        self.title("Aufgabe bearbeiten" if task else "Neue Aufgabe")
        self.transient(parent)
        self.resizable(False, False)

        frame = ttk.Frame(self, padding=14)
        frame.grid(sticky="nsew")
        self.title_var = tk.StringVar(value=task.title if task else "")
        self.priority_var = tk.StringVar(value=task.priority.label if task else default_priority)
        self.due_var = tk.StringVar(value=fmt.format_date(task.due_date) if task and task.due_date else "")
        self.tags_var = tk.StringVar(value=", ".join(task.tags) if task else "")
        place_id = task.location_id if task else default_place_id
        self.place_var = tk.StringVar(value=todos.place_name(place_id) or NO_PLACE)

        title_entry = self._row(frame, 0, "Titel *", ttk.Entry(frame, textvariable=self.title_var, width=46))
        self.description = tk.Text(frame, width=46, height=5, wrap="word", font="TkDefaultFont")
        self.description.insert("1.0", task.description if task else "")
        self._row(frame, 1, "Beschreibung", self.description)
        self._row(frame, 2, "Priorität", ttk.Combobox(frame, textvariable=self.priority_var, state="readonly",
                                                      values=[p.label for p in Priority], width=12))
        self._row(frame, 3, "Fällig am", ttk.Entry(frame, textvariable=self.due_var, width=16))
        self._hint(frame, 4, f"Format {fmt.date_hint}, 'heute', 'morgen' oder '+N'")
        self._row(frame, 5, "Tags", ttk.Entry(frame, textvariable=self.tags_var, width=46))
        self._hint(frame, 6, "kommagetrennt, z. B. uni, sqe")
        if with_place:
            self._row(frame, 7, "Ort", ttk.Combobox(frame, textvariable=self.place_var, state="readonly",
                                                    values=place_choices(todos), width=24))
            self._hint(frame, 8, "Aufgabe erscheint automatisch, wenn du an diesem Ort bist")

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Speichern", command=self._save).pack(side="right", padx=6)

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        title_entry.focus_set()
        self.grab_set()
        self.wait_window()

    @staticmethod
    def _row(frame, row: int, label: str, widget):
        """Creates a form row from a label and an input field."""
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=4)
        widget.grid(row=row, column=1, sticky="w", pady=4)
        return widget

    @staticmethod
    def _hint(frame, row: int, text: str):
        """Grey hint text below an input field."""
        ttk.Label(frame, text=text, foreground=HINT).grid(row=row, column=1, sticky="w")

    def _save(self):
        """Validates the input and stores the result in self.result."""
        if not self.title_var.get().strip():
            messagebox.showerror("Fehlender Titel", "Bitte einen Titel eingeben.", parent=self)
            return
        try:
            due = self.fmt.parse_date(self.due_var.get())
        except ValueError as error:
            messagebox.showerror("Ungültiges Datum", str(error), parent=self)
            return
        self.result = {
            "title": self.title_var.get(),
            "description": self.description.get("1.0", "end").strip(),
            "priority": Priority.parse(self.priority_var.get()),
            "due_date": due,
            "tags": [t.strip() for t in self.tags_var.get().split(",") if t.strip()],
        }
        if self.with_place:
            self.result["location_id"] = place_id_from_choice(self.todos, self.place_var.get())
        self.destroy()


class PlacesDialog(tk.Toplevel):
    """Shows places, creates/edits them on the map and deletes them."""

    def __init__(self, parent, todos: TodoList, location: LocationContext, config: Config):
        """Builds the list and the buttons and waits until the dialog is closed."""
        super().__init__(parent)
        self.todos = todos
        self.location = location
        self.config = config
        self.changed = False
        self.title("Orte verwalten")
        self.transient(parent)
        self.minsize(600, 340)

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        columns = (("name", "Name", 160), ("radius", "Radius", 80), ("distance", "Entfernung", 100),
                   ("open", "Offene Aufgaben", 110), ("coords", "Koordinaten", 170))
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=9,
                                 selectmode="browse")
        for key, heading, width in columns:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._edit())

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Neuer Ort auf Karte ...", command=self._add).pack(side="left")
        ttk.Button(buttons, text="Bearbeiten ...", command=self._edit).pack(side="left", padx=6)
        ttk.Button(buttons, text="Löschen", command=self._delete).pack(side="left")
        ttk.Button(buttons, text="Schließen", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh()
        self.grab_set()
        self.wait_window()

    def _refresh(self):
        """Reloads the list of places."""
        self.tree.delete(*self.tree.get_children())
        for place, distance in self.location.distances():
            self.tree.insert("", "end", iid=str(place.id), values=(
                place.name, f"{place.radius_m} m", format_distance(distance) if distance is not None else "?",
                self.todos.count_for_place(place), f"{place.latitude:.5f}, {place.longitude:.5f}"))

    def _open_map(self, place=None):
        """Opens the map to create or edit a place."""
        others = [p for p in self.todos.places if p is not place]
        picked = pick_on_map(self.config, self.location, place, others, parent=self)
        self.grab_set()  # make the dialog modal again after the map was closed
        return picked

    def _add(self):
        """Creates a new place via the map."""
        picked = self._open_map()
        if picked:
            self._save(lambda: self.todos.add_place(picked.name, picked.position, picked.radius_m))

    def _edit(self):
        """Edits the selected place on the map."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Ort auswählen.", parent=self)
            return
        place = self.todos.get_place(int(selection[0]))
        picked = self._open_map(place)
        if picked:
            self._save(lambda: self.todos.update_place(place.id, picked.name, picked.position, picked.radius_m))

    def _save(self, action):
        """Runs a save action and shows errors as a message."""
        try:
            action()
        except ERRORS as error:
            messagebox.showerror("Ort", str(error), parent=self)
            return
        self.changed = True
        self._refresh()

    def _delete(self):
        """Deletes the selected place after confirmation."""
        selection = self.tree.selection()
        if not selection:
            return
        place = self.todos.get_place(int(selection[0]))
        if messagebox.askyesno("Ort löschen", f"'{place.name}' löschen?\nZugeordnete Aufgaben bleiben erhalten.",
                               parent=self):
            self.todos.delete_place(place.id)
            self.changed = True
            self._refresh()


class TodoGui:
    """Main window: list with filters, location bar, actions via buttons, keyboard or context menu."""

    def __init__(self, todos: TodoList, formatter: TaskFormatter, config: Config, location: LocationContext):
        """Creates the main window with all areas."""
        self.todos = todos
        self.fmt = formatter
        self.config = config
        self.location = location

        self.root = tk.Tk()
        self.root.title("Todo-App")
        self.root.geometry("1040x640")
        self.root.minsize(820, 440)

        self.search_var = tk.StringVar()
        self.priority_var = tk.StringVar(value=ALL)
        self.tag_var = tk.StringVar(value=ALL)
        self.sort_var = tk.StringVar(value=config.default_sort)
        self.show_done_var = tk.BooleanVar(value=config.show_completed)
        self.status_var = tk.StringVar()
        self.position_var = tk.StringVar(value="Standort wird ermittelt ...")
        self.place_var = tk.StringVar(value=AUTO_PLACE)
        self.place_filter_var = tk.BooleanVar(value=True)
        self._locating = False

        self._build_filter_bar()
        if location.enabled:
            self._build_location_bar()
        self._build_table()
        self._build_detail_and_buttons()
        self._build_menu()
        self._bind_keys()
        self.refresh()

    def run(self):
        """Shows the window and starts the tkinter event loop."""
        overdue = self.todos.overdue()
        if overdue:
            self.root.after(300, lambda: messagebox.showwarning(
                "Überfällig", f"Du hast {len(overdue)} überfällige Aufgabe(n).", parent=self.root))
        if self.location.enabled:
            self.root.after(100, self.locate)
        self.root.mainloop()

    # --- Layout -----------------------------------------------------------------
    def _build_filter_bar(self):
        """Top bar: search, priority, tag, sort order, show completed."""
        bar = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Suche:").pack(side="left")
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=22)
        self.search_entry.pack(side="left", padx=(4, 14))
        ttk.Label(bar, text="Priorität:").pack(side="left")
        ttk.Combobox(bar, textvariable=self.priority_var, state="readonly", width=9,
                     values=[ALL] + [p.label for p in Priority]).pack(side="left", padx=(4, 14))
        ttk.Label(bar, text="Tag:").pack(side="left")
        self.tag_box = ttk.Combobox(bar, textvariable=self.tag_var, state="readonly", width=12)
        self.tag_box.pack(side="left", padx=(4, 14))
        ttk.Label(bar, text="Sortierung:").pack(side="left")
        ttk.Combobox(bar, textvariable=self.sort_var, state="readonly", width=10,
                     values=SORT_KEYS).pack(side="left", padx=(4, 14))
        ttk.Checkbutton(bar, text="Erledigte anzeigen", variable=self.show_done_var,
                        command=self.refresh).pack(side="left")
        for var in (self.search_var, self.priority_var, self.tag_var, self.sort_var):
            var.trace_add("write", lambda *_: self.refresh())

    def _build_location_bar(self):
        """Second bar: position, current place, place filter, manage places."""
        bar = ttk.Frame(self.root, padding=(10, 2, 10, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Standort:").pack(side="left")
        ttk.Label(bar, textvariable=self.position_var, foreground=HINT).pack(side="left", padx=(4, 14))
        ttk.Button(bar, text="Orte verwalten ...", command=self.manage_places).pack(side="right")
        ttk.Button(bar, text="Neu orten", command=self.locate).pack(side="right", padx=6)
        ttk.Checkbutton(bar, text="Nach Ort filtern", variable=self.place_filter_var,
                        command=self.refresh).pack(side="right", padx=(10, 6))
        self.place_box = ttk.Combobox(bar, textvariable=self.place_var, state="readonly", width=18)
        self.place_box.pack(side="right")
        ttk.Label(bar, text="Aktueller Ort:").pack(side="right", padx=(0, 4))
        self.place_box.bind("<<ComboboxSelected>>", lambda _e: self._on_place_chosen())

    def _columns(self) -> tuple:
        """Columns of the task table (the column 'Ort' only if the location feature is on)."""
        columns = [("id", "ID", 45), ("status", "Status", 70), ("priority", "Priorität", 75),
                   ("due", "Fällig", 95)]
        if self.location.enabled:
            columns.append(("place", "Ort", 110))
        return tuple(columns + [("title", "Titel", 330), ("tags", "Tags", 170)])

    def _build_table(self):
        """Task table with scroll bar."""
        frame = ttk.Frame(self.root, padding=(10, 4))
        frame.pack(fill="both", expand=True)
        columns = self._columns()
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, heading, width in columns:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="e" if key == "id" else "w", stretch=key == "title")
        for tag, color in ROW_COLORS.items():
            self.tree.tag_configure(tag, foreground=color)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_details())
        self.tree.bind("<Double-1>", lambda _e: self.edit_task())

    def _build_detail_and_buttons(self):
        """Detail area, action buttons and status bar."""
        bottom = ttk.Frame(self.root, padding=(10, 4, 10, 0))
        bottom.pack(fill="x")
        self.detail_label = ttk.Label(bottom, text="", justify="left", anchor="nw", wraplength=960)
        self.detail_label.pack(fill="x", pady=(0, 6))

        buttons = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        buttons.pack(fill="x")
        for text, command in (("Neu", self.add_task), ("Bearbeiten", self.edit_task),
                              ("Erledigt / Offen", self.toggle_done), ("Löschen", self.delete_task)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))
        for text, command in (("Bericht", self.create_report), ("CSV-Export", self.export_csv),
                              ("Statistik", self.show_statistics),
                              ("Erledigte entfernen", self.clear_completed)):
            ttk.Button(buttons, text=text, command=command).pack(side="right", padx=(6, 0))

        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w",
                  padding=(10, 3)).pack(fill="x", side="bottom")

    def _build_menu(self):
        """Context menu for a right click on a task."""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Bearbeiten", command=self.edit_task)
        self.context_menu.add_command(label="Erledigt / Offen", command=self.toggle_done)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Löschen", command=self.delete_task)
        for event in RIGHT_CLICK:
            self.tree.bind(event, self._open_context_menu)

    def _bind_keys(self):
        """Keyboard shortcuts (Cmd on the Mac, Ctrl on Windows/Linux)."""
        self.root.bind(f"<{MOD}-n>", lambda _e: self.add_task())
        self.root.bind(f"<{MOD}-f>", lambda _e: self.search_entry.focus_set())
        self.tree.bind("<Return>", lambda _e: self.edit_task())
        self.tree.bind("<space>", lambda _e: self.toggle_done())
        self.tree.bind("<Delete>", lambda _e: self.delete_task())
        if IS_MAC:  # Mac keyboards usually have no Delete key
            self.tree.bind("<BackSpace>", lambda _e: self.delete_task())

    # --- Location -----------------------------------------------------------------
    def locate(self):
        """Locates in the background so that the window does not freeze."""
        if self._locating:
            return
        self._locating = True
        self.position_var.set("Standort wird ermittelt ...")
        worker = threading.Thread(target=lambda: self.location.position(refresh=True), daemon=True)
        worker.start()
        self._wait_for_location(worker)

    def _wait_for_location(self, worker: threading.Thread):
        """Checks regularly whether the background location lookup has finished."""
        if worker.is_alive():
            self.root.after(150, lambda: self._wait_for_location(worker))
            return
        self._locating = False
        self.position_var.set(self.location.position_text())
        self.refresh()

    def _on_place_chosen(self):
        """Reacts to the selection in the drop-down 'Aktueller Ort'."""
        choice = self.place_var.get()
        if choice == AUTO_PLACE:
            self.location.use_automatic()
        elif choice == NO_PLACE:
            self.location.choose(None)
        else:
            self.location.choose(self.todos.get_place(choice))
        self.refresh()

    def manage_places(self):
        """Opens the dialog for managing places."""
        dialog = PlacesDialog(self.root, self.todos, self.location, self.config)
        if dialog.changed:
            self.refresh()

    def _update_location_bar(self):
        """Updates the place drop-down in the location bar."""
        values = [AUTO_PLACE] + place_choices(self.todos)
        self.place_box["values"] = values
        if self.location.manual and self.place_var.get() not in values:  # the chosen place was deleted
            self.location.use_automatic()
        if not self.location.manual:
            detected = self.location.current_place
            self.place_var.set(f"{AUTO_PLACE}: {detected.name}" if detected else AUTO_PLACE)

    def _place_filter(self) -> dict:
        """Filter arguments for the place (empty if the place filter is off)."""
        if not self.location.enabled or not self.place_filter_var.get():
            return {}
        return self.location.filter_kwargs()

    # --- Display ------------------------------------------------------------------
    def refresh(self):
        """Reloads the table and applies all filters."""
        selected = self._selected_id()  # remember the selection so that it survives the reload
        priority = None if self.priority_var.get() == ALL else Priority.parse(self.priority_var.get())
        tag = None if self.tag_var.get() == ALL else self.tag_var.get()
        tasks = self.todos.list(self.sort_var.get(), self.show_done_var.get(), priority, tag, **self._place_filter())
        if self.search_var.get().strip():
            tasks = self.todos.search(self.search_var.get().strip(), tasks)

        # refill the whole table
        self.tree.delete(*self.tree.get_children())
        for task in tasks:
            self.tree.insert("", "end", iid=str(task.id), tags=(self._row_tag(task),), values=self._values(task))
        if selected is not None and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))

        self.tag_box["values"] = [ALL] + self.todos.all_tags()
        stats = self.todos.statistics()
        place = self._place_filter().get("place")
        place_text = f"  ·  gefiltert nach Ort: {place.name}" if place else ""
        self.status_var.set(f"{len(tasks)} angezeigt  ·  {stats.open} offen  ·  {stats.done} erledigt  ·  "
                            f"{stats.overdue} überfällig{place_text}")
        if self.location.enabled:
            self._update_location_bar()
        self._show_details()

    def _values(self, task: Task) -> tuple:
        """Values of a table row for a task."""
        values = [task.id, "erledigt" if task.done else "offen", task.priority.label, self._due_text(task)]
        if self.location.enabled:
            values.append(self.todos.place_name(task.location_id) or "-")
        return tuple(values + [task.title, " ".join(f"#{t}" for t in task.tags)])

    def _row_tag(self, task: Task) -> str:
        """Color marking of a row: done, overdue or due soon."""
        if task.done:
            return "done"
        if task.is_overdue():
            return "overdue"
        if task.is_due_soon(self.config.due_soon_days):
            return "soon"
        return ""

    def _due_text(self, task: Task) -> str:
        """Due date; overdue tasks get a '!'."""
        text = self.fmt.format_date(task.due_date)
        return f"{text} !" if task.is_overdue() else text

    def _show_details(self):
        """Shows the details of the selected task below the table."""
        task_id = self._selected_id()
        if task_id is None:
            self.detail_label.config(text="Keine Aufgabe ausgewählt. Doppelklick = bearbeiten, "
                                          "Leertaste = erledigt/offen, Entf = löschen.")
            return
        task = self.todos.get(task_id)
        created = f"Erstellt: {task.created_at.strftime(self.fmt.date_format + ' %H:%M')}"
        if task.completed_at:
            created += f"   ·   Erledigt: {task.completed_at.strftime(self.fmt.date_format + ' %H:%M')}"
        if self.location.enabled and task.location_id:
            created += f"   ·   Ort: {self.todos.place_name(task.location_id)}"
        parts = [f"#{task.id}  {task.title}", task.description or "(keine Beschreibung)", created]
        self.detail_label.config(text="\n".join(parts))

    # --- Actions ------------------------------------------------------------------
    def add_task(self):
        """Opens the dialog for a new task."""
        current = self.location.current_place
        dialog = TaskDialog(self.root, self.todos, self.fmt, self.config.default_priority,
                            default_place_id=current.id if current else None, with_place=self.location.enabled)
        if dialog.result:
            self._run(lambda: self.todos.add(**dialog.result))

    def edit_task(self):
        """Opens the dialog for editing the selected task."""
        task = self._selected_task()
        if task:
            dialog = TaskDialog(self.root, self.todos, self.fmt, self.config.default_priority, task,
                                with_place=self.location.enabled)
            if dialog.result:
                self._run(lambda: self.todos.update(task.id, **dialog.result))

    def toggle_done(self):
        """Toggles the selected task between done and open."""
        task = self._selected_task()
        if task:
            self._run(lambda: self.todos.reopen(task.id) if task.done else self.todos.complete(task.id))

    def delete_task(self):
        """Deletes the selected task (with confirmation if configured)."""
        task = self._selected_task()
        if not task:
            return
        if self.config.confirm_delete and not messagebox.askyesno(
                "Löschen", f"'{task.title}' wirklich löschen?", parent=self.root):
            return
        self._run(lambda: self.todos.delete(task.id))

    def clear_completed(self):
        """Removes all completed tasks."""
        if messagebox.askyesno("Erledigte entfernen", "Alle erledigten Aufgaben entfernen?", parent=self.root):
            self._run(self.todos.clear_completed)

    def export_csv(self):
        """Exports all tasks as a CSV file."""
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
                                            initialfile="todos_export.csv", initialdir=str(self.config.base_dir),
                                            filetypes=[("CSV-Datei", "*.csv")])
        if path:
            CsvExporter.export(self.todos.list("id"), path)
            messagebox.showinfo("Export", f"Exportiert nach\n{path}", parent=self.root)

    def create_report(self):
        """Creates a report; the format is taken from the file extension."""
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".html",
                                            initialfile="bericht.html", initialdir=str(self.config.base_dir),
                                            filetypes=[("HTML", "*.html"), ("Text", "*.txt"), ("CSV", "*.csv")])
        if not path:
            return
        report_format = {".html": "html", ".csv": "csv"}.get(Path(path).suffix.lower(), "text")
        manager = TaskReportManager(self.todos, self.config, self.fmt, self.location,
                                    include_places=self.location.enabled)
        manager.save_report(path, report_format)
        reminders = "\n".join(manager.build_reminders()) or "keine"
        messagebox.showinfo("Bericht", f"Gespeichert unter\n{path}\n\n{manager.summary()}\n\nErinnerungen:\n{reminders}",
                            parent=self.root)

    def show_statistics(self):
        """Shows the statistics in a message box."""
        stats = self.todos.statistics()
        lines = [f"Gesamt: {stats.total}", f"Offen: {stats.open}",
                 f"Erledigt: {stats.done} ({stats.completion_rate:.0f} %)", f"Überfällig: {stats.overdue}", "",
                 "Offen nach Priorität:"] + [f"   {k}: {v}" for k, v in stats.by_priority.items()]
        if stats.by_tag:
            lines += ["", "Offen nach Tag:"] + [f"   #{k}: {v}" for k, v in stats.by_tag.items()]
        if self.location.enabled and self.todos.places:
            lines += ["", "Offen nach Ort:"] + [f"   {p.name}: {self.todos.count_for_place(p)}"
                                                for p in self.todos.places]
        # completed tasks in the last 7 and 30 days
        done_week = 0
        done_month = 0
        for task in self.todos.tasks:
            if task.done == True:
                if task.completed_at != None:
                    age = (datetime.now() - task.completed_at).days
                    if age <= 7:
                        done_week = done_week + 1
                        done_month = done_month + 1
                    else:
                        if age <= 30:
                            done_month = done_month + 1
        lines += ["", "Erledigt in den letzten 7 Tagen: " + str(done_week),
                  "Erledigt in den letzten 30 Tagen: " + str(done_month)]
        # average age of the open tasks
        total_age = 0
        open_count = 0
        for task in self.todos.tasks:
            if task.done == False:
                total_age = total_age + (datetime.now() - task.created_at).days
                open_count = open_count + 1
        if open_count > 0:
            lines.append("Durchschnittsalter offener Aufgaben: " + str(round(total_age / open_count)) + " Tage")
        else:
            lines.append("Durchschnittsalter offener Aufgaben: 0 Tage")
        if len(lines) > 0:
            messagebox.showinfo("Statistik", "\n".join(lines), parent=self.root)
        else:
            messagebox.showinfo("Statistik", "\n".join(lines), parent=self.root)

    # --- Helpers --------------------------------------------------------------------
    def _run(self, action):
        """Runs an action, shows errors as a message and refreshes the table afterwards."""
        try:
            action()
        except ERRORS as error:
            messagebox.showerror("Fehler", str(error), parent=self.root)
        self.refresh()

    def _selected_id(self) -> Optional[int]:
        """Id of the selected task or None."""
        selection = self.tree.selection() if hasattr(self, "tree") else ()
        return int(selection[0]) if selection else None

    def _selected_task(self) -> Optional[Task]:
        """Selected task; without a selection a hint is shown."""
        task_id = self._selected_id()
        if task_id is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Aufgabe auswählen.", parent=self.root)
            return None
        return self.todos.get(task_id)

    def _open_context_menu(self, event):
        """Selects the clicked row and opens the context menu."""
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.context_menu.tk_popup(event.x_root, event.y_root)
