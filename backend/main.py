"""Sonic Telescope FastAPI — Phase 1 semantic library + legacy scan."""

from __future__ import annotations

import os
import subprocess
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actions import delete_directory_safely, delete_file_safely
from analyzer import FileAnalyzer
from explain import ExplainError, FileExplainer
from indexer import Indexer
from search import SemanticSearch

app = FastAPI(
    title="Sonic Telescope API",
    description="Local semantic file library (Phase 1). Cleanup/organize stubs later.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-capable shared instances
analyzer = FileAnalyzer()
indexer = Indexer()
searcher = SemanticSearch(store=indexer.store)
explainer = FileExplainer(store=indexer.store)


class DirectoryRequest(BaseModel):
    directory: str


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = Field(default=20, ge=1, le=100)


class ExplainRequest(BaseModel):
    path: str
    model: Optional[str] = Field(
        default=None,
        description="Optional Ollama model override (default: qwen3:4b-instruct / SONIC_EXPLAIN_MODEL).",
    )


class DeleteRequest(BaseModel):
    file_path: str


class OpenRequest(BaseModel):
    file_path: str


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "product": "sonic-telescope",
        "phase": 1,
        "indexed_files": indexer.store.count(),
        "explain_model": explainer.model,
    }


@app.post("/index")
def index_directory(req: DirectoryRequest):
    """Walk a directory, embed files, upsert into the local SQLite index (sync v1)."""
    directory = req.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    try:
        result = indexer.index_directory(directory)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Index failed: {exc}") from exc


@app.post("/search")
def semantic_search(req: SearchRequest):
    """Embed the query and return top-k cosine matches from the local index."""
    try:
        hits = searcher.search(req.query, limit=req.limit or 20)
        return {"query": req.query, "count": len(hits), "results": hits}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc


@app.post("/explain")
def explain_file(req: ExplainRequest):
    """Ask local Ollama why a file might matter. Default: qwen3:4b-instruct. Fail closed if down."""
    try:
        if req.model:
            return FileExplainer(store=indexer.store, model=req.model).explain(req.path)
        return explainer.explain(req.path)
    except ExplainError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Explain failed: {exc}") from exc


@app.post("/scan")
def scan_directory(req: DirectoryRequest):
    """
    LEGACY: importance-score scan using FileAnalyzer.

    Prefer POST /index + POST /search for the Phase 1 product flow.
    Kept for compatibility during the redesign transition.
    """
    directory = req.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail="Invalid directory path")

    results = []
    for root, dirs, files in os.walk(directory):
        for d in dirs:
            if d.startswith("."):
                continue
            full_path = os.path.join(root, d)
            results.append(
                {
                    "path": full_path,
                    "filename": d,
                    "importance": "Container",
                    "score": 0.0,
                    "reasons": "Sub-directory",
                    "mime_type": "directory",
                    "modified": "",
                }
            )
        for file in files:
            if file.startswith("."):
                continue
            full_path = os.path.join(root, file)
            results.append(analyzer.analyze_file(full_path))

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@app.post("/delete")
def delete_item(req: DeleteRequest):
    """Manually delete a file OR directory (send to Trash)."""
    if os.path.isdir(req.file_path):
        success, msg = delete_directory_safely(req.file_path)
    else:
        success, msg = delete_file_safely(req.file_path)

    if not success:
        raise HTTPException(status_code=400, detail=msg)
    # Keep search index consistent when possible
    try:
        indexer.store.delete(req.file_path)
    except Exception:
        pass
    return {"status": "deleted", "path": req.file_path}


@app.post("/browse")
def browse_directory():
    """Open a native folder picker on the server machine; return selected path."""
    return browse_directory_process()


def _tkinter_worker(queue):
    import tkinter as tk
    from tkinter import filedialog

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder_selected = filedialog.askdirectory()
        root.destroy()
        queue.put(folder_selected)
    except Exception:
        queue.put(None)


def browse_directory_process():
    import multiprocessing
    from queue import Empty

    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=_tkinter_worker, args=(queue,))
    p.start()
    try:
        result = queue.get(timeout=60)
        p.join()
        return {"path": result or ""}
    except Empty:
        p.terminate()
        return {"path": ""}
    except Exception:
        return {"path": ""}


@app.post("/open")
def open_file(req: OpenRequest):
    """Open a file with the default OS application (macOS `open`)."""
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        subprocess.call(["open", req.file_path])
        return {"status": "opened", "path": req.file_path}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Failed to open file: {exc}"
        ) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
