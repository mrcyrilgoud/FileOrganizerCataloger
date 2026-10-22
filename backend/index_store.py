"""SQLite index store for Sonic Telescope Phase 1 semantic library."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

APP_DIR = Path.home() / ".sonic-telescope"
DB_PATH = APP_DIR / "index.db"
_KEYS = (
    "path",
    "mtime",
    "size",
    "mime",
    "text_excerpt",
    "embedding",
    "embedding_dim",
    "last_indexed",
)
_UPSERT_SQL = (
    "INSERT INTO files (%s) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
    "mtime=excluded.mtime, size=excluded.size, mime=excluded.mime, "
    "text_excerpt=excluded.text_excerpt, embedding=excluded.embedding, "
    "embedding_dim=excluded.embedding_dim, last_indexed=excluded.last_indexed"
    % ", ".join(_KEYS)
)


class IndexStore:
    """Local SQLite store for file metadata + embedding blobs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS files ("
                "path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL, "
                "mime TEXT, text_excerpt TEXT, embedding BLOB, embedding_dim INTEGER, "
                "last_indexed REAL NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime)")

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
            return dict(row) if row else None

    def meta_map(self) -> Dict[str, Tuple[float, int]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute("SELECT path, mtime, size FROM files").fetchall()
        return {r["path"]: (float(r["mtime"]), int(r["size"])) for r in rows}

    def upsert_many(self, rows: Iterable[Dict[str, Any]]) -> None:
        payload = [tuple(row[k] for k in _KEYS) for row in rows]
        if not payload:
            return
        with closing(self._connect()) as conn, conn:
            conn.executemany(_UPSERT_SQL, payload)

    def delete(self, path: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM files WHERE path = ?", (path,))

    def delete_many(self, paths: Iterable[str]) -> int:
        payload = [(path,) for path in paths]
        if not payload:
            return 0
        with closing(self._connect()) as conn, conn:
            cursor = conn.executemany("DELETE FROM files WHERE path = ?", payload)
            return cursor.rowcount

    def all_with_embeddings(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE embedding IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def iter_embedding_batches(self, batch_size: int = 512):
        """Yield bounded batches so searches do not materialize the full index."""
        size = max(1, int(batch_size))
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "SELECT path, mtime, size, mime, text_excerpt, embedding, embedding_dim "
                "FROM files WHERE embedding IS NOT NULL ORDER BY path"
            )
            while True:
                rows = cursor.fetchmany(size)
                if not rows:
                    break
                yield [dict(row) for row in rows]

    def count(self) -> int:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()
            return int(row["n"]) if row else 0
