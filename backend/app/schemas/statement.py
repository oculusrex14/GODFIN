from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.financial import LegacyIncomeFrequency, PositiveMoney


class ReconcilePreview(BaseModel):
    matched: int
    possible: int
    new: int
    income_detected: int
    details: dict


class ImportRequest(BaseModel):
    import_new: bool = True
    import_possible: bool = False


class IncomeSourceCreate(BaseModel):
    source_name: str = Field(..., min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: LegacyIncomeFrequency = 'monthly'


class IncomeSourceUpdate(BaseModel):
    source_name: Optional[str] = Field(None, min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: Optional[LegacyIncomeFrequency] = None
    is_active: Optional[bool] = None


class StatementControlTotals(BaseModel):
    opening_balance: Optional[float]
    closing_balance: Optional[float]
    total_debits: Optional[float]
    total_credits: Optional[float]


class StatementPreviewTransaction(BaseModel):
    date: str
    description: str
    amount: float
    type: str
    reference: Optional[str]
    instrument: Optional[str]
    is_transfer: bool
    is_income: bool
    semantic_type: str
    merchant_name: Optional[str]


class StatementPreviewResponse(BaseModel):
    statement_type: str
    parser_profile: str
    recognized: bool
    reconciliation_status: str
    reconciliation_method: str
    parse_fingerprint: str
    period_start: Optional[str]
    period_end: Optional[str]
    control_totals: StatementControlTotals
    total_transactions: int
    transactions: list[StatementPreviewTransaction]


class ReconciledTransactionSummary(BaseModel):
    date: str
    description: str
    amount: float
    type: Optional[str] = None


class ExistingTransactionSummary(BaseModel):
    id: str
    date: str
    merchant: Optional[str]
    amount: float


class PotentialDuplicateResponse(BaseModel):
    parsed: ReconciledTransactionSummary
    existing: ExistingTransactionSummary


class StatementReconcileResponse(BaseModel):
    account_id: str
    statement_type: str
    parser_profile: str
    reconciliation_status: str
    reconciliation_method: str
    parse_fingerprint: str
    control_totals: StatementControlTotals
    total_parsed: int
    matched_count: int
    possible_count: int
    new_count: int
    income_count: int
    statement_closing_balance: Optional[float]
    computed_balance: Optional[float]
    balance_discrepancy: Optional[float]
    new_transactions: list[ReconciledTransactionSummary]
    potential_duplicates: list[PotentialDuplicateResponse]
    income_detected: list[ReconciledTransactionSummary]


class StatementImportResponse(BaseModel):
    statement_type: str
    total_parsed: int
    matched: int
    skipped_dup: int
    possible: int
    new_imported: int
    imported: int
    classified: int
    review_queue: int
    errors: list[str]
    income_detected: int
    income_items: list[ReconciledTransactionSummary]
    statement_closing_balance: Optional[float]
    computed_balance: Optional[float]
    balance_discrepancy: Optional[float]


class IncomeSourceResponse(BaseModel):
    id: str
    source_name: str
    expected_amount: Optional[float]
    frequency: str
    last_detected_date: Optional[str]
    last_detected_amount: Optional[float]
    is_active: bool


class IncomeSourceCreatedResponse(BaseModel):
    id: str
    source_name: str
    expected_amount: Optional[float]
    frequency: str


class IncomeSourceUpdatedResponse(BaseModel):
    id: str
    source_name: str
    status: str
