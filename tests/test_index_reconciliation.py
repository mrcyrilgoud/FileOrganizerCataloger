from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from index_store import IndexStore  # noqa: E402
from indexer import Indexer  # noqa: E402
from search import SemanticSearch  # noqa: E402


class IndexReconciliationTests(unittest.TestCase):
    @staticmethod
    def _encode(texts, **_kwargs):
        return np.tile([1.0, 0.0], (len(texts), 1))

    def test_reconciles_deleted_and_moved_paths_only_within_selected_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_a = base / "a"
            root_b = base / "b"
            root_a.mkdir()
            root_b.mkdir()
            deleted = root_a / "deleted.txt"
            moved = root_a / "moved.txt"
            other_root_file = root_b / "keep.txt"
            deleted.write_text("deleted file", encoding="utf-8")
            moved.write_text("moved file", encoding="utf-8")
            other_root_file.write_text("other root", encoding="utf-8")

            store = IndexStore(db_path=base / "index.db")
            searcher = SemanticSearch(store=store)
            indexer = Indexer(store=store, on_change=searcher.invalidate)
            with patch("indexer.encode_texts", side_effect=self._encode):
                indexer.index_directory(str(root_a))
                indexer.index_directory(str(root_b))

            with patch("search.encode_texts", side_effect=self._encode):
                before = searcher.search("file", limit=20)
            self.assertEqual(len(before), 3)
            deleted.unlink()
            moved.rename(base / "moved.txt")

            with patch("indexer.encode_texts", side_effect=self._encode):
                result = indexer.index_directory(str(root_a))

            self.assertEqual(result["removed"], 2)
            self.assertEqual(result["total_in_store"], 1)
            self.assertIsNone(store.get(str(deleted.resolve())))
            self.assertIsNone(store.get(str(moved.resolve())))
            self.assertIsNotNone(store.get(str(other_root_file.resolve())))
            with patch("search.encode_texts", side_effect=self._encode):
                after = searcher.search("file", limit=20)
            self.assertEqual([hit["path"] for hit in after], [str(other_root_file.resolve())])

    def test_preserves_row_when_path_stat_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "root"
            root.mkdir()
            existing = root / "keep.txt"
            existing.write_text("preserve me", encoding="utf-8")
            existing_path = str(existing.resolve())
            store = IndexStore(db_path=base / "index.db")
            indexer = Indexer(store=store)
            with patch("indexer.encode_texts", side_effect=self._encode):
                indexer.index_directory(str(root))

            original_stat = os.stat

            def stat_with_permission_error(path, *args, **kwargs):
                if os.fspath(path) == existing_path:
                    raise PermissionError("permission denied")
                return original_stat(path, *args, **kwargs)

            with patch("indexer.os.stat", side_effect=stat_with_permission_error):
                result = indexer.index_directory(str(root))

            self.assertEqual(result["removed"], 0)
            self.assertIsNotNone(store.get(existing_path))


if __name__ == "__main__":
    unittest.main()
