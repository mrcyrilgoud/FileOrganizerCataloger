# Sonic Telescope — Product Redesign

**Working title:** FileOrganizerCataloger / Sonic Telescope  
**Decision date:** 2026-09  
**Constraint:** Fully local AI. No cloud LLM APIs. Ollama on loopback only.

---

## Product spine

Sonic Telescope is a **local semantic file library**, not an importance-score scanner with a delete button.

Three phases, same app:

| Phase | Name | Goal | Status |
|-------|------|------|--------|
| 1 | **Semantic library** | Index files locally; plain-English search; explain why a file might matter | **Build now** |
| 2 | **Cleanup agent** | Propose trash / archive / keep with confirm-before-action | Stub only |
| 3 | **Organizer** | Category tree + move plans (preview then apply) | Stub only |

Phase 1 is the product. Cleanup and organization are agents that *query the same index* later — they are not bolted onto the old color-coded importance table.

---

## Phase 1 — Semantic library

### User loop
1. Pick a directory → **Index**
2. Ask in plain English (“tax docs from 2023”, “passport photos”, “draft notes about the thesis”)
3. See ranked results with path, score, snippet
4. Optionally **Explain** — local LLM narrates why that file might matter (metadata + short excerpt only)
5. Open / delete remain secondary actions

### Architecture

```
┌─────────────┐     POST /index      ┌──────────────┐
│  React UI   │ ───────────────────► │   indexer    │
│  (Vite)     │                      │  walk + text │
│             │     POST /search     │  + embed     │
│             │ ───────────────────► │              │
│             │     POST /explain    └──────┬───────┘
│             │ ───────────────────►        │
└─────────────┘                      ┌──────▼───────┐
                                     │ index_store  │
                                     │  SQLite      │
                                     │ ~/.sonic-    │
                                     │ telescope/   │
                                     └──────┬───────┘
                                            │
                     ┌──────────────────────┼──────────────────────┐
                     ▼                      ▼                      ▼
              SentenceTransformers    CLIP (images)         Ollama loopback
              all-MiniLM-L6-v2        clip-ViT-B-32         qwen3:4b-instruct
              (text embeddings)       (optional cheap)      (explain only)
```

### Components

| Module | Role |
|--------|------|
| `backend/index_store.py` | SQLite under `~/.sonic-telescope/`. Files table: path, mtime, size, mime, text_excerpt, embedding blob, last_indexed. |
| `backend/models.py` | Shared lazy singletons: `get_text_model()` / optional `get_image_model()`. |
| `backend/indexer.py` | Walk + skip unchanged (mtime+size); batch embed; CLIP only if `SONIC_ENABLE_CLIP`; `upsert_many`. |
| `backend/search.py` | Shared text model; L2 matrix cache; vectorized cosine + argpartition top-k. |
| `backend/explain.py` | Call `http://127.0.0.1:11434` with **qwen3:4b-instruct**. Input = metadata + short excerpt only. Fail closed if Ollama is down. |
| `backend/main.py` | FastAPI: `/index`, `/search`, `/explain` + keep `/health`, `/browse`, `/open`, `/delete`. |

### Index store details
- App data dir: `~/.sonic-telescope/`
- DB file: `~/.sonic-telescope/index.db`
- Embeddings stored as float32 blobs (numpy `tobytes`) so search stays in-process with no vector DB dependency for v1
- Upsert keyed by absolute path; re-index only when mtime **or** size changes

### Privacy (local-only)
- File bytes never leave the machine
- Embeddings and excerpts stay in local SQLite
- Explain sends **only** path basename, mime, size, mtime, and a short excerpt to Ollama on `127.0.0.1`
- No OpenAI / Anthropic / cloud embedding APIs
- HuggingFace model weights may download once on first embed load (same as today)

### Default Ollama model
**`qwen3:4b-instruct`** — A/B winner on 16GB M5 (fast, grounded, ~2.9GB). Override with `SONIC_EXPLAIN_MODEL` or `POST /explain` `{"model":"qwen3:8b"}` (thinking disabled in client).

---

## Phase 2 — Cleanup agent (stub)

**Module:** `backend/agent.py` (docstring stub; no fake implementation)

Future shape:
- `POST /cleanup/propose` `{ directory? | paths?, policy? }` → list of `{ path, action: trash|archive|keep, rationale, confidence }`
- Reads from the **same index** (snippets + embeddings + metadata); may call Ollama for rationale
- **Never** mutates disk without an explicit confirm endpoint
- `POST /cleanup/confirm` `{ proposals[] }` → uses existing `actions.py` (send2trash) only after user confirm

Phase 2 plugs in by importing `index_store` + `search` + `explain` — no rewrite of Phase 1.

---

## Phase 3 — Organizer (stub)

**Module:** `backend/organize.py` (docstring stub)

Future shape:
- `POST /organize/plan` → proposed category tree + move operations (dry-run)
- `POST /organize/apply` → execute moves after confirm
- Categories derived from embeddings + optional LLM labels
- Move plans are data; the UI previews diffs before apply

Same index; no schema rewrite required beyond optional `category` / `planned_path` columns later.

---

## What we are deliberately *not* doing
- Making the old importance color table the main product with Ollama bolted on
- Auto-deleting or auto-moving files
- Sending full file contents to any LLM
- Cloud vector DBs or hosted search

---

## Compatibility
- Frontend primary flow is Index → Search → Explain
- Legacy importance analyzer / `POST /scan` has been removed
