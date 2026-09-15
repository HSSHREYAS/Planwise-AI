"""
PlanWise AI - Backend Configuration

Centralized configuration loaded from environment variables.
No secrets should be hardcoded.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Base paths
BACKEND_DIR = Path(__file__).parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"

# Ollama / LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# Retrieval
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Backend server
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Agent
MAX_REPLAN_ATTEMPTS = int(os.getenv("MAX_REPLAN_ATTEMPTS", "2"))
