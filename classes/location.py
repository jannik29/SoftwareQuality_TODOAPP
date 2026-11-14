"""Places (e.g. home, university) and coordinates."""
import math
from dataclasses import dataclass
from typing import Optional

EARTH_RADIUS_M = 6_371_000


@dataclass
class Coordinates:
    """A position on earth (latitude and longitude in degrees)."""
    latitude: float
    longitude: float
    source: str = ""          # where the position comes from (windows, macos, ip, manuell)
    label: str = ""           # e.g. city name for IP based location

    def __post_init__(self):
        """Checks after creation that the values are within the valid range."""
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Breitengrad muss zwischen -90 und 90 liegen: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Längengrad muss zwischen -180 und 180 liegen: {self.longitude}")

    def distance_to(self, other: "Coordinates") -> float:
        """Distance in meters (haversine formula)."""
        lat1, lat2 = math.radians(self.latitude), math.radians(other.latitude)
        d_lat = lat2 - lat1
        d_lon = math.radians(other.longitude - self.longitude)
        a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
        return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))

    def __str__(self):
        """Readable representation, e.g. 'Berlin (52.52000, 13.40000)'."""
        text = f"{self.latitude:.5f}, {self.longitude:.5f}"
        return f"{self.label} ({text})" if self.label else text


@dataclass
class Place:
    """A saved place with name, position and radius in meters."""
    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: int = 300

    @property
    def coordinates(self) -> Coordinates:
        """Position of the place as a Coordinates object."""
        return Coordinates(self.latitude, self.longitude)

    def distance_to(self, position: Coordinates) -> float:
        """Distance to the given position in meters."""
        return self.coordinates.distance_to(position)

    def contains(self, position: Coordinates) -> bool:
        """True if the position lies within the radius."""
        return self.distance_to(position) <= self.radius_m


def nearest_place(places: list, position: Optional[Coordinates]) -> Optional[Place]:
    """The nearest place whose radius contains the position (or None)."""
    if position is None:
        return None
    inside = [p for p in places if p.contains(position)]
    return min(inside, key=lambda p: p.distance_to(position), default=None)


def format_distance(meters: float) -> str:
    """Formats a distance: below 1 km in m, otherwise in km."""
    return f"{meters:.0f} m" if meters < 1000 else f"{meters / 1000:.1f} km"
