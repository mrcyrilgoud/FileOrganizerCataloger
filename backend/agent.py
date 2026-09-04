"""Phase 2 — Cleanup agent (STUB ONLY).

Future API (not implemented):

  POST /cleanup/propose
    Body: { directory?: str, paths?: str[], policy?: str }
    Returns: [{ path, action: "trash"|"archive"|"keep", rationale, confidence }]

  POST /cleanup/confirm
    Body: { proposals: [{ path, action }] }
    Effect: apply confirmed trash/archive via actions.py (send2trash) only
            after explicit user confirmation. Never auto-mutate.

Design notes:
  - Reads from the same IndexStore + SemanticSearch used by Phase 1.
  - May call FileExplainer / Ollama for rationales (metadata + excerpt only).
  - Confirm-before-action is mandatory; this module must not delete on its own.
  - Plug-in path: import index_store, search, explain — no Phase 1 rewrite.
"""

from __future__ import annotations

# Intentionally empty of runtime behavior. Phase 2 will land here.
