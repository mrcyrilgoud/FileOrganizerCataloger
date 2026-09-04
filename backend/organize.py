"""Phase 3 — Organizer (STUB ONLY).

Future API (not implemented):

  POST /organize/plan
    Body: { directory?: str, strategy?: str }
    Returns: {
      categories: [{ name, description }],
      moves: [{ path, from, to, category, rationale }]
    }
    Dry-run only — no disk changes.

  POST /organize/apply
    Body: { moves: [{ path, to }] }
    Effect: execute moves after explicit user confirmation in the UI.

Design notes:
  - Category labels derived from embeddings (+ optional local LLM labels).
  - Move plans are data the UI previews as a diff before apply.
  - Same IndexStore as Phase 1; optional future columns: category, planned_path.
  - No fake implementations that pretend to organize files.
"""

from __future__ import annotations

# Intentionally empty of runtime behavior. Phase 3 will land here.
