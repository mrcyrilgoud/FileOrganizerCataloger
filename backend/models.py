"""Shared lazy SentenceTransformer singletons for Sonic Telescope."""

from __future__ import annotations

import os
from typing import Optional

TEXT_MODEL_NAME = "all-MiniLM-L6-v2"
IMAGE_MODEL_NAME = "clip-ViT-B-32"

_text_model = None  # type: Optional[object]
_image_model = None  # type: Optional[object]


def clip_enabled():
    return os.environ.get("SONIC_ENABLE_CLIP", "").strip().lower() in {"1", "true", "yes"}


def get_text_model():
    """Load all-MiniLM-L6-v2 once per process."""
    global _text_model
    if _text_model is None:
        # Deferred: sentence-transformers/torch is heavy; keep import off the health path.
        from sentence_transformers import SentenceTransformer

        _text_model = SentenceTransformer(TEXT_MODEL_NAME)
    return _text_model


def get_image_model():
    """Load clip-ViT-B-32 once per process (only used when CLIP is enabled)."""
    global _image_model
    if _image_model is None:
        from sentence_transformers import SentenceTransformer

        _image_model = SentenceTransformer(IMAGE_MODEL_NAME)
    return _image_model


def image_file_label(path):
    """Return a search label for an image. CLIP only if SONIC_ENABLE_CLIP is set."""
    name = os.path.basename(str(path))
    fallback = "Image file: %s" % name
    if not clip_enabled():
        return fallback
    try:
        from PIL import Image
        from sentence_transformers import util

        img = Image.open(path).convert("RGB")
        clip = get_image_model()
        prompts = [
            "a photo of a document or ID",
            "a receipt or invoice",
            "a screenshot",
            "a personal photo",
            "a diagram or chart",
            "other image",
        ]
        img_emb = clip.encode(img)
        prompt_embs = clip.encode(prompts)
        sims = util.cos_sim(img_emb, prompt_embs)[0]
        return "Image (%s): %s" % (prompts[int(sims.argmax())], name)
    except Exception:
        return fallback
