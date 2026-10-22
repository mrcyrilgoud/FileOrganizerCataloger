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
            conn.execute(
                "CREATE TABLE IF NOT EXISTS index_metadata ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
            return dict(row) if row else None

    def meta_map(self) -> Dict[str, Tuple[float, int]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute("SELECT path, mtime, size FROM files").fetchall()
        return {r["path"]: (float(r["mtime"]), int(r["size"])) for r in rows}

    def upsert_many(self, rows: Iterable[Dict[str, Any]], embedding_model: Optional[str] = None) -> None:
        rows = list(rows)
        payload = [tuple(row[k] for k in _KEYS) for row in rows]
        if not payload:
            return
        with closing(self._connect()) as conn, conn:
            if embedding_model is not None:
                dimensions = {int(row["embedding_dim"]) for row in rows}
                if len(dimensions) != 1:
                    raise ValueError("A single index update must use one embedding dimension")
                dimension = dimensions.pop()
                self._assert_profile(conn, embedding_model, dimension)
            conn.executemany(_UPSERT_SQL, payload)
            if embedding_model is not None:
                conn.executemany(
                    "INSERT INTO index_metadata(key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (("embedding_model", embedding_model), ("embedding_dimension", str(dimension))),
                )

    def _assert_profile(self, conn, model: str, dimension: Optional[int] = None) -> None:
        rows_exist = conn.execute(
            "SELECT 1 FROM files WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone() is not None
        if not rows_exist:
            return
        profile = dict(conn.execute(
            "SELECT key, value FROM index_metadata WHERE key IN ('embedding_model','embedding_dimension')"
        ).fetchall())
        stored_model = profile.get("embedding_model")
        stored_dimension = profile.get("embedding_dimension")
        if not stored_model or not stored_dimension:
            raise EmbeddingCompatibilityError(
                "The index contains legacy embeddings without a verified model profile. "
                "Clear the catalog and re-index folders to continue."
            )
        if stored_model != model or (dimension is not None and int(stored_dimension) != dimension):
            raise EmbeddingCompatibilityError(
                "The index uses embedding profile %s (%s dimensions), but this app uses %s%s. "
                "Clear the catalog and re-index folders to continue."
                % (
                    stored_model, stored_dimension, model,
                    (" (%s dimensions)" % dimension) if dimension is not None else "",
                )
            )

    def assert_embedding_profile(self, model: str, dimension: Optional[int] = None) -> None:
        with closing(self._connect()) as conn:
            self._assert_profile(conn, model, dimension)

    def embedding_profile(self) -> Dict[str, str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT key, value FROM index_metadata WHERE key IN ('embedding_model','embedding_dimension')"
            ).fetchall()
            return dict(rows)

    def clear_all(self) -> int:
        with closing(self._connect()) as conn, conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM index_metadata")
            return int(count)

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

    def has_embeddings(self) -> bool:
        with closing(self._connect()) as conn:
            return conn.execute(
                "SELECT 1 FROM files WHERE embedding IS NOT NULL LIMIT 1"
            ).fetchone() is not None


class EmbeddingCompatibilityError(Exception):
    """Raised when stored vectors cannot safely be compared with this model."""
