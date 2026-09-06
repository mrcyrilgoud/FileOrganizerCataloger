"""Lightweight Phase 1 store/search tests (no SentenceTransformer download)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from index_store import IndexStore
from indexer import Indexer
from search import SemanticSearch


class _FakeModel(object):
    def encode(self, texts, batch_size=32, show_progress_bar=False):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for text in texts:
            vec = np.zeros(4, dtype=np.float32)
            vec[0] = 1.0 if "alpha" in text else 0.2
            vec[1] = 1.0 if "beta" in text else 0.1
            out.append(vec)
        arr = np.vstack(out)
        return arr[0] if len(texts) == 1 else arr


def _row(path, vec, excerpt="excerpt"):
    return {
        "path": path,
        "mtime": 1.0,
        "size": 10,
        "mime": "text/plain",
        "text_excerpt": excerpt,
        "embedding": np.asarray(vec, dtype=np.float32).tobytes(),
        "embedding_dim": 4,
        "last_indexed": time.time(),
    }


class IndexStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(db_path=Path(self.tmp.name) / "index.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_upsert_many_and_meta_map(self):
        self.store.upsert_many(
            [
                _row("/a.txt", [1, 0, 0, 0]),
                _row("/b.txt", [0, 1, 0, 0]),
            ]
        )
        meta = self.store.meta_map()
        self.assertEqual(meta["/a.txt"], (1.0, 10))
        self.assertEqual(meta["/b.txt"], (1.0, 10))
        self.store.upsert(
            path="/a.txt",
            mtime=2.5,
            size=99,
            mime="text/plain",
            text_excerpt="x",
            embedding=np.ones(4, dtype=np.float32).tobytes(),
            embedding_dim=4,
            last_indexed=time.time(),
        )
        self.assertEqual(self.store.meta_map()["/a.txt"], (2.5, 99))
        self.assertEqual(self.store.count(), 2)


class SearchCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(db_path=Path(self.tmp.name) / "index.db")
        self.searcher = SemanticSearch(store=self.store)
        self._real = None

    def tearDown(self):
        import search as search_mod

        if self._real is not None:
            search_mod.get_text_model = self._real
        self.tmp.cleanup()

    def _patch_model(self):
        import search as search_mod

        self._real = search_mod.get_text_model
        search_mod.get_text_model = lambda: _FakeModel()

    def test_cache_and_argpartition(self):
        self._patch_model()
        rows = []
        for i in range(12):
            vec = np.array([0.1, 0.1, 0.0, 0.0], dtype=np.float32)
            if i == 3:
                vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
            if i == 7:
                vec = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)
            rows.append(_row("/f%02d.txt" % i, vec, excerpt="alpha" if i in (3, 7) else "other"))
        self.store.upsert_many(rows)
        hits = self.searcher.search("alpha", limit=2)
        self.assertEqual(len(hits), 2)
        self.assertEqual(set(h["path"] for h in hits), {"/f03.txt", "/f07.txt"})
        self.assertGreaterEqual(hits[0]["score"], hits[1]["score"])
        warm = self.searcher._matrix
        self.searcher.search("alpha", limit=1)
        self.assertIs(self.searcher._matrix, warm)
        self.searcher.invalidate()
        self.assertIsNone(self.searcher._matrix)


class IndexerSkipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "corpus"
        self.root.mkdir()
        self.store = IndexStore(db_path=Path(self.tmp.name) / "index.db")
        self.indexer = Indexer(store=self.store)
        self._real = None

    def tearDown(self):
        import indexer as indexer_mod

        if self._real is not None:
            indexer_mod.get_text_model = self._real
        self.tmp.cleanup()

    def _patch_model(self):
        import indexer as indexer_mod

        self._real = indexer_mod.get_text_model
        indexer_mod.get_text_model = lambda: _FakeModel()

    def test_skip_when_mtime_and_size_unchanged(self):
        self._patch_model()
        path = self.root / "note.txt"
        path.write_text("alpha document")
        first = self.indexer.index_directory(str(self.root))
        self.assertEqual(first["indexed"], 1)
        second = self.indexer.index_directory(str(self.root))
        self.assertEqual(second["indexed"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertGreaterEqual(second["skipped"], 1)
        path.write_text("alpha document changed")
        third = self.indexer.index_directory(str(self.root))
        self.assertEqual(third["updated"], 1)


class ClipDefaultTests(unittest.TestCase):
    def test_clip_off_uses_filename_label(self):
        old = os.environ.get("SONIC_ENABLE_CLIP")
        os.environ.pop("SONIC_ENABLE_CLIP", None)
        try:
            from models import clip_enabled, image_file_label

            self.assertFalse(clip_enabled())
            self.assertEqual(image_file_label("/tmp/passport.png"), "Image file: passport.png")
        finally:
            if old is None:
                os.environ.pop("SONIC_ENABLE_CLIP", None)
            else:
                os.environ["SONIC_ENABLE_CLIP"] = old


class ApiSurfaceTests(unittest.TestCase):
    def test_stable_routes_and_no_scan(self):
        from fastapi.testclient import TestClient
        import main as main_mod

        paths = {route.path for route in main_mod.app.routes}
        for needed in ("/health", "/index", "/search", "/explain", "/browse", "/open", "/delete"):
            self.assertIn(needed, paths)
        self.assertNotIn("/scan", paths)
        client = TestClient(main_mod.app)
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["product"], "sonic-telescope")


if __name__ == "__main__":
    unittest.main()
