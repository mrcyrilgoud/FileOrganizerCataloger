"""Local Ollama explanations for indexed files (loopback only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from index_store import IndexStore

OLLAMA_BASE = "http://127.0.0.1:11434"
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
        if row:
            excerpt = (row.get("text_excerpt") or "")[:MAX_EXCERPT_FOR_LLM]
            mime = row.get("mime") or "unknown"
            size = row.get("size") or 0
            mtime = row.get("mtime")
        else:
            if not os.path.exists(abs_path):
                raise ExplainError("File not found and not in index: %s" % abs_path)
            excerpt, mime = "", "unknown"
            try:
                st = os.stat(abs_path)
                size, mtime = st.st_size, st.st_mtime
            except OSError as exc:
                raise ExplainError(str(exc)) from exc

        prompt = (
            "You are a careful local file librarian. Given ONLY the metadata and "
            "short excerpt below, explain in 2-4 sentences why this file might "
            "matter to the user (or why it might be disposable). Do not invent "
            "contents that are not implied. If unsure, say so.\n\n"
            "Filename: %s\nPath: %s\nMIME: %s\nSize bytes: %s\nmtime epoch: %s\n"
            "Excerpt:\n%s\n"
            % (
                os.path.basename(abs_path),
                abs_path,
                mime,
                size,
                mtime,
                excerpt if excerpt else "(no excerpt available)",
            )
        )
        try:
            explanation = self._call_ollama(prompt)
        except ExplainError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExplainError(
                "Ollama request failed. Is Ollama running on %s? Details: %s"
                % (self.base_url, exc)
            ) from exc
        return {
            "path": abs_path,
            "model": self.model,
            "explanation": explanation,
            "used_excerpt_chars": len(excerpt),
        }

    def _call_ollama(self, prompt: str) -> str:
        url = "%s/api/generate" % self.base_url
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 256},
        }
        timeout = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
        try:
            with httpx.Client(timeout=timeout) as client:
                try:
                    client.get("%s/api/tags" % self.base_url)
                except httpx.ConnectError as exc:
                    raise ExplainError(
                        "Ollama is not reachable at %s. "
                        "Start Ollama and pull the Explain model (default: qwen3:4b-instruct)."
                        % self.base_url
                    ) from exc
                except httpx.TimeoutException as exc:
                    raise ExplainError(
                        "Ollama timed out at %s during health check." % self.base_url
                    ) from exc
                try:
                    resp = client.post(url, json=payload)
                except httpx.TimeoutException as exc:
                    raise ExplainError(
                        "Ollama generate timed out after 180s using model %s. "
                        "Retry once the model is warm, or check `ollama ps`."
                        % self.model
                    ) from exc
                if resp.status_code != 200:
                    raise ExplainError(
                        "Ollama returned HTTP %s: %s" % (resp.status_code, resp.text[:300])
                    )
                text = (resp.json().get("response") or "").strip()
                if not text:
                    raise ExplainError("Ollama returned an empty response.")
                return text
        except ExplainError:
            raise
        except httpx.ConnectError as exc:
            raise ExplainError(
                "Ollama is not reachable at %s. Start Ollama locally and retry."
                % self.base_url
            ) from exc
        except httpx.HTTPError as exc:
            raise ExplainError(
                "Ollama request failed at %s: %s" % (self.base_url, exc)
            ) from exc
