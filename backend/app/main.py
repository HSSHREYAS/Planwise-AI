"""
PlanWise AI - Backend Application Entry Point

FastAPI application setup.
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import BACKEND_HOST, BACKEND_PORT, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="PlanWise AI",
    description="Agentic Personal Task and Trip Planning Assistant",
    version="1.0.0",
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("PlanWise AI Backend Starting")
    logger.info("=" * 60)

    # Try to load FAISS indexes
    try:
        from app.retrieval.index_manager import load_all_indexes
        results = load_all_indexes()
        for domain, loaded in results.items():
            status = "✓" if loaded else "✗"
            logger.info(f"  {status} {domain} index")
    except Exception as e:
        logger.warning(f"Could not load FAISS indexes: {e}")
        logger.info("  Indexes will be loaded on first search request")

    # Check Ollama
    try:
        from app.llm.ollama_client import OllamaClient
        llm = OllamaClient()
        if llm.is_available():
            logger.info("  ✓ Ollama is available")
        else:
            logger.warning("  ✗ Ollama is not available")
    except Exception:
        logger.warning("  ✗ Could not check Ollama status")

    logger.info(f"Backend ready at http://{BACKEND_HOST}:{BACKEND_PORT}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
    )
