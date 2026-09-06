# Sonic Telescope

**Local semantic file library** — index once, search in plain English, explain why a file matters. All AI stays on your machine.

> Formerly framed as an importance scorer. The product spine is now a **semantic library** (Phase 1), with cleanup and organize agents as later phases. See [REDESIGN.md](./REDESIGN.md).

## What it does (Phase 1)

1. **Index** a folder — extract bounded text, embed with SentenceTransformers (`all-MiniLM-L6-v2`); images can use CLIP (`clip-ViT-B-32`).
2. **Search** with natural language — cosine similarity over your local index.
3. **Explain** — Ollama (`qwen3:4b-instruct` on `127.0.0.1`) narrates why a hit might matter, using metadata + a short excerpt only.
4. Open / trash remain secondary actions (confirm before delete).

**Phases 2–3 (stubs):** cleanup proposals and organizer move plans — see `backend/agent.py` and `backend/organize.py`.

## Privacy

- Processing is **local**. No cloud LLM APIs.
- Ollama is called only on loopback (`http://127.0.0.1:11434`).
- Full large files are never sent to the model — only short excerpts + metadata.
- Index lives under `~/.sonic-telescope/index.db`.

## Stack
Backend FastAPI, frontend React+Vite, embeddings SentenceTransformers+CLIP, explain via Ollama qwen3:4b-instruct, store SQLite.

## Prerequisites
- Python 3.8+ (this Mac currently has models on python3.8; plain python3 is 3.13)
- Node.js
- Optional: Ollama with `qwen3:4b-instruct` (default Explain); `qwen3:8b` / `llama3.1:8b` also work

## Setup
Backend: cd backend, install requirements with the Python that has sentence-transformers (on this Mac: python3.8 -m pip install -r requirements.txt), then python3.8 main.py (port 8000).
Frontend: cd frontend, install deps, run Vite dev server, open localhost:5173.

## API Phase 1
GET /health | POST /index | POST /search | POST /explain | POST /browse | POST /open | POST /delete

## Smoke test
Hit /health, /index a small folder, /search a query, /explain a path when Ollama is up.

See REDESIGN.md for architecture. Local only; do not commit unless asked.
