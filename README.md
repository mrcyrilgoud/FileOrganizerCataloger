# Sonic Telescope

Sonic Telescope is a local semantic file library for macOS. Index a directory once, search it using natural language, and inspect why a result may be relevant—all from a lightweight React interface.

The application is currently focused on its Phase 1 workflow:

**Index → Search → Explain**

## Features

- Indexes supported files recursively and skips unchanged files on subsequent runs.
- Searches indexed content with SentenceTransformers embeddings and cosine similarity.
- Displays ranked results with filenames, paths, MIME types, sizes, scores, and excerpts.
- Optionally classifies images with CLIP when `SONIC_ENABLE_CLIP` is enabled; otherwise images are indexed by filename.
- Generates grounded explanations through Ollama on `127.0.0.1`, using only file metadata and a short stored excerpt.
- Opens files in the default macOS application and moves files to the system Trash after confirmation.

Cleanup proposals and organizer move plans are planned for later phases; their current modules are stubs. See [REDESIGN.md](REDESIGN.md) for the product direction and [docs/CODE_WALKTHROUGH.md](docs/CODE_WALKTHROUGH.md) for implementation details.

## Privacy and local data

File indexing, embeddings, search, and the SQLite index run locally. Sonic Telescope does not use cloud LLM or hosted vector-search APIs. Explanations call Ollama only through its loopback endpoint, and send the model a basename, path, MIME type, size, modification time, and at most a short excerpt—not the full file.

The text embedding model is downloaded by SentenceTransformers the first time it is needed. The optional CLIP model is downloaded only when image classification is enabled. Local index data is stored at:

```text
~/.sonic-telescope/index.db
```

## Requirements

- macOS (the folder picker, file opening, and Trash actions use macOS system behavior)
- Python 3.10 or newer
- Node.js 20.19+ or 22.12+
- Optional: [Ollama](https://ollama.com/) for the Explain action

The default explanation model is `qwen3:4b-instruct`. Install it with:

```bash
ollama pull qwen3:4b-instruct
```

You can choose another installed model with `SONIC_EXPLAIN_MODEL` or the API's optional `model` field.

## Installation

From the repository root, create a Python environment and install the backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install the frontend dependencies in a second terminal:

```bash
cd frontend
npm install
```

## Run locally

Start the API from the `backend` directory:

```bash
source .venv/bin/activate
python main.py
```

The API listens on `http://localhost:8000`.

Start the Vite development server in another terminal:

```bash
cd frontend
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. Choose a directory, select **Index**, then enter a natural-language query. The first indexing or search operation may take longer while the embedding model loads.

## API overview

The FastAPI service exposes:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Report service status, indexed-file count, and explanation model |
| `POST /index` | Index a directory: `{"directory": "/path/to/folder"}` |
| `POST /search` | Search the index: `{"query": "tax documents", "limit": 20}` |
| `POST /explain` | Explain a file: `{"path": "/path/to/file"}` |
| `POST /browse` | Open the macOS folder picker |
| `POST /open` | Open a file with the default macOS application |
| `POST /delete` | Move a file to the system Trash |

Interactive API documentation is available at `http://localhost:8000/docs` while the backend is running.

## Indexing boundaries

To keep indexing predictable, the current implementation:

- reads at most 4,000 characters from each text file;
- stores at most an 800-character excerpt;
- ignores empty files and files larger than 8 MiB;
- skips hidden directories and common generated directories such as `.git`, `node_modules`, `dist`, and `build`;
- removes catalog rows for paths confirmed missing beneath the selected directory after indexing; this never deletes files from disk;
- indexes unknown file types using a filename label.

## Development checks

Run the project checks before submitting changes:

```bash
cd /path/to/FileOrganizerCataloger
python3 -m compileall -q backend

cd frontend
npm run lint
npm run build
```

## Project structure

```text
backend/                 FastAPI service, indexer, embeddings, search, and SQLite store
frontend/                React + Vite interface
docs/CODE_WALKTHROUGH.md Detailed implementation walkthrough
REDESIGN.md              Product direction and future phases
```

## Status

Sonic Telescope is an active Phase 1 project. The current release is intended for local development and experimentation; cleanup and organization automation are not yet implemented.
