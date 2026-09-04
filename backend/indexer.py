"""Directory walker + embedder for Sonic Telescope Phase 1."""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from index_store import IndexStore

TEXT_MODEL_NAME = "all-MiniLM-L6-v2"
IMAGE_MODEL_NAME = "clip-ViT-B-32"

# Skip binaries / huge files
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB hard cap for any file we open
MAX_TEXT_CHARS = 4000
MAX_EXCERPT_CHARS = 800
SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".sonic-telescope",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".html",
    ".htm",
    ".css",
    ".xml",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".r",
    ".tex",
    ".log",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class Indexer:
    """Walk a directory, extract text, embed, upsert into IndexStore."""

    def __init__(self, store: Optional[IndexStore] = None):
        self.store = store or IndexStore()
        self._text_model = None
        self._image_model = None

    def _load_text_model(self):
        if self._text_model is None:
            from sentence_transformers import SentenceTransformer

            print("Loading text embedding model...")
            self._text_model = SentenceTransformer(TEXT_MODEL_NAME)
        return self._text_model

    def _load_image_model(self):
        if self._image_model is None:
            from sentence_transformers import SentenceTransformer

            print("Loading CLIP image model...")
            self._image_model = SentenceTransformer(IMAGE_MODEL_NAME)
        return self._image_model

    def index_directory(self, directory: str) -> Dict[str, Any]:
        root = Path(directory).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        indexed = 0
        skipped = 0
        errors: List[str] = []
        updated = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".") and d not in SKIP_DIR_NAMES
            ]
            for name in filenames:
                if name.startswith("."):
                    skipped += 1
                    continue
                path = Path(dirpath) / name
                try:
                    result = self._index_one(path)
                    if result == "indexed":
                        indexed += 1
                    elif result == "updated":
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:  # noqa: BLE001 — collect and continue
                    errors.append(f"{path}: {exc}")
                    skipped += 1

        return {
            "directory": str(root),
            "indexed": indexed,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:50],
            "error_count": len(errors),
            "total_in_store": self.store.count(),
        }

    def _index_one(self, path: Path) -> str:
        try:
            stat = path.stat()
        except OSError:
            return "skipped"

        if not path.is_file():
            return "skipped"
        if stat.st_size > MAX_FILE_BYTES:
            return "skipped"
        if stat.st_size == 0:
            return "skipped"

        abs_path = str(path.resolve())
        existing = self.store.get(abs_path)
        if existing and abs(existing["mtime"] - stat.st_mtime) < 0.001:
            return "skipped"  # unchanged

        mime, _ = mimetypes.guess_type(abs_path)
        mime = mime or "application/octet-stream"
        ext = path.suffix.lower()

        excerpt = ""
        embedding: Optional[np.ndarray] = None

        if ext in TEXT_EXTENSIONS or (mime.startswith("text/")):
            excerpt, embedding = self._embed_text_file(path)
        elif ext in IMAGE_EXTENSIONS or mime.startswith("image/"):
            excerpt, embedding = self._embed_image_file(path, abs_path)
        else:
            # Filename-only fallback for unknown types (cheap)
            label = f"File named {path.name}"
            excerpt = label
            model = self._load_text_model()
            embedding = np.asarray(model.encode(label), dtype=np.float32)

        if embedding is None:
            return "skipped"

        blob = embedding.astype(np.float32).tobytes()
        self.store.upsert(
            path=abs_path,
            mtime=stat.st_mtime,
            size=stat.st_size,
            mime=mime,
            text_excerpt=excerpt[:MAX_EXCERPT_CHARS],
            embedding=blob,
            embedding_dim=int(embedding.shape[0]),
            last_indexed=time.time(),
        )
        return "updated" if existing else "indexed"

    def _embed_text_file(self, path: Path) -> Tuple[str, Optional[np.ndarray]]:
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "", None
        text = raw[:MAX_TEXT_CHARS]
        if not text.strip():
            return "", None
        excerpt = text[:MAX_EXCERPT_CHARS]
        model = self._load_text_model()
        emb = np.asarray(model.encode(text), dtype=np.float32)
        return excerpt, emb

    def _embed_image_file(
        self, path: Path, abs_path: str
    ) -> Tuple[str, Optional[np.ndarray]]:
        """Index images in the *text* embedding space so NL search works.

        CLIP is optional and used only to enrich the excerpt label when cheap;
        the stored vector always comes from the text model (same space as queries).
        """
        visual_label = None
        try:
            if path.stat().st_size <= 8 * 1024 * 1024:
                from PIL import Image

                img = Image.open(path).convert("RGB")
                clip = self._load_image_model()
                prompts = [
                    "a photo of a document or ID",
                    "a receipt or invoice",
                    "a screenshot",
                    "a personal photo",
                    "a diagram or chart",
                    "other image",
                ]
                from sentence_transformers import util

                img_emb = clip.encode(img)
                prompt_embs = clip.encode(prompts)
                sims = util.cos_sim(img_emb, prompt_embs)[0]
                visual_label = prompts[int(sims.argmax())]
        except Exception:
            visual_label = None

        if visual_label:
            label = f"Image ({visual_label}): {path.name}"
        else:
            label = f"Image file: {path.name}"
        model = self._load_text_model()
        emb = np.asarray(model.encode(label), dtype=np.float32)
        return label, emb
