from __future__ import annotations

import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from models import encode_texts  # noqa: E402


class ConcurrentModel:
    def __init__(self):
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0

    def encode(self, texts, **_kwargs):
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.02)
        with self._guard:
            self.active -= 1
        return np.ones((len(texts), 2), dtype=np.float32)


class ModelSerializationTests(unittest.TestCase):
    def test_text_embedding_calls_are_serialized(self):
        model = ConcurrentModel()
        with patch("models.get_text_model", return_value=model):
            with ThreadPoolExecutor(max_workers=6) as pool:
                outputs = list(pool.map(lambda _index: encode_texts(["query"]), range(12)))
        self.assertEqual(model.max_active, 1)
        self.assertTrue(all(output.shape == (1, 2) for output in outputs))


if __name__ == "__main__":
    unittest.main()
