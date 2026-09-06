"""API surface + module compile checks (outside backend/*.py LOC metric)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from actions import delete_directory_safely, delete_file_safely  # noqa: E402
from explain import ExplainError, FileExplainer  # noqa: E402
from index_store import IndexStore  # noqa: E402
from indexer import Indexer  # noqa: E402
from main import app  # noqa: E402
from search import SemanticSearch  # noqa: E402


EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("POST", "/index"),
    ("POST", "/search"),
    ("POST", "/explain"),
    ("POST", "/browse"),
    ("POST", "/open"),
    ("POST", "/delete"),
}


class SurfaceTests(unittest.TestCase):
    def test_routes_unchanged(self):
        found = set()
        for route in app.routes:
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", None)
            for method in methods:
                if method in {"HEAD", "OPTIONS"}:
                    continue
                found.add((method, path))
        self.assertTrue(EXPECTED_ROUTES.issubset(found), found)
        self.assertNotIn(("POST", "/scan"), found)

    def test_health_shape(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        for key in ("status", "product", "phase", "indexed_files", "explain_model"):
            self.assertIn(key, body)
        self.assertEqual(body["product"], "sonic-telescope")

    def test_search_empty_query(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.post("/search", json={"query": "   "})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_index_rejects_bad_dir(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.post("/index", json={"directory": "/definitely/not/a/real/path"})
        self.assertEqual(res.status_code, 400)

    def test_open_missing_is_404(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.post("/open", json={"file_path": "/definitely/missing.txt"})
        self.assertEqual(res.status_code, 404)

    def test_delete_missing_is_400(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.post("/delete", json={"file_path": "/definitely/missing.txt"})
        self.assertEqual(res.status_code, 400)

    def test_store_skip_and_search_cache(self):
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            self.skipTest("sentence-transformers not installed")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "index.db"
            store = IndexStore(db_path=db)
            searcher = SemanticSearch(store=store)
            indexer = Indexer(store=store, on_change=searcher.invalidate)
            folder = Path(tmp) / "corpus"
            folder.mkdir()
            sample = folder / "note.txt"
            sample.write_text("passport renewal notes and tax docs", encoding="utf-8")
            first = indexer.index_directory(str(folder))
            self.assertGreaterEqual(first["indexed"], 1)
            second = indexer.index_directory(str(folder))
            self.assertEqual(second["indexed"], 0)
            self.assertEqual(second["updated"], 0)
            self.assertGreaterEqual(second["skipped"], 1)
            hits = searcher.search("passport tax", limit=5)
            self.assertTrue(hits)
            self.assertIn("score", hits[0])
            self.assertIn("path", hits[0])
            cached = searcher.search("passport tax", limit=5)
            self.assertEqual(hits[0]["path"], cached[0]["path"])

    def test_trash_helpers(self):
        ok, msg = delete_file_safely("/definitely/missing.txt")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())
        ok, msg = delete_directory_safely("/definitely/missing-dir")
        self.assertFalse(ok)

    def test_explain_missing_file(self):
        explainer = FileExplainer()
        with self.assertRaises(ExplainError):
            explainer.explain("/definitely/missing-and-unindexed.txt")

    def test_clip_off_by_default(self):
        os.environ.pop("SONIC_ENABLE_CLIP", None)
        from models import clip_enabled, image_file_label

        self.assertFalse(clip_enabled())
        self.assertTrue(image_file_label("photo.png").startswith("Image file:"))


if __name__ == "__main__":
    unittest.main()
