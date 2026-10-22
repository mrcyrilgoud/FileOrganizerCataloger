from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from index_store import IndexStore  # noqa: E402
from search import SemanticSearch  # noqa: E402


class ObservedStore(IndexStore):
    def __init__(self, db_path):
        self.batch_sizes = []
        super().__init__(db_path=db_path)

    def all_with_embeddings(self):
        raise AssertionError("search must not materialize the complete index")

    def iter_embedding_batches(self, batch_size=512):
        for batch in super().iter_embedding_batches(batch_size):
            self.batch_sizes.append(len(batch))
            yield batch


class SearchStreamingTests(unittest.TestCase):
    def test_streams_bounded_batches_and_preserves_top_k_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservedStore(Path(tmp) / "index.db")
            rows = []
            for index in range(1025):
                vector = np.asarray([1.0, 0.0] if index % 3 else [0.0, 1.0], dtype=np.float32)
                path = str(Path(tmp) / f"{index:04}.txt")
                rows.append({
                    "path": path, "mtime": 1.0, "size": 1, "mime": "text/plain",
                    "text_excerpt": "item", "embedding": vector.tobytes(),
                    "embedding_dim": 2, "last_indexed": 1.0,
                })
            store.upsert_many(rows)
            searcher = SemanticSearch(store=store)

            with patch("search.encode_texts", return_value=np.asarray([[1.0, 0.0]], dtype=np.float32)):
                hits = searcher.search("query", limit=10)

            expected = sorted(
                [row["path"] for i, row in enumerate(rows) if i % 3 != 0]
            )[:10]
            self.assertEqual([hit["path"] for hit in hits], expected)
            self.assertEqual(store.batch_sizes, [512, 512, 1])
            self.assertTrue(all(hit["score"] == 1.0 for hit in hits))


if __name__ == "__main__":
    unittest.main()
