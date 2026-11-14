"""Determines the current position - without extra packages, on Windows and macOS.

Sources (config "location_source"):
    auto     -> system location (Windows location service / macOS CoreLocationCLI), otherwise IP location
    system   -> system location only
    ip       -> IP location only (city accuracy, needs internet)
    manuell  -> fixed coordinates from config (location_latitude / location_longitude)
"""
import json
import platform
import shutil
import subprocess
import urllib.request
from typing import Optional

from classes.config import Config
from classes.location import Coordinates

IP_SERVICES = ("https://ipinfo.io/json", "https://ipapi.co/json/")
USER_AGENT = "TodoApp/1.0"

WINDOWS_SCRIPT = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher
$w.Start()
$i = 0
while (($w.Status -ne 'Ready') -and ($w.Permission -ne 'Denied') -and ($i -lt {steps})) {{ Start-Sleep -Milliseconds 100; $i++ }}
$c = $w.Position.Location
$w.Stop()
if ($c.IsUnknown) {{ exit 1 }}
$inv = [System.Globalization.CultureInfo]::InvariantCulture
Write-Output ($c.Latitude.ToString($inv) + ';' + $c.Longitude.ToString($inv))
"""


class LocationService:
    """Determines the position via system location, IP address or fixed values from the config."""
    def __init__(self, config: Config):
        """Prepares the service; the position is only determined when needed."""
        self.config = config
        self.last_error = ""
        self._cache: Optional[Coordinates] = None
        self._cached = False

    @property
    def enabled(self) -> bool:
        """Whether the location feature is turned on."""
        return self.config.location_enabled

    def current_position(self, refresh: bool = False) -> Optional[Coordinates]:
        """Current position (cached, refresh=True forces a new lookup)."""
        if not self.enabled:
            return None
        if refresh or not self._cached:
            self._cache = self._locate()
            self._cached = True
        return self._cache

    # --- Sources ---------------------------------------------------------------
    def _locate(self) -> Optional[Coordinates]:
        """Chooses the matching source depending on location_source."""
        source = self.config.location_source
        self.last_error = ""
        if source == "manuell":
            return self._from_config()
        if source in ("auto", "system"):
            position = self._from_system()
            if position or source == "system":
                return position
        return self._from_ip()

    def _from_config(self) -> Optional[Coordinates]:
        """Fixed position from config.json."""
        lat, lon = self.config.location_latitude, self.config.location_longitude
        if lat is None or lon is None:
            self._error("location_latitude/location_longitude in config.json fehlen")
            return None
        return Coordinates(float(lat), float(lon), "manuell", "manuell")

    def _from_system(self) -> Optional[Coordinates]:
        """System location depending on the operating system (Windows or macOS)."""
        system = platform.system()
        try:
            if system == "Windows":
                return self._from_windows()
            if system == "Darwin":
                return self._from_macos()
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            self._error(f"Systemortung fehlgeschlagen: {error}")
            return None
        self._error(f"Keine Systemortung für {system} verfügbar")
        return None

    def _from_windows(self) -> Optional[Coordinates]:
        """Windows location service (Settings > Privacy > Location must be enabled)."""
        timeout = self.config.location_timeout_s
        script = WINDOWS_SCRIPT.format(steps=int(timeout * 10))
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=timeout + 10, check=False)
        if result.returncode != 0 or ";" not in result.stdout:
            self._error("Windows-Standortdienst liefert keine Position (Datenschutz > Position aktiv?)")
            return None
        lat, lon = result.stdout.strip().splitlines()[-1].split(";")
        return Coordinates(float(lat), float(lon), "windows", "Windows-Ortung")

    def _from_macos(self) -> Optional[Coordinates]:
        """macOS: requires CoreLocationCLI (brew install corelocationcli)."""
        tool = shutil.which("CoreLocationCLI")
        if not tool:
            self._error("CoreLocationCLI nicht installiert (brew install corelocationcli)")
            return None
        for flag in ("--json", "-json"):  # new and old versions
            result = subprocess.run([tool, flag], capture_output=True, text=True,
                                    timeout=self.config.location_timeout_s + 5, check=False)
            if result.returncode == 0 and result.stdout.strip().startswith("{"):
                data = json.loads(result.stdout)
                return Coordinates(float(data["latitude"]), float(data["longitude"]), "macos", "macOS-Ortung")
        self._error("CoreLocationCLI liefert keine Position (Ortungsdienste erlaubt?)")
        return None

    def _from_ip(self) -> Optional[Coordinates]:
        """Approximate position via the IP address (city accuracy)."""
        errors = []
        for url in IP_SERVICES:
            try:
                data = self._fetch_json(url)
                if "loc" in data:  # ipinfo.io: "lat,lon"
                    lat, lon = data["loc"].split(",")
                else:              # ipapi.co
                    lat, lon = data["latitude"], data["longitude"]
                return Coordinates(float(lat), float(lon), "ip", data.get("city", "IP-Ortung"))
            except (OSError, ValueError, KeyError) as error:
                errors.append(str(error))
        self._error(f"IP-Ortung fehlgeschlagen: {errors[-1]}")
        return None

    def _error(self, message: str):
        """Collects errors so that all failed sources are visible with 'auto'."""
        self.last_error = f"{self.last_error}; {message}" if self.last_error else message

    def _fetch_json(self, url: str) -> dict:
        """Loads a URL and returns the JSON response."""
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.config.location_timeout_s) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
