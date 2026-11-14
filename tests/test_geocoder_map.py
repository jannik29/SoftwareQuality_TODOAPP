"""Tests for the address search (network mocked) and the map math of the tile map."""
import unittest
from unittest import mock

from classes.geocoder import Geocoder
from classes.location import Coordinates
from tests.test_location import FakeResponse

try:  # the map needs tkinter; skip these tests if it is missing
    from classes.tile_map import meters_per_pixel, to_latlon, to_pixel
    HAS_TK = True
except ImportError:
    HAS_TK = False


class GeocoderTest(unittest.TestCase):
    def test_search_parses_results(self):
        data = [{"display_name": "Schlossplatz, Stuttgart", "lat": "48.7785", "lon": "9.1797"}]
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(data)) as urlopen:
            results = Geocoder().search("Schlossplatz")
        self.assertEqual(results[0].label, "Schlossplatz, Stuttgart")
        self.assertEqual((results[0].position.latitude, results[0].position.longitude), (48.7785, 9.1797))
        request = urlopen.call_args[0][0]
        self.assertIn("q=Schlossplatz", request.full_url)
        self.assertTrue(request.get_header("User-agent"))

    def test_empty_query_raises_without_request(self):
        with mock.patch("urllib.request.urlopen") as urlopen, self.assertRaises(ValueError):
            Geocoder().search("  ")
        urlopen.assert_not_called()

    def test_reverse(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"display_name": "Adresse"})):
            self.assertEqual(Geocoder().reverse(Coordinates(1, 2)), "Adresse")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse([])):
            self.assertIsNone(Geocoder().reverse(Coordinates(1, 2)))


@unittest.skipUnless(HAS_TK, "tkinter not available")
class MapMathTest(unittest.TestCase):
    def test_round_trip(self):
        for lat, lon, zoom in ((48.7758, 9.1829, 15), (-33.86, 151.2, 3), (0.0, 0.0, 2)):
            x, y = to_pixel(lat, lon, zoom)
            back_lat, back_lon = to_latlon(x, y, zoom)
            self.assertAlmostEqual(back_lat, lat, places=9)
            self.assertAlmostEqual(back_lon, lon, places=9)

    def test_world_corners(self):
        self.assertEqual(to_pixel(0, -180, 0), (0.0, 128.0))
        self.assertAlmostEqual(to_pixel(0, 0, 1)[0], 256.0)

    def test_meters_per_pixel_shrinks_with_zoom(self):
        self.assertAlmostEqual(meters_per_pixel(0, 0), 156543.03392)
        self.assertAlmostEqual(meters_per_pixel(48.77, 16), 1.57, places=2)


if __name__ == "__main__":
    unittest.main()
