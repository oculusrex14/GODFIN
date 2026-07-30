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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **GODFIN** (7555 symbols, 15359 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/GODFIN/context` | Codebase overview, check index freshness |
| `gitnexus://repo/GODFIN/clusters` | All functional areas |
| `gitnexus://repo/GODFIN/processes` | All execution flows |
| `gitnexus://repo/GODFIN/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
