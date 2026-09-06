"""Sonic Telescope FastAPI — Phase 1 semantic library."""

from __future__ import annotations

import os
import subprocess
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actions import delete_directory_safely, delete_file_safely
from explain import ExplainError, FileExplainer
from indexer import Indexer
from search import SemanticSearch

app = FastAPI(title="Sonic Telescope API", description="Local semantic file library (Phase 1).")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
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
    fn = delete_directory_safely if os.path.isdir(req.file_path) else delete_file_safely
    success, msg = fn(req.file_path)
    if not success:
        _http(400, msg)
    try:
        indexer.store.delete(req.file_path)
        searcher.invalidate()
    except Exception:
        pass
    return {"status": "deleted", "path": req.file_path}


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
        p.join()
        return {"path": result or ""}
    except Empty:
        p.terminate()
        return {"path": ""}
    except Exception:
        return {"path": ""}


@app.post("/browse")
def browse_directory():
    return browse_directory_process()


@app.post("/open")
def open_file(req: OpenRequest):
    if not os.path.exists(req.file_path):
        _http(404, "File not found")
    try:
        subprocess.call(["open", req.file_path])
        return {"status": "opened", "path": req.file_path}
    except Exception as exc:  # noqa: BLE001
        _http(500, "Failed to open file: %s" % exc, exc)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
