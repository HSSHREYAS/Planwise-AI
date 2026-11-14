# PlanWise AI — Agentic Personal Task & Trip Planning Assistant

> **Undergraduate GenAI ABL-1 Project**  
> Submission Deadline: 30 October 2026  
> Version: 2.0.0

## What's New in v2

| Area | v1 | v2 |
|------|----|----|
| **LLM** | Local Ollama (Qwen2.5-3B) | **Hosted free-tier LLM APIs** - Groq, Google Gemini, OpenRouter, with automatic fallback and a keyless endpoint so it works with zero setup |
| **Location** | Cambridge, UK only | **Any place in the world** - your current location (browser GPS) or a place you search for; live hotels, restaurants, attractions and transport hubs from OpenStreetMap |
| **Dates** | Not supported | **From / To dates** in the home-page search bar; plans carry real calendar dates per day |
| **Currency** | Hard-coded | Derived from the destination country (or the currency you mention); totals are computed in Python |
| **Robustness** | Fails without the LLM | Every step has a deterministic fallback; unverified places are flagged as AI suggestions |

Quick start: run `.\start.ps1`, open the printed frontend URL, and (recommended) add a free
`GROQ_API_KEY` or `GEMINI_API_KEY` to `.env` - see [Installation & Setup](#16-installation--setup).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Objectives & Goals](#2-objectives--goals)
3. [System Architecture](#3-system-architecture)
4. [Agent Design & State Machine](#4-agent-design--state-machine)
5. [Technology Stack](#5-technology-stack)
6. [Project Structure](#6-project-structure)
7. [Core Modules & Components](#7-core-modules--components)
8. [Dataset — MultiWOZ 2.2](#8-dataset--multiwoz-22)
9. [Data Pipeline & Vector Search (FAISS)](#9-data-pipeline--vector-search-faiss)
10. [API Reference](#10-api-reference)
11. [Constraint & Validation Engine](#11-constraint--validation-engine)
12. [Replanning Model](#12-replanning-model)
13. [Prompt Engineering](#13-prompt-engineering)
14. [Frontend — Streamlit UI](#14-frontend--streamlit-ui)
15. [Evaluation & Test Cases](#15-evaluation--test-cases)
16. [Installation & Setup](#16-installation--setup)
17. [Running the Application](#17-running-the-application)
18. [Configuration Reference](#18-configuration-reference)
19. [Supported User Journeys](#19-supported-user-journeys)
20. [Limitations & Scope](#20-limitations--scope)
21. [Future Enhancements](#21-future-enhancements)
22. [References](#22-references)

---

## 1. Project Overview

**PlanWise AI** is an **agentic AI planning assistant** that accepts natural-language user goals and converts them into structured, constraint-aware, multi-step executable plans. The system demonstrates the complete lifecycle of a modern GenAI agent:

- 🧠 **Intent Understanding** — Parsing user messages to extract goals and parameters
- 🔍 **Task Decomposition** — Breaking high-level goals into actionable subtasks
- 🛠️ **Tool Invocation** — Calling domain-specific search tools with validated parameters
- 📦 **Information Retrieval** — Semantic vector search over a local knowledge base
- 🔄 **State Management** — Maintaining session context across conversation turns
- ✅ **Constraint Validation** — Deterministic rule checking (budget, duration, preferences)
- 📋 **Schedule Generation** — LLM-guided structured plan construction
- 🔁 **Replanning** — Revising existing plans when requirements change
- 🗂️ **Memory** — Retaining preferences and context within active sessions

The system supports **two primary planning domains**:

| Domain | Example Request |
|--------|---------------|
| **Trip Planning** | *"Plan a 2-day trip to Cambridge with places to visit and food options"* |
| **Study Planning** | *"Plan my study schedule for the next 7 days covering math, physics, and chemistry"* |

**Data sources.** For any location in the world the agent uses **live OpenStreetMap data** (geocoding and
category search through Nominatim - free, no API key). For Cambridge, UK it uses the bundled **MultiWOZ 2.2**
dataset (hotels, restaurants, attractions and train timetables with price information) through FAISS semantic
search. The language model is a **hosted free-tier LLM API**; no local model is required.

---

## 2. Objectives & Goals

### Primary Goal
Build a working AI agent that demonstrates agentic reasoning — not just a chatbot. The agent must:

1. Understand what the user wants
2. Extract constraints and preferences
3. Break the goal into meaningful subtasks
4. Invoke appropriate tools in sequence
5. Maintain state across turns
6. Retrieve information from a local dataset
7. Generate a feasible schedule
8. Validate the plan against constraints
9. Reject or revise infeasible plans
10. Replan when a user changes requirements
11. Remember preferences during the conversation
12. Return a coherent, structured final plan

### Success Criterion
The system must demonstrate an **actual agentic workflow** — not conversational ability alone. The agent must reason over goals, use tools, maintain state, validate constraints, and revise plans.

---

## 3. System Architecture

### High-Level Architecture

```
+---------------------------------+
|              USER               |
+---------------------------------+
                 | Natural Language Input
                 v
+---------------------------------+
|         STREAMLIT UI            |
|  Chat Input | Plan Display      |
|  Sidebar | Session Controls     |
+---------------------------------+
                 | HTTP REST (JSON)
                 v
+---------------------------------+
|      FASTAPI APPLICATION        |
|  Routes | Session Management    |
|  CORS Middleware                |
+---------------------------------+
                 |
                 v
+---------------------------------------------------------+
|                   PLANNING AGENT                        |
|                                                         |
|  RECEIVED -> UNDERSTANDING -> DECOMPOSING -> EXECUTING  |
|      -> PLANNING -> VALIDATING -> VERIFYING -> COMPLETED|
|                                                         |
|  Branches:                                              |
|    MISSING_INFORMATION -> WAITING_FOR_USER              |
|    CONSTRAINT_VIOLATION -> REPLANNING                   |
|    ERROR -> CONTROLLED_RECOVERY                         |
+---------+-----------------+-----------------+-----------+
          |                 |                 |
          v                 v                 v
    +---------+     +-----------+    +------------------+
    |  TOOLS  |     |    LLM    |    |   VALIDATION     |
    |  Hotel  |     | Hosted    |    |  Constraint      |
    |  Rest.  |     |  via      |    |  Engine          |
    |  Attr.  |     |  LLM API  |    |  Verifier        |
    |  Trans. |     +-----------+    +------------------+
    +----+----+
         |
         v
+------------------+
|    RETRIEVAL     |
|   FAISS Search   |
|  all-MiniLM-L6   |
|  sentence-trans. |
+--------+---------+
         |
         v
+------------------+
|   DATA LAYER     |
|  MultiWOZ 2.2    |
|  JSON + FAISS    |
|  Index Files     |
+------------------+
```

### Layer Descriptions

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| **Presentation** | Streamlit | Chat UI, plan rendering, session controls |
| **API / Controller** | FastAPI + Uvicorn | REST endpoints, CORS, session routing |
| **Agent / Orchestration** | Python State Machine | Intent -> Decompose -> Execute -> Plan -> Validate -> Respond |
| **LLM** | Hosted free-tier LLM API (Groq / Gemini / OpenRouter / keyless fallback) | NL understanding, planning decisions, response generation |
| **State Management** | Pydantic models | Session context, conversation history, plan state |
| **Tools** | Python functions | Domain search wrappers (hotel, restaurant, attraction, transport) |
| **Retrieval** | FAISS + sentence-transformers | Semantic vector search over local data |
| **Validation** | Python + Pydantic | Deterministic constraint checking (budget, duration, preferences) |
| **Data** | MultiWOZ 2.2 JSON + FAISS | Local knowledge base |

---

## 4. Agent Design & State Machine

### Core State Machine

The `PlanningAgent` class in `backend/app/agent/planner.py` implements an explicit Python state machine with 13 states:

```
AgentStatus Enum:
  RECEIVED            -> Initial state upon message receipt
  UNDERSTANDING       -> Extracting intent and parameters
  DECOMPOSING         -> Breaking goal into subtasks
  EXECUTING           -> Running tool calls
  PLANNING            -> Generating candidate plan via LLM
  VALIDATING          -> Checking plan against constraints
  VERIFYING           -> Final consistency check
  COMPLETED           -> Success — plan delivered
  MISSING_INFORMATION -> Required fields are absent
  WAITING_FOR_USER    -> Awaiting clarification
  CONSTRAINT_VIOLATION-> Plan fails constraint checks
  REPLANNING          -> Revising plan after violation/change
  ERROR               -> Unrecoverable failure
```

### Main Execution Flow

```
handle_message(message, state)
    |
    +-- UNDERSTANDING: _understand() -> LLM -> IntentResult
    |       +-- Fallback: keyword-based _fallback_intent()
    |
    +-- check modification? -> _handle_replanning()
    |
    +-- _check_missing_info()
    |       +-- WAITING_FOR_USER if missing
    |
    +-- check_impossible_constraints() (early warnings)
    |
    +-- DECOMPOSING: _decompose() -> List[Task]
    |       +-- Deterministic for single-domain
    |       +-- LLM for trip_planning
    |
    +-- EXECUTING: _execute_tools() -> state with tool_results
    |
    +-- is_single_domain_search? -> _handle_search_results() -> Return
    |
    +-- PLANNING: _generate_plan() -> Plan (structured JSON via LLM)
    |       +-- Fallback: _fallback_plan() from tool_results
    |
    +-- VALIDATING: validate_plan() -> ConstraintResult
    |       +-- Loop up to MAX_REPLAN_ATTEMPTS if invalid
    |               +-- REPLANNING: _replan() -> new Plan
    |
    +-- VERIFYING: verify_plan() -> ConstraintResult (warnings only)
    |
    +-- COMPLETED: _generate_response() -> AgentResponse
```

### Intent Types

| Intent | Trigger | Tools Called |
|--------|---------|-------------|
| `hotel_search` | "Find a hotel..." | `hotel_search` |
| `restaurant_search` | "Find restaurants..." | `restaurant_search` |
| `attraction_search` | "What to visit..." | `attraction_search` |
| `transport_search` | "Find trains/taxis..." | `transport_search` |
| `trip_planning` | "Plan a 2-day trip..." | `attraction_search`, `restaurant_search`, optionally `hotel_search`, `transport_search` |
| `study_planning` | "Plan my study schedule..." | None (pure LLM) |
| `schedule_generation` | Generic schedule request | None |
| `replanning` | "Change the budget to..." | Conditional re-tool |
| `general_query` | Catch-all | None |

---

## 5. Technology Stack

### Core Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.x | Primary implementation language |
| **LLM** | Hosted free-tier APIs: Groq (`llama-3.3-70b-versatile`), Google Gemini (`gemini-2.5-flash`), OpenRouter (`:free` models), keyless Pollinations fallback | OpenAI-compatible chat API | NL understanding, planning, response generation |
| **Live Location Data** | OpenStreetMap Nominatim | Public API | Geocoding, reverse geocoding, hotels / restaurants / attractions / transport hubs anywhere |
| **Web UI** | Vite + vanilla JS (`frontend-web/`) | Vite 5 | Search bar with location + dates, chat, itinerary drawer |
| **Agent Orchestration** | Plain Python State Machine | — | Sequential workflow control |
| **UI Framework** | Streamlit | >=1.28.0 | Chat interface and plan display |
| **API Framework** | FastAPI | >=0.104.0 | RESTful backend API |
| **ASGI Server** | Uvicorn | >=0.24.0 | FastAPI server |
| **Data Validation** | Pydantic | >=2.5.0 | Schema definition and validation |
| **Vector Search** | FAISS (CPU) | >=1.7.4 | Semantic similarity search |
| **Embeddings** | sentence-transformers | >=2.2.0 | Text embedding model |
| **Embedding Model** | all-MiniLM-L6-v2 | — | 384-dim sentence embeddings |
| **Dataset** | MultiWOZ 2.2 | v2.2 | Local travel domain knowledge base |
| **HTTP Client** | requests | >=2.31.0 | Frontend-backend communication |
| **Config** | python-dotenv | >=1.0.0 | Environment variable management |
| **Testing** | pytest + pytest-asyncio | >=7.4.0 | Unit and integration tests |
| **Logging** | Python logging | stdlib | Execution tracing |
| **Version Control** | Git + GitHub | — | Source control |

### Why These Choices?

| Decision | Rationale |
|----------|-----------|
| **Hosted free LLM APIs** | No GPU or local model download; much stronger models than a local 3B model; one OpenAI-compatible client covers every provider, with automatic fallback |
| **OpenStreetMap (Nominatim)** | Free worldwide place data with no API key; lets the app work for the user's current or chosen location |
| **Plain Python State Machine** | Simplest, most transparent orchestration; no framework overhead |
| **FAISS-CPU** | Efficient vector search without GPU; handles the dataset size comfortably |
| **MultiWOZ 2.2** | Freely available, well-structured travel dataset; avoids paid APIs |
| **Pydantic v2** | Schema enforcement for all inter-module data contracts |
| **Streamlit** | Fastest way to build a functional AI chat UI in Python |
| **FastAPI** | Modern, high-performance REST API; auto-generates OpenAPI docs |

---

## 6. Project Structure

```
planwise-AI/
|
+-- backend/                        # Python FastAPI backend
|   +-- app/
|   |   +-- __init__.py
|   |   +-- main.py                 # FastAPI application entry point
|   |   +-- config.py               # Centralized configuration
|   |   |
|   |   +-- agent/                  # Core planning agent
|   |   |   +-- planner.py          # State machine implementation (948 lines)
|   |   |   +-- prompts.py          # All LLM prompt templates
|   |   |
|   |   +-- api/                    # REST API layer
|   |   |   +-- routes.py           # FastAPI routes
|   |   |
|   |   +-- geo/                    # Live location data (OpenStreetMap)
|   |   |   +-- geocoder.py         # Geocoding, reverse geocoding, autocomplete
|   |   |   +-- places.py           # Live hotels / restaurants / attractions / transport
|   |   |
|   |   +-- llm/                    # LLM client
|   |   |   +-- client.py           # Hosted LLM APIs (Groq / Gemini / OpenRouter / keyless)
|   |   |
|   |   +-- models/                 # Pydantic schemas
|   |   |   +-- schemas.py          # Core data models (PlanState, Plan, etc.)
|   |   |   +-- requests.py         # API request/response models
|   |   |
|   |   +-- retrieval/              # Vector search subsystem
|   |   |   +-- embeddings.py       # sentence-transformers embeddings
|   |   |   +-- index_manager.py    # FAISS index loading/searching
|   |   |   +-- search.py           # High-level retrieval service
|   |   |
|   |   +-- services/               # Application services
|   |   |   +-- session_service.py  # Session lifecycle management
|   |   |
|   |   +-- state/                  # State management
|   |   |   +-- manager.py          # PlanState update logic
|   |   |
|   |   +-- tools/                  # Domain search tools
|   |   |   +-- __init__.py         # Tool exports
|   |   |   +-- registry.py         # Tool registration & dispatch
|   |   |   +-- hotel.py            # hotel_search tool
|   |   |   +-- restaurant.py       # restaurant_search tool
|   |   |   +-- attraction.py       # attraction_search tool
|   |   |   +-- transport.py        # transport_search tool
|   |   |
|   |   +-- validation/             # Constraint engine
|   |       +-- constraints.py      # Deterministic constraint checks
|   |       +-- verifier.py         # Plan verification
|   |
|   +-- data/
|   |   +-- raw/db/                 # Original MultiWOZ 2.2 JSON files
|   |   |   +-- hotel_db.json       # 33 hotel records
|   |   |   +-- restaurant_db.json  # ~100 restaurant records
|   |   |   +-- attraction_db.json  # ~80 attraction records
|   |   |   +-- train_db.json       # ~10,000+ train records
|   |   |
|   |   +-- processed/              # Preprocessed normalized records
|   |   +-- index/                  # FAISS indexes (pre-built)
|   |       +-- hotel.faiss         # 50 KB
|   |       +-- hotel_metadata.json
|   |       +-- restaurant.faiss    # 165 KB
|   |       +-- restaurant_metadata.json
|   |       +-- attraction.faiss    # 118 KB
|   |       +-- attraction_metadata.json
|   |       +-- transport.faiss     # 4.1 MB
|   |       +-- transport_metadata.json
|   |
|   +-- scripts/
|   |   +-- preprocess_multiwoz.py  # Data preprocessing
|   |   +-- build_index.py          # FAISS index builder
|   |
|   +-- tests/                      # pytest test suite
|   +-- requirements.txt            # Backend Python dependencies
|
+-- frontend/                       # Streamlit frontend
|   +-- app.py                      # Main Streamlit application (643 lines)
|   +-- components/                 # UI components
|   +-- services/                   # API client
|   +-- utils/                      # Helper utilities
|   +-- requirements.txt            # Frontend dependencies
|
+-- frontend-web/                   # Optional Vite/HTML web frontend
|   +-- index.html
|   +-- app.js
|   +-- styles.css
|   +-- vite.config.js
|   +-- package.json
|
+-- evaluation/
|   +-- test_cases.json             # 13 structured evaluation test cases
|
+-- docs/                           # Documentation
+-- .env.example                    # Environment configuration template
+-- .gitignore
+-- PlanWise_AI_PRD.txt                             # Product Requirements Document
+-- PlanWise_AI_Complete_System_Architecture.txt    # Full system architecture spec
+-- PlanWise_AI_Technology_Stack.txt                # Technology selection guide
+-- PlanWise_AI_API_Specific_Document.txt           # API specification
+-- PlanWise_AI_Project_Context_and_Decision_History.md  # Design decisions log
```

---

## 7. Core Modules & Components

### 7.1 Planning Agent (`backend/app/agent/planner.py`)

The central orchestrator. The `PlanningAgent` class is 948 lines and implements the full state machine.

**Key Methods:**

| Method | State | Description |
|--------|-------|-------------|
| `handle_message()` | Entry point | Processes all user messages through the full pipeline |
| `_understand()` | UNDERSTANDING | Calls LLM to extract `IntentResult` (structured JSON) |
| `_fallback_intent()` | — | Keyword-based intent extraction when LLM fails |
| `_check_missing_info()` | — | Verifies required fields (location, duration) are present |
| `_decompose()` | DECOMPOSING | Creates `List[Task]` from the user's goal |
| `_execute_tools()` | EXECUTING | Dispatches each task to the tool registry |
| `_generate_plan()` | PLANNING | LLM generates a structured `Plan` JSON object |
| `_fallback_plan()` | — | Constructs plan directly from tool_results if LLM fails |
| `_generate_response()` | COMPLETED | Converts structured plan to natural language |
| `_handle_replanning()` | REPLANNING | Modifies state and regenerates plan |
| `_is_single_domain_search()` | — | Routes hotel/restaurant/attraction/transport searches |
| `_handle_search_results()` | COMPLETED | Returns search results without full planning |

### 7.2 LLM Client (`backend/app/llm/client.py`)

Single controlled interface to hosted LLM APIs. Every supported provider speaks the OpenAI
"chat completions" protocol, so one client covers them all.

| Provider | Key needed | Default model | Notes |
|----------|-----------|---------------|-------|
| Groq | free key - https://console.groq.com/keys | `llama-3.3-70b-versatile` | Recommended: very fast |
| Google Gemini | free key - https://aistudio.google.com/apikey | `gemini-2.5-flash` | |
| OpenRouter | free key - https://openrouter.ai/keys | `google/gemma-4-31b-it:free` | Any `:free` model |
| Pollinations | **none** | `openai` | Keyless fallback: about one reply per 45 s, slow |
| Custom / Ollama | optional | configurable | Any OpenAI-compatible endpoint |

**Key Features:**
- **Provider chain with fallback** - `LLM_PROVIDER=auto` uses every provider that has a key (Groq -> Gemini -> OpenRouter -> custom), then the keyless endpoint. A provider that fails or is rate limited is put on a short cooldown and the next one is tried.
- `generate()` - text generation with system prompt and conversation history
- `generate_structured()` - JSON output validated against a Pydantic schema with automatic retry (up to `LLM_MAX_RETRIES`); uses the provider's JSON mode where available
- `_extract_json()` - robust JSON extraction (markdown code blocks, surrounding text)
- **Limited ("frugal") mode** - when only the keyless endpoint is configured, the agent spends its single AI call on the answer itself and uses rule-based logic for intent detection, so the app still responds from a live API with zero setup.

### 7.2a Live Location Services (`backend/app/geo/`)

- `geocoder.py` - place name -> coordinates (`geocode`, `search` for autocomplete) and coordinates -> place (`reverse`, used for "use my current location"). Throttled to 1 request/second and cached, per the Nominatim usage policy.
- `places.py` - real hotels, restaurants, attractions and transport hubs around any coordinates, normalized to the same record shape as the Cambridge dataset, ranked by notability and distance, cached for an hour.
- `backend/app/money.py` - currency by country, formatting and price-level estimates. All budget arithmetic is deterministic Python.
- `backend/app/tools/common.py` - routes each tool call to live data, the bundled Cambridge dataset, or an explicit "unknown location" result (never silently substituting Cambridge data for another place).

### 7.3 Pydantic Data Models (`backend/app/models/schemas.py`)

All inter-module data contracts are Pydantic v2 models:

| Model | Purpose |
|-------|---------|
| `AgentStatus` | Enum of 13 state machine states |
| `ResponseStatus` | API response status codes |
| `IntentType` | Enum of 9 supported intent types |
| `IntentResult` | Output of intent understanding (intent, location, budget, preferences, etc.) |
| `Task` | A single subtask with type, parameters, and execution status |
| `TaskStatus` | PENDING / IN_PROGRESS / COMPLETED / FAILED / SKIPPED |
| `ToolResult` | Tool execution output (success, results list, error) |
| `PlanActivity` | Single activity (name, type, cost, duration, details) |
| `PlanTimeSlot` | Time-of-day container (morning/afternoon/evening) |
| `PlanDay` | One day with multiple time slots |
| `Plan` | Complete plan (location, days, total cost, assumptions) |
| `ConstraintResult` | Validation output (valid, violations, warnings) |
| `ConversationMessage` | Single chat turn (role, content, timestamp) |
| `PlanState` | Complete session state (source of truth) |
| `AgentResponse` | Final response from agent to API/frontend |

### 7.4 State Manager (`backend/app/state/manager.py`)

The `StateManager` class handles all `PlanState` mutations:

- `create_state()` — Fresh session state
- `update_from_intent()` — Merges `IntentResult` without overwriting existing values
- `update_from_tool_result()` — Adds tool results and chosen options to state
- `apply_changes()` — Updates state from replanning `raw_changes` dict
- `add_message()` — Appends to conversation history
- `get_state_summary()` — Formats state for LLM prompts
- `get_retrieved_options_summary()` — Formats tool results for LLM schedule generation
- `get_conversation_summary()` — Formats chat history for intent context

### 7.5 Tool Registry (`backend/app/tools/registry.py`)

Simple function registration and dispatch:

```python
execute_tool(tool_name: str, parameters: dict) -> ToolResult
```

Registered tools:
- `hotel_search` — `backend/app/tools/hotel.py`
- `restaurant_search` — `backend/app/tools/restaurant.py`
- `attraction_search` — `backend/app/tools/attraction.py`
- `transport_search` — `backend/app/tools/transport.py`

Each tool validates its parameters, calls the `RetrievalService`, and returns a `ToolResult`.

### 7.6 Retrieval Service (`backend/app/retrieval/search.py`)

The `RetrievalService` class handles semantic search:

**Pipeline:**
```
Query String
    |
    v
generate_single_embedding()   [all-MiniLM-L6-v2, 384-dim]
    |
    v
search_index(domain, embedding, top_k=50)   [FAISS IndexFlatIP]
    |
    v
_apply_filters(records, filters)   [metadata post-filter]
    |
    v
Return top_k results
```

**Fallback Chain:**
1. Semantic FAISS search + metadata filter
2. Semantic search only (if filter yields 0)
3. Metadata-only filter (if FAISS unavailable)
4. All records (if filters unavailable)

### 7.7 Session Service (`backend/app/services/session_service.py`)

Manages planning sessions in-memory:

- `create_session()` — New `PlanState` with unique `session_id`
- `get_session(session_id)` — Retrieves state
- `handle_message(session_id, message)` — Delegates to `PlanningAgent`
- `replan(session_id, changes)` — Triggers explicit replanning

---

## 8. Dataset — MultiWOZ 2.2

### Overview

MultiWOZ (Multi-Domain Wizard-Of-Oz) 2.2 is a large-scale dialogue dataset covering task-oriented conversations across 5 domains in **Cambridge, UK**.

| Property | Value |
|----------|-------|
| Source | Hugging Face: `pfb30/multi_woz_v22` |
| Original repo | https://github.com/budzianowski/multiwoz |
| Coverage | Cambridge, UK |
| License | MIT |

### Domains Used

| Domain | File | Records (approx.) | FAISS Index Size |
|--------|------|--------------------|-----------------|
| **Hotel** | `hotel_db.json` | 33 | 50 KB |
| **Restaurant** | `restaurant_db.json` | ~100 | 165 KB |
| **Attraction** | `attraction_db.json` | ~80 | 118 KB |
| **Transport (Train)** | `train_db.json` | ~10,000+ | 4.1 MB |

### Hotel Record Fields
`name`, `type` (hotel/guesthouse), `pricerange` (cheap/moderate/expensive), `stars` (1-5), `area` (centre/north/south/east/west), `parking`, `internet`, `address`, `phone`, `postcode`

### Restaurant Record Fields
`name`, `food` (cuisine type), `pricerange`, `area`, `address`, `phone`, `postcode`

### Attraction Record Fields
`name`, `type` (museum/park/college/etc.), `area`, `entrance_fee`, `address`, `phone`, `postcode`

### Transport Record Fields
`departure`, `destination`, `day`, `leaveAt`, `arriveBy`, `price`, `duration`, `trainID`, `type`

---

## 9. Data Pipeline & Vector Search (FAISS)

### Preprocessing (`backend/scripts/preprocess_multiwoz.py`)

Extracts and normalizes raw MultiWOZ JSON into clean domain records.

### Index Building (`backend/scripts/build_index.py`)

```
Raw DB JSON
    |
    v
record_to_text(record, domain)    [domain-specific field concatenation]
    |
    v
generate_embeddings(texts)        [sentence-transformers: all-MiniLM-L6-v2]
    |
    v
faiss.IndexFlatIP(dimension)      [Inner Product = cosine similarity for L2-normalized]
    |
    v
index.add(embeddings)
    |
    v
faiss.write_index() -> {domain}.faiss
json.dump(records) -> {domain}_metadata.json
```

### Embedding Model: `all-MiniLM-L6-v2`

| Property | Value |
|----------|-------|
| Model family | Sentence-BERT (SBERT) |
| Dimensions | 384 |
| Max sequence length | 256 tokens |
| Normalization | L2-normalized (cosine similarity via inner product) |
| Language | English |

### Search at Query Time

1. User query -> `generate_single_embedding(query)` -> 384-dim vector
2. FAISS `search(query_vector, k=50)` -> top-50 candidate records + distances
3. Metadata post-filtering (pricerange, food type, etc.)
4. Return top-k results

---

## 10. API Reference

### Base URL
```
http://localhost:8000/api/v1
```

### Endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/health` | Backend health + LLM provider status (`?probe=true` actively tests the LLM) |
| `GET` | `/geo/search?q=` | Place autocomplete for the location picker |
| `GET` | `/geo/reverse?lat=&lon=` | Name the user's current location |
| `POST` | `/geo/prefetch?lat=&lon=` | Warm live data for a picked location |
| `POST` | `/sessions` | Create a new planning session |
| `GET` | `/sessions/{session_id}` | Get current session state |
| `POST` | `/sessions/{session_id}/messages` | **Main endpoint** — send user message |
| `GET` | `/sessions/{session_id}/plan` | Get current plan with validation |
| `POST` | `/sessions/{session_id}/replan` | Replan with explicit changes |

**Message context.** `POST /sessions/{id}/messages` accepts an optional `context` with what the user picked in the UI:

```json
{
  "message": "Plan a trip to Mysuru",
  "context": {
    "location": "Mysuru, India", "lat": 12.3041, "lon": 76.6529,
    "start_date": "2026-12-12", "end_date": "2026-12-13",
    "explicit": true
  }
}
```

A place named in the message wins over the context; the context wins over the session's earlier location.
Responses additionally carry `results` (structured records for result cards), `results_domain`, and a
`context` object (location, coordinates, dates, duration, budget, currency, data source, LLM provider).

### Key Request/Response Examples

**Create Session**
```json
POST /api/v1/sessions
Response: { "session_id": "uuid-v4", "status": "active" }
```

**Send Message**
```json
POST /api/v1/sessions/{session_id}/messages
{ "message": "Plan a 2-day trip to Cambridge" }

Response:
{
  "session_id": "...",
  "status": "completed",
  "message": "Here is your 2-day Cambridge itinerary...",
  "plan": { "location": "Cambridge", "duration_days": 2, "days": [...] },
  "validation": { "valid": true, "violations": [], "warnings": [] },
  "intent": { "intent": "trip_planning", "location": "Cambridge", "duration_days": 2 }
}
```

**Response Status Values**

| Status | Meaning |
|--------|---------|
| `completed` | Plan generated successfully |
| `clarification_required` | Missing info — agent asked a question |
| `replanning` | Plan was revised |
| `constraint_failure` | Plan could not satisfy constraints |
| `tool_failure` | Search tools returned no results |
| `error` | Unexpected failure |

---

## 11. Constraint & Validation Engine

### Architecture Principle
> **The LLM is NEVER responsible for deterministic constraint checking or budget arithmetic.** All validation is done in Python.

### Constraint Checks (`backend/app/validation/constraints.py`)

| Check | Function | Description |
|-------|---------|-------------|
| **Budget** | `check_budget()` | `plan.estimated_total_cost <= state.budget` |
| **Duration** | `check_duration()` | `len(plan.days) == state.duration_days` |
| **Preferences** | `check_preferences()` | Non-vegetarian restaurants flagged for vegetarian users |
| **Components** | `check_required_components()` | Trip plans must have at least 1 activity per day |
| **Impossible** | `check_impossible_constraints()` | Budget < 300/day warns early |

### Validation Flow

```
validate_plan(plan, state) -> ConstraintResult
    +-- check_budget()      -> violations[]
    +-- check_duration()    -> violations[]
    +-- check_preferences() -> violations[]
    +-- check_required_components() -> violations[]

ConstraintResult:
  valid: bool
  violations: List[str]   <- blocks plan delivery
  warnings: List[str]     <- non-blocking, shown to user
```

### Replanning Loop
```python
while not validation.valid and replan_attempts < MAX_REPLAN_ATTEMPTS:
    replan_attempts += 1
    candidate_plan = _replan(state, validation.violations)
    validation = validate_plan(candidate_plan, state)
```

`MAX_REPLAN_ATTEMPTS` defaults to `2` (configurable via `.env`).

### Plan Verifier (`backend/app/validation/verifier.py`)
Secondary non-blocking check after validation passes:
- All activity names are non-empty
- Estimated costs are non-negative
- Schedule structure is consistent

---

## 12. Replanning Model

Replanning is a **core requirement** of the agentic design. The system treats the plan as stateful and modifies it when requirements change.

### Triggered When:
- User changes budget: *"Reduce the budget to 1,500"*
- User changes duration: *"Make it a 3-day trip instead"*
- User changes preferences: *"Actually, I want vegetarian food only"*
- User changes location: *"Plan for London instead"*

### Replanning Flow:
```
User sends modification message
    |
    v
_understand() detects is_modification=true
    |
    v
_handle_replanning(state, intent)
    +-- Apply raw_changes to state
    +-- Check if new retrieval needed (location changed?)
    |       +-- Re-run _decompose() and _execute_tools()
    +-- REPLANNING: _generate_plan() with updated state
    +-- validate_plan() loop
    +-- Return updated AgentResponse
```

The existing session state is **preserved** — unchanged values (location, preferences, interests) carry over to the revised plan.

---

## 13. Prompt Engineering

All LLM prompts are in `backend/app/agent/prompts.py`. Each prompt follows a strict structure:

```
Role statement       -> "You are PlanWise AI's [module name]"
Context/State        -> Current state summary, conversation history
Instructions         -> What to do
Output schema        -> Exact JSON structure expected
Rules                -> Hallucination guards, constraints
```

### Prompt Templates

| Function | Used In | Output |
|----------|---------|--------|
| `intent_prompt()` | `_understand()` | `IntentResult` JSON |
| `decomposition_prompt()` | `_decompose()` | `{"tasks": [...]}` JSON |
| `schedule_prompt()` | `_generate_plan()` | `Plan` JSON (trip) |
| `study_schedule_prompt()` | `_generate_plan()` | `Plan` JSON (study) |
| `replanning_prompt()` | `_replan()` | Revised `Plan` JSON |
| `response_prompt()` | `_generate_response()` | Natural language string |
| `clarification_prompt()` | Missing info path | Clarification question |
| `search_results_prompt()` | Single-domain search | Formatted search results |

### Hallucination Prevention Strategy
Every prompt includes:
> *"Use ONLY names and details from the AVAILABLE OPTIONS above. Do NOT invent places, restaurants, or attractions not listed."*

The LLM is instructed to use **only** the retrieved MultiWOZ records — not its training knowledge.

### Temperature Settings
| Operation | Temperature | Reason |
|-----------|------------|--------|
| Intent extraction | 0.1 | High precision, low creativity |
| Decomposition | 0.1 | Deterministic task selection |
| Plan generation | 0.1 | Structured JSON required |
| Response generation | 0.3–0.5 | Slightly warmer for readable prose |

---

## 14. Frontend — Streamlit UI

### Primary Frontend (`frontend/app.py`) — 643 lines

The Streamlit UI is a **thin presentation layer** — all business logic lives in the backend.

**Design:**
- Dark theme with glassmorphism card effects
- CSS custom properties (design tokens)
- Google Font: Inter
- Color palette: Purple accent (`#7c3aed`), dark backgrounds (`#0f0f1a`)
- Smooth gradient transitions

**Key UI Sections:**

| Section | Description |
|---------|-------------|
| **Chat Area** | Conversation history with user/assistant bubbles |
| **Input Box** | Natural language query input |
| **Plan Display** | Day-by-day schedule cards with time slots |
| **Sidebar** | Session info, budget tracker, preferences, quick examples |
| **Constraint Panel** | Validation status, warnings, violations |

**Session Management:**
- `st.session_state.session_id` — UUID assigned per browser session
- `st.session_state.messages` — Chat history
- `st.session_state.current_plan` — Current plan object

### Optional Web Frontend (`frontend-web/`)
A standalone Vite/Vanilla JS web application with the same feature set, for deployment as a static web app.

---

## 15. Evaluation & Test Cases

### Test Suite (`evaluation/test_cases.json`)

13 structured test cases covering all functional requirements:

| ID | Name | Intent | Key Check |
|----|------|--------|-----------|
| TEST_01 | Simple Hotel Search | `hotel_search` | Returns hotel results, no hallucination |
| TEST_02 | Restaurant + Preference | `restaurant_search` | Respects vegetarian preference |
| TEST_03 | Attraction Search | `attraction_search` | Returns attraction results |
| TEST_04 | Multi-Domain Trip | `trip_planning` | 2-day plan with attractions & restaurants |
| TEST_05 | Budget-Constrained Trip | `trip_planning` | Estimated cost <= 2,000 |
| TEST_06 | Replanning (Budget) | `replanning` | Budget updated to 1,500; plan revised |
| TEST_07 | Preference Memory | — | Vegetarian preference retained |
| TEST_08 | Impossible Constraints | `trip_planning` | Identifies conflict; no invalid plan |
| TEST_09 | Changed Preference | — | Italian food preference applied |
| TEST_10 | Study Planning | `study_planning` | 7-day schedule, no tool calls |
| TEST_11 | Missing Info | `trip_planning` | System asks for location & duration |
| TEST_12 | Tool Failure | — | Graceful error; no crash |
| TEST_13 | Transport Search | `transport_search` | Returns train results |

### Evaluation Dimensions
- **Functional Correctness** — Does the agent follow the right state path?
- **Constraint Compliance** — Is the budget/duration respected?
- **Replanning Correctness** — Is state preserved; does plan update?
- **Hallucination Detection** — Are all results from MultiWOZ data?
- **Error Handling** — Does the system recover gracefully?

---

## 16. Installation & Setup

### Prerequisites

| Requirement | Version | Notes |
|------------|---------|-------|
| Python | >= 3.10 | Backend |
| Node.js | >= 18 | Web frontend (Vite) |
| Internet access | - | Hosted LLM API and OpenStreetMap |
| LLM API key | optional, free | Groq / Gemini / OpenRouter - strongly recommended |

### Step 1 - Clone the Repository
```bash
git clone <repo-url>
cd planwise-AI
```

### Step 2 - Configure Environment
```bash
cp .env.example .env
```

Then add **one free API key** to `.env` (takes about a minute, no credit card):

```
GROQ_API_KEY=your_key_here        # https://console.groq.com/keys
# or
GEMINI_API_KEY=your_key_here      # https://aistudio.google.com/apikey
```

Without a key the app still works through a keyless endpoint, but that endpoint allows roughly
**one AI reply every 45 seconds** and is slow. Live map data is always fast.

### Step 3 - Install Dependencies
```bash
cd backend
pip install -r requirements.txt
cd ../frontend-web
npm install
```

### Step 4 - Build FAISS Indexes (only if not pre-built)
```bash
cd backend
python -m scripts.preprocess_multiwoz
python -m scripts.build_index
```

> The pre-built indexes are already in `backend/data/index/`. They are only used for Cambridge, UK.

---

## 17. Running the Application

### One command (Windows)
```powershell
.\start.ps1
```
The script installs dependencies, picks free ports if 8000 / 3000 are already in use, starts the backend
and the web frontend in two windows, and prints the URLs.

### Manually
```bash
# Terminal 1 - backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - web frontend (set BACKEND_PORT if the backend is not on 8000)
cd frontend-web
npm run dev
```

### Access the Application
- **Web UI:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs (Swagger):** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/v1/health

The legacy Streamlit UI (`frontend/`, `streamlit run app.py`) still works for chat but does not have the
location picker or date range.

### Deploy for Free (Render, straight from GitHub)

The repository contains a `render.yaml` blueprint: one free web service runs the backend, which also
serves the web frontend, so there is nothing else to host.

1. Open **https://render.com/deploy?repo=https://github.com/HSSHREYAS/Planwise-AI** and sign in with GitHub.
2. When asked for environment variables, paste a free `GROQ_API_KEY` (https://console.groq.com/keys)
   and/or `GEMINI_API_KEY`. They can be left empty, but then AI replies are limited to about one per 45 seconds.
3. Click **Apply**. After the build (2-3 minutes) the site is live at `https://planwise-ai.onrender.com`
   (Render adds a suffix if the name is taken). Every push to `master` redeploys automatically.

Notes: the free plan sleeps after 15 minutes without traffic, so the first visit afterwards takes about a
minute. The deployment uses `backend/requirements-deploy.txt`, which leaves out FAISS and
sentence-transformers (too heavy for free tiers); the Cambridge dataset is then searched by metadata
filtering instead of semantic vectors. Sessions are in memory and reset on each restart.

### Using It
1. Allow location access when the browser asks (or type any city in **Where** and pick a suggestion). The 📍 button re-detects your current location.
2. Optionally choose **From** and **To** dates, what to plan, and a budget style, then press search.
3. In the planner, the 📍 chip shows the active location - click it to change. Naming a place in a message ("hotels in Jaipur") switches location too.
4. Refine in chat: "make it 3 days", "change the budget to 8000 rupees", "vegetarian only".

### Run Tests
```bash
cd backend
pytest tests/ -v
```
The suite (181 tests) runs offline: the LLM and map services are replaced by fakes.

---

## 18. Configuration Reference

All configuration is via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `auto` | `auto`, `groq`, `gemini`, `openrouter`, `pollinations`, `custom`, `ollama` |
| `GROQ_API_KEY` / `GROQ_MODEL` | - / `llama-3.3-70b-versatile` | Groq (free key) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | - / `gemini-2.5-flash` | Google Gemini (free key) |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | - / `google/gemma-4-31b-it:free` | OpenRouter (free key) |
| `POLLINATIONS_BASE_URL` / `POLLINATIONS_MODEL` | keyless endpoint / `openai` | Fallback that needs no key |
| `CUSTOM_LLM_BASE_URL` / `_API_KEY` / `_MODEL` | - | Any OpenAI-compatible endpoint |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `qwen2.5:3b-instruct` | Only with `LLM_PROVIDER=ollama` |
| `LLM_TIMEOUT` | `60` | Request timeout (seconds) |
| `LLM_MAX_RETRIES` | `2` | Retries for structured output |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Geocoding / places service |
| `GEO_USER_AGENT` | `PlanWiseAI/2.0 ...` | Identifies the app to OpenStreetMap |
| `MAX_TRIP_DAYS` | `14` | Longest plan the agent will build |
| `RETRIEVAL_TOP_K` | `5` | Max results per search |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `BACKEND_HOST` | `0.0.0.0` | FastAPI server host |
| `BACKEND_PORT` | `8000` | FastAPI server port |
| `BACKEND_URL` | `http://localhost:8000` | URL used by frontend |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `MAX_REPLAN_ATTEMPTS` | `2` | Max constraint fix iterations |

---

## 19. Supported User Journeys

### Journey 1: Trip Planning
```
User: "I am travelling to Cambridge for two days. Plan places to visit, 
       food options and a reasonable schedule."

Agent:
  1. UNDERSTANDING: intent=trip_planning, location=Cambridge, duration=2
  2. DECOMPOSING: [attraction_search, restaurant_search, hotel_search]
  3. EXECUTING: Runs all 3 tools -> retrieves real MultiWOZ records
  4. PLANNING: LLM generates 2-day schedule from retrieved options
  5. VALIDATING: Checks duration=2, budget=None (passes)
  6. VERIFYING: Checks structural consistency
  7. COMPLETED: Returns formatted 2-day itinerary
```

### Journey 2: Budget-Constrained Trip
```
User: "Create a one-day trip plan with a 2,000 rupee budget."

Agent:
  -> Same as above but with budget constraint
  -> Validation: estimated_total_cost <= 2000
  -> If exceeded -> REPLANNING: tries cheaper alternatives
```

### Journey 3: Replanning
```
User (turn 1): "Plan a 2-day trip with 2,000 rupee budget."
Agent: [Returns plan]

User (turn 2): "Reduce the budget to 1,500."
Agent:
  1. UNDERSTANDING: is_modification=true, raw_changes={budget: 1500}
  2. _handle_replanning(): Updates budget, preserves location/duration
  3. Regenerates plan with lower cost constraint
  4. Returns revised plan
```

### Journey 4: Study Planning
```
User: "Plan my study schedule for 7 days covering math, physics, chemistry."

Agent:
  1. UNDERSTANDING: intent=study_planning, duration=7
  2. DECOMPOSING: No tool calls needed
  3. PLANNING: study_schedule_prompt() -> LLM generates study plan
  4. VALIDATING: Checks 7-day structure
  5. COMPLETED: Returns subject-distributed study schedule
```

### Journey 5: Impossible Constraints
```
User: "I have 2 days, 500 rupees, and want to visit 10 attractions."

Agent:
  1. check_impossible_constraints(): Warns 250/day is very tight
  2. Generates plan within data
  3. validate_plan(): Likely constraint violations
  4. Explains infeasibility clearly; does not return invalid plan
```

### Journey 6: Missing Information
```
User: "Plan a trip for me."

Agent:
  1. UNDERSTANDING: intent=trip_planning
  2. _check_missing_info(): location=None, duration=None -> missing!
  3. WAITING_FOR_USER: Asks "Could you tell me your destination and 
     how many days you're planning to travel?"
```

---

## 20. Limitations & Scope

### In Scope
- Natural-language trip and study planning
- Any location worldwide (live OpenStreetMap data) - current location or chosen place
- Travel dates, budget (in the destination's currency), duration and preference constraints
- Multi-turn conversation with state retention
- Replanning on requirement changes
- Impossible constraint detection

### Out of Scope (Intentional)
| Excluded | Reason |
|----------|--------|
| Paid travel APIs (Booking.com, etc.) | Unnecessary cost and complexity |
| Real booking / purchasing, live prices and availability | Not required for the project |
| Payment processing | Out of scope |
| Production authentication (JWT, OAuth) | Not required |
| MongoDB / PostgreSQL | Not required; in-memory sessions are sufficient |
| Mobile application | The web UI is responsive instead |

### Known Limitations
1. **Costs are estimates.** OpenStreetMap carries no prices; per-person costs come from the LLM (or price-level tables) and are summed in Python. They are not quotes.
2. **Data coverage varies.** OpenStreetMap is excellent in cities and thinner in small towns. When nothing is mapped the assistant says so and may offer AI suggestions, clearly labelled as unverified.
3. **Train timetables** exist only for Cambridge, UK (bundled dataset). Elsewhere the transport search lists stations and airports, not schedules.
4. **Free-tier limits.** Hosted LLM free tiers are rate limited; without any key the keyless endpoint allows about one AI reply per 45 seconds. The public Nominatim service is limited to 1 request/second, so the first search for a new city takes a few seconds (then it is cached).
5. **Session Persistence:** Sessions are in-memory only; they are lost when the server restarts.
6. **Current location** needs browser permission and a secure context (`localhost` or HTTPS).

---

## 21. Future Enhancements

| Enhancement | Description |
|-------------|-------------|
| **Persistent Sessions** | Replace in-memory store with SQLite or Redis |
| **More Cities** | Expand dataset beyond Cambridge |
| **Real API Integration** | Optional hooks for live hotel/restaurant APIs |
| **Map Integration** | Visualize itinerary on a map |
| **PDF Export** | Export generated plans as PDF |
| **Streaming Responses** | Stream the AI answer token by token |
| **User Authentication** | Save plans per user account |
| **Streaming Responses** | Stream LLM output for better UX |
| **LangGraph Migration** | Optional: Replace Python state machine with LangGraph |

---

## 22. References

| Reference | Description |
|-----------|-------------|
| MultiWOZ 2.2 — Hugging Face (https://huggingface.co/datasets/pfb30/multi_woz_v22) | Dataset used for knowledge base |
| MultiWOZ GitHub (https://github.com/budzianowski/multiwoz) | Original MultiWOZ repository |
| Groq (https://console.groq.com), Google AI Studio (https://aistudio.google.com), OpenRouter (https://openrouter.ai), Pollinations (https://pollinations.ai) | Hosted LLM APIs |
| OpenStreetMap / Nominatim (https://nominatim.org) | Live place data (c) OpenStreetMap contributors, ODbL |
| FAISS — Facebook AI (https://github.com/facebookresearch/faiss) | Vector similarity search library |
| sentence-transformers (https://www.sbert.net) | Sentence embedding library |
| all-MiniLM-L6-v2 (https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | Embedding model |
| FastAPI (https://fastapi.tiangolo.com) | Python web framework |
| Streamlit (https://streamlit.io) | Python UI framework |
| Pydantic v2 (https://docs.pydantic.dev/latest/) | Data validation library |

---

## Authors

**PlanWise AI** — Undergraduate GenAI ABL-1 Project  
Target: Demonstrating agentic AI concepts including intent understanding, task decomposition, tool calling, state management, constraint validation, and replanning.

---

*This README was prepared as part of the project submission documentation for the GenAI ABL-1 course.*  
*Submission Deadline: 30 October 2026*
