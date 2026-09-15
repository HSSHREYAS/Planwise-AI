"""
PlanWise AI - Retrieval Service

High-level search interface used by domain tools.
Handles query building, FAISS search, and metadata filtering.
"""

import logging
from typing import Any, Dict, List, Optional

from app.retrieval.embeddings import generate_single_embedding
from app.retrieval.index_manager import get_all_records, search_index

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    Domain-agnostic retrieval service.

    Pipeline:
        Query → Embedding → FAISS top-k → Metadata filter → Ranked results
    """

    def search(
        self,
        domain: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search a domain for relevant records.

        Args:
            domain: hotel, restaurant, attraction, or transport
            query: Natural language query string
            filters: Optional metadata filters (e.g. {"pricerange": "cheap"})
            top_k: Max results to return

        Returns:
            List of matching record dicts, ranked by relevance
        """
        logger.info(f"Retrieval search: domain={domain}, query='{query}', filters={filters}")

        # Generate query embedding
        try:
            query_embedding = generate_single_embedding(query)
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            # Fallback to metadata-only filtering
            return self._filter_records(domain, filters, top_k)

        # FAISS search
        try:
            raw_results = search_index(domain, query_embedding, top_k=max(top_k * 10, 50))
        except Exception as e:
            logger.error(f"FAISS search failed: {e}")
            # Fallback to metadata-only filtering
            return self._filter_records(domain, filters, top_k)

        if not raw_results:
            logger.info(f"No FAISS results for {domain}, trying direct filter")
            return self._filter_records(domain, filters, top_k)

        # Extract records from (record, distance) tuples
        records = [record for record, _ in raw_results]

        # Apply metadata filters
        if filters:
            filtered = self._apply_filters(records, filters)
            if filtered:
                records = filtered
            else:
                logger.info(f"Strict filters {filters} yielded 0 results for {domain}, retaining top semantic matches")

        # Limit to top_k
        results = records[:top_k]

        logger.info(f"Retrieval returned {len(results)} {domain} results")
        return results

    def _apply_filters(
        self,
        records: List[Dict[str, Any]],
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Apply metadata filters to a list of records."""
        filtered = []
        for record in records:
            match = True
            for key, value in filters.items():
                if value is None:
                    continue
                record_value = record.get(key, "")
                if isinstance(value, str):
                    if record_value and value.lower() not in str(record_value).lower():
                        match = False
                        break
                elif isinstance(value, list):
                    # Check if any filter value matches
                    if record_value and not any(
                        v.lower() in str(record_value).lower()
                        for v in value
                        if isinstance(v, str)
                    ):
                        match = False
                        break
            if match:
                filtered.append(record)
        return filtered

    def _filter_records(
        self,
        domain: str,
        filters: Optional[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Fallback: filter all records by metadata when FAISS isn't available."""
        all_records = get_all_records(domain)
        if not all_records:
            return []

        if filters:
            all_records = self._apply_filters(all_records, filters)

        return all_records[:top_k]


# Module-level instance
retrieval_service = RetrievalService()
