"""Sonic Telescope FastAPI — Phase 1 semantic library."""

from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actions import trash_path
from explain import ExplainError, FileExplainer
from indexer import IndexCancelled, Indexer
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
_explain_lock = threading.Lock()


class IndexJobManager:
    """In-process job registry; one index writer runs at a time."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def start(self, directory):
        with self._lock:
            for job in self._jobs.values():
                if job["status"] in {"queued", "running", "cancelling"}:
                    raise RuntimeError("An indexing job is already active")
            job_id = uuid.uuid4().hex
            job = {
                "job_id": job_id, "directory": str(Path(directory).expanduser().resolve()),
                "status": "queued", "stage": "queued", "completed": 0,
                "total": None, "result": None, "error": None,
                "created_at": time.time(), "cancel_event": threading.Event(),
            }
            self._jobs[job_id] = job
            threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
            return self._public(job)

    def _run(self, job_id):
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "running"

        def progress(update):
            with self._lock:
                current = self._jobs.get(job_id)
                if current is not None:
                    current.update(update)

        try:
            result = indexer.index_directory(
                job["directory"], progress_callback=progress,
                cancel_event=job["cancel_event"],
            )
        except IndexCancelled:
            with self._lock:
                job.update(status="cancelled", stage="cancelled")
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.update(status="failed", stage="failed", error=str(exc))
        else:
            with self._lock:
                job.update(status="completed", stage="completed", result=result)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None, "missing"
            if job["status"] not in {"queued", "running", "cancelling"}:
                return self._public(job), "finished"
            if job["stage"] == "saving":
                return self._public(job), "saving"
            job["cancel_event"].set()
            job["status"] = "cancelling"
            return self._public(job), "accepted"

    @staticmethod
    def _public(job):
        return {key: value for key, value in job.items() if key != "cancel_event"}


index_jobs = IndexJobManager()


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


@app.post("/index", status_code=202)
def index_directory(req: DirectoryRequest, response: Response):
    if not os.path.isdir(req.directory):
        _http(400, "Invalid directory path")
    try:
        job = index_jobs.start(req.directory)
        response.headers["Location"] = "/jobs/%s" % job["job_id"]
        return job
    except RuntimeError as exc:
        _http(409, str(exc), exc)


@app.get("/jobs/{job_id}")
def get_index_job(job_id: str):
    job = index_jobs.get(job_id)
    if job is None:
        _http(404, "Index job not found")
    return job


@app.post("/jobs/{job_id}/cancel")
def cancel_index_job(job_id: str):
    job, outcome = index_jobs.cancel(job_id)
    if outcome == "missing":
        _http(404, "Index job not found")
    if outcome == "finished":
        _http(409, "Index job has already finished")
    if outcome == "saving":
        _http(409, "Index job is saving catalog changes and can no longer be cancelled")
    return job


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
        with _explain_lock:
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
