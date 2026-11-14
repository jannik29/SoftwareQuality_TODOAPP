"""Tests for loading and validating config.json."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from classes.config import DEFAULTS, Config
from tests.helpers import write_config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_created_with_defaults(self):
        path = self.folder / "config.json"
        config = Config(path)
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text()), DEFAULTS)
        self.assertEqual(config.default_sort, "faellig")

    def test_missing_values_fall_back_to_defaults(self):
        path = self.folder / "config.json"
        path.write_text(json.dumps({"due_soon_days": 7}))
        config = Config(path)
        self.assertEqual(config.due_soon_days, 7)
        self.assertEqual(config.max_title_length, DEFAULTS["max_title_length"])

    def test_relative_data_file_is_relative_to_config_folder(self):
        config = write_config(self.folder, data_file="sub/db.sqlite")
        self.assertEqual(config.data_file, self.folder / "sub" / "db.sqlite")
        self.assertEqual(config.tile_cache_dir, self.folder / "sub" / "tile_cache")

    def test_unknown_keys_print_a_warning(self):
        path = self.folder / "config.json"
        path.write_text(json.dumps({"tippfehler": 1}))
        output = io.StringIO()
        with redirect_stdout(output):
            Config(path)
        self.assertIn("tippfehler", output.getvalue())

    def test_invalid_values_raise_value_error(self):
        invalid = [
            {"start_mode": "browser"},
            {"default_sort": "farbe"},
            {"max_title_length": 0},
            {"due_soon_days": -1},
            {"location_source": "gps"},
            {"location_default_radius_m": 0},
            {"map_tile_url": "https://example.com/tile.png"},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                write_config(self.folder, **values)

    def test_typed_properties(self):
        config = write_config(self.folder, use_colors=False, location_timeout_s=2, show_completed=False)
        self.assertFalse(config.use_colors)
        self.assertEqual(config.location_timeout_s, 2.0)
        self.assertFalse(config.show_completed)
        self.assertEqual(config.get("due_soon_days"), DEFAULTS["due_soon_days"])


if __name__ == "__main__":
    unittest.main()
