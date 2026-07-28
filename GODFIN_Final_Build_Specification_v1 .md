# GODFIN — Final Build Specification v1.0
## Single Source of Truth for Claude Code Execution

**Date:** 2026-02-27  
**Target Builder:** Claude Code (Opus 4.6) via Anthropic Pro Plan  
**Target User:** Single user, HDFC Bank (Savings + HDFC Credit Card), macOS M4
**Total Resolved Issues:** 50 (from 5 model critiques + user Q&A)

---

# PART 1: SYSTEM OVERVIEW

## 1.1 What GODFIN Is

A local-first, AI-augmented personal finance tracker that:
- Ingests transaction alerts from Gmail (HDFC Bank)
- Classifies transactions using a 5-layer deterministic-first engine
- Detects recurring payments and subscriptions
- Provides budget planning with goal simulation
- Computes financial health metrics
- Generates PDF reports with charts and AI commentary
- Learns from user corrections to improve over time

## 1.2 Architecture

```
Electron / Browser (Vite + React 19 + Tailwind v4)
        ↓ HTTP
FastAPI Backend (127.0.0.1:5100)
        ↓
SQLite Database (WAL mode)
        ↓
Gmail API (OAuth, read + optional user-authorized send)
        ↓
Optional Local Embedding Model (FastEmbed, downloaded on demand)
        ↓
BYO LLM provider key (fallback classification + report commentary)
```

## 1.3 Access Model

- Backend: `http://127.0.0.1:5100` by default
- Frontend: `http://127.0.0.1:5200`
- Phone access is off by default. The explicit **Allow network access** setting
  binds both services to the local network; phone access then uses
  `http://{mac-ip}:5200` on the same trusted Wi-Fi.
- PIN/password gate on app launch
- All API routes: `/api/v1/` prefix

## 1.4 Accounts

| Account | Type | Last 4 | Email Sender |
|---|---|---|---|
| HDFC Savings | Savings/UPI | 0000 | `alerts@hdfcbank.net` |
| HDFC Credit Card | Credit Card | 0001 | `alerts@hdfcbank.bank.in` |

---

# PART 1.5: AUDIT-FIRST FINANCIAL INTEGRITY PHILOSOPHY

GODFIN is built on an audit-first integrity model. Financial data does not silently mutate.

**Core Principles:**

1. **No silent retroactive mutations.** Edits during review do not immediately rewrite historical aggregates. The user controls when financial history becomes permanent.

2. **User-controlled finalization.** Each month has a lifecycle: `draft → finalized`. Only after the user clicks "Finalize Audit" are monthly aggregates computed and locked. Until then, the month is "provisional" — editable, re-classifiable, and explicitly marked as uncommitted.

3. **Trend stability.** Once finalized, a month's aggregates are immutable. This prevents historical trends from drifting due to later reclassification. Year-over-year comparisons are reliable because finalized data does not change.

4. **Hard delete allowed, with guardrails.** Transactions can be deleted from non-finalized months freely. For finalized months, the user must explicitly "Reopen Audit" first, which creates a new draft session and unlocks the period.

5. **This is not SaaS accounting software.** No double-entry, no journal systems, no distributed locking. This is a single-machine, single-user personal integrity mechanism. The audit model exists to protect you from your own future reclassifications corrupting past data — not to comply with GAAP.

**State Machine:**

```
Month Lifecycle:
  
  [No Audit]  →  User clicks "Start Audit"  →  [Draft]
                                                   │
                                    User reviews / edits / splits
                                                   │
                               User clicks "Finalize Audit"  →  [Finalized]
                                                                    │
                                              User clicks "Reopen"  →  [New Draft]
                                                                           │
                                                           Finalize again  →  [Finalized]
  
  [No Audit]: Transactions are editable. Aggregates are provisional (recomputed live).
  [Draft]:    Edits tied to audit session. Aggregates NOT updated yet.
  [Finalized]: Transactions locked. Aggregates frozen. Month is read-only.
```

---

# PART 2: COMPLETE DATA MODEL

## 2.1 accounts
```sql
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,  -- UUID
    bank TEXT NOT NULL DEFAULT 'HDFC',
    account_type TEXT NOT NULL,  -- 'savings' | 'credit_card'
    last_4_digits TEXT NOT NULL,
    nickname TEXT,  -- e.g., "Swiggy Card"
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data:
-- ('uuid1', 'HDFC', 'savings', '0000', 'HDFC Savings', TRUE)
-- ('uuid2', 'HDFC', 'credit_card', '0001', 'HDFC Credit Card', TRUE)
```

## 2.2 transactions
```sql
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,  -- UUID
    date DATE NOT NULL,
    time TIME,
    raw_text TEXT NOT NULL,  -- Original email body (never modified)
    merchant_raw TEXT,  -- Exactly as parsed from email
    merchant_normalized TEXT,  -- After normalization pipeline
    amount REAL NOT NULL,
    type TEXT NOT NULL,  -- 'debit' | 'credit'
    instrument TEXT NOT NULL,  -- 'upi' | 'credit_card' | 'debit_card' | 'neft' | 'auto_debit' | 'manual'
    account_id TEXT NOT NULL REFERENCES accounts(id),
    category TEXT,
    subcategory TEXT,
    confidence REAL,  -- 0.0 to 1.0
    classification_source TEXT,  -- 'exact_match' | 'regex' | 'fuzzy' | 'embedding' | 'llm' | 'user'
    status TEXT DEFAULT 'settled',  -- 'pending' | 'settled' | 'failed' | 'reversed'
    is_transfer BOOLEAN DEFAULT FALSE,
    is_recurring BOOLEAN DEFAULT FALSE,
    recurring_type TEXT,  -- 'fixed' | 'variable' | 'quarterly' | 'annual'
    is_split BOOLEAN DEFAULT FALSE,
    is_income BOOLEAN DEFAULT FALSE,
    source TEXT NOT NULL,  -- 'gmail' | 'statement_upload' | 'manual'
    vpa_handle TEXT,  -- For UPI transactions
    upi_ref_number TEXT,
    email_message_id TEXT,  -- Gmail message ID for dedup
    checksum_source TEXT,  -- hash(raw_text + source) for same-source dedup
    checksum_canonical TEXT,  -- hash(date + amount + merchant_normalized + instrument + account_id)
    reconciled BOOLEAN DEFAULT FALSE,
    tags TEXT,  -- JSON array of tag strings
    notes TEXT,
    classification_version INTEGER DEFAULT 1,
    audit_session_id TEXT REFERENCES audit_sessions(id),  -- NULL if no audit in progress
    is_locked BOOLEAN DEFAULT FALSE,  -- TRUE after month is finalized
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.3 transaction_splits
```sql
CREATE TABLE transaction_splits (
    id TEXT PRIMARY KEY,
    parent_transaction_id TEXT NOT NULL REFERENCES transactions(id),
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Constraint: SUM(splits.amount) must equal parent.amount
```

## 2.4 merchant_memory
```sql
CREATE TABLE merchant_memory (
    id TEXT PRIMARY KEY,
    raw_string TEXT NOT NULL,  -- Original merchant text
    normalized_name TEXT NOT NULL UNIQUE,
    display_name TEXT,  -- Human-friendly name (e.g., "Swiggy" instead of "PYU*Swiggy Food")
    category TEXT NOT NULL,
    subcategory TEXT,
    embedding_vector BLOB,  -- numpy-serialized 384-dim float32 array
    embedding_model_version TEXT DEFAULT 'all-MiniLM-L6-v2',
    avg_confidence REAL DEFAULT 1.0,
    times_seen INTEGER DEFAULT 1,
    is_person BOOLEAN DEFAULT FALSE,  -- For P2P UPI
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.5 monthly_aggregates
```sql
CREATE TABLE monthly_aggregates (
    id TEXT PRIMARY KEY,
    month TEXT NOT NULL,  -- 'YYYY-MM'
    account_id TEXT REFERENCES accounts(id),  -- NULL = all accounts
    total_spend REAL DEFAULT 0,
    total_income REAL DEFAULT 0,
    savings_rate REAL,  -- (income - spend) / income * 100
    fixed_total REAL DEFAULT 0,
    semi_flexible_total REAL DEFAULT 0,
    flexible_total REAL DEFAULT 0,
    transfer_total REAL DEFAULT 0,  -- excluded from spend
    recurring_total REAL DEFAULT 0,
    category_breakdown TEXT,  -- JSON: {"FOOD & DINING": 5400, ...}
    transaction_count INTEGER DEFAULT 0,
    is_finalized BOOLEAN DEFAULT FALSE,  -- TRUE after audit finalization
    audit_session_id TEXT REFERENCES audit_sessions(id),  -- Which audit session finalized this
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Aggregation Integrity Rules:**
- **Finalized months:** Aggregates are frozen. They are ONLY recomputed if the audit is explicitly reopened and re-finalized.
- **Current / non-finalized months:** Aggregates are "provisional" — recomputed live on each dashboard load. Displayed with a visual indicator (e.g., dotted border, "provisional" badge).
- **Trend charts and YoY comparisons** use only finalized months. Provisional data is shown separately and clearly labeled.
- **Hard delete** of transactions is allowed in non-finalized months. For finalized months, user must first "Reopen Audit" to unlock.
```

## 2.6 income_sources
```sql
CREATE TABLE income_sources (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,  -- e.g., "Salary", "Freelance"
    expected_amount REAL,
    frequency TEXT DEFAULT 'monthly',  -- 'monthly' | 'biweekly' | 'irregular'
    last_detected_date DATE,
    last_detected_amount REAL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.7 classification_rules
```sql
CREATE TABLE classification_rules (
    id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL,  -- 'exact' | 'regex' | 'contains'
    pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    priority INTEGER DEFAULT 100,  -- Lower = higher priority
    is_system BOOLEAN DEFAULT TRUE,  -- FALSE for user-created rules
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.8 goals
```sql
CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    current_saved REAL DEFAULT 0,
    deadline_date DATE NOT NULL,
    pressure_level TEXT DEFAULT 'moderate',  -- 'minimal' | 'moderate' | 'aggressive'
    annual_return_rate REAL DEFAULT 0.035,  -- 3.5% savings account
    minimum_flexible_floor REAL DEFAULT 5000,  -- Never reduce flexible below this
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.9 recurring_patterns
```sql
CREATE TABLE recurring_patterns (
    id TEXT PRIMARY KEY,
    merchant_normalized TEXT NOT NULL,
    account_id TEXT REFERENCES accounts(id),
    avg_amount REAL NOT NULL,
    amount_stddev REAL,
    frequency TEXT NOT NULL,  -- 'monthly' | 'quarterly' | 'annual'
    avg_interval_days INTEGER,
    last_occurrence DATE,
    next_expected DATE,
    times_detected INTEGER DEFAULT 2,
    category TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.10 app_settings
```sql
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Required keys:
-- 'user_timezone' → 'Asia/Kolkata'
-- 'last_gmail_history_id' → '{historyId}'
-- 'last_ingestion_run' → ISO timestamp
-- 'pin_hash' → bcrypt hash of user PIN
-- 'is_first_run' → 'true'
-- 'polling_interval_minutes' → '15'
-- 'nightly_batch_hour' → '23'
-- 'nightly_batch_minute' → '59'
```

## 2.11 audit_sessions
```sql
CREATE TABLE audit_sessions (
    id TEXT PRIMARY KEY,  -- UUID
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,  -- 1-12
    status TEXT NOT NULL DEFAULT 'draft',  -- 'draft' | 'finalized' | 'discarded'
    change_summary TEXT,  -- JSON: {"reclassified": 3, "deleted": 1, "split": 0}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP  -- Set when status → finalized
);

-- Constraints:
-- Only ONE draft audit per (year, month) allowed.
-- Once status = 'finalized' → row is immutable.
-- UNIQUE(period_year, period_month) WHERE status = 'draft'  (enforced in app logic)
```

**Audit Session Behavior:**
- `Start Audit` → creates a draft session for the target month.
- During draft: all edits (reclassify, split, delete) to that month's transactions set `audit_session_id` to the draft session ID.
- `Finalize Audit` → recalculates monthly aggregates for that period, sets `is_locked = True` on all transactions in that month, sets session status to `finalized`.
- `Discard Audit` → reverts all changes made during the session (using audit_log to rollback), sets status to `discarded`.
- `Reopen Audit` on a finalized month → creates a NEW draft session, sets `is_locked = False` on that month's transactions.
- Only one draft session can exist at a time across all months.

## 2.12 audit_log
```sql
CREATE TABLE audit_log (
    id TEXT PRIMARY KEY,
    transaction_id TEXT REFERENCES transactions(id),
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_source TEXT,  -- 'user' | 'system' | 'reconciliation'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 2.13 system_log
```sql
CREATE TABLE system_log (
    id TEXT PRIMARY KEY,
    level TEXT NOT NULL,  -- 'INFO' | 'WARN' | 'ERROR'
    component TEXT NOT NULL,  -- 'ingestion' | 'classification' | 'recurring' | 'llm' | 'scheduler'
    message TEXT NOT NULL,
    details TEXT,  -- JSON with extra context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

# PART 3: CATEGORY TAXONOMY (Configuration File)

Store as `backend/app/core/taxonomy.py`:

```python
TAXONOMY = {
    "HOUSING": {
        "elasticity": "fixed",
        "subcategories": ["Rent", "Maintenance/Society", "Home Repairs"],
        "confidence_threshold": 0.85
    },
    "TRANSPORTATION": {
        "elasticity": "semi_flexible",
        "subcategories": ["Fuel", "Public Transit", "Ride Hailing", "Parking/Tolls"],
        "confidence_threshold": 0.85
    },
    "FOOD & DINING": {
        "elasticity": "flexible",
        "subcategories": ["Groceries", "Food Delivery", "Restaurants", "Coffee/Snacks"],
        "confidence_threshold": 0.85
    },
    "UTILITIES & BILLS": {
        "elasticity": "semi_flexible",
        "subcategories": ["Electricity", "Water", "Internet/Phone", "Gas"],
        "confidence_threshold": 0.85
    },
    "FINANCIAL OBLIGATIONS": {
        "elasticity": "fixed",
        "subcategories": ["EMI - Loan", "EMI - Credit Card", "Insurance Premium", "SIP/Investment"],
        "confidence_threshold": 0.95  # High threshold — mistakes here are costly
    },
    "HEALTH & WELLNESS": {
        "elasticity": "semi_flexible",
        "subcategories": ["Medical/Pharmacy", "Gym/Fitness", "Personal Care"],
        "confidence_threshold": 0.85
    },
    "SHOPPING": {
        "elasticity": "flexible",
        "subcategories": ["Clothing", "Electronics", "Home/Kitchen", "General"],
        "confidence_threshold": 0.85
    },
    "ENTERTAINMENT": {
        "elasticity": "flexible",
        "subcategories": ["Subscriptions", "Movies/Events", "Gaming"],
        "confidence_threshold": 0.85
    },
    "EDUCATION": {
        "elasticity": "semi_flexible",
        "subcategories": ["Courses/Books", "Software/Tools"],
        "confidence_threshold": 0.85
    },
    "TRANSFERS": {
        "elasticity": "none",
        "subcategories": ["Credit Card Payment", "Own Account Transfer", "Investment Transfer"],
        "confidence_threshold": 0.95,  # Misclassifying a transfer is critical
        "exclude_from_spend": True
    },
    "INCOME": {
        "elasticity": "none",
        "subcategories": ["Salary", "Freelance", "Refund", "Cashback", "Interest", "Other Income"],
        "confidence_threshold": 0.90,
        "is_income": True
    },
    "MISCELLANEOUS": {
        "elasticity": "flexible",
        "subcategories": ["Personal", "Gifts", "Donations", "Other"],
        "confidence_threshold": 0.80
    }
}
```

---

# PART 4: EMAIL PARSER SPECIFICATIONS

## 4.1 Sender Whitelist

```python
SENDER_WHITELIST = {
    "alerts@hdfcbank.net": "hdfc_savings",      # UPI/Savings alerts
    "alerts@hdfcbank.bank.in": "hdfc_credit",    # Credit card alerts
}

SENDER_BLACKLIST_SUBJECTS = [
    "Missed Call from your HDFC",
    "Relationship Manager",
    "Your OTP",
    "Welcome to HDFC",
    "eStatement",       # Statement delivery emails (we handle PDFs separately)
    "SmartStatement",   # Link-only statements
    "e-mandate",
]
```

## 4.2 UPI Debit Parser (Savings Account)

**Sender:** `alerts@hdfcbank.net`  
**Subject:** `❗ You have done a UPI txn. Check details!` (or similar)  
**Account:** Savings ending 0000

**Body pattern:**
```
Dear Customer, Rs.{amount} has been debited from account {account_last4} to VPA 
{vpa_handle} {merchant_name} on {date_DD-MM-YY}. Your UPI transaction reference 
number is {ref_number}. If you did not authorize this transaction...
```

**Regex:**
```python
UPI_DEBIT_PATTERN = re.compile(
    r'Rs\.(?P<amount>[\d,]+\.\d{2})\s+has been debited from account\s+'
    r'(?P<account>\d{4})\s+to VPA\s+'
    r'(?P<vpa>\S+)\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{2}-\d{2}-\d{2,4})\.\s+'
    r'Your UPI transaction reference number is\s+'
    r'(?P<ref>\d+)',
    re.DOTALL | re.IGNORECASE
)
```

**Extracted fields:**
- `amount` → parse float (remove commas)
- `account_last4` → "0000" → map to savings account
- `vpa_handle` → e.g., `playo.easebuzz@ypbiz`
- `merchant_name` → e.g., `PLAYO` or `RANGANATHA K`
- `date` → parse DD-MM-YY
- `ref_number` → UPI reference (used for dedup)
- `instrument` → `"upi"`
- `type` → `"debit"`

**P2P Detection:** If VPA matches pattern `\d{10}@(ybl|paytm|okaxis|okicici|apl)`, flag as P2P (person-to-person). Set `is_person = True` in merchant_memory.

## 4.3 Credit Card Debit Parser

**Sender:** `alerts@hdfcbank.bank.in`  
**Subject:** `Rs.{amount} debited via Credit Card **{last4}`  
**Account:** Credit card ending 0001

**Body pattern:**
```
Rs.{amount} is debited from your HDFC Bank Credit Card ending {last4} towards 
{merchant} on {date}, {year} at {time}.
```

**Regex:**
```python
CC_DEBIT_PATTERN = re.compile(
    r'Rs\.(?P<amount>[\d,]+\.\d{2})\s+is debited from your HDFC Bank\s+'
    r'Credit Card ending\s+(?P<card_last4>\d{4})\s+towards\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{1,2}\s+\w+,?\s+\d{4})\s+at\s+'
    r'(?P<time>[\d:]+)',
    re.DOTALL | re.IGNORECASE
)
```

**Extracted fields:**
- `amount` → parse float
- `card_last4` → "0001" → map to credit card account
- `merchant_raw` → e.g., `PYU*Swiggy Food` or `AMAZON PAY INDIA PRIVA`
- `date` → parse "25 Feb, 2026"
- `time` → "20:09:15"
- `instrument` → `"credit_card"`
- `type` → `"debit"`

## 4.4 Merchant Normalization Pipeline

```python
def normalize_merchant(raw: str) -> str:
    text = raw.strip()
    text = unicodedata.normalize('NFKC', text)
    text = text.upper()
    
    # Strip payment gateway prefixes
    GATEWAY_PREFIXES = ['PYU*', 'PAY*', 'PP*', 'SQ*', 'GOOGLE *', 'AMZN*']
    for prefix in GATEWAY_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
    
    # Strip corporate suffixes
    CORPORATE_SUFFIXES = [
        ' PVT LTD', ' PRIVATE LIMITED', ' PRIVATE LTD', ' LIMITED', ' LTD',
        ' INDIA', ' PRIVA', ' INC', ' LLC', ' P '
    ]
    for suffix in CORPORATE_SUFFIXES:
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    
    # Strip trailing location info (common in CC alerts)
    text = re.sub(r'\s+(BANGALORE|BENGALURU|MUMBAI|DELHI|CHENNAI|INDIA|IN)\s*$', '', text)
    
    text = text.strip()
    return text
```

## 4.5 Seed Merchant Alias Table

```python
MERCHANT_ALIASES = {
    "BUNDL TECHNOLOGIES": "Swiggy",
    "SWIGGY FOOD": "Swiggy",
    "SWIGGY INSTAMART": "Swiggy Instamart",
    "ZOMATO ZOMATO": "Zomato",
    "ZOMATO": "Zomato",
    "AMAZON PAY INDIA": "Amazon",
    "AMAZON": "Amazon",
    "GOOGLE YOUTUBEPRE": "YouTube Premium",
    "GOOGLE YOUTUBE": "YouTube Premium",
    "IRCTC WEB": "IRCTC",
    "UBER INDIA": "Uber",
    "OLA": "Ola",
    "RAPIDO": "Rapido",
    "FLIPKART": "Flipkart",
    "MYNTRA": "Myntra",
    "BIGBASKET": "BigBasket",
    "BLINKIT": "Blinkit",
    "NETFLIX": "Netflix",
    "SPOTIFY": "Spotify",
    "HOTSTAR": "Hotstar",
    "PLAYO": "Playo",
    # Add more as discovered
}

# Default category mappings for known merchants
MERCHANT_CATEGORIES = {
    "Swiggy": ("FOOD & DINING", "Food Delivery"),
    "Swiggy Instamart": ("FOOD & DINING", "Groceries"),
    "Zomato": ("FOOD & DINING", "Food Delivery"),
    "Amazon": ("SHOPPING", "General"),
    "YouTube Premium": ("ENTERTAINMENT", "Subscriptions"),
    "Netflix": ("ENTERTAINMENT", "Subscriptions"),
    "Spotify": ("ENTERTAINMENT", "Subscriptions"),
    "IRCTC": ("TRANSPORTATION", "Public Transit"),
    "Uber": ("TRANSPORTATION", "Ride Hailing"),
    "Ola": ("TRANSPORTATION", "Ride Hailing"),
    "Playo": ("HEALTH & WELLNESS", "Gym/Fitness"),
    # Add more as discovered
}
```

---

# PART 5: CLASSIFICATION PIPELINE

## 5.1 Five-Layer Priority System

```
Input: (merchant_raw, amount, instrument, account_id)
           ↓
Layer 1: Exact Match (merchant_memory table)
  → Hit? Return (category, confidence=1.0, source='exact_match')
           ↓
Layer 2: Classification Rules (regex/contains patterns)
  → Hit? Return (category, confidence=0.95, source='regex')
           ↓
Layer 3: Fuzzy String Match (against merchant_memory, threshold=85%)
  → Hit? Return (category, confidence=0.85 * match_ratio, source='fuzzy')
           ↓
Layer 4: Embedding Similarity (cosine similarity, threshold=0.80)
  → Hit? Return (category, confidence=similarity_score * 0.90, source='embedding')
           ↓
Layer 5: LLM Fallback
  → Return (category, confidence=llm_confidence * 0.85, source='llm')
  → On LLM failure: Return (None, 0.0, 'unclassified') → Review Queue
```

## 5.2 Confidence Thresholds (Per-Category)

```python
def should_auto_accept(category: str, confidence: float) -> bool:
    threshold = TAXONOMY[category].get("confidence_threshold", 0.85)
    return confidence >= threshold

def get_review_status(category: str, confidence: float) -> str:
    threshold = TAXONOMY[category].get("confidence_threshold", 0.85)
    if confidence >= threshold:
        return "auto_accepted"
    elif confidence >= 0.60:
        return "soft_flagged"  # Shown in dashboard, not in review queue
    else:
        return "needs_review"  # Goes to review queue
```

## 5.3 Transfer Detection Heuristics

```python
TRANSFER_KEYWORDS = [
    'HDFC CREDIT CARD', 'CREDIT CARD PAYMENT', 'CRED', 'BILLDESK',
    'HDFC BANK', 'NEFT SELF', 'SELF TRANSFER', 'OWN ACCOUNT',
    'CREDIT CARD BILL'
]

def detect_transfer(transaction) -> bool:
    merchant = transaction.merchant_normalized.upper()
    
    # Keyword match
    for keyword in TRANSFER_KEYWORDS:
        if keyword in merchant:
            return True
    
    # Amount-based heuristic for CC bill payment:
    # Large round-number debit from savings to CC-related merchant
    if (transaction.account_type == 'savings' and 
        transaction.amount >= 1000 and
        any(kw in merchant for kw in ['HDFC', 'CREDIT', 'CRED', 'BILL'])):
        return True
    
    return False
```

## 5.4 LLM Classification Prompt

```python
LLM_CLASSIFICATION_PROMPT = """You are a financial transaction classifier for an Indian user.

Given a transaction, classify it into EXACTLY one category and subcategory from the list below.

CATEGORIES AND SUBCATEGORIES:
{taxonomy_list}

TRANSACTION:
- Merchant: {merchant_name}
- Amount: ₹{amount}
- Payment Method: {instrument}

Respond with ONLY this JSON format, no other text:
{{"category": "...", "subcategory": "...", "confidence": 0.0-1.0}}

Rules:
- You MUST select from the provided categories and subcategories ONLY
- confidence should reflect how certain you are (0.5 = guess, 0.9 = very sure)
- If you cannot determine the category, use "MISCELLANEOUS" / "Other"
"""
```

**Backend validation:** After LLM response, validate category/subcategory against taxonomy. If invalid → reject → review queue.

---

# PART 6: FINANCIAL FORMULAS

## 6.1 Goal Calculator (Future Value of Annuity)

```python
def calculate_required_monthly_saving(
    goal_amount: float,
    current_saved: float,
    deadline_months: int,
    annual_return_rate: float = 0.035,
    pressure_level: str = 'moderate',
    avg_flexible_spend: float = None,
    minimum_floor: float = 5000
) -> dict:
    remaining = goal_amount - current_saved
    monthly_rate = annual_return_rate / 12
    
    # Future Value of Annuity formula
    if monthly_rate > 0 and deadline_months > 0:
        required_monthly = remaining * monthly_rate / (
            (1 + monthly_rate) ** deadline_months - 1
        )
    else:
        required_monthly = remaining / max(deadline_months, 1)
    
    # Pressure level determines max reduction
    pressure_map = {'minimal': 0.40, 'moderate': 0.60, 'aggressive': 0.80}
    max_reduction_pct = pressure_map.get(pressure_level, 0.60)
    
    # Feasibility check
    if avg_flexible_spend:
        max_saveable = avg_flexible_spend * max_reduction_pct
        # Enforce minimum floor
        max_saveable = min(max_saveable, avg_flexible_spend - minimum_floor)
        max_saveable = max(max_saveable, 0)
        
        feasible = required_monthly <= max_saveable
        reduction_pct = (required_monthly / avg_flexible_spend) * 100 if avg_flexible_spend > 0 else 0
        
        if not feasible:
            # Calculate extended deadline
            if max_saveable > 0 and monthly_rate > 0:
                import math
                extended_months = math.ceil(
                    math.log(1 + remaining * monthly_rate / max_saveable) / 
                    math.log(1 + monthly_rate)
                )
            else:
                extended_months = math.ceil(remaining / max(max_saveable, 1))
        else:
            extended_months = None
    else:
        feasible = True
        reduction_pct = 0
        extended_months = None
    
    return {
        "required_monthly": round(required_monthly, 2),
        "feasible": feasible,
        "reduction_percent": round(reduction_pct, 1),
        "suggested_extended_months": extended_months,
        "remaining_amount": round(remaining, 2)
    }
```

## 6.2 Financial Profile Metrics

```python
def compute_impulse_index(transactions: list, flexible_categories: list) -> float:
    """Measures frequency of small, unplanned discretionary transactions (0-100)"""
    flexible_txns = [t for t in transactions if t.category in flexible_categories]
    if not flexible_txns:
        return 0.0
    
    median_amount = statistics.median([t.amount for t in flexible_txns])
    
    impulse_txns = [t for t in flexible_txns 
                    if t.amount < median_amount 
                    and t.date.weekday() < 5  # Weekday
                    and 10 <= t.time.hour <= 16]  # Work hours
    
    return round((len(impulse_txns) / len(flexible_txns)) * 100, 1)


def compute_lifestyle_inflation(current_month_flexible: float, 
                                 trailing_6m_avg: float) -> float:
    """Month-over-month flexible spend change vs 6-month average (%)"""
    if trailing_6m_avg <= 0:
        return 0.0
    return round(((current_month_flexible / trailing_6m_avg) - 1) * 100, 1)


def compute_fixed_expense_ratio(total_fixed: float, total_income: float) -> float:
    """Fixed expenses as percentage of income. Healthy: <50%, Warning: 50-70%, Critical: >70%"""
    if total_income <= 0:
        return 0.0
    return round((total_fixed / total_income) * 100, 1)


def compute_recurring_burden(all_recurring_debits: float, total_income: float) -> float:
    """All recurring debits as percentage of income"""
    if total_income <= 0:
        return 0.0
    return round((all_recurring_debits / total_income) * 100, 1)


def compute_subscription_dependency(annual_sub_total: float, 
                                     annual_flexible_total: float) -> float:
    """Subscription spending as percentage of all flexible spending"""
    if annual_flexible_total <= 0:
        return 0.0
    return round((annual_sub_total / annual_flexible_total) * 100, 1)


def compute_savings_rate(total_income: float, total_spend: float) -> float:
    """Savings as percentage of income"""
    if total_income <= 0:
        return 0.0
    return round(((total_income - total_spend) / total_income) * 100, 1)
```

## 6.3 Recurring Detection Algorithm

```python
def detect_recurring_patterns(transactions: list, lookback_days: int = 365) -> list:
    """
    Group by merchant_normalized, find patterns.
    Returns list of RecurringPattern objects.
    """
    from collections import defaultdict
    import statistics
    
    # Group transactions by merchant
    merchant_groups = defaultdict(list)
    for t in transactions:
        if t.type == 'debit' and not t.is_transfer:
            merchant_groups[t.merchant_normalized].append(t)
    
    patterns = []
    for merchant, txns in merchant_groups.items():
        if len(txns) < 2:
            continue
        
        txns.sort(key=lambda t: t.date)
        amounts = [t.amount for t in txns]
        
        # Calculate intervals between consecutive transactions
        intervals = []
        for i in range(1, len(txns)):
            gap = (txns[i].date - txns[i-1].date).days
            intervals.append(gap)
        
        if not intervals:
            continue
        
        avg_interval = statistics.mean(intervals)
        avg_amount = statistics.mean(amounts)
        amount_stddev = statistics.stdev(amounts) if len(amounts) > 1 else 0
        
        # Monthly fixed: 28-31 day interval, ±5% amount
        if 28 <= avg_interval <= 31:
            amount_cv = amount_stddev / avg_amount if avg_amount > 0 else 0
            if amount_cv <= 0.05:
                patterns.append(RecurringPattern(
                    merchant=merchant, frequency='monthly', type='fixed',
                    avg_amount=avg_amount, stddev=amount_stddev,
                    avg_interval=avg_interval
                ))
            elif amount_cv <= 0.50:
                patterns.append(RecurringPattern(
                    merchant=merchant, frequency='monthly', type='variable',
                    avg_amount=avg_amount, stddev=amount_stddev,
                    avg_interval=avg_interval
                ))
        
        # Quarterly: 85-95 day interval
        elif 85 <= avg_interval <= 95:
            patterns.append(RecurringPattern(
                merchant=merchant, frequency='quarterly', type='fixed',
                avg_amount=avg_amount, stddev=amount_stddev,
                avg_interval=avg_interval
            ))
        
        # Annual: 360-370 day interval
        elif 360 <= avg_interval <= 370:
            patterns.append(RecurringPattern(
                merchant=merchant, frequency='annual', type='fixed',
                avg_amount=avg_amount, stddev=amount_stddev,
                avg_interval=avg_interval
            ))
    
    return patterns
```

## 6.4 Statement Reconciliation Algorithm

```python
def reconcile_statement(statement_txns: list, existing_txns: list) -> dict:
    """
    Match statement lines against existing email-ingested transactions.
    Returns: {matched: [...], possible: [...], new: [...]}
    """
    from thefuzz import fuzz
    
    results = {"matched": [], "possible": [], "new": []}
    used_existing = set()
    
    for stmt_txn in statement_txns:
        best_match = None
        best_score = 0
        
        for existing in existing_txns:
            if existing.id in used_existing:
                continue
            
            date_diff = abs((stmt_txn.date - existing.date).days)
            amount_match = abs(stmt_txn.amount - existing.amount) < 0.01
            
            if date_diff <= 2 and amount_match:
                merchant_score = fuzz.ratio(
                    stmt_txn.merchant_normalized, 
                    existing.merchant_normalized
                )
                
                if merchant_score > best_score:
                    best_match = existing
                    best_score = merchant_score
        
        if best_match and best_score >= 70:
            results["matched"].append((stmt_txn, best_match))
            used_existing.add(best_match.id)
        elif best_match and best_score >= 40:
            results["possible"].append((stmt_txn, best_match))
            used_existing.add(best_match.id)
        else:
            results["new"].append(stmt_txn)
    
    return results
```

---

# PART 7: API ENDPOINTS

All routes prefixed with `/api/v1/`.

## 7.1 Authentication
```
POST   /api/v1/auth/verify-pin       → Verify PIN, return session token
POST   /api/v1/auth/set-pin          → Set/change PIN (first run)
```

## 7.2 Transactions
```
GET    /api/v1/transactions           → List (with filters: date range, category, account, search)
GET    /api/v1/transactions/{id}      → Detail
POST   /api/v1/transactions           → Manual entry
PUT    /api/v1/transactions/{id}      → Edit category/notes/tags
POST   /api/v1/transactions/{id}/split → Split transaction
DELETE /api/v1/transactions/{id}      → Soft delete
```

## 7.3 Review Queue
```
GET    /api/v1/review                 → List items needing review
POST   /api/v1/review/{id}/resolve    → Assign category (updates merchant_memory)
POST   /api/v1/review/batch-resolve   → Batch assign
GET    /api/v1/review/stats           → Queue size, avg resolution time
```

## 7.4 Ingestion
```
POST   /api/v1/ingest/gmail           → Trigger Gmail ingestion now
POST   /api/v1/ingest/upload          → Upload PDF statement
GET    /api/v1/ingest/status          → Last run info, errors
```

## 7.5 Analytics
```
GET    /api/v1/aggregates             → Monthly aggregates (with month filter)
GET    /api/v1/aggregates/trends      → Multi-month trend data
GET    /api/v1/recurring              → Recurring patterns list
GET    /api/v1/profile                → Financial profile metrics
```

## 7.6 Budget & Goals
```
GET    /api/v1/goals                  → List goals
POST   /api/v1/goals                  → Create goal
PUT    /api/v1/goals/{id}             → Update goal
POST   /api/v1/goals/{id}/simulate    → Run simulation with parameters
DELETE /api/v1/goals/{id}             → Delete goal
```

## 7.7 Reports
```
GET    /api/v1/reports/summary        → Summary data (JSON for dashboard)
GET    /api/v1/reports/pdf/summary    → Download summary PDF
GET    /api/v1/reports/pdf/detailed   → Download detailed PDF
```

## 7.8 Settings & System
```
GET    /api/v1/settings               → All settings
PUT    /api/v1/settings               → Update settings
GET    /api/v1/system/health          → System health status
POST   /api/v1/system/backup          → Trigger backup now
POST   /api/v1/system/reanalyze       → Re-run classification on all transactions
GET    /api/v1/export/csv             → Export all transactions as CSV
```

## 7.9 Gmail OAuth
```
GET    /api/v1/auth/gmail/url         → Get OAuth authorization URL
GET    /api/v1/auth/gmail/callback    → OAuth callback handler
GET    /api/v1/auth/gmail/status      → Check if Gmail is connected
```

## 7.10 Audit Sessions
```
GET    /api/v1/audit                  → List all audit sessions (with status filter)
GET    /api/v1/audit/{year}/{month}   → Get audit status for a specific month
POST   /api/v1/audit/start            → Start draft audit for a month (body: {year, month})
POST   /api/v1/audit/{id}/finalize    → Finalize audit: lock transactions, freeze aggregates
POST   /api/v1/audit/{id}/discard     → Discard draft: rollback changes via audit_log
POST   /api/v1/audit/{id}/reopen      → Reopen finalized month: creates new draft, unlocks txns
```

**Endpoint behavior:**
- `POST /start` → Fails if a draft already exists for any month. Returns 409 Conflict.
- `POST /finalize` → Recalculates monthly_aggregates, sets is_finalized=True, locks all transactions in that period, sets finalized_at timestamp.
- `POST /discard` → Reverts all changes made during the draft session using audit_log entries. Sets status to 'discarded'.
- `POST /reopen` → Only works on finalized months. Creates new draft session, sets is_locked=False on that month's transactions. Old finalized aggregates are preserved in audit_log before being unlocked.
- All transaction edit/delete endpoints must check `is_locked`: if True and no active draft for that month, return 403 Forbidden with message "Month is finalized. Reopen audit to edit."

---

# PART 8: FRONTEND PAGES & COMPONENTS

## Tech Stack
- **Vite + React 19** (NOT Next.js — simpler for local app)
- **Tailwind CSS** (utility-first, mobile-responsive)
- **Recharts** (charts/visualizations)
- **React Router** (client-side routing)
- **React Query / TanStack Query** (data fetching + caching)

## 8.1 Pages

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | Overview: month spend, category breakdown, recent transactions, health card |
| `/transactions` | Transaction List | Full searchable/filterable table |
| `/review` | Review Queue | Card-based review with quick-assign |
| `/audit` | Audit Manager | Start/finalize/reopen monthly audits, view audit history |
| `/budget` | Budget & Goals | Goal list, simulation sliders, projections |
| `/reports` | Reports | Summary charts + PDF download |
| `/upload` | Upload Statement | PDF upload with reconciliation preview |
| `/settings` | Settings | Account config, timezone, developer mode toggle, backup |
| `/onboarding` | First-Run Wizard | Gmail connect, initial setup |

## 8.1.1 Audit Flow UI

**Audit Manager Page (`/audit`):**
- Month selector (grid of months, current year + previous year)
- Each month shows status: `No Audit` (grey), `Draft` (amber pulse), `Finalized` (green lock icon)
- Click a month to see: transaction count, category breakdown preview, audit history

**Audit Actions:**
- `Start Audit` button (visible for non-finalized months) → Creates draft session
- `Finalize Audit` button (visible during draft) → Confirmation modal: "This will lock all transactions for {Month Year}. Aggregates will be frozen. Continue?"
- `Reopen Audit` button (visible for finalized months) → Warning modal: "This will unlock {Month Year} for editing. A new audit draft will be created."
- `Discard Audit` button (visible during draft) → Confirmation: "Discard all changes made in this audit session?"

**Dashboard Integration:**
- When ANY month has a draft audit in progress, dashboard shows a top banner:
  ```
  ┌─────────────────────────────────────────────────────────────┐
  │ ⚠ AUDIT IN PROGRESS: February 2026          [View] [Finalize] │
  └─────────────────────────────────────────────────────────────┘
  ```
- Provisional months (no finalized audit) show aggregates with a dotted border and "Provisional" label
- Finalized months show a small 🔒 icon on their stat cards

**Transaction List Integration:**
- Locked transactions (finalized month) show a lock icon and are non-editable
- If user tries to edit a locked transaction → tooltip: "This month is finalized. Reopen audit to edit."
- During draft audit, edited transactions show an amber dot indicating "changed in current audit"

## 8.2 Dashboard Layout (Desktop)

```
┌─────────────────────────────────────────────────────────────────┐
│ GODFIN                                      [Settings] [User]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Month    │ │ Income   │ │ Savings  │ │ Review   │           │
│  │ Spend    │ │          │ │ Rate     │ │ Queue    │           │
│  │ ₹45,200  │ │ ₹85,000  │ │ 46.8%   │ │ 3 items  │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                  │
│  ┌───────────────────────────┐ ┌───────────────────────┐        │
│  │ Category Breakdown (Pie)  │ │ Spending Trend (Line) │        │
│  │                           │ │                       │        │
│  │                           │ │                       │        │
│  └───────────────────────────┘ └───────────────────────┘        │
│                                                                  │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Recent Transactions                           [View All]│      │
│  │ Today                                                   │      │
│  │  Swiggy Food    ₹332    Food & Dining    CC **0001     │      │
│  │  Amazon         ₹2,603  Shopping          CC **0001     │      │
│  │ Yesterday                                               │      │
│  │  JP Badminton   ₹360    Health            UPI           │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌─────────────────────────┐ ┌───────────────────────────┐      │
│  │ Financial Health Card   │ │ System Status             │      │
│  │ Savings Discipline: B+  │ │ Last run: 2h ago ✓        │      │
│  │ Impulse Index: 23       │ │ LLM quota: 847/1000       │      │
│  │ Fixed Ratio: 45%        │ │ Review queue: 3 items     │      │
│  └─────────────────────────┘ └───────────────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 8.3 Mobile Layout

Same components, stacked vertically. Tailwind responsive classes:
- Cards: `grid grid-cols-2 md:grid-cols-4`
- Charts: Full width on mobile
- Transactions: Card view instead of table on mobile
- Review queue: Swipeable cards

## 8.4 Design Language

- **NOT generic AI aesthetic.** Clean, financial, trustworthy.
- Color palette: Deep navy (#1a1f36) backgrounds, white cards, accent green (#22c55e) for positive, accent red (#ef4444) for negative
- Font: Inter (clean, modern, excellent number rendering)
- No emojis in core UI (professional finance tool)
- Subtle animations (framer-motion for page transitions)
- Dark mode default (easier on eyes for financial data)

---

# PART 9: PHASED BUILD PLAN (Optimized for Claude Code)

## Build Principles for Claude Code
1. **One phase at a time.** Complete and test before moving on.
2. **Each phase = one Claude Code session.** Keep context focused.
3. **Test after each phase.** Verify before building on top.
4. **Backend first, frontend second** within each phase.
5. **Use mock data** until Gmail is connected (Phase 3).

## Phase 1: Foundation (Session 1)
**Duration:** ~1 session  
**Prompt to Claude Code:**
```
Build the GODFIN project foundation:
1. Create project structure (backend/ with FastAPI, frontend/ with Vite+React+Tailwind)
2. Implement all SQLAlchemy models from the data model spec
3. Create tables idempotently with SQLAlchemy `create_all`
4. Apply the documented idempotent startup schema/seed upgrades
5. Configure SQLite with WAL mode
6. Create FastAPI app with health endpoint
7. Set up CORS for local network access
8. Create app_settings table with defaults
9. Create the taxonomy.py config file
10. Create seed data for accounts table
```
**Test:** `curl http://127.0.0.1:5100/api/v1/health` returns OK. Database file created with all tables.

## Phase 2: Manual Transaction Entry + Basic Dashboard (Session 2)
**Prompt:**
```
Add manual transaction entry and basic dashboard:
1. POST /api/v1/transactions (manual entry with validation)
2. GET /api/v1/transactions (list with date/category/account filters)
3. Frontend: PIN gate (set on first run, verify on subsequent)
4. Frontend: Dashboard with stat cards (total spend, transaction count)
5. Frontend: Transaction list page with search and filters
6. Frontend: "Quick Add" transaction form
7. Frontend: Basic responsive layout with Tailwind
```
**Test:** Open app, set PIN, add a manual transaction, see it in the list.

## Phase 3: Gmail Ingestion (Session 3)
**Prompt:**
```
Implement Gmail ingestion:
1. Gmail OAuth flow (get credentials, store refresh token in keychain)
2. Email fetch service using history API (historyId-based sync)
3. Sender whitelist filtering
4. Subject-based noise filtering (blacklist)
5. UPI debit parser (regex from spec)
6. Credit card debit parser (regex from spec)
7. HTML extraction using BeautifulSoup
8. Merchant normalization pipeline
9. Deduplication (source checksum + canonical checksum)
10. POST /api/v1/ingest/gmail endpoint
11. Mock mode with fixture emails for testing
12. Circuit breaker for Gmail API
```
**Test:** Trigger ingestion, see real transactions appear. Also test with mock mode.

## Phase 4: Classification Engine (Session 4)
**Prompt:**
```
Build the 5-layer classification engine:
1. Exact match layer (merchant_memory lookup)
2. Classification rules engine (regex/contains from classification_rules table)
3. Seed classification_rules with MERCHANT_CATEGORIES from spec
4. Fuzzy string match layer (TheFuzz against merchant_memory)
5. Stub for embedding layer (to be completed in Phase 7)
6. Stub for LLM layer (to be completed in Phase 7)
7. Confidence scoring with per-category thresholds
8. Transfer detection heuristics
9. P2P UPI detection (VPA pattern matching)
10. Review queue: GET /api/v1/review, POST /api/v1/review/{id}/resolve
11. When user resolves review item → update merchant_memory
12. Audit log for all changes
```
**Test:** Ingest emails, see classifications with confidence scores. Unresolved items in review queue. Resolve one, see it remembered for next occurrence.

## Phase 5: Review Queue UI + Dashboard Enhancement (Session 5)
**Prompt:**
```
Build the Review Queue UI and enhance dashboard:
1. Review queue page: card-based layout showing transaction + suggested category
2. Quick-assign buttons for each category
3. Batch select and resolve
4. "Remember this merchant" toggle (on by default)
5. P2P UPI: show person name prominently, ask for category
6. Dashboard: category breakdown pie chart (Recharts)
7. Dashboard: spending trend line chart (last 6 months)
8. Dashboard: recent transactions list
9. System health card (last run, errors, queue size)
10. Mobile-responsive layout for all pages
```
**Test:** Full loop: email → ingestion → classification → review → dashboard display.

## Phase 6: Statement Upload + Income Tracking (Session 6)
**Prompt:**
```
Implement statement upload and income:
1. POST /api/v1/ingest/upload for PDF statement
2. PDF parsing with pdfplumber (handle password-protected PDFs)
3. HDFC Credit Card statement parser (extract transactions table)
4. HDFC Savings Account statement parser
5. Statement reconciliation algorithm (fuzzy matching)
6. Reconciliation preview UI (matched/possible/new)
7. Income detection from statement credits
8. income_sources table management
9. Manual income entry
10. Update monthly_aggregates with income data
11. Savings rate calculation
```
**Test:** Upload a CC statement PDF, see reconciliation results. Income detected and reflected in dashboard.

## Phase 7: Embeddings + LLM Integration (Session 7)
**Prompt:**
```
Add embedding similarity and LLM fallback:
1. Optional local embedding model (FastEmbed, downloaded only after opt-in)
2. Generate embeddings for all merchants in merchant_memory
3. Cosine similarity search (numpy, in-memory)
4. Integrate as Layer 4 in classification pipeline
5. LLM service with pluggable interface (OAuth-based)
6. LLM classification prompt (from spec, with taxonomy)
7. Backend validation of LLM responses against taxonomy
8. Semantic cache (check merchant_memory before calling LLM)
9. Circuit breaker for LLM API
10. Rate limit handling (queue + fallback to deterministic)
11. Only pass extracted fields to LLM (never raw email)
```
**Test:** Create a transaction with unknown merchant. See it go through embedding → LLM → classified. Verify no prompt injection possible.

## Phase 8: Recurring + Budget + Profile (Session 8)
**Prompt:**
```
Build recurring detection, budget engine, and financial profile:
1. Recurring detection algorithm (monthly/quarterly/annual)
2. recurring_patterns table management
3. Subscription tracker view
4. Budget engine: expense elasticity mapping
5. Goal calculator with Future Value of Annuity formula
6. Goal simulation with pressure levels and minimum floor
7. Budget page UI: goal cards, simulation sliders
8. Financial profile metrics (all 6 formulas from spec)
9. Financial health card on dashboard
10. Category elasticity override (user can reclassify)
```
**Test:** See recurring patterns detected. Create a goal, run simulation. Financial profile shows sensible numbers.

## Phase 9: Reporting Engine (Session 9)
**Prompt:**
```
Build the reporting engine:
1. Aggregation service (prepare structured report data)
2. Summary report data endpoint
3. Detailed report data endpoint
4. PDF generation (server-side, WeasyPrint or similar)
5. Charts embedded in PDF (matplotlib → PNG → embed)
6. LLM commentary (structured templates, capped at 2 sentences)
7. Reports page UI: summary view with charts
8. PDF download buttons
9. Date range selector for reports
10. Category comparison chart (current month vs average)
```
**Test:** Generate summary and detailed PDF reports. Charts render correctly. Commentary is relevant and templated.

## Phase 10: Hardening + Polish (Session 10)
**Prompt:**
```
Final hardening and polish:
1. Automated daily backup (copy SQLite to user-configured directory, encrypted)
2. Restore from backup endpoint and UI
3. APScheduler: nightly batch at 11:59 PM (user timezone)
4. APScheduler: polling every 15 minutes
5. Run-on-wake detection (check last run, execute if missed)
6. Developer mode toggle in settings
7. Developer mode: rule editing with regex validation
8. Developer mode: raw transaction view
9. CSV export endpoint
10. Transaction tags and notes
11. Transaction split UI
12. Structured JSON logging with rotation
13. Error handling: graceful degradation everywhere
14. Onboarding wizard (first-run flow)
15. Single startup script (start.sh)
16. Audit session system:
    - POST /api/v1/audit/start (create draft for a month, enforce one-draft-at-a-time)
    - POST /api/v1/audit/{id}/finalize (recalc aggregates, lock transactions, freeze month)
    - POST /api/v1/audit/{id}/discard (rollback changes via audit_log)
    - POST /api/v1/audit/{id}/reopen (unlock finalized month, create new draft)
    - All transaction PUT/DELETE endpoints check is_locked before allowing edits
    - Audit manager page: month grid with status indicators
    - Dashboard banner when draft audit is in progress
    - Provisional vs finalized visual distinction on aggregate displays
    - Trend charts use only finalized months
```
**Test:** Full system test: start app, onboarding, Gmail connect, ingestion, classification, review, budget, report, backup. Then: start audit for current month, reclassify a transaction, finalize audit, verify month is locked, verify aggregates frozen, reopen audit, verify unlocked.

---

# PART 10: TECH STACK (Locked)

## Backend
| Component | Technology | Version |
|---|---|---|
| Framework | FastAPI | Latest |
| ORM | SQLAlchemy | 2.0+ |
| Database | SQLite | WAL mode |
| Schema lifecycle | SQLAlchemy `create_all` + idempotent startup upgrades/seeds | Built-in |
| Scheduler | APScheduler | 3.x |
| Gmail | google-auth + google-api-python-client | Latest |
| PDF Parsing | pdfplumber | Latest |
| PDF Generation | WeasyPrint or ReportLab | Latest |
| Embeddings | FastEmbed (optional, on-demand) | 0.8.x |
| Fuzzy Match | TheFuzz + python-Levenshtein | Latest |
| HTML Parse | BeautifulSoup4 | Latest |
| Charts (PDF) | matplotlib | Latest |
| Logging | Python logging (JSON formatter) | Built-in |
| Keychain | keyring | Latest |

## Frontend
| Component | Technology |
|---|---|
| Build Tool | Vite |
| Framework | React 19 |
| Styling | Tailwind CSS v4 |
| Charts | Recharts |
| Routing | React Router v6 |
| Data Fetching | TanStack Query |
| Animations | Framer Motion |
| Icons | Lucide React |
| Date Handling | date-fns |

---

# PART 11: ACCEPTANCE CRITERIA

The system is V1-complete when:

1. ✅ Gmail ingestion processes all HDFC email types without errors
2. ✅ ≤10% of transactions need manual review after 1 month of use
3. ✅ Zero transfers misclassified as expenses
4. ✅ Recurring detection catches ≥90% of actual subscriptions
5. ✅ Statement upload and reconciliation works for both CC and savings PDFs
6. ✅ Income correctly detected from statements
7. ✅ Dashboard accessible from phone on local network
8. ✅ PDF reports generate with charts and sensible commentary
9. ✅ Backup system runs daily without intervention
10. ✅ System recovers gracefully from Gmail/LLM outages
11. ✅ Review queue resolution takes <5 seconds per item
12. ✅ No duplicate transactions across email + statement sources
13. ✅ Finalized months are truly immutable — locked transactions reject edits with clear error
14. ✅ Reopen audit correctly unlocks a finalized month and creates a new draft
15. ✅ Trend charts and YoY comparisons use only finalized aggregate data

---

*Specification complete. This document is the single source of truth for Claude Code to build GODFIN.*
