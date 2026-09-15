# PlanWise AI — Project Decision & Build Context

## Purpose of This Document

This document gives the AI coding/development agent the project history, decisions,
constraints, selected technologies, architecture, API direction, and current
understanding of **PlanWise AI**.

The goal is that the agent can understand not only **what to build**, but also
**why this project was selected, what alternatives were rejected, and which
decisions are already final**.

The agent should treat the supplied PRD, System Architecture, Technology Stack,
and API Specification as the primary implementation documents.

---

# 1. Original Project Context

The user's college provided a list of GEN AI projects for ABL-1. The supplied
project list contains 24 projects, including:

1. AI Legal Contract Summarizer
2. AI Study Companion
3. DisasterHelp AI
4. AgriVision AI
5. VisionVoice AI
6. EcoSort AI
7. MedResearch AI
8. ScamShield AI
9. CyberGuard AI
10. FactCheck AI
11. NutriGuide AI
12. StudentWell AI
13. DocuMind AI
14. MeetingMind AI
15. CodeMentor AI
16. EcoEnergy AI
17. VoiceBridge AI
18. **PlanWise AI**
19. KnowledgeGraph AI
20. SmartRoad AI
21. TransitSense AI
22. LearnMate AI
23. AccessAI
24. CivicAgent AI

The original supplied document explicitly lists PlanWise AI as project number 18
and AccessAI as project number 23. fileciteturn0file0L2-L27

---

# 2. Project Selection Journey

## Initial Goal

The user was not looking for a project merely because it was easy.

The desired project needed to balance:

- Fast/easy completion
- Genuine AI-agent implementation
- Strong technical learning
- Resume value for FAANG/MAANG-level software engineering interviews
- Potential to be developed into something academically presentable
- Ability to build from scratch through deployment
- Minimal unnecessary infrastructure
- Ability to complete reliably within the academic deadline

The user specifically rejected projects/directions that felt too generic for a
strong software-engineering resume.

---

# 3. AccessAI Direction Was Considered

A more ambitious direction was considered around **AccessAI + Web Agent**.

The proposed concept was:

> Instead of limiting accessibility assistance to physical surroundings, make
> the system capable of interacting with inaccessible digital interfaces.

Example:

> "Find the cheapest flight from Bangalore to Delhi next Friday and tell me the
> departure time."

Proposed conceptual pipeline:

```text
Voice
  ↓
Intent Understanding
  ↓
Browser Agent
  ↓
Visual Webpage Understanding
  ↓
Accessibility Tree
  ↓
Element Grounding
  ↓
Action
  ↓
Verification
  ↓
Voice Response
```

This direction was recognized as technically impressive because it touches:

- Multimodal agents
- Browser automation
- Computer use
- Accessibility
- Planning
- Grounding
- Verification
- Safety
- Human-computer interaction

However, it was also recognized as substantially more complex and difficult to
complete reliably.

The user then explicitly prioritized a project that could be completed as early
and easily as possible using an AI agent.

Therefore, the ambitious AccessAI/Web Agent direction was **not selected**.

---

# 4. DisasterHelp Was Also Rejected

DisasterHelp AI was considered but rejected because the user felt disaster-help
was too generic to be sufficiently distinctive for a strong resume/project
profile.

Therefore:

```text
DisasterHelp AI → NOT SELECTED
```

---

# 5. Final Project Choice

The selected project is:

# PlanWise AI

**Full title:**

> PlanWise AI — Agentic Personal Task and Trip Planning Assistant

The reason for selecting PlanWise is that it gives a relatively manageable
implementation while still demonstrating a genuine agentic workflow.

It includes:

- Intent understanding
- Task decomposition
- Tool calling
- Information retrieval
- State management
- Constraint handling
- Verification
- Schedule generation
- Replanning
- Memory
- Agent evaluation
- Streamlit UI
- Local LLM execution

This gives the project more engineering depth than a simple chatbot while
remaining substantially easier than a multimodal browser/computer-use agent.

---

# 6. Important Scope Decision

A major decision was made:

> **Do not expand the project beyond the supplied Project 18 specification.**

The user explicitly wants the project to remain **exactly this much**.

Do NOT add extra features simply to make the project sound more advanced.

The implementation should prioritize:

- Correctness
- Reliability
- Complete end-to-end functionality
- Clean architecture
- Testing
- Maintainability
- Fast completion

over unnecessary feature expansion.

---

# 7. Original PlanWise Requirement

The core use case is:

> "I am travelling to Bengaluru for two days. Create a plan covering places
> to visit, food options and a reasonable schedule."

The system should perform:

```text
User Goal
   ↓
Planning Agent
   ↓
Information Retrieval
   ↓
Constraint Checking
   ↓
Schedule Generation
   ↓
Final Plan
```

A second use case is:

> "Plan my study schedule for the next seven days."

Another example:

> "Create a one-day trip plan based on a ₹2,000 budget."

The project is intended to introduce students to agentic GenAI.

---

# 8. Core Agent Capabilities

The final system must demonstrate:

1. Intent understanding
2. Task decomposition
3. Tool calling
4. State management
5. Constraint handling
6. Verification
7. Final response generation
8. Replanning
9. Basic memory
10. Evaluation

The system does not require multiple expensive LLMs.

A single small model should perform different roles sequentially.

---

# 9. Dataset Decision

The selected dataset is:

**MultiWOZ 2.2**

Relevant domains:

- Hotel
- Restaurant
- Attraction
- Train
- Taxi

The dataset is used as local/static domain knowledge.

Important:

**Do not interpret this as a requirement to train Qwen from scratch on MultiWOZ.**

The intended flow is:

```text
MultiWOZ 2.2
    ↓
Data Preparation
    ↓
Processed Local Records
    ↓
Search / Retrieval
    ↓
Domain Tools
    ↓
Planning Agent
```

The project does not require paid travel APIs.

---

# 10. Why Local/Static Data Was Chosen

The original specification explicitly allows local/static datasets so that the
project does not depend on paid external APIs.

Therefore the project should be:

- Reproducible
- Low cost
- Local-first
- Easier to test
- Easier to deploy
- Less dependent on external services

Do not introduce live travel APIs unless the project specification is changed.

---

# 11. Technology Decisions

The agreed primary technology stack is:

```text
Python
Streamlit
Qwen2.5-3B-Instruct
Ollama
Plain Python State Machine
Pydantic
FAISS
Local Embeddings
MultiWOZ 2.2
pytest
Python logging
Git
GitHub
```

LangGraph is optional.

---

# 12. Agent Orchestration Decision

The original specification recommends:

> LangGraph

but also explicitly permits:

> Plain Python state machine

The decision for fastest implementation is:

### PRIMARY

**Plain Python state machine**

### OPTIONAL

**LangGraph**

Reason:

- Lower complexity
- Faster implementation
- Easier debugging
- Easier for an undergraduate developer
- Fully sufficient for the required sequential agent workflow

Do not introduce LangGraph merely for the sake of using a framework.

If the implementation is already clean and working with the Python state machine,
there is no requirement to migrate it.

---

# 13. LLM Decision

Selected model:

**Qwen2.5-3B-Instruct**

Runtime:

**Ollama**

The same model can handle:

- Intent classification
- Parameter extraction
- Task decomposition
- Structured tool decisions
- Planning
- Replanning
- Final response generation

Do not introduce multiple LLM providers or expensive model APIs.

---

# 14. Hardware Context

The user's development machine is:

```text
Laptop: ASUS TUF F15
RAM: 16 GB
Storage: 1 TB
GPU: RTX 3050
GPU VRAM: 8 GB
```

This hardware is intended to run the local PlanWise stack.

The local-first architecture is therefore intentional.

---

# 15. Cost / API-Key Decision

The core project is intended to use free/open-source/local components.

No paid API keys are required for the planned implementation.

Specifically, the project does NOT require:

- OpenAI API key
- Gemini API key
- Claude API key
- Google Maps API key
- Hotel API key
- Restaurant API key
- Booking API key

The core architecture is:

```text
Qwen2.5-3B-Instruct
        ↓
      Ollama
        ↓
    Local Agent
        ↓
 Local MultiWOZ Data
        ↓
       FAISS
```

Do not introduce a paid API dependency without an explicit project decision.

---

# 16. Product Architecture Decision

The high-level architecture is:

```text
                    USER
                      ↓
                 STREAMLIT
                      ↓
             APPLICATION LAYER
                      ↓
               PLANNING AGENT
                      ↓
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
     STATE          TOOLS           LLM
       ↓              ↓              ↓
   Pydantic       Retrieval       Ollama
                      ↓              ↓
                    FAISS       Qwen2.5-3B
                      ↓
                MultiWOZ 2.2
                      ↓
               CONSTRAINT ENGINE
                      ↓
                  VERIFIER
                      ↓
                FINAL RESPONSE
                      ↓
                  STREAMLIT
```

---

# 17. Critical Architecture Principle

The most important design separation is:

```text
LLM      = Understand + Reason + Plan + Communicate

Python   = State + Tools + Rules + Validation

Data     = Grounding

FAISS    = Retrieval

Streamlit = Interaction
```

The LLM should not control the entire application.

Instead:

```text
USER
 ↓
LLM — understand
 ↓
PYTHON — control execution
 ↓
TOOLS — retrieve
 ↓
STATE — remember
 ↓
PYTHON — enforce constraints
 ↓
LLM — generate plan
 ↓
PYTHON — verify
 ↓
USER
```

---

# 18. Required Tools

The system must provide:

```python
search_hotel()
search_restaurant()
search_attraction()
search_transport()
```

The tools use local/static data.

The LLM should request tools using structured parameters.

Python validates and executes the approved tool.

The LLM must never execute arbitrary Python/code.

---

# 19. Required State

Minimum state:

```text
Location
Dates / Duration
Budget
Preferences
Chosen Options
```

Recommended internal state also includes:

```text
Current Goal
Intent
Subtasks
Tool Results
Interests
Constraints
Current Plan
Validation Results
Conversation History
```

State is required for proper multi-turn replanning.

---

# 20. Constraint Handling Decision

Constraints should be enforced programmatically wherever possible.

Important constraints:

- Budget
- Duration
- Time availability
- Preferences
- Required activities

Example:

```text
Budget = ₹2,000
Generated cost = ₹2,450

→ INVALID
```

The planner should then replan.

The LLM should not be solely responsible for arithmetic or hard constraint
validation.

---

# 21. Replanning Decision

Replanning is a core requirement.

Example:

Initial:

> "Plan a two-day trip with ₹2,000."

Follow-up:

> "Reduce the budget to ₹1,500."

The system must:

```text
Existing State
    ↓
Detect Changed Constraint
    ↓
Update Budget
    ↓
Re-evaluate affected choices
    ↓
Replan
    ↓
Validate
    ↓
Verify
    ↓
Return Updated Plan
```

It should not force the user to restart the conversation.

---

# 22. Memory Decision

The system should remember relevant preferences during the active conversation.

Examples:

- Vegetarian
- Budget
- Preferred travel time
- Interests

Example:

```text
User:
"I am vegetarian."

Later:
"Plan my second day."

→ Vegetarian preference remains available.
```

No complex long-term memory infrastructure is required.

---

# 23. Verification Decision

The final plan must be verified before being returned.

Verification should check:

- Constraint compliance
- Retrieved-data grounding
- Schedule consistency
- Required components
- Preference compliance
- Obvious contradictions

If verification fails:

```text
Candidate Plan
    ↓
Verifier
    ↓
Failure
    ↓
Replan
    ↓
Validate
    ↓
Verify Again
```

---

# 24. Hallucination-Control Decision

The system should follow:

```text
Retrieved Data
      ↓
Planning
      ↓
Validation
      ↓
Verification
      ↓
Response
```

rather than:

```text
User
 ↓
LLM
 ↓
Invented Information
```

The system should never fabricate retrieved hotel, restaurant, attraction or
transport records.

---

# 25. UI Decision

Use:

**Streamlit**

The UI should remain simple.

Required:

- Input box
- Submit action
- Conversation display
- Plan display
- Updated/replanned plan
- Constraint information
- Error/clarification messages

No React or separate frontend is required.

---

# 26. API Decision

The core stack does not require a separate HTTP server.

The logical frontend/backend API contracts were nevertheless defined so that
the system has clean boundaries and can later be exposed through FastAPI if
needed.

Primary user-facing logical endpoints:

```text
GET  /api/v1/health

POST /api/v1/sessions

GET  /api/v1/sessions/{session_id}

POST /api/v1/sessions/{session_id}/messages

GET  /api/v1/sessions/{session_id}/plan

POST /api/v1/sessions/{session_id}/replan
```

Internal logical contracts:

```text
POST /api/v1/tools/hotels/search

POST /api/v1/tools/restaurants/search

POST /api/v1/tools/attractions/search

POST /api/v1/tools/transport/search

POST /api/v1/validation/plan
```

However, with Streamlit + Python, these can remain Python service interfaces
rather than actual HTTP endpoints.

**Do not add FastAPI just to create APIs.**

If an actual REST API becomes necessary, add a thin FastAPI layer over the same
business logic.

---

# 27. Frontend → Backend Responsibility

The frontend should know only about:

```text
Session
Message
Plan
Replan
Health
```

The frontend should NOT know about:

```text
Qwen
Ollama
FAISS
MultiWOZ
Prompt engineering
Tool implementation
Constraint implementation
Agent state transitions
```

This keeps the frontend thin and the backend modular.

---

# 28. Recommended Project Structure

```text
planwise-ai/
│
├── app.py
│
├── agent/
│   ├── planner.py
│   ├── prompts.py
│   ├── state.py
│   └── schemas.py
│
├── llm/
│   └── ollama_client.py
│
├── tools/
│   ├── registry.py
│   ├── hotel.py
│   ├── restaurant.py
│   ├── attraction.py
│   └── transport.py
│
├── retrieval/
│   ├── index.py
│   ├── search.py
│   └── embeddings.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── index/
│
├── validation/
│   ├── constraints.py
│   └── verifier.py
│
├── evaluation/
│   ├── test_cases.json
│   └── evaluate.py
│
├── tests/
│   ├── test_tools.py
│   ├── test_state.py
│   ├── test_constraints.py
│   └── test_agent.py
│
├── requirements.txt
├── README.md
└── .env.example
```

This can be simplified if needed.

---

# 29. Implementation Order

Build in this order:

```text
1. Environment
2. Ollama + Qwen2.5-3B
3. MultiWOZ preprocessing
4. Local data
5. Retrieval / FAISS
6. Domain tools
7. Pydantic schemas
8. State management
9. Intent extraction
10. Task decomposition
11. Tool invocation
12. Candidate plan generation
13. Constraint engine
14. Verification
15. Replanning
16. Memory/preferences
17. Streamlit UI
18. Evaluation
19. Documentation
```

Do not spend significant time polishing the UI before the core agent works.

---

# 30. Testing Requirements

The final system must test:

### Intent recognition

```text
"Find a reasonably priced hotel."
→ hotel_search
```

### Tool selection

```text
Restaurant request
→ search_restaurant()
```

### Parameter extraction

Verify:

- Location
- Budget
- Duration
- Preferences

### State

Test multi-turn requests.

### Constraint validation

Test budget and duration conflicts.

### Replanning

Test:

```text
₹2,000 → ₹1,500
```

### Impossible constraints

Test:

```text
2 days
₹500
10 attractions
```

### Hallucination control

Verify that unavailable records are not invented.

### End-to-end flow

Test:

```text
User
→ Intent
→ Decomposition
→ Tools
→ Retrieval
→ State
→ Plan
→ Validation
→ Verification
→ Response
```

---

# 31. Definition of Done

The project is complete when the following works reliably:

```text
Understand
   ↓
Decompose
   ↓
Retrieve
   ↓
Use Tools
   ↓
Maintain State
   ↓
Check Constraints
   ↓
Generate Schedule
   ↓
Verify
   ↓
Respond
```

And:

```text
User changes requirement
   ↓
Detect change
   ↓
Update state
   ↓
Replan
   ↓
Validate
   ↓
Verify
   ↓
Updated plan
```

---

# 32. What the AI Coding Agent Must NOT Do

Do not:

- Change the project concept.
- Replace PlanWise with another project.
- Add AccessAI functionality.
- Add browser automation.
- Add computer-use agents.
- Add multimodal vision.
- Add real booking.
- Add paid APIs.
- Add unnecessary databases.
- Add microservices.
- Add Kubernetes.
- Add React.
- Add multiple LLMs.
- Add unnecessary cloud infrastructure.
- Train a large model.
- Add features simply to increase the apparent complexity.

Do not sacrifice completion speed and reliability for unnecessary sophistication.

---

# 33. What the AI Coding Agent SHOULD Do

The coding agent should:

1. Read all supplied project documents first.
2. Treat the PRD as the product scope.
3. Treat the System Architecture as the architectural source of truth.
4. Treat the Technology Stack as the technology source of truth.
5. Treat the API document as the interface-contract source of truth.
6. Inspect the actual codebase before modifying it.
7. Implement incrementally.
8. Keep modules separated.
9. Use structured Pydantic schemas.
10. Keep deterministic logic in Python.
11. Keep domain data grounded in MultiWOZ/local data.
12. Test every major component.
13. Run the complete application before declaring it complete.
14. Fix actual errors instead of working around them blindly.
15. Avoid unnecessary dependencies.
16. Keep the implementation understandable.
17. Preserve existing working code when adding new functionality.
18. Never silently change an architectural decision.

---

# 34. Current Final Decision Set

These decisions are considered FINAL unless the user explicitly changes them:

```text
PROJECT
PlanWise AI

PROJECT NUMBER
18

MODEL
Qwen2.5-3B-Instruct

LLM RUNTIME
Ollama

LANGUAGE
Python

UI
Streamlit

AGENT ORCHESTRATION
Plain Python State Machine

OPTIONAL ORCHESTRATION
LangGraph

STRUCTURED VALIDATION
Pydantic

VECTOR SEARCH
FAISS

EMBEDDINGS
Local embeddings

DATASET
MultiWOZ 2.2

DATA MODE
Local/static

TOOLS
search_hotel()
search_restaurant()
search_attraction()
search_transport()

STATE
Pydantic + Streamlit session state

TESTING
pytest

LOGGING
Python logging

VERSION CONTROL
Git + GitHub

PAID API KEYS
Not required

PRIMARY DEPLOYMENT
Local

OPTIONAL DEPLOYMENT
Cloud deployment only if desired/required

FRONTEND
Thin Streamlit layer

BACKEND
Python application/agent layer

CORE PRINCIPLE
LLM + deterministic Python + tools + state + validation
```

---

# 35. Source Documents to Be Supplied to the Agent

The agent should receive these project documents together:

```text
1. Official Project 18 specification
2. PlanWise AI PRD
3. PlanWise AI Complete System Architecture
4. PlanWise AI Technology Stack
5. PlanWise AI API-Specific Document
6. MultiWOZ 2.2 dataset
```

These documents should be treated as the project's working specification.

---

# 36. Final Understanding

The project is intentionally positioned between two extremes:

```text
Simple chatbot
      ↑
      |
  PLANWISE AI
      |
      ↓
Complex multimodal browser/computer-use agent
```

PlanWise is chosen because it provides a real agentic architecture without the
large implementation burden of browser automation, computer use, multimodal
grounding, or other advanced systems.

The objective is to build the specified system **completely and reliably,
from setup through testing and deployment**, rather than continually expanding
the scope.

---

# 37. Next Step

The next artifact to create is the **Master AI Coding-Agent Prompt**.

That prompt should instruct the coding agent to:

```text
Read all project documents
        ↓
Understand final decisions
        ↓
Inspect environment
        ↓
Inspect dataset
        ↓
Inspect existing code
        ↓
Create implementation plan
        ↓
Implement
        ↓
Run tests
        ↓
Run application
        ↓
Fix errors
        ↓
Perform end-to-end verification
        ↓
Complete the project
```

The master prompt should reference this document and the PRD, architecture,
technology-stack, and API documents as the project's source of truth.

---

# END OF PLANWISE AI PROJECT CONTEXT
