"""Directory walker + batch embedder for Sonic Telescope Phase 1."""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from index_store import IndexStore
from models import encode_texts, image_file_label

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 4000
MAX_EXCERPT_CHARS = 800
SKIP_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".sonic-telescope",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".html", ".htm",
    ".css", ".xml", ".sql", ".sh", ".bash", ".zsh", ".rs", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".r", ".tex", ".log",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class Indexer:
    """Walk a directory, extract text, embed in batches, upsert into IndexStore."""

    def __init__(self, store=None, on_change: Optional[Callable[[], None]] = None):
        self.store = store or IndexStore()
        self.on_change = on_change

    def index_directory(self, directory: str) -> Dict[str, Any]:
        root = Path(directory).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Not a directory: %s" % directory)
        skipped, errors, pending = 0, [], []
        meta = self.store.meta_map()
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIR_NAMES]
            for name in filenames:
                if name.startswith("."):
                    skipped += 1
                    continue
                path = Path(dirpath) / name
                try:
                    item = self._collect_pending(path, meta)
                except Exception as exc:  # noqa: BLE001
                    errors.append("%s: %s" % (path, exc))
                    skipped += 1
                    continue
                if item is None:
                    skipped += 1
                else:
                    pending.append(item)
        rows, extra_skipped, extra_errors = self._embed_pending(pending)
        skipped += extra_skipped
        errors.extend(extra_errors)
        if rows:
            self.store.upsert_many(rows)
            if self.on_change is not None:
                self.on_change()
        indexed = sum(1 for row in rows if row["path"] not in meta)
        return {
            "directory": str(root),
            "indexed": indexed,
            "updated": len(rows) - indexed,
            "skipped": skipped,
            "errors": errors[:50],
            "error_count": len(errors),
            "total_in_store": self.store.count(),
        }

    def _collect_pending(self, path: Path, meta: Dict[str, Tuple[float, int]]):
        try:
            stat = path.stat()
        except OSError:
            return None
        if not path.is_file() or stat.st_size == 0 or stat.st_size > MAX_FILE_BYTES:
            return None
        abs_path = str(path.resolve())
        existing = meta.get(abs_path)
        if existing and abs(existing[0] - stat.st_mtime) < 0.001 and existing[1] == stat.st_size:
            return None
        mime, _ = mimetypes.guess_type(abs_path)
        mime = mime or "application/octet-stream"
        ext = path.suffix.lower()
        if ext in TEXT_EXTENSIONS or mime.startswith("text/"):
            kind = "text"
        elif ext in IMAGE_EXTENSIONS or mime.startswith("image/"):
            kind = "image"
        else:
            kind = "other"
        return {
            "path": abs_path, "src": path, "mtime": stat.st_mtime,
            "size": stat.st_size, "mime": mime, "kind": kind,
        }

    def _embed_pending(self, pending: List[Dict[str, Any]]):
        if not pending:
            return [], 0, []
        skipped, errors, text_items, label_items = 0, [], [], []
        for item in pending:
            try:
                if item["kind"] == "text":
                    with open(str(item["src"]), "r", encoding="utf-8", errors="ignore") as handle:
                        text = handle.read(MAX_TEXT_CHARS)
                    if not text.strip():
                        skipped += 1
                        continue
                    text_items.append((item, text))
                elif item["kind"] == "image":
                    label_items.append((item, image_file_label(item["src"])))
                else:
                    label_items.append((item, "File named %s" % item["src"].name))
            except Exception as exc:  # noqa: BLE001
                errors.append("%s: %s" % (item["path"], exc))
                skipped += 1
        now = time.time()
        rows = self._rows_from_batch(text_items, now, True)
        rows.extend(self._rows_from_batch(label_items, now, False))
        return rows, skipped, errors

    def _rows_from_batch(self, items, now, excerpt_from_text):
        if not items:
            return []
        embs = encode_texts([text for _item, text in items])
        rows = []
        for (item, text), emb in zip(items, embs):
            excerpt = text[:MAX_EXCERPT_CHARS] if excerpt_from_text else text
            emb = np.asarray(emb, dtype=np.float32)
            rows.append({
                "path": item["path"], "mtime": item["mtime"], "size": item["size"],
                "mime": item["mime"], "text_excerpt": excerpt[:MAX_EXCERPT_CHARS],
                "embedding": emb.tobytes(), "embedding_dim": int(emb.shape[0]),
                "last_indexed": now,
            })
        return rows
