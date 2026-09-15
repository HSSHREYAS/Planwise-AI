"""
PlanWise AI - FAISS Index Manager

Manages loading and querying per-domain FAISS indexes.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.config import INDEX_DIR, RETRIEVAL_TOP_K

logger = logging.getLogger(__name__)

# Module-level cache for loaded indexes
_indexes: Dict[str, Any] = {}
_metadata: Dict[str, List[Dict]] = {}


def load_index(domain: str) -> bool:
    """
    Load a FAISS index and its metadata for a domain.

    Args:
        domain: One of hotel, restaurant, attraction, transport

    Returns:
        True if loaded successfully
    """
    import faiss

    index_path = Path(INDEX_DIR) / f"{domain}.faiss"
    metadata_path = Path(INDEX_DIR) / f"{domain}_metadata.json"

    if not index_path.exists():
        logger.warning(f"FAISS index not found: {index_path}")
        return False

    if not metadata_path.exists():
        logger.warning(f"Metadata not found: {metadata_path}")
        return False

    try:
        _indexes[domain] = faiss.read_index(str(index_path))
        with open(metadata_path, "r", encoding="utf-8") as f:
            _metadata[domain] = json.load(f)
        logger.info(
            f"Loaded {domain} index: {_indexes[domain].ntotal} vectors, "
            f"{len(_metadata[domain])} records"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to load {domain} index: {e}")
        return False


def load_all_indexes() -> Dict[str, bool]:
    """Load all domain indexes. Returns status per domain."""
    domains = ["hotel", "restaurant", "attraction", "transport"]
    results = {}
    for domain in domains:
        results[domain] = load_index(domain)
    return results


def search_index(
    domain: str,
    query_embedding: np.ndarray,
    top_k: int = RETRIEVAL_TOP_K,
) -> List[Tuple[Dict[str, Any], float]]:
    """
    Search a domain FAISS index with a query embedding.

    Args:
        domain: Domain to search
        query_embedding: Query vector (1D)
        top_k: Number of results to return

    Returns:
        List of (record_dict, distance_score) tuples, sorted by relevance
    """
    if domain not in _indexes:
        if not load_index(domain):
            logger.warning(f"Cannot search {domain}: index not loaded")
            return []

    index = _indexes[domain]
    metadata = _metadata[domain]

    # Reshape for FAISS
    query = query_embedding.reshape(1, -1).astype(np.float32)

    # Search
    actual_k = min(top_k, index.ntotal)
    if actual_k == 0:
        return []

    distances, indices = index.search(query, actual_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        results.append((metadata[idx], float(dist)))

    return results


def get_all_records(domain: str) -> List[Dict[str, Any]]:
    """Get all records for a domain (for non-FAISS filtering)."""
    if domain not in _metadata:
        if not load_index(domain):
            # Try loading directly from processed data
            from app.config import PROCESSED_DATA_DIR
            data_path = Path(PROCESSED_DATA_DIR) / f"{domain}s.json"
            if not data_path.exists():
                data_path = Path(PROCESSED_DATA_DIR) / f"{domain}.json"
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
    return _metadata.get(domain, [])


def is_index_loaded(domain: str) -> bool:
    """Check if a domain index is loaded."""
    return domain in _indexes
