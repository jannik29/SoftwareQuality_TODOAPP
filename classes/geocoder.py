"""Address search (address -> coordinates) and reverse search via OpenStreetMap Nominatim."""
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from classes.location import Coordinates

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "TodoApp/1.0"


@dataclass
class SearchResult:
    """A result of the address search: description and coordinates."""
    label: str
    position: Coordinates


class Geocoder:
    """Searches addresses via the Nominatim service of OpenStreetMap."""
    def __init__(self, timeout: float = 8, base_url: str = NOMINATIM_URL):
        """Sets the timeout and the server address."""
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, limit: int = 5) -> list:
        """Searches addresses/places. Raises ValueError for an empty query, OSError for network problems."""
        query = (query or "").strip()
        if not query:
            raise ValueError("Bitte einen Suchbegriff eingeben")
        data = self._get("search", {"q": query, "format": "jsonv2", "limit": limit})
        return [SearchResult(item["display_name"], Coordinates(float(item["lat"]), float(item["lon"]), "suche"))
                for item in data]

    def reverse(self, position: Coordinates) -> Optional[str]:
        """Address for coordinates (or None if nothing was found)."""
        data = self._get("reverse", {"lat": position.latitude, "lon": position.longitude,
                                     "format": "jsonv2", "zoom": 18})
        return data.get("display_name") if isinstance(data, dict) else None

    def _get(self, endpoint: str, params: dict):
        """Calls a Nominatim endpoint and returns the JSON response."""
        params["accept-language"] = "de"
        url = f"{self.base_url}/{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310 (fixed https URL)
            return json.loads(response.read().decode("utf-8"))
