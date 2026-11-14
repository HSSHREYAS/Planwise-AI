"""
PlanWise AI - Backend Application Entry Point

FastAPI application setup.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import BACKEND_HOST, BACKEND_PORT, LOG_LEVEL

# Windows consoles default to a legacy code page; place names from all
# over the world must never crash logging.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("PlanWise AI Backend Starting")
    logger.info("=" * 60)

    # Bundled Cambridge dataset (FAISS indexes)
    try:
        from app.retrieval.index_manager import load_all_indexes
        for domain, loaded in load_all_indexes().items():
            logger.info(f"  {'OK ' if loaded else 'MISSING'} {domain} index (Cambridge dataset)")
    except Exception as e:
        logger.warning(f"Could not load FAISS indexes: {e}")
        logger.info("  Indexes will be loaded on first Cambridge search")

    # Hosted LLM providers
    try:
        from app.llm.client import get_llm_client
        llm = get_llm_client()
        logger.info(f"  LLM provider chain: {', '.join(llm.describe())}")
        if llm.frugal:
            logger.warning(
                "  No LLM API key configured - using the keyless free endpoint "
                "(~1 AI reply / 45s). Add GROQ_API_KEY or GEMINI_API_KEY to .env "
                "for fast, full AI answers."
            )
    except Exception as e:
        logger.warning(f"  Could not initialise the LLM client: {e}")

    logger.info("  Live location data: OpenStreetMap (Nominatim)")
    logger.info("Backend ready")
    logger.info("=" * 60)
    yield


app = FastAPI(
    title="PlanWise AI",
    description="Agentic Personal Task and Trip Planning Assistant",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for the web frontends (no cookies are used, so credentials stay off)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"service": "planwise-api", "docs": "/docs", "health": "/api/v1/health"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
    )
