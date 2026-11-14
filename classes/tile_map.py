"""Interactive map as a tkinter canvas (OpenStreetMap tiles, no extra packages).

Usage: click = set point, drag = move, mouse wheel / +/- = zoom.
Tiles are loaded in the background and cached in data/tile_cache.
"""
import base64
import math
import queue
import tkinter as tk
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from classes.location import Coordinates

TILE_SIZE = 256
MIN_ZOOM, MAX_ZOOM = 2, 19
MAX_LAT = 85.0511
USER_AGENT = "TodoApp/1.0"
CLICK_TOLERANCE_PX = 4
MEMORY_CACHE_SIZE = 400


def to_pixel(lat: float, lon: float, zoom: int) -> tuple:
    """Geo coordinates -> world pixels (Web Mercator) at the given zoom level."""
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    size = TILE_SIZE * 2 ** zoom
    x = (lon + 180.0) / 360.0 * size
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * size
    return x, y


def to_latlon(x: float, y: float, zoom: int) -> tuple:
    """World pixels -> geo coordinates."""
    size = TILE_SIZE * 2 ** zoom
    lon = x / size * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size))))
    return lat, (lon + 180.0) % 360.0 - 180.0


def meters_per_pixel(lat: float, zoom: int) -> float:
    """How many meters one screen pixel corresponds to at this latitude and zoom level."""
    return 156543.03392 * math.cos(math.radians(lat)) / 2 ** zoom


class TileMap(tk.Canvas):
    """Map view made of OpenStreetMap tiles (256x256 pixels each)."""
    def __init__(self, parent, tile_url: str, cache_dir: Optional[Path] = None,
                 on_click: Optional[Callable[[Coordinates], None]] = None, **kwargs):
        """Prepares the map, the tile cache, the download threads and the mouse events."""
        super().__init__(parent, background="#e5e3df", highlightthickness=0, cursor="hand2", **kwargs)
        self.tile_url = tile_url
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.on_click = on_click
        self.zoom = 6
        self.center_x, self.center_y = to_pixel(51.16, 10.45, self.zoom)   # Germany
        self.marker: Optional[Coordinates] = None
        self.radius_m = 0
        self.other_places: list = []                                        # [(name, Coordinates)]

        self._images: dict = {}           # (z, x, y) -> PhotoImage
        self._pending: set = set()
        self._failed: set = set()
        self._results: queue.Queue = queue.Queue()
        self._executor = ThreadPoolExecutor(max_workers=2)   # OSM usage policy: few parallel downloads
        self._drag_start = None
        self._moved = False
        self.png_supported = True

        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)                                 # Windows / macOS
        self.bind("<Button-4>", lambda e: self.zoom_at(1, e.x, e.y))               # Linux
        self.bind("<Button-5>", lambda e: self.zoom_at(-1, e.x, e.y))
        self.bind("<Destroy>", lambda _e: self._executor.shutdown(wait=False), add="+")
        self.after(50, self._poll_tiles)

    # --- Public methods ---------------------------------------------------------
    def center_on(self, position: Coordinates, zoom: Optional[int] = None):
        """Centers the map on a position (optionally with a new zoom level)."""
        if zoom is not None:
            self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.center_x, self.center_y = to_pixel(position.latitude, position.longitude, self.zoom)
        self.redraw()

    def set_marker(self, position: Optional[Coordinates], radius_m: Optional[int] = None):
        """Sets the red marker and optionally the radius."""
        self.marker = position
        if radius_m is not None:
            self.radius_m = radius_m
        self.redraw()

    def zoom_at(self, step: int, x: Optional[float] = None, y: Optional[float] = None):
        """Zooms by step levels; the point under (x, y) stays in place."""
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom + step))
        if new_zoom == self.zoom:
            return
        width, height = self._size()
        x = width / 2 if x is None else x
        y = height / 2 if y is None else y
        lat, lon = self._screen_to_latlon(x, y)
        self.zoom = new_zoom
        px, py = to_pixel(lat, lon, self.zoom)
        self.center_x, self.center_y = px - (x - width / 2), py - (y - height / 2)
        self.redraw()

    # --- Drawing ------------------------------------------------------------------
    def redraw(self):
        """Draws all visible tiles and the markers on top."""
        self.delete("all")
        width, height = self._size()
        left, top = self.center_x - width / 2, self.center_y - height / 2
        tiles = 2 ** self.zoom
        for tile_x in range(math.floor(left / TILE_SIZE), math.floor((left + width) / TILE_SIZE) + 1):
            for tile_y in range(math.floor(top / TILE_SIZE), math.floor((top + height) / TILE_SIZE) + 1):
                if 0 <= tile_y < tiles:
                    key = (self.zoom, tile_x % tiles, tile_y)
                    image = self._images.get(key) or self._request(key)
                    if image is not None:
                        self.create_image(tile_x * TILE_SIZE - left, tile_y * TILE_SIZE - top,
                                          image=image, anchor="nw")
        self._draw_overlays()

    def _draw_overlays(self):
        """Draws places, marker, radius circle and attribution."""
        for name, position in self.other_places:
            x, y = self._latlon_to_screen(position.latitude, position.longitude)
            self.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#1e64c8", outline="white", width=2)
            self.create_text(x + 8, y, text=name, anchor="w", fill="#1e3a6e", font=("TkDefaultFont", 9, "bold"))
        if self.marker:
            x, y = self._latlon_to_screen(self.marker.latitude, self.marker.longitude)
            if self.radius_m:
                r = self.radius_m / meters_per_pixel(self.marker.latitude, self.zoom)
                self.create_oval(x - r, y - r, x + r, y + r, outline="#d32f2f", width=2, dash=(6, 4))
            self.create_line(x, y - 4, x, y - 22, fill="#d32f2f", width=3)
            self.create_oval(x - 8, y - 30, x + 8, y - 14, fill="#d32f2f", outline="white", width=2)
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#d32f2f", outline="")
        width, height = self._size()
        self.create_rectangle(width - 190, height - 18, width, height, fill="white", outline="")
        self.create_text(width - 4, height - 3, text="© OpenStreetMap-Mitwirkende", anchor="se",
                         fill="#333", font=("TkDefaultFont", 8))
        if not self.png_supported:
            self.create_text(width / 2, height / 2, fill="#c62828", font=("TkDefaultFont", 11, "bold"),
                             text="Diese Tk-Version kann keine PNG-Kartenbilder anzeigen (Tk >= 8.6 nötig).\n"
                                  "Ort kann trotzdem per Suche gesetzt werden.")

    # --- Loading tiles -----------------------------------------------------------
    def _request(self, key: tuple):
        """Requests a missing tile to be loaded in the background."""
        if key in self._pending or key in self._failed or not self.png_supported:
            return None
        self._pending.add(key)
        self._executor.submit(self._load_tile, key)
        return None

    def _load_tile(self, key: tuple):
        """Runs in the background thread: only returns bytes, the PhotoImage is created in the main thread."""
        zoom, x, y = key
        cache_file = self.cache_dir / str(zoom) / str(x) / f"{y}.png" if self.cache_dir else None
        try:
            if cache_file and cache_file.exists():
                data = cache_file.read_bytes()
            else:
                url = self.tile_url.format(z=zoom, x=x, y=y)
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
                    data = response.read()
                if cache_file:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_bytes(data)
            self._results.put((key, data))
        except OSError:
            self._results.put((key, None))

    def _poll_tiles(self):
        """Takes over finished tiles in the main thread and redraws."""
        changed = False
        while not self._results.empty():
            key, data = self._results.get_nowait()
            self._pending.discard(key)
            if data is None:
                self._failed.add(key)
                continue
            try:
                self._images[key] = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
                changed = True
            except tk.TclError:
                self.png_supported = False
                changed = True
        if len(self._images) > MEMORY_CACHE_SIZE:
            for old in list(self._images)[: len(self._images) - MEMORY_CACHE_SIZE]:
                del self._images[old]
        if changed:
            self.redraw()
        if self.winfo_exists():
            self.after(80, self._poll_tiles)

    # --- Mouse -----------------------------------------------------------------------
    def _on_press(self, event):
        """Remembers the start point of a click or a drag."""
        self._drag_start = (event.x, event.y)
        self._moved = False

    def _on_drag(self, event):
        """Moves the map while dragging with the mouse."""
        if self._drag_start is None:
            return
        dx, dy = event.x - self._drag_start[0], event.y - self._drag_start[1]
        if abs(dx) + abs(dy) > CLICK_TOLERANCE_PX or self._moved:
            self._moved = True
            self.center_x -= dx
            self.center_y -= dy
            self._drag_start = (event.x, event.y)
            self.redraw()

    def _on_release(self, event):
        """A click without dragging sets a point."""
        if not self._moved and self.on_click:
            lat, lon = self._screen_to_latlon(event.x, event.y)
            self.on_click(Coordinates(lat, lon, "karte"))
        self._drag_start = None

    def _on_wheel(self, event):
        """Zooms with the mouse wheel at the position of the mouse pointer."""
        if event.delta:
            self.zoom_at(1 if event.delta > 0 else -1, event.x, event.y)

    # --- Conversion -----------------------------------------------------------------
    def _size(self) -> tuple:
        """Current size of the map in pixels."""
        return max(self.winfo_width(), 1), max(self.winfo_height(), 1)

    def _screen_to_latlon(self, x: float, y: float) -> tuple:
        """Screen position -> geo coordinates."""
        width, height = self._size()
        return to_latlon(self.center_x - width / 2 + x, self.center_y - height / 2 + y, self.zoom)

    def _latlon_to_screen(self, lat: float, lon: float) -> tuple:
        """Geo coordinates -> screen position."""
        width, height = self._size()
        px, py = to_pixel(lat, lon, self.zoom)
        return px - self.center_x + width / 2, py - self.center_y + height / 2

