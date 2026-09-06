"""Shared lazy SentenceTransformer singletons for Sonic Telescope."""

from __future__ import annotations

import os

import numpy as np

TEXT_MODEL_NAME = "all-MiniLM-L6-v2"
IMAGE_MODEL_NAME = "clip-ViT-B-32"
CLIP_PROMPTS = (
    "a photo of a document or ID",
    "a receipt or invoice",
    "a screenshot",
    "a personal photo",
    "a diagram or chart",
    "other image",
)
_models = {}


def clip_enabled():
    return os.environ.get("SONIC_ENABLE_CLIP", "").strip().lower() in {"1", "true", "yes"}


def _get_model(name):
    if name not in _models:
        from sentence_transformers import SentenceTransformer

        _models[name] = SentenceTransformer(name)
    return _models[name]


def get_text_model():
    return _get_model(TEXT_MODEL_NAME)


def get_image_model():
    return _get_model(IMAGE_MODEL_NAME)


def encode_texts(texts, batch_size=32):
    embs = np.asarray(
        get_text_model().encode(texts, batch_size=batch_size, show_progress_bar=False),
        dtype=np.float32,
    )
    return embs.reshape(1, -1) if embs.ndim == 1 else embs


def l2_normalize(vec):
    n = float(np.linalg.norm(vec))
    return None if n == 0 else vec / n


def image_file_label(path):
    name = os.path.basename(str(path))
    fallback = "Image file: %s" % name
    if not clip_enabled():
        return fallback
    try:
        from PIL import Image
        from sentence_transformers import util

        clip = get_image_model()
        img_emb = clip.encode(Image.open(path).convert("RGB"))
        sims = util.cos_sim(img_emb, clip.encode(list(CLIP_PROMPTS)))[0]
        return "Image (%s): %s" % (CLIP_PROMPTS[int(sims.argmax())], name)
    except Exception:
        return fallback
