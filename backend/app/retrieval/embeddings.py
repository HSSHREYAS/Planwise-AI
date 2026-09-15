"""
PlanWise AI - Embeddings

Local embedding generation using sentence-transformers.
No paid embedding APIs.
"""

import logging
from typing import List

import numpy as np

from app.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# Module-level cache for the model
_model = None


def get_embedding_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _model


def generate_embeddings(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: List of text strings to embed

    Returns:
        numpy array of shape (len(texts), embedding_dim)
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return np.array(embeddings, dtype=np.float32)


def generate_single_embedding(text: str) -> np.ndarray:
    """Generate embedding for a single text string."""
    return generate_embeddings([text])[0]


def record_to_text(record: dict, domain: str) -> str:
    """
    Convert a domain record to a text string for embedding.
    Combines all relevant fields into a searchable description.
    """
    parts = []

    name = record.get("name", "")
    if name:
        parts.append(name)

    if domain == "hotel":
        for field in ["area", "pricerange", "type", "stars", "parking", "internet"]:
            val = record.get(field, "")
            if val:
                parts.append(f"{field}: {val}")

    elif domain == "restaurant":
        for field in ["area", "food", "pricerange", "address"]:
            val = record.get(field, "")
            if val:
                parts.append(f"{field}: {val}")

    elif domain == "attraction":
        for field in ["area", "type", "entrance_fee", "address"]:
            val = record.get(field, "")
            if val:
                parts.append(f"{field}: {val}")

    elif domain == "transport":
        for field in ["departure", "destination", "day", "leaveAt",
                       "arriveBy", "price", "type"]:
            val = record.get(field, "")
            if val:
                parts.append(f"{field}: {val}")

    return " | ".join(parts)
