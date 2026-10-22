from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from settings import Settings  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_defaults_and_environment_overrides(self):
        defaults = Settings.from_env({})
        self.assertEqual(defaults.host, "127.0.0.1")
        self.assertEqual(defaults.port, 8000)
        self.assertEqual(defaults.cors_origins, (
            "http://localhost:5173", "http://127.0.0.1:5173",
        ))

        configured = Settings.from_env({
            "SONIC_HOST": "0.0.0.0",
            "SONIC_PORT": "8765",
            "SONIC_CORS_ORIGINS": " https://app.example.test/ , http://localhost:5180 ",
        })
        self.assertEqual(configured.host, "0.0.0.0")
        self.assertEqual(configured.port, 8765)
        self.assertEqual(configured.cors_origins, (
            "https://app.example.test", "http://localhost:5180",
        ))

    def test_rejects_invalid_ports(self):
        for value in ("nope", "0", "65536"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings.from_env({"SONIC_PORT": value})


if __name__ == "__main__":
    unittest.main()
