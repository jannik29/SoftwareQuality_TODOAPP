"""Tests for coordinates, places, the location service and the location context."""
import io
import json
import subprocess
import unittest
from unittest import mock

from classes.location import Coordinates, Place, format_distance, nearest_place
from classes.location_service import LocationService
from tests.helpers import TEST_LAT, TEST_LON, AppTestCase

BERLIN = Coordinates(52.5200, 13.4050)
MUNICH = Coordinates(48.1351, 11.5820)


class FakeResponse(io.BytesIO):
    """Stand-in for the response of urllib.request.urlopen."""

    def __init__(self, data: dict):
        super().__init__(json.dumps(data).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class CoordinatesTest(unittest.TestCase):
    def test_invalid_values_raise(self):
        with self.assertRaises(ValueError):
            Coordinates(91, 0)
        with self.assertRaises(ValueError):
            Coordinates(0, -181)

    def test_distance_berlin_munich(self):
        self.assertAlmostEqual(BERLIN.distance_to(MUNICH) / 1000, 504, delta=3)
        self.assertEqual(BERLIN.distance_to(BERLIN), 0)

    def test_str_with_and_without_label(self):
        self.assertEqual(str(Coordinates(1.5, 2.25)), "1.50000, 2.25000")
        self.assertEqual(str(Coordinates(1.5, 2.25, label="X")), "X (1.50000, 2.25000)")

    def test_format_distance(self):
        self.assertEqual(format_distance(950), "950 m")
        self.assertEqual(format_distance(1250), "1.2 km")


class PlaceTest(unittest.TestCase):
    def test_contains_and_nearest_place(self):
        center = Place(1, "Mitte", 48.0, 9.0, 500)
        near = Place(2, "Nah", 48.001, 9.0, 500)        # about 111 m north
        far = Place(3, "Fern", 49.0, 9.0, 500)
        position = Coordinates(48.0009, 9.0)
        self.assertTrue(center.contains(position))
        self.assertFalse(far.contains(position))
        self.assertIs(nearest_place([center, near, far], position), near)
        self.assertIsNone(nearest_place([far], position))
        self.assertIsNone(nearest_place([center], None))


class LocationServiceTest(AppTestCase):
    def service(self, **values) -> LocationService:
        self.config._values.update(values)
        return LocationService(self.config)

    def test_manual_source_uses_config(self):
        position = self.service().current_position()
        self.assertEqual((position.latitude, position.longitude, position.source), (TEST_LAT, TEST_LON, "manuell"))

    def test_manual_source_without_coordinates(self):
        service = self.service(location_latitude=None)
        self.assertIsNone(service.current_position())
        self.assertIn("location_latitude", service.last_error)

    def test_disabled_returns_none(self):
        self.assertIsNone(self.service(location_enabled=False).current_position())

    def test_position_is_cached_until_refresh(self):
        service = self.service(location_source="ip")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"loc": "1,2"})) as urlopen:
            service.current_position()
            service.current_position()
            self.assertEqual(urlopen.call_count, 1)
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"loc": "3,4"})):
            self.assertEqual(service.current_position(refresh=True).latitude, 3)

    def test_ip_source_supports_both_services(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"loc": "52.5,13.4", "city": "Berlin"})):
            position = self.service(location_source="ip").current_position()
        self.assertEqual((position.latitude, position.label, position.source), (52.5, "Berlin", "ip"))
        with mock.patch("urllib.request.urlopen",
                        side_effect=[OSError("down"), FakeResponse({"latitude": 1.5, "longitude": 2.5})]):
            self.assertEqual(self.service(location_source="ip").current_position(refresh=True).longitude, 2.5)

    def test_ip_source_offline(self):
        service = self.service(location_source="ip")
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(service.current_position())
        self.assertIn("offline", service.last_error)

    def test_windows_system_location(self):
        result = subprocess.CompletedProcess([], 0, stdout="48.1;9.2\n", stderr="")
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=result) as run:
            position = self.service(location_source="system").current_position()
        self.assertEqual((position.latitude, position.longitude, position.source), (48.1, 9.2, "windows"))
        self.assertEqual(run.call_args[0][0][0], "powershell")

    def test_auto_falls_back_to_ip_and_collects_errors(self):
        denied = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        service = self.service(location_source="auto")
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=denied), \
                mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(service.current_position())
        self.assertIn("Windows", service.last_error)
        self.assertIn("IP", service.last_error)

    def test_macos_without_tool(self):
        service = self.service(location_source="system")
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("shutil.which", return_value=None):
            self.assertIsNone(service.current_position())
        self.assertIn("CoreLocationCLI", service.last_error)

    def test_macos_with_tool(self):
        result = subprocess.CompletedProcess([], 0, stdout='{"latitude": 1.0, "longitude": 2.0}', stderr="")
        with mock.patch("platform.system", return_value="Darwin"), \
                mock.patch("shutil.which", return_value="/usr/local/bin/CoreLocationCLI"), \
                mock.patch("subprocess.run", return_value=result):
            position = self.service(location_source="system").current_position()
        self.assertEqual(position.source, "macos")

    def test_unsupported_system(self):
        service = self.service(location_source="system")
        with mock.patch("platform.system", return_value="Linux"):
            self.assertIsNone(service.current_position())
        self.assertIn("Linux", service.last_error)


class LocationContextTest(AppTestCase):
    def test_detects_place_at_current_position(self):
        home = self.add_place_here("Zuhause")
        self.assertIs(self.location.current_place, home)
        self.assertEqual(self.location.filter_kwargs(), {"place": home, "include_unassigned": True})
        self.assertIn("Zuhause", self.location.place_text())
        self.assertIn("manuell", self.location.position_text())

    def test_no_place_when_nothing_is_near(self):
        self.todos.add_place("Berlin", BERLIN, 300)
        self.assertIsNone(self.location.current_place)
        self.assertIn("kein gespeicherter Ort", self.location.place_text())

    def test_manual_choice_and_back_to_automatic(self):
        home = self.add_place_here("Zuhause")
        berlin = self.todos.add_place("Berlin", BERLIN, 300)
        self.location.choose(berlin)
        self.assertIs(self.location.current_place, berlin)
        self.assertIn("manuell gewählt", self.location.place_text())
        self.location.choose(None)
        self.assertIsNone(self.location.current_place)
        self.location.use_automatic()
        self.assertIs(self.location.current_place, home)

    def test_manually_chosen_place_that_was_deleted(self):
        berlin = self.todos.add_place("Berlin", BERLIN, 300)
        self.location.choose(berlin)
        self.todos.delete_place(berlin.id)
        self.assertIsNone(self.location.current_place)

    def test_distances_sorted(self):
        self.todos.add_place("Berlin", BERLIN, 300)
        self.add_place_here("Zuhause")
        names = [place.name for place, _ in self.location.distances()]
        self.assertEqual(names, ["Zuhause", "Berlin"])

    def test_disabled_location(self):
        self.config._values["location_enabled"] = False
        self.add_place_here()
        self.assertIsNone(self.location.current_place)
        self.assertEqual(self.location.filter_kwargs(), {})
        self.assertIn("deaktiviert", self.location.position_text())


if __name__ == "__main__":
    unittest.main()
