# GODFIN Change Log

## Phase 2.5 - Syntax Fix

**Date:** 2026-03-07
**Commit:** 3e3f5f4e

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| SYNTAX-001 | });); syntax error in GlassButton.jsx | ✅ FIXED |
| SYNTAX-002 | });); syntax error in GlassCard.jsx | ✅ FIXED |
| SYNTAX-003 | });); syntax error in GlassInput.jsx | ✅ FIXED |
| SYNTAX-004 | Missing }); and export default in StatCard.jsx | ✅ FIXED |

### Changes
- Fixed JSX syntax errors in 4 component files

---

## Phase 2 - Session 6 (P2-S6): Performance, Graph, Filter Fixes

**Date:** 2026-03-07
**Commit:** 6fac64d3

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| PERF-001 | Missing React.memo on reusable components | ✅ FIXED |
| PERF-002 | Missing useMemo in Dashboard.jsx | ✅ Already Correct |
| PERF-006 | AuthContext retry without cleanup | ✅ FIXED |
| GRAPH-001 | Y-axis doesn't use INR formatting | ✅ FIXED |
| GRAPH-005 | X-axis bar chart doesn't use INR formatting | ✅ FIXED |
| GRAPH-008 | HealthGauge null values produce NaN | ✅ Already Fixed (P2-S5) |
| FILTER-001/006 | No debouncing on search | ✅ Already Correct |

### Changes

- **frontend/src/components/GlassButton.jsx**: Added React.memo wrapper
- **frontend/src/components/GlassCard.jsx**: Added React.memo wrapper
- **frontend/src/components/GlassInput.jsx**: Added React.memo wrapper
- **frontend/src/components/GlassSelect.jsx**: Added React.memo wrapper
- **frontend/src/components/StatCard.jsx**: Added React.memo wrapper
- **frontend/src/context/AuthContext.jsx**: Added cleanup function for setTimeout on unmount
- **frontend/src/pages/Dashboard.jsx**: Added formatINRAbbreviated function for Y-axis
- **frontend/src/pages/Reports.jsx**: Added formatINRAbbreviated function for X-axis

---

## Phase 2 - Session 5 (P2-S5): Medium Priority UI Fixes

**Date:** 2026-03-07
**Commit:** f7bec96d

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| FILTER-002 | No date range validation | ✅ FIXED |
| FILTER-007 | No status filter in Review Queue | ✅ FIXED |
| GRAPH-003 | Fixed chart container sizes don't scale | ✅ Already Correct |
| GRAPH-006 | No null handling for bar chart | ✅ FIXED |
| GRAPH-008 | HealthGauge null values produce NaN | ✅ FIXED |
| UI-001 | Missing ARIA labels on interactive elements | ✅ FIXED |
| UI-005 | Native window.confirm() used | ✅ FIXED |

### Changes

- **frontend/src/components/FilterBar.jsx**: Added date range validation (date_to >= date_from) and ARIA labels
- **frontend/src/components/ConfirmDialog.jsx**: New accessible confirmation dialog component
- **frontend/src/pages/ReviewQueue.jsx**: Added type filter (debit/credit) and ARIA labels
- **frontend/src/pages/Transactions.jsx**: Replaced window.confirm with ConfirmDialog, added ARIA labels
- **frontend/src/pages/Income.jsx**: Replaced window.confirm with ConfirmDialog, added ARIA labels
- **frontend/src/pages/Reports.jsx**: Added null filtering for bar chart data
- **frontend/src/pages/Budget.jsx**: HealthGauge now handles null values gracefully

---

## Phase 2 - Session 4 (P2-S4): Feature & Integration Fixes

**Date:** 2026-03-07
**Commit:** 823de0fc

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| FEAT-001 | Transaction create doesn't invalidate dashboard query | ✅ Already Fixed |
| FEAT-009 | LLM classification timeout silently ignored | ✅ FIXED |
| FEAT-017 | Review queue not invalidated after import | ✅ FIXED |
| FEAT-023 | Profile not invalidated on goal create | ✅ FIXED |
| FEAT-030 | Period date calculation bug (off-by-one) | ✅ Already Correct |
| FEAT-037 | No file size limit on statement upload | ✅ FIXED |
| INT-001 | Query key mismatch - dashboard stale | ✅ Already Fixed |
| INT-002 | Race condition on merchant memory updates | ✅ Already Fixed |
| INT-004 | Frontend isAuditActive stale across tabs | ✅ Already Fixed |
| PERF-003 | Large transaction list without virtualization | ⚠️ Not Fixed (Low priority) |
| PERF-004 | Missing AbortController on fetch calls | ✅ Already Fixed |
| PERF-005 | setInterval not cleared on cleanup | ✅ Already Fixed |
| EDGE-001 | XSS via merchant name | ✅ Already Fixed |
| EDGE-002 | Negative amounts accepted | ✅ Already Fixed |

### Changes

- **backend/app/core/llm_providers.py**: Added timeout logging for Ollama provider
- **frontend/src/pages/Budget.jsx**: Added financialProfile invalidation on goal create
- **frontend/src/pages/Upload.jsx**: Added 10MB file size limit and reviewQueue invalidation

---

## Phase 2 - Session 3 (P2-S3): Database & API Fixes

**Date:** 2026-03-07
**Commit:** cfeff526

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| DB-002 | N+1 query pattern in dashboard | ✅ FIXED |
| DB-003 | Missing transaction decorators | ✅ FIXED |
| DB-004 | Race condition in MerchantMemory upsert | ✅ Already Fixed |
| DB-005 | Audit state machine not enforced at DB level | ✅ Already Fixed |
| DB-006 | Missing transaction on audit finalize/reopen | ✅ FIXED |
| API-002 | No rate limiting on any auth endpoints | ✅ Done in P2-S1 |
| API-004 | No OAuth state parameter (CSRF vulnerability) | ✅ Already Fixed |
| API-005 | Tokens stored in plain text in database | ✅ Done in P2-S1 |
| API-006 | No token expiration implemented | ✅ Done in P2-S1 |
| API-007 | No OAuth PKCE implementation | ✅ FIXED |
| API-008 | File validation by extension only | ✅ Already Fixed |
| API-009 | Soft delete doesn't cascade to related tables | ✅ Already Fixed |
| API-010 | N+1 query in dashboard spending_trend | ✅ FIXED (same as DB-002) |
| API-011 | Race condition in MerchantMemory upsert | ✅ Already Fixed |
| API-014 | Missing audit logging on write operations | ✅ Already Fixed |
| API-015 | No PIN history/reuse prevention | ✅ Already Fixed |

### Changes

- **backend/app/api/v1/endpoints/dashboard.py**: Fixed N+1 query in spending_trend by using GROUP BY
- **backend/app/api/v1/endpoints/review.py**: Added transaction decorators to batch_resolve
- **backend/app/api/v1/endpoints/audit.py**: Added rollback handling to finalize/discard/reopen endpoints
- **backend/app/core/gmail_service.py**: Added PKCE support for OAuth flow
- **backend/app/api/v1/endpoints/transactions.py**: Added audit logging for updates and cascade delete for splits
- **backend/app/api/v1/endpoints/auth.py**: Added PIN history tracking and reuse prevention

---

## Phase 2 - Session 2 (P2-S2): Critical Crash & Data Fixes

**Date:** 2026-03-07
**Commit:** a212741a

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| INT-003 | audit lock date range Timezone mismatch on | N/A - Already using correct date logic |
| INT-009 | Email parsing silently fails without logging | ✅ FIXED |
| INT-011 | Network errors not handled consistently | ✅ FIXED |
| INT-013 | No classification cache invalidation | N/A - No cache exists |
| DB-001 | Unencrypted sensitive credentials in LLMConfiguration | ✅ FIXED in P2-S1 |
| API-001 | No PIN format validation | ✅ FIXED |
| API-003 | Open redirect in OAuth callback | ✅ FIXED |

### Changes

- **backend/app/api/v1/endpoints/auth.py**: Added PIN format validation (length 4-8 digits, weak PIN rejection)
- **backend/app/api/v1/endpoints/gmail.py**: Added open redirect protection in OAuth callback
- **backend/app/core/email_parser.py**: Added logging import
- **backend/app/core/ingestion.py**: Added comprehensive error logging for failed email parsing
- **frontend/src/api/client.js**: Added try-catch for network errors in fetch calls

---

## Phase 2 - Session 1 (P2-S1): Critical Security Fixes

**Date:** 2026-03-07
**Commit:** 5038bdd7 (security fixes applied), bf08f417 (individual fixes)

### Bugs Fixed

| Bug ID | Description | Status |
|--------|-------------|--------|
| SEC-001 | LLM API keys stored in plaintext | ✅ FIXED |
| SEC-002 | Gmail OAuth tokens stored unencrypted | ✅ FIXED |
| SEC-003 | Authentication tokens never expire | ✅ FIXED |
| SEC-006 | No session invalidation on logout | ✅ FIXED |
| SEC-007 | No rate limiting on PIN verification | ✅ FIXED |
| SEC-010 | CORS allows all origins | ✅ FIXED |
| SEC-011 | PIN hash exposed via settings endpoint | ✅ FIXED |
| SEC-014 | Gmail client secrets in repo | ✅ FIXED |
