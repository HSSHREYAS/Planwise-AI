# PlanWise AI — Agentic Personal Task and Trip Planning Assistant

An AI-powered planning agent that understands natural language requests, decomposes goals into subtasks, retrieves real data, generates structured schedules, validates constraints, and supports replanning.

## Tech Stack

| Component | Technology |
|---|---|
| LLM | Qwen2.5-3B-Instruct via Ollama |
| Frontend | Streamlit |
| Backend API | FastAPI (thin layer) |
| Schemas | Pydantic v2 |
| Retrieval | FAISS + sentence-transformers |
| Data | MultiWOZ 2.2 (local) |
| Tests | pytest |
| Agent | Plain Python state machine |

## Architecture

```
Streamlit → FastAPI → Planning Agent → Qwen2.5-3B (Ollama)
                           ↓
                    Tool Registry → FAISS Retrieval → MultiWOZ
                           ↓
                    Constraint Engine → Verifier → Response
```

**Key principle:** LLM = understand + plan + communicate. Python = state + tools + rules + validation.

## Prerequisites

1. **Python 3.10+**
2. **Ollama** installed and running
3. **Qwen2.5-3B-Instruct** model pulled:
   ```bash
   ollama pull qwen2.5:3b-instruct
   ```
4. **MultiWOZ 2.2 dataset** downloaded

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

### 3. Place MultiWOZ 2.2 Dataset

Place the extracted MultiWOZ 2.2 dataset folder inside:

```
backend/data/raw/
```

The structure should be:
```
backend/data/raw/
└── <dataset-folder>/    (e.g., MULTIWOZ2.2 or MultiWOZ_2.2)
    └── db/
        ├── hotel_db.json
        ├── restaurant_db.json
        ├── attraction_db.json
        └── train_db.json
```

### 4. Preprocess Data

```bash
cd backend
python -m scripts.preprocess_multiwoz
```

### 5. Build FAISS Indexes

```bash
cd backend
python -m scripts.build_index
```

### 6. Configure Environment

Copy and edit the `.env` file if needed:
```bash
cp .env.example .env
```

### 7. Start Ollama

```bash
ollama serve
```

### 8. Run the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 9. Run the Frontend (new terminal)

```bash
cd frontend
streamlit run app.py
```

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

## Project Structure

```
planwise-AI/
├── backend/
│   ├── app/
│   │   ├── agent/         # Planning agent + prompts
│   │   ├── api/           # FastAPI routes (thin)
│   │   ├── llm/           # Ollama client
│   │   ├── models/        # Pydantic schemas
│   │   ├── retrieval/     # FAISS search
│   │   ├── services/      # Session management
│   │   ├── state/         # State manager
│   │   ├── tools/         # Domain search tools
│   │   ├── validation/    # Constraints + verifier
│   │   ├── config.py
│   │   └── main.py
│   ├── data/
│   │   ├── raw/           # MultiWOZ 2.2 (user places here)
│   │   ├── processed/     # Normalized JSON records
│   │   └── index/         # FAISS indexes
│   ├── scripts/           # Preprocessing scripts
│   └── tests/             # pytest tests
├── frontend/
│   ├── app.py             # Streamlit entry point
│   └── services/          # Backend API client
├── evaluation/            # Test scenarios
└── docs/                  # Documentation
```

## Capabilities

- ✅ Natural language intent understanding
- ✅ Trip planning (multi-domain)
- ✅ Study/personal schedule planning
- ✅ Hotel, restaurant, attraction, transport search
- ✅ Budget constraint validation
- ✅ Duration constraint validation
- ✅ Preference handling (vegetarian, etc.)
- ✅ Impossible constraint detection
- ✅ Replanning after requirement changes
- ✅ Conversation memory
- ✅ Hallucination control via grounded data
- ✅ Plan verification
