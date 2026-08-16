from __future__ import annotations

from datetime import date

from app.core.email_parser import (
    CC_DEBIT_PATTERN,
    DEBIT_CARD_PATTERN,
    RUPAY_CREDIT_UPI_PATTERN,
    UPI_CREDIT_PATTERN,
    UPI_DEBIT_PATTERN,
    compute_canonical_checksum,
    compute_source_checksum,
    extract_text_from_html,
    is_blacklisted_subject,
    is_whitelisted_sender,
    normalize_merchant,
    parse_amount,
    parse_cc_date,
    parse_debit_card_date,
    parse_email_body,
    parse_upi_date,
)


# --- Merchant Normalization ---

def test_normalize_basic():
    assert normalize_merchant("  Swiggy Food  ") == "SWIGGY FOOD"


def test_normalize_strips_gateway_prefix():
    assert normalize_merchant("PAY*NETFLIX") == "NETFLIX"
    assert normalize_merchant("GOOGLE *YouTube") == "YOUTUBE"


def test_normalize_strips_corporate_suffix():
    assert normalize_merchant("AMAZON PAY INDIA PVT LTD") == "AMAZON PAY"


def test_normalize_strips_city():
    assert normalize_merchant("UBER INDIA BANGALORE") == "UBER"


def test_normalize_combined():
    assert normalize_merchant("PAY*SWIGGY PVT LTD BANGALORE") == "SWIGGY"


# --- UPI Debit Pattern ---

def test_upi_debit_pattern_match():
    text = (
        'Dear Customer, Rs.350.00 has been debited from account 0000 to VPA '
        'swiggy@ybl Swiggy Food Order on 10-02-26. '
        'Your UPI transaction reference number is 504123456789.'
    )
    match = UPI_DEBIT_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '350.00'
    assert match.group('account') == '0000'
    assert match.group('vpa') == 'swiggy@ybl'
    assert match.group('merchant') == 'Swiggy Food Order'
    assert match.group('date') == '10-02-26'
    assert match.group('ref') == '504123456789'


def test_upi_debit_pattern_with_comma_amount():
    text = (
        'Dear Customer, Rs.1,500.00 has been debited from account 0000 to VPA '
        '9876543210@ybl John Doe on 11-02-26. '
        'Your UPI transaction reference number is 504987654321.'
    )
    match = UPI_DEBIT_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '1,500.00'


# --- CC Debit Pattern ---

def test_cc_debit_pattern_match():
    text = (
        'Rs.2,499.00 is debited from your HDFC Bank '
        'Credit Card ending 0001 towards '
        'AMAZON PAY INDIA PVT LTD on 12 February, 2026 at 18:45:00.'
    )
    match = CC_DEBIT_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '2,499.00'
    assert match.group('card_last4') == '0001'
    assert match.group('merchant') == 'AMAZON PAY INDIA PVT LTD'
    assert match.group('date') == '12 February, 2026'
    assert match.group('time') == '18:45:00'


# --- Date Parsing ---

def test_parse_upi_date_short_year():
    assert parse_upi_date('10-02-26') == date(2026, 2, 10)


def test_parse_upi_date_full_year():
    assert parse_upi_date('10-02-2026') == date(2026, 2, 10)


def test_parse_cc_date():
    assert parse_cc_date('12 February, 2026') == date(2026, 2, 12)


def test_parse_cc_date_no_comma():
    assert parse_cc_date('12 February 2026') == date(2026, 2, 12)


# --- Amount Parsing ---

def test_parse_amount_simple():
    assert parse_amount('350.00') == 350.00


def test_parse_amount_with_comma():
    assert parse_amount('1,500.00') == 1500.00


def test_parse_amount_large():
    assert parse_amount('85,000.00') == 85000.00


# --- Checksums ---

def test_source_checksum_deterministic():
    c1 = compute_source_checksum('test body', 'gmail')
    c2 = compute_source_checksum('test body', 'gmail')
    assert c1 == c2


def test_source_checksum_different():
    c1 = compute_source_checksum('body 1', 'gmail')
    c2 = compute_source_checksum('body 2', 'gmail')
    assert c1 != c2


def test_canonical_checksum_deterministic():
    c1 = compute_canonical_checksum(date(2026, 2, 10), 350.0, 'SWIGGY', 'upi', 'acc1')
    c2 = compute_canonical_checksum(date(2026, 2, 10), 350.0, 'SWIGGY', 'upi', 'acc1')
    assert c1 == c2


# --- Filtering ---

def test_whitelisted_sender():
    assert is_whitelisted_sender('alerts@hdfcbank.net') == 'hdfc_savings'
    assert is_whitelisted_sender('alerts@hdfcbank.bank.in') == 'hdfc_credit'
    assert is_whitelisted_sender('random@email.com') is None


def test_blacklisted_subject():
    assert is_blacklisted_subject('Your OTP for transaction') is True
    assert is_blacklisted_subject('Transaction Alert - UPI') is False
    assert is_blacklisted_subject('Welcome to HDFC Bank') is True


# --- HTML Extraction ---

def test_extract_text_from_html():
    html = '<html><body><p>Rs.350.00 has been debited</p></body></html>'
    text = extract_text_from_html(html)
    assert 'Rs.350.00' in text
    assert '<p>' not in text


# --- Full Parse ---

def test_parse_upi_email():
    body = (
        'Dear Customer, Rs.350.00 has been debited from account 0000 to VPA '
        'swiggy@ybl Swiggy Food Order on 10-02-26. '
        'Your UPI transaction reference number is 504123456789.'
    )
    result = parse_email_body(body, 'hdfc_savings')
    assert result is not None
    assert result.amount == 350.00
    assert result.merchant_normalized == 'SWIGGY FOOD ORDER'
    assert result.instrument == 'upi'
    assert result.vpa_handle == 'swiggy@ybl'
    assert result.upi_ref_number == '504123456789'
    assert result.is_p2p is False
    assert result.account_last4 == '0000'


def test_explicit_savings_upi_content_overrides_credit_sender_hint():
    body = (
        'Dear Customer, Rs.350.00 has been debited from account 0000 to VPA '
        'cafe@ybl Synthetic Cafe on 10-02-26. '
        'Your UPI transaction reference number is 504123456789.'
    )

    result = parse_email_body(body, 'hdfc_credit')

    assert result is not None
    assert result.account_type == 'hdfc_savings'
    assert result.account_last4 == '0000'
    assert result.instrument == 'upi'


def test_parse_upi_p2p():
    body = (
        'Dear Customer, Rs.1,500.00 has been debited from account 0000 to VPA '
        '9876543210@ybl John Doe on 11-02-26. '
        'Your UPI transaction reference number is 504987654321.'
    )
    result = parse_email_body(body, 'hdfc_savings')
    assert result is not None
    assert result.amount == 1500.00
    assert result.is_p2p is True


def test_parse_cc_email():
    body = (
        'Rs.2,499.00 is debited from your HDFC Bank '
        'Credit Card ending 0001 towards '
        'AMAZON PAY INDIA PVT LTD on 12 February, 2026 at 18:45:00.'
    )
    result = parse_email_body(body, 'hdfc_credit')
    assert result is not None
    assert result.amount == 2499.00
    assert result.merchant_normalized == 'AMAZON PAY'
    assert result.instrument == 'credit_card'
    assert result.account_last4 == '0001'


def test_parse_no_match():
    result = parse_email_body('Random email text', 'hdfc_savings')
    assert result is None


# --- Debit Card Pattern Tests ---

def test_debit_card_pattern_match():
    text = (
        'Thank you for using HDFC Bank Debit Card ending with 6785 '
        'for Rs. 1818.60 at OLLAMA on 28-02-2026 01:07:44.'
    )
    match = DEBIT_CARD_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '1818.60'
    assert match.group('card_last4') == '6785'
    assert match.group('merchant') == 'OLLAMA'
    assert match.group('date') == '28-02-2026'
    assert match.group('time') == '01:07:44'


def test_parse_debit_card_email():
    body = (
        'Thank you for using HDFC Bank Debit Card ending with 6785 '
        'for Rs. 1818.60 at OLLAMA on 28-02-2026 01:07:44.'
    )
    result = parse_email_body(body, 'hdfc_savings')
    assert result is not None
    assert result.amount == 1818.60
    assert result.merchant_raw == 'OLLAMA'
    assert result.instrument == 'debit_card'
    assert result.txn_type == 'debit'
    assert result.txn_date == date(2026, 2, 28)


# --- RuPay Credit UPI Pattern Tests ---

def test_rupay_credit_upi_pattern_match():
    text = (
        'Rs.470.00 has been debited from your HDFC Bank RuPay Credit Card XX4525 '
        'to amznplprvr4000621@yapi PVR INOX Limited on 28-02-26. '
        'Your UPI transaction reference number is 605990103912.'
    )
    match = RUPAY_CREDIT_UPI_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '470.00'
    assert match.group('card_last4') == '4525'
    assert match.group('vpa') == 'amznplprvr4000621@yapi'
    assert 'PVR INOX Limited' in match.group('merchant')
    assert match.group('date') == '28-02-26'
    assert match.group('ref') == '605990103912'


def test_parse_rupay_credit_upi_email():
    body = (
        'Rs.470.00 has been debited from your HDFC Bank RuPay Credit Card XX4525 '
        'to amznplprvr4000621@yapi PVR INOX Limited on 28-02-26. '
        'Your UPI transaction reference number is 605990103912.'
    )
    result = parse_email_body(body, 'hdfc_savings')
    assert result is not None
    assert result.amount == 470.00
    assert result.instrument == 'rupay_credit_upi'
    assert result.txn_type == 'debit'
    assert result.vpa_handle == 'amznplprvr4000621@yapi'
    assert result.upi_ref_number == '605990103912'
    assert result.account_type == 'hdfc_credit'
    assert result.account_last4 == '4525'


# --- UPI Credit Pattern Tests ---

def test_upi_credit_pattern_match():
    text = (
        'Rs. 1.00 is successfully credited to your account **0000 by VPA '
        'paytm-ptmbbp@ptybl Paytm Utility Bill on 27-02-26.'
    )
    match = UPI_CREDIT_PATTERN.search(text)
    assert match is not None
    assert match.group('amount') == '1.00'
    assert match.group('account') == '0000'
    assert match.group('vpa') == 'paytm-ptmbbp@ptybl'
    assert 'Paytm Utility Bill' in match.group('merchant')
    assert match.group('date') == '27-02-26'


def test_parse_upi_credit_email():
    body = (
        'Rs. 1.00 is successfully credited to your account **0000 by VPA '
        'paytm-ptmbbp@ptybl Paytm Utility Bill on 27-02-26.'
    )
    result = parse_email_body(body, 'hdfc_savings')
    assert result is not None
    assert result.amount == 1.00
    assert result.instrument == 'upi'
    assert result.txn_type == 'credit'
    assert result.vpa_handle == 'paytm-ptmbbp@ptybl'


# --- Credit Card Variations Tests ---

def test_cc_debit_with_at_instead_of_towards():
    body = (
        'Rs.2603.00 is debited from your HDFC Bank '
        'Credit Card ending 0001 at '
        'AMAZON PAY INDIA PRIVA on 25 Feb, 2026 at 18:08:57.'
    )
    result = parse_email_body(body, 'hdfc_credit')
    assert result is not None
    assert result.amount == 2603.00
    assert result.instrument == 'credit_card'
    assert result.txn_date == date(2026, 2, 25)


def test_cc_debit_no_comma_in_date():
    body = (
        'Rs.2603.00 is debited from your HDFC Bank '
        'Credit Card ending 0001 at '
        'AMAZON PAY INDIA PRIVA on 25 Feb 2026 at 18:08:57.'
    )
    result = parse_email_body(body, 'hdfc_credit')
    assert result is not None
    assert result.amount == 2603.00
    assert result.txn_date == date(2026, 2, 25)


def test_parse_debit_card_date():
    assert parse_debit_card_date('28-02-2026') == date(2026, 2, 28)
    assert parse_debit_card_date('01-03-2025') == date(2025, 3, 1)
