"""Semantic search over the local Sonic Telescope index."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from index_store import IndexStore
from models import encode_texts, l2_normalize


class SemanticSearch:
    """Embed a query and rank indexed files by cosine similarity."""

    def __init__(self, store=None):
        self.store = store or IndexStore()
        self._matrix = None
        self._meta = None

    def invalidate(self):
        self._matrix = self._meta = None

    def _ensure_cache(self):
        if self._matrix is not None:
            return
        vecs, meta = [], []
        for row in self.store.all_with_embeddings():
            blob, dim = row.get("embedding"), row.get("embedding_dim") or 0
            if not blob or not dim:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.shape[0] != dim:
                continue
            unit = l2_normalize(vec)
            if unit is None:
                continue
            vecs.append(unit)
            snippet = (row.get("text_excerpt") or "")[:240]
            reasons = []
            if snippet:
                reasons.append("Matched indexed excerpt")
            if row.get("mime"):
                reasons.append("mime=%s" % row["mime"])
            meta.append({
                "path": row["path"],
                "filename": row["path"].rsplit("/", 1)[-1],
                "snippet": snippet,
                "reasons": "; ".join(reasons) if reasons else "Embedding similarity",
                "mime": row.get("mime"),
                "size": row.get("size"),
                "mtime": row.get("mtime"),
            })
        self._matrix = (
            np.ascontiguousarray(np.vstack(vecs), dtype=np.float32)
            if vecs else np.zeros((0, 0), dtype=np.float32)
        )
        self._meta = meta

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        limit = max(1, min(int(limit or 20), 100))
        self._ensure_cache()
        matrix, meta = self._matrix, self._meta or []
        if matrix is None or matrix.size == 0 or not meta:
            return []
        q = l2_normalize(np.asarray(encode_texts([query])[0], dtype=np.float32))
        if q is None or q.shape[0] != matrix.shape[1]:
            return []
        scores = matrix @ q
        k = min(limit, scores.shape[0])
        if k == scores.shape[0]:
            top = np.argsort(-scores)
        else:
            part = np.argpartition(-scores, kth=k - 1)[:k]
            top = part[np.argsort(-scores[part])]
        hits = []
        for idx in top:
            item = dict(meta[int(idx)])
            item["score"] = round(float(scores[int(idx)]), 4)
            hits.append(item)
        return hits
