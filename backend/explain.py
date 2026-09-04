"""Local Ollama explanations for indexed files (loopback only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from index_store import IndexStore

OLLAMA_BASE = "http://127.0.0.1:11434"
# Winner of 2026-09 A/B on 16GB M5: fast, grounded, ~2.9GB resident.
# Override with SONIC_EXPLAIN_MODEL or FileExplainer(model=...).
DEFAULT_MODEL = os.environ.get("SONIC_EXPLAIN_MODEL", "qwen3:4b-instruct")
MAX_EXCERPT_FOR_LLM = 600


class ExplainError(Exception):
    """Raised when explanation cannot be produced (fail closed)."""


class FileExplainer:
    """Explain why a file might matter using ONLY metadata + short excerpt."""

    def __init__(
        self,
        store: Optional[IndexStore] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE,
    ):
        self.store = store or IndexStore()
        self.model = model
        self.base_url = base_url.rstrip("/")

    def explain(self, path: str) -> Dict[str, Any]:
        abs_path = str(Path(path).expanduser().resolve())
        row = self.store.get(abs_path)

        # Prefer indexed metadata; fall back to light filesystem stats
        if row:
            excerpt = (row.get("text_excerpt") or "")[:MAX_EXCERPT_FOR_LLM]
            mime = row.get("mime") or "unknown"
            size = row.get("size") or 0
            mtime = row.get("mtime")
        else:
            if not os.path.exists(abs_path):
                raise ExplainError(f"File not found and not in index: {abs_path}")
            excerpt = ""
            mime = "unknown"
            try:
                st = os.stat(abs_path)
                size = st.st_size
                mtime = st.st_mtime
            except OSError as exc:
                raise ExplainError(str(exc)) from exc

        basename = os.path.basename(abs_path)
        prompt = self._build_prompt(basename, abs_path, mime, size, mtime, excerpt)

        try:
            explanation = self._call_ollama(prompt)
        except ExplainError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExplainError(
                f"Ollama request failed. Is Ollama running on {self.base_url}? "
                f"Details: {exc}"
            ) from exc

        return {
            "path": abs_path,
            "model": self.model,
            "explanation": explanation,
            "used_excerpt_chars": len(excerpt),
        }

    def _build_prompt(
        self,
        basename: str,
        abs_path: str,
        mime: str,
        size: int,
        mtime: Any,
        excerpt: str,
    ) -> str:
        return (
            "You are a careful local file librarian. Given ONLY the metadata and "
            "short excerpt below, explain in 2-4 sentences why this file might "
            "matter to the user (or why it might be disposable). Do not invent "
            "contents that are not implied. If unsure, say so.\n\n"
            f"Filename: {basename}\n"
            f"Path: {abs_path}\n"
            f"MIME: {mime}\n"
            f"Size bytes: {size}\n"
            f"mtime epoch: {mtime}\n"
            f"Excerpt:\n{excerpt if excerpt else '(no excerpt available)'}\n"
        )

    def _call_ollama(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Disable Qwen3 "thinking" so tokens go to the visible response.
            "think": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 2048,
                "num_predict": 256,
            },
        }
        try:
            timeout = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
            with httpx.Client(timeout=timeout) as client:
                # Quick health probe
                try:
                    client.get(f"{self.base_url}/api/tags")
                except httpx.ConnectError as exc:
                    raise ExplainError(
                        f"Ollama is not reachable at {self.base_url}. "
                        "Start Ollama and pull the Explain model (default: qwen3:4b-instruct)."
                    ) from exc
                except httpx.TimeoutException as exc:
                    raise ExplainError(
                        f"Ollama timed out at {self.base_url} during health check."
                    ) from exc

                try:
                    resp = client.post(url, json=payload)
                except httpx.TimeoutException as exc:
                    raise ExplainError(
                        f"Ollama generate timed out after 180s using model {self.model}. "
                        "Retry once the model is warm, or check `ollama ps`."
                    ) from exc

                if resp.status_code != 200:
                    raise ExplainError(
                        f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                text = (data.get("response") or "").strip()
                if not text:
                    raise ExplainError("Ollama returned an empty response.")
                return text
        except ExplainError:
            raise
        except httpx.ConnectError as exc:
            raise ExplainError(
                f"Ollama is not reachable at {self.base_url}. "
                "Start Ollama locally and retry."
            ) from exc
        except httpx.HTTPError as exc:
            raise ExplainError(
                f"Ollama request failed at {self.base_url}: {exc}"
            ) from exc
