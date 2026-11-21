"""
PlanWise AI - Backend Configuration

Centralized configuration loaded from environment variables.
No secrets should be hardcoded.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"

# Load .env from the project root (and the working directory, if different)
load_dotenv(PROJECT_DIR / ".env")
load_dotenv()

# ── LLM (hosted, free-tier APIs) ────────────────────────────────
# LLM_PROVIDER: auto | groq | gemini | openrouter | pollinations | ollama | custom
#   auto  → use every provider that has an API key (in the order below),
#           then fall back to the keyless Pollinations endpoint.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")

# Keyless free endpoint (no signup needed) - used as the last fallback
POLLINATIONS_BASE_URL = os.getenv("POLLINATIONS_BASE_URL", "https://text.pollinations.ai/openai")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "openai")

# Optional: any other OpenAI-compatible endpoint
CUSTOM_LLM_BASE_URL = os.getenv("CUSTOM_LLM_BASE_URL", "").strip()
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", "").strip()
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL", "").strip()

# Optional: local Ollama (only used when LLM_PROVIDER=ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ── Live location data (OpenStreetMap, free, no key) ────────────
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
GEO_USER_AGENT = os.getenv("GEO_USER_AGENT", "PlanWiseAI/2.0 (trip planning assistant; https://planwise-ai-bqcm.onrender.com; contact: planwise.app@gmail.com)")
GEO_TIMEOUT = int(os.getenv("GEO_TIMEOUT", "25"))

# Overpass serves bounded OpenStreetMap POI queries. Keep these configurable so
# deployments can use a regional or self-hosted instance if needed.
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter").strip()
OVERPASS_FALLBACK_URL = os.getenv(
    "OVERPASS_FALLBACK_URL", "https://overpass.private.coffee/api/interpreter"
).strip()
OVERPASS_TIMEOUT = int(os.getenv("OVERPASS_TIMEOUT", "18"))

# Retrieval (bundled Cambridge dataset)
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Backend server
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Firebase Authentication ───────────────────────────────────────
# Browser config is public and is returned only by the auth config endpoint.
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "").strip()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID", "").strip()

# Admin credentials stay on the server. Store private-key newlines as literal
# \\n sequences in .env / Render and restore them before creating credentials.
FIREBASE_ADMIN_CLIENT_EMAIL = os.getenv("FIREBASE_ADMIN_CLIENT_EMAIL", "").strip()
FIREBASE_ADMIN_PRIVATE_KEY_ID = os.getenv("FIREBASE_ADMIN_PRIVATE_KEY_ID", "").strip()
FIREBASE_ADMIN_PRIVATE_KEY = os.getenv("FIREBASE_ADMIN_PRIVATE_KEY", "").strip().replace("\\n", "\n")

# Agent
MAX_REPLAN_ATTEMPTS = int(os.getenv("MAX_REPLAN_ATTEMPTS", "2"))
MAX_TRIP_DAYS = int(os.getenv("MAX_TRIP_DAYS", "14"))
