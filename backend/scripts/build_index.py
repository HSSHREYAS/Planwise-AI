"""
PlanWise AI - FAISS Index Builder

Reads processed domain records and builds per-domain FAISS indexes.

Usage:
    cd backend
    python -m scripts.build_index

Prerequisites:
    - Run preprocess_multiwoz.py first
    - sentence-transformers installed
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
INDEX_DIR = BACKEND_DIR / "data" / "index"


def build_domain_index(domain: str, records: list) -> bool:
    """Build a FAISS index for a domain."""
    import faiss
    from app.retrieval.embeddings import generate_embeddings, record_to_text

    if not records:
        logger.warning(f"No records for {domain}, skipping")
        return False

    # Generate text descriptions for each record
    texts = [record_to_text(record, domain) for record in records]
    logger.info(f"  Generating embeddings for {len(texts)} {domain} records...")

    # Generate embeddings
    embeddings = generate_embeddings(texts)
    logger.info(f"  Embedding shape: {embeddings.shape}")

    # Build FAISS index (inner product for normalized embeddings)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    logger.info(f"  FAISS index built: {index.ntotal} vectors")

    # Save index
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index_path = INDEX_DIR / f"{domain}.faiss"
    metadata_path = INDEX_DIR / f"{domain}_metadata.json"

    faiss.write_index(index, str(index_path))
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    logger.info(f"  Saved: {index_path}")
    logger.info(f"  Saved: {metadata_path}")
    return True


def main():
    """Build FAISS indexes for all domains."""
    logger.info("=" * 60)
    logger.info("PlanWise AI - FAISS Index Builder")
    logger.info("=" * 60)

    if not PROCESSED_DIR.exists():
        logger.error(f"Processed data directory not found: {PROCESSED_DIR}")
        logger.info("Run preprocess_multiwoz.py first.")
        sys.exit(1)

    # Add backend to Python path for imports
    sys.path.insert(0, str(BACKEND_DIR))

    domains = {
        "hotel": "hotels.json",
        "restaurant": "restaurants.json",
        "attraction": "attractions.json",
        "transport": "transport.json",
    }

    results = {}
    for domain, filename in domains.items():
        filepath = PROCESSED_DIR / filename
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            results[domain] = False
            continue

        logger.info(f"\nBuilding {domain} index...")
        with open(filepath, "r", encoding="utf-8") as f:
            records = json.load(f)

        results[domain] = build_domain_index(domain, records)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Index build complete!")
    for domain, success in results.items():
        status = "✓" if success else "✗"
        logger.info(f"  {status} {domain}")
    logger.info(f"Output: {INDEX_DIR}")


if __name__ == "__main__":
    main()
