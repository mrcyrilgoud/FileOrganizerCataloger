"""Semantic search over the local Sonic Telescope index."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from index_store import IndexStore
from models import TEXT_MODEL_NAME, encode_texts, l2_normalize


class SemanticSearch:
    """Embed a query and rank indexed files by cosine similarity."""

    def __init__(self, store=None):
        self.store = store or IndexStore()

    def invalidate(self):
        """Retained for callers; searches read current rows in bounded batches."""

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        if not self.store.has_embeddings():
            return []
        limit = max(1, min(int(limit or 20), 100))
        q = l2_normalize(np.asarray(encode_texts([query])[0], dtype=np.float32))
        if q is None:
            return []
        self.store.assert_embedding_profile(TEXT_MODEL_NAME, q.shape[0])
        best = []
        for batch in self.store.iter_embedding_batches():
            vecs, meta = [], []
            for row in batch:
                blob, dim = row.get("embedding"), row.get("embedding_dim") or 0
                if not blob or not dim:
                    continue
                vec = np.frombuffer(blob, dtype=np.float32)
                if vec.shape[0] != dim or vec.shape != q.shape:
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
            if not vecs:
                continue
            scores = np.ascontiguousarray(np.vstack(vecs), dtype=np.float32) @ q
            paths = [item["path"] for item in meta]
            local_order = np.lexsort((paths, -scores))[:limit]
            candidates = best + [
                (float(scores[idx]), meta[int(idx)]) for idx in local_order
            ]
            best = sorted(candidates, key=lambda item: (-item[0], item[1]["path"]))[:limit]
        return [dict(item, score=round(score, 4)) for score, item in best]
