"""
PlanWise AI - Backend Application Entry Point

FastAPI application setup.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import BACKEND_HOST, BACKEND_PORT, LOG_LEVEL, PROCESSED_DATA_DIR, PROJECT_DIR

FRONTEND_DIR = PROJECT_DIR / "frontend-web"

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

    # Bundled Cambridge dataset: make sure the processed records exist
    # (they are generated from the raw MultiWOZ files, no heavy dependencies)
    if not (PROCESSED_DATA_DIR / "hotels.json").exists():
        try:
            from scripts.preprocess_multiwoz import main as preprocess
            preprocess()
            logger.info("  Generated processed Cambridge dataset")
        except BaseException as e:  # the script may call sys.exit
            logger.warning(f"  Could not generate the Cambridge dataset: {e}")

    # Bundled Cambridge dataset (FAISS indexes)
    try:
        from app.retrieval.index_manager import load_all_indexes
        for domain, loaded in load_all_indexes().items():
            logger.info(
                f"  {domain}: {'FAISS semantic search' if loaded else 'metadata filtering (no FAISS index)'}"
            )
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


# ── Web frontend ────────────────────────────────────────────────
# The frontend is three static files, so the backend can serve the whole
# site from one process (this is what makes single-service hosting work).

@app.get("/", include_in_schema=False)
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return {"service": "planwise-api", "docs": "/docs", "health": "/api/v1/health"}


@app.get("/app.js", include_in_schema=False)
def frontend_script():
    return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")


@app.get("/styles.css", include_in_schema=False)
def frontend_styles():
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.head("/", include_in_schema=False)
def root_head():
    return {}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
    )
