"""Semantic search over the local Sonic Telescope index."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from index_store import IndexStore
from indexer import TEXT_MODEL_NAME


class SemanticSearch:
    """Embed a query and rank indexed files by cosine similarity."""

    def __init__(self, store: Optional[IndexStore] = None):
        self.store = store or IndexStore()
        self._text_model = None

    def _load_text_model(self):
        if self._text_model is None:
            from sentence_transformers import SentenceTransformer

            print("Loading text embedding model for search...")
            self._text_model = SentenceTransformer(TEXT_MODEL_NAME)
        return self._text_model

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        limit = max(1, min(int(limit or 20), 100))
        rows = self.store.all_with_embeddings()
        if not rows:
            return []

        model = self._load_text_model()
        q = np.asarray(model.encode(query), dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm

        scored: List[Dict[str, Any]] = []
        for row in rows:
            blob = row.get("embedding")
            dim = row.get("embedding_dim") or 0
            if not blob or not dim:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.shape[0] != dim:
                # Tolerate dim mismatch (e.g. text vs CLIP) by skipping
                # when dimensions differ from query space
                if vec.shape[0] != q.shape[0]:
                    continue
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                continue
            score = float(np.dot(q, vec / v_norm))
            snippet = (row.get("text_excerpt") or "")[:240]
            reasons = []
            if snippet:
                reasons.append("Matched indexed excerpt")
            if row.get("mime"):
                reasons.append(f"mime={row['mime']}")
            scored.append(
                {
                    "path": row["path"],
                    "filename": row["path"].rsplit("/", 1)[-1],
                    "score": round(score, 4),
                    "snippet": snippet,
                    "reasons": "; ".join(reasons) if reasons else "Embedding similarity",
                    "mime": row.get("mime"),
                    "size": row.get("size"),
                    "mtime": row.get("mtime"),
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
