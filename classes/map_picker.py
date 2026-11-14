"""Dialog: choose a place on the map (address search, click on the map, set the radius)."""
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable, Optional

from classes.config import Config
from classes.geocoder import Geocoder
from classes.location import Coordinates, Place
from classes.location_context import LocationContext
from classes.tile_map import TileMap

HINT = "#777777"
MIN_RADIUS, MAX_RADIUS = 25, 3000


@dataclass
class PickedPlace:
    """Result of the map dialog: name, position and radius."""
    name: str
    position: Coordinates
    radius_m: int


class BackgroundRunner:
    """Runs network calls in the background and delivers the result in the tkinter thread."""

    def __init__(self, widget: tk.Misc):
        """Prepares the queue for the results."""
        self.widget = widget
        self._results: queue.Queue = queue.Queue()

    def run(self, func: Callable, on_done: Callable, on_error: Callable):
        """Starts func in a thread and then calls on_done or on_error."""
        def worker():
            """Runs in the background thread and puts the result into the queue."""
            try:
                self._results.put((on_done, func()))
            except (OSError, ValueError, KeyError) as error:
                self._results.put((on_error, error))
        threading.Thread(target=worker, daemon=True).start()
        self._poll()

    def _poll(self):
        """Checks regularly whether a result is available (tkinter may only run in the main thread)."""
        if self._results.empty():
            if self.widget.winfo_exists():
                self.widget.after(100, self._poll)
            return
        callback, value = self._results.get_nowait()
        if self.widget.winfo_exists():
            callback(value)


class MapPickerDialog(tk.Toplevel):
    """Result after closing in self.result (PickedPlace or None)."""

    def __init__(self, parent, config: Config, location: Optional[LocationContext] = None,
                 place: Optional[Place] = None, other_places: Optional[list] = None):
        """Builds the search, the map and the inputs and waits until it is closed."""
        super().__init__(parent)
        self.config = config
        self.location = location
        self.geocoder = Geocoder()
        self.runner = BackgroundRunner(self)
        self.result: Optional[PickedPlace] = None
        self.position: Optional[Coordinates] = place.coordinates if place else None
        self.search_results: list = []

        self.title("Ort bearbeiten" if place else "Neuen Ort auf der Karte wählen")
        self.geometry("860x640")
        self.minsize(640, 480)
        if parent.winfo_viewable():
            self.transient(parent)

        self.search_var = tk.StringVar()
        self.name_var = tk.StringVar(value=place.name if place else "")
        self.radius_var = tk.IntVar(value=place.radius_m if place else config.location_default_radius_m)
        self.info_var = tk.StringVar(value="Klicke in die Karte oder suche nach einer Adresse.")

        self._build_search_bar()
        self._build_map(other_places or [])
        self._build_bottom()
        self._initial_view(place)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.search_entry.focus_set()
        self.grab_set()
        self.wait_window()

    # --- Layout ---------------------------------------------------------------------
    def _build_search_bar(self):
        """Search field, search button, 'Mein Standort' and result list."""
        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Adresse / Ort suchen:").pack(side="left")
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.search_entry.bind("<Return>", lambda _e: self.search())
        ttk.Button(bar, text="Suchen", command=self.search).pack(side="left")
        if self.location and self.location.enabled:
            ttk.Button(bar, text="Mein Standort", command=self.use_current_position).pack(side="left", padx=(6, 0))

        self.results_list = tk.Listbox(self, height=4, activestyle="dotbox")
        self.results_list.bind("<<ListboxSelect>>", lambda _e: self._choose_result())

    def _build_map(self, other_places: list):
        """Map with zoom buttons and usage hint."""
        frame = ttk.Frame(self, padding=(10, 4))
        frame.pack(fill="both", expand=True)
        self.map = TileMap(frame, self.config.map_tile_url, self.config.tile_cache_dir, on_click=self.set_position)
        self.map.other_places = [(p.name, p.coordinates) for p in other_places]
        self.map.pack(fill="both", expand=True)
        zoom = ttk.Frame(self.map)
        ttk.Button(zoom, text="+", width=3, command=lambda: self.map.zoom_at(1)).pack()
        ttk.Button(zoom, text="−", width=3, command=lambda: self.map.zoom_at(-1)).pack()
        zoom.place(x=10, y=10)
        ttk.Label(frame, text="Klicken = Ort setzen  ·  Ziehen = verschieben  ·  Mausrad oder +/− = zoomen",
                  foreground=HINT).pack(anchor="w", pady=(4, 0))

    def _build_bottom(self):
        """Name, radius slider, info text and the buttons."""
        bottom = ttk.Frame(self, padding=(10, 6, 10, 10))
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Name *").grid(row=0, column=0, sticky="w")
        ttk.Entry(bottom, textvariable=self.name_var, width=24).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(bottom, text="Radius").grid(row=0, column=2, sticky="w")
        self.radius_label = ttk.Label(bottom, width=8)
        self.radius_label.grid(row=0, column=4, sticky="w")
        radius_scale = ttk.Scale(bottom, from_=MIN_RADIUS, to=MAX_RADIUS, orient="horizontal", length=200,
                                 command=self._on_radius)
        radius_scale.grid(row=0, column=3, sticky="w", padx=6)
        radius_scale.set(self.radius_var.get())
        ttk.Label(bottom, textvariable=self.info_var, foreground=HINT, wraplength=820, justify="left").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(bottom)
        buttons.grid(row=0, column=5, sticky="e")
        bottom.columnconfigure(5, weight=1)
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Übernehmen", command=self._accept).pack(side="right", padx=6)

    def _initial_view(self, place: Optional[Place]):
        """Initial view: the edited place, the own position or Germany."""
        self.update_idletasks()
        if place:
            self.map.center_on(place.coordinates, 16)
            self.set_position(place.coordinates, lookup=False)
            return
        position = self.location.position() if self.location and self.location.enabled else None
        if position:
            self.map.center_on(position, 15 if position.source != "ip" else 12)
        else:
            self.map.redraw()

    # --- Actions ------------------------------------------------------------------------
    def set_position(self, position: Coordinates, lookup: bool = True):
        """Sets the marker; lookup=True also looks up the address."""
        self.position = position
        self.map.set_marker(position, self.radius_var.get())
        self.info_var.set(f"Koordinaten: {position.latitude:.5f}, {position.longitude:.5f}")
        if lookup:
            self.runner.run(lambda: self.geocoder.reverse(position), self._show_address, lambda _e: None)

    def search(self):
        """Starts the address search in the background."""
        query = self.search_var.get().strip()
        if not query:
            return
        self.info_var.set(f"Suche nach '{query}' ...")
        self.runner.run(lambda: self.geocoder.search(query), self._show_results, self._search_failed)

    def use_current_position(self):
        """Locates again and jumps to the own position."""
        self.info_var.set("Standort wird ermittelt ...")
        self.runner.run(lambda: self.location.position(refresh=True), self._show_current, self._search_failed)

    # --- Callbacks --------------------------------------------------------------------------
    def _show_results(self, results: list):
        """Shows the search results and selects the first one."""
        self.search_results = results
        self.results_list.delete(0, "end")
        if not results:
            self.results_list.pack_forget()
            self.info_var.set("Nichts gefunden. Anderen Suchbegriff versuchen oder in die Karte klicken.")
            return
        for result in results:
            self.results_list.insert("end", result.label)
        self.results_list.pack(fill="x", padx=10, after=self.search_entry.master)
        self.results_list.selection_set(0)
        self._choose_result()

    def _choose_result(self):
        """Jumps to the selected result and suggests a name."""
        selection = self.results_list.curselection()
        if not selection:
            return
        result = self.search_results[selection[0]]
        self.map.center_on(result.position, 16)
        self.set_position(result.position, lookup=False)
        self.info_var.set(f"{result.label}\nKoordinaten: {result.position.latitude:.5f}, "
                          f"{result.position.longitude:.5f}")
        if not self.name_var.get().strip():
            self.name_var.set(result.label.split(",")[0][:40])

    def _show_address(self, address: Optional[str]):
        """Shows the address of the placed marker."""
        if address and self.position:
            self.info_var.set(f"{address}\nKoordinaten: {self.position.latitude:.5f}, {self.position.longitude:.5f}")

    def _show_current(self, position: Optional[Coordinates]):
        """Jumps to the determined own position."""
        if position is None:
            self.info_var.set(self.location.position_text())
            return
        self.map.center_on(position, 16 if position.source != "ip" else 12)
        self.set_position(position)

    def _search_failed(self, error: Exception):
        """Shows an error of the search or the location lookup."""
        self.info_var.set(f"Fehler: {error} (Internetverbindung?)")

    def _on_radius(self, value: str):
        """Rounds the radius to 25 m and redraws the circle."""
        radius = int(round(float(value) / 25) * 25)
        self.radius_var.set(radius)
        self.radius_label.config(text=f"{radius} m")
        if self.position:
            self.map.set_marker(self.position, radius)

    def _accept(self):
        """Validates the input and closes the dialog with a result."""
        if self.position is None:
            messagebox.showwarning("Ort", "Bitte zuerst einen Punkt auf der Karte wählen.", parent=self)
            return
        if not self.name_var.get().strip():
            messagebox.showwarning("Ort", "Bitte einen Namen eingeben.", parent=self)
            return
        self.result = PickedPlace(self.name_var.get().strip(), self.position, self.radius_var.get())
        self.destroy()


def pick_on_map(config: Config, location: Optional[LocationContext] = None, place: Optional[Place] = None,
                other_places: Optional[list] = None, parent: Optional[tk.Misc] = None) -> Optional[PickedPlace]:
    """Opens the map - also without a running GUI (e.g. from the CLI menu)."""
    if parent is not None:
        return MapPickerDialog(parent, config, location, place, other_places).result
    root = tk.Tk()
    root.withdraw()
    try:
        return MapPickerDialog(root, config, location, place, other_places).result
    finally:
        root.destroy()
