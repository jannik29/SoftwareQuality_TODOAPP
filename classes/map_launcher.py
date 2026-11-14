"""Opens the map from the console. tkinter is only loaded here so that the CLI also runs without tkinter."""
from typing import Optional

from classes.config import Config
from classes.location import Place
from classes.location_context import LocationContext


def open_map(config: Config, location: Optional[LocationContext] = None, place: Optional[Place] = None,
             other_places: Optional[list] = None):
    """Returns a PickedPlace (name, position, radius_m) or None if cancelled."""
    try:
        import tkinter
        from classes.map_picker import pick_on_map
    except ImportError as error:
        raise ValueError("Die Karte braucht tkinter. Alternativ: Adresssuche verwenden.") from error
    print("Karte geöffnet – Ort wählen und 'Übernehmen' klicken ...")
    try:
        return pick_on_map(config, location, place, other_places)
    except tkinter.TclError as error:  # e.g. no screen available
        raise ValueError(f"Karte konnte nicht geöffnet werden: {error}") from error
