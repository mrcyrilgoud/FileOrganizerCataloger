"""API surface + module compile checks (outside backend/*.py LOC metric)."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
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
    ("GET", "/jobs/{job_id}"),
    ("POST", "/jobs/{job_id}/cancel"),
    ("POST", "/index/reset"),
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

    def test_index_job_progress_serialization_and_cancellation(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            started = threading.Event()
            db = IndexStore(db_path=Path(tmp) / "index.db")

            def wait_for_cancel(directory, progress_callback, cancel_event):
                progress_callback({"stage": "scanning", "completed": 1, "total": None})
                started.set()
                while not cancel_event.wait(0.01):
                    pass
                from indexer import IndexCancelled
                raise IndexCancelled("cancelled")

            with patch("main.indexer.store", db), patch("main.indexer.index_directory", side_effect=wait_for_cancel):
                client = TestClient(app)
                response = client.post("/index", json={"directory": tmp})
                self.assertEqual(response.status_code, 202)
                job_id = response.json()["job_id"]
                self.assertTrue(started.wait(1))
                self.assertEqual(client.get(f"/jobs/{job_id}").status_code, 200)
                self.assertEqual(client.post("/index", json={"directory": tmp}).status_code, 409)
                cancelled = client.post(f"/jobs/{job_id}/cancel")
                self.assertEqual(cancelled.status_code, 200)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    state = client.get(f"/jobs/{job_id}").json()
                    if state["status"] == "cancelled":
                        break
                    time.sleep(0.01)
                self.assertEqual(state["status"], "cancelled")
                self.assertEqual(client.post(f"/jobs/{job_id}/cancel").status_code, 409)
                self.assertEqual(client.get("/jobs/unknown").status_code, 404)

    def test_index_job_api_completes_and_searches_indexed_files(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            corpus.mkdir()
            sample = corpus / "passport.txt"
            sample.write_text("passport renewal checklist", encoding="utf-8")
            db = IndexStore(db_path=root / "index.db")

            def encode(texts, **_kwargs):
                return np.tile([1.0, 0.0], (len(texts), 1))

            with patch("main.indexer.store", db), patch("main.searcher.store", db), patch("indexer.encode_texts", side_effect=encode), patch("search.encode_texts", side_effect=encode):
                client = TestClient(app)
                started = client.post("/index", json={"directory": str(corpus)})
                self.assertEqual(started.status_code, 202)
                job_id = started.json()["job_id"]
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    state = client.get(f"/jobs/{job_id}").json()
                    if state["status"] in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(state["status"], "completed", state)
                self.assertEqual(state["result"]["indexed"], 1)
                response = client.post("/search", json={"query": "passport", "limit": 5})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"][0]["path"], str(sample.resolve()))

    def test_legacy_embedding_index_requires_explicit_clear_before_rebuild(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            corpus.mkdir()
            sample = corpus / "note.txt"
            sample.write_text("legacy migration test", encoding="utf-8")
            db = IndexStore(db_path=root / "index.db")
            legacy_path = str((root / "legacy.txt").resolve())
            db.upsert_many([{
                "path": legacy_path, "mtime": 1.0, "size": 6, "mime": "text/plain",
                "text_excerpt": "legacy", "embedding": np.asarray([1.0, 0.0], dtype=np.float32).tobytes(),
                "embedding_dim": 2, "last_indexed": 1.0,
            }])

            def encode(texts, **_kwargs):
                return np.tile([1.0, 0.0], (len(texts), 1))

            with patch("main.indexer.store", db), patch("main.searcher.store", db), patch("search.encode_texts", side_effect=encode), patch("indexer.encode_texts", side_effect=encode):
                client = TestClient(app)
                conflict = client.post("/index", json={"directory": str(corpus)})
                self.assertEqual(conflict.status_code, 409)
                self.assertIn("legacy embeddings", conflict.json()["detail"])
                self.assertEqual(client.post("/search", json={"query": "legacy"}).status_code, 409)

                reset = client.post("/index/reset")
                self.assertEqual(reset.status_code, 200)
                self.assertEqual(reset.json()["removed"], 1)
                self.assertFalse(reset.json()["files_deleted_from_disk"])
                self.assertIsNotNone(sample.stat())

                started = client.post("/index", json={"directory": str(corpus)})
                self.assertEqual(started.status_code, 202)
                job_id = started.json()["job_id"]
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    state = client.get(f"/jobs/{job_id}").json()
                    if state["status"] in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(state["status"], "completed", state)
                self.assertEqual(db.embedding_profile(), {
                    "embedding_model": "all-MiniLM-L6-v2", "embedding_dimension": "2",
                })

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

    def test_file_actions_require_indexed_regular_files_and_normalize_paths(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexed = root / "indexed.txt"
            unindexed = root / "unindexed.txt"
            folder = root / "folder"
            indexed.write_text("indexed content", encoding="utf-8")
            unindexed.write_text("outside catalog", encoding="utf-8")
            folder.mkdir()
            db = IndexStore(db_path=root / "index.db")
            db.upsert_many([{
                "path": str(indexed.resolve()), "mtime": 1.0, "size": 16,
                "mime": "text/plain", "text_excerpt": "indexed content",
                "embedding": b"\x00\x00\x80?", "embedding_dim": 1,
                "last_indexed": 1.0,
            }])
            with patch("main.indexer.store", db), patch("main.trash_path", return_value=(True, "ok")) as trash, patch("main.searcher.invalidate"):
                client = TestClient(app)
                rejected = client.post("/delete", json={"file_path": str(unindexed)})
                self.assertEqual(rejected.status_code, 404)
                self.assertEqual(client.post("/delete", json={"file_path": str(folder)}).status_code, 400)

                alias = root / "alias.txt"
                alias.symlink_to(indexed)
                response = client.post("/delete", json={"file_path": str(alias)})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["path"], str(indexed.resolve()))
                trash.assert_called_once_with(str(indexed.resolve()))
                self.assertIsNone(db.get(str(indexed.resolve())))

    def test_delete_reports_trash_success_when_catalog_cleanup_fails(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "indexed.txt"
            file_path.write_text("indexed content", encoding="utf-8")
            db = IndexStore(db_path=Path(tmp) / "index.db")
            db.upsert_many([{
                "path": str(file_path.resolve()), "mtime": 1.0, "size": 16,
                "mime": "text/plain", "text_excerpt": "indexed content",
                "embedding": b"\x00\x00\x80?", "embedding_dim": 1,
                "last_indexed": 1.0,
            }])
            with patch("main.indexer.store", db), patch("main.trash_path", return_value=(True, "ok")), patch.object(db, "delete", side_effect=OSError("database locked")):
                response = TestClient(app).post("/delete", json={"file_path": str(file_path)})
            self.assertEqual(response.status_code, 500)
            self.assertIn("moved to Trash, but index cleanup failed", response.json()["detail"])

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
