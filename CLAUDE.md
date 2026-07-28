# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GODFIN is a local-first, AI-augmented personal finance tracker for HDFC Bank users. It ingests transaction alerts from Gmail, classifies transactions using a 5-layer deterministic engine, and provides budgeting, reporting, and audit capabilities.

## Commands

### Backend (FastAPI + Python 3.9)

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Run backend server (port 5100)
uvicorn app.main:app --reload --host 0.0.0.0 --port 5100

# Run tests
pytest
```

### Frontend (Vite + React 19 + Tailwind CSS v4)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run dev server (port 5173)
npm run dev

# Build for production
npm run build

# Lint
npm run lint
```

## Architecture

### Backend Structure (`backend/app/`)

```
app/
├── main.py              # FastAPI app entry point, lifespan events
├── core/                # Core business logic and services
│   ├── config.py        # Pydantic settings (DB path, host, port)
│   ├── database.py      # SQLite engine with WAL mode, session factory
│   ├── classifier.py    # 5-layer classification engine (exact, rules, fuzzy, embedding, LLM)
│   ├── taxonomy.py      # Category/subcategory definitions
│   ├── auth.py          # PIN-based authentication
│   ├── gmail_service.py # Gmail API integration for transaction emails
│   ├── embedding_service.py # Sentence transformers for merchant matching
│   ├── llm_service.py   # Multi-provider LLM classification (OpenAI/Anthropic/Google)
│   ├── reconciliation.py # Statement reconciliation logic
│   ├── reporting.py     # PDF report generation
│   └── scheduler.py     # APScheduler for backups and recurring tasks
├── models/              # SQLAlchemy ORM models
│   ├── transaction.py, account.py, audit_session.py, merchant_memory.py
│   ├── classification_rule.py, recurring_pattern.py, monthly_aggregate.py
│   └── goal.py, income_source.py, budget.py, app_setting.py, audit_log.py
├── schemas/             # Pydantic schemas for request/response validation
└── api/v1/
    ├── router.py        # API router aggregation
    └── endpoints/       # Route handlers (transactions, accounts, dashboard, etc.)
```

### Frontend Structure (`frontend/src/`)

```
src/
├── main.jsx             # Entry point, React Query setup
├── App.jsx              # Router with protected routes
├── context/             # React contexts (Auth, Toast, Theme, Audit)
├── components/          # Reusable UI components
├── pages/               # Route pages (Dashboard, Transactions, Review, etc.)
└── assets/              # Static assets
```

### Key Architectural Patterns

1. **5-Layer Classification Engine** (`backend/app/core/classifier.py`):
   - Layer 1: Exact match from merchant_memory table
   - Layer 2: Classification rules (regex/contains patterns)
   - Layer 3: Fuzzy string matching (thefuzz)
   - Layer 4: Embedding similarity (sentence-transformers)
   - Layer 5: LLM fallback (OpenAI/Anthropic/Google with PII sanitization)

2. **Audit State Machine**: Transactions flow through states: `draft` → `finalized` → `locked`. Finalized months are immutable without explicit reopening.

3. **Database**: SQLite with WAL mode enabled, busy_timeout=5000ms, foreign_keys=ON. Use Alembic for all schema changes.

4. **API Convention**: All routes use `/api/v1/` prefix. CORS enabled for all origins (local-first app).

5. **Frontend State**: React Query for server state, custom contexts for auth/theme/audit/toast.

## Important Files

- `GODFIN_Final_Build_Specification_v1 .md` — Single source of truth for project requirements
- `Claude_Build_Plan.md` — 10-phase build strategy with skill usage guidelines
- `backend/alembic.ini` — Database migration configuration
- `backend/app/core/taxonomy.py` — Category/subcategory definitions (do not modify without spec alignment)
- `backend/app/models/` — All data models; understand relationships before modifying

## Development Notes

- The virtual environment (`backend/venv/`) is Python 3.9
- Backend runs on port 5100 (configurable via `PORT` env var)
- Frontend uses Tailwind CSS v4 with Vite plugin (no tailwind.config.js needed)
- The app uses a PIN-based auth system with persistent token storage
- LLM provider configuration is stored in the `llm_configs` table
