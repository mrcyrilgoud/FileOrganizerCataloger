"""Sonic Telescope FastAPI — Phase 1 semantic library."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actions import trash_path
from explain import ExplainError, FileExplainer
from indexer import Indexer
from search import SemanticSearch

app = FastAPI(title="Sonic Telescope API", description="Local semantic file library (Phase 1).")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)
searcher = SemanticSearch()
indexer = Indexer(store=searcher.store, on_change=searcher.invalidate)
explainer = FileExplainer(store=searcher.store)


class DirectoryRequest(BaseModel):
    directory: str


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = Field(default=20, ge=1, le=100)


class ExplainRequest(BaseModel):
    path: str
    model: Optional[str] = None


class DeleteRequest(BaseModel):
    file_path: str


class OpenRequest(BaseModel):
    file_path: str


def _http(code, detail, exc=None):
    raise HTTPException(status_code=code, detail=detail) from exc


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
    if not os.path.isdir(req.directory):
        _http(400, "Invalid directory path")
    try:
        return indexer.index_directory(req.directory)
    except ValueError as exc:
        _http(400, str(exc), exc)
    except Exception as exc:  # noqa: BLE001
        _http(500, "Index failed: %s" % exc, exc)


@app.post("/search")
def semantic_search(req: SearchRequest):
    try:
        hits = searcher.search(req.query, limit=req.limit or 20)
        return {"query": req.query, "count": len(hits), "results": hits}
    except Exception as exc:  # noqa: BLE001
        _http(500, "Search failed: %s" % exc, exc)


@app.post("/explain")
def explain_file(req: ExplainRequest):
    try:
        target = FileExplainer(store=indexer.store, model=req.model) if req.model else explainer
        return target.explain(req.path)
    except ExplainError as exc:
        _http(503, str(exc), exc)
    except Exception as exc:  # noqa: BLE001
        _http(500, "Explain failed: %s" % exc, exc)


@app.post("/delete")
def delete_item(req: DeleteRequest):
    path = str(Path(req.file_path).expanduser().resolve())
    if not os.path.isfile(path):
        _http(400, "Only indexed regular files can be moved to Trash")
    if indexer.store.get(path) is None:
        _http(404, "File is not in the index")
    success, msg = trash_path(path)
    if not success:
        _http(400, msg)
    try:
        indexer.store.delete(path)
        searcher.invalidate()
    except Exception as exc:  # noqa: BLE001
        _http(500, "File moved to Trash, but index cleanup failed; search results may be stale", exc)
    return {"status": "deleted", "path": path}


def _tkinter_worker(queue):
    import tkinter as tk
    from tkinter import filedialog

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        queue.put(filedialog.askdirectory())
        root.destroy()
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
        p.join(timeout=1)
        return {"path": result or ""}
    except Empty:
        return {"path": ""}
    except Exception:
        return {"path": ""}
    finally:
        if p.is_alive():
            p.terminate()
        p.join(timeout=1)
        queue.close()


@app.post("/browse")
def browse_directory():
    return browse_directory_process()


@app.post("/open")
def open_file(req: OpenRequest):
    path = str(Path(req.file_path).expanduser().resolve())
    if not os.path.isfile(path):
        _http(404, "File not found")
    if indexer.store.get(path) is None:
        _http(404, "File is not in the index")
    try:
        subprocess.run(["open", path], check=True)
        return {"status": "opened", "path": path}
    except Exception as exc:  # noqa: BLE001
        _http(500, "Failed to open file: %s" % exc, exc)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
