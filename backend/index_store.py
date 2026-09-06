"""SQLite index store for Sonic Telescope Phase 1 semantic library."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

APP_DIR = Path.home() / ".sonic-telescope"
DB_PATH = APP_DIR / "index.db"

_UPSERT_SQL = """
INSERT INTO files (
    path, mtime, size, mime, text_excerpt,
    embedding, embedding_dim, last_indexed
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(path) DO UPDATE SET
    mtime = excluded.mtime,
    size = excluded.size,
    mime = excluded.mime,
    text_excerpt = excluded.text_excerpt,
    embedding = excluded.embedding,
    embedding_dim = excluded.embedding_dim,
    last_indexed = excluded.last_indexed
"""


def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


class IndexStore:
    """Local SQLite store for file metadata + embedding blobs."""

    def __init__(self, db_path: Optional[Path] = None):
        ensure_app_dir()
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    mime TEXT,
                    text_excerpt TEXT,
                    embedding BLOB,
                    embedding_dim INTEGER,
                    last_indexed REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime)")
            conn.commit()

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
            return dict(row) if row else None

    def meta_map(self) -> Dict[str, Tuple[float, int]]:
        """path -> (mtime, size) for cheap unchanged-file skips."""
        with self._connect() as conn:
            rows = conn.execute("SELECT path, mtime, size FROM files").fetchall()
        return {r["path"]: (float(r["mtime"]), int(r["size"])) for r in rows}

    def upsert_many(self, rows: Iterable[Dict[str, Any]]) -> None:
        payload = [
            (
                row["path"],
                row["mtime"],
                row["size"],
                row["mime"],
                row["text_excerpt"],
                row["embedding"],
                row["embedding_dim"],
                row["last_indexed"],
            )
            for row in rows
        ]
        if not payload:
            return
        with self._connect() as conn:
            conn.executemany(_UPSERT_SQL, payload)
            conn.commit()

    def upsert(
        self,
        *,
        path: str,
        mtime: float,
        size: int,
        mime: str,
        text_excerpt: str,
        embedding: bytes,
        embedding_dim: int,
        last_indexed: float,
    ) -> None:
        self.upsert_many(
            [
                {
                    "path": path,
                    "mtime": mtime,
                    "size": size,
                    "mime": mime,
                    "text_excerpt": text_excerpt,
                    "embedding": embedding,
                    "embedding_dim": embedding_dim,
                    "last_indexed": last_indexed,
                }
            ]
        )

    def delete(self, path: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (path,))
            conn.commit()

    def all_with_embeddings(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE embedding IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()
            return int(row["n"]) if row else 0
