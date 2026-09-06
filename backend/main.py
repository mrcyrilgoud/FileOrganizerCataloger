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
    directory = req.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    try:
        return indexer.index_directory(directory)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Index failed: %s" % exc) from exc


@app.post("/search")
def semantic_search(req: SearchRequest):
    try:
        hits = searcher.search(req.query, limit=req.limit or 20)
        return {"query": req.query, "count": len(hits), "results": hits}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Search failed: %s" % exc) from exc


@app.post("/explain")
def explain_file(req: ExplainRequest):
    try:
        if req.model:
            return FileExplainer(store=indexer.store, model=req.model).explain(req.path)
        return explainer.explain(req.path)
    except ExplainError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Explain failed: %s" % exc) from exc


@app.post("/delete")
def delete_item(req: DeleteRequest):
    if os.path.isdir(req.file_path):
        success, msg = delete_directory_safely(req.file_path)
    else:
        success, msg = delete_file_safely(req.file_path)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    try:
        indexer.store.delete(req.file_path)
    except Exception:
        pass
    return {"status": "deleted", "path": req.file_path}


@app.post("/browse")
def browse_directory():
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
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        subprocess.call(["open", req.file_path])
        return {"status": "opened", "path": req.file_path}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail="Failed to open file: %s" % exc
        ) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
