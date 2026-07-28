from __future__ import annotations

MOCK_UPI_DEBIT_EMAIL = {
    'id': 'mock_upi_001',
    'sender': 'alerts@hdfcbank.net',
    'subject': 'Transaction Alert - UPI',
    'date': 'Mon, 10 Feb 2026 14:30:00 +0530',
    'body': (
        'Dear Customer, Rs.350.00 has been debited from account 0000 to VPA '
        'swiggy@ybl Swiggy Food Order on 10-02-26. '
        'Your UPI transaction reference number is 504123456789. '
        'If you did not authorize this transaction, please contact us.'
    ),
}

MOCK_UPI_P2P_EMAIL = {
    'id': 'mock_upi_p2p_001',
    'sender': 'alerts@hdfcbank.net',
    'subject': 'Transaction Alert - UPI',
    'date': 'Tue, 11 Feb 2026 10:00:00 +0530',
    'body': (
        'Dear Customer, Rs.1,500.00 has been debited from account 0000 to VPA '
        '9876543210@ybl John Doe on 11-02-26. '
        'Your UPI transaction reference number is 504987654321. '
        'If you did not authorize this transaction, please contact us.'
    ),
}

MOCK_CC_DEBIT_EMAIL = {
    'id': 'mock_cc_001',
    'sender': 'alerts@hdfcbank.bank.in',
    'subject': 'Transaction Alert - Credit Card',
    'date': 'Wed, 12 Feb 2026 18:45:00 +0530',
    'body': (
        'Rs.2,499.00 is debited from your HDFC Bank '
        'Credit Card ending 0001 towards '
        'AMAZON PAY INDIA PVT LTD on 12 February, 2026 at 18:45:00.'
    ),
}

MOCK_BLACKLISTED_EMAIL = {
    'id': 'mock_blacklist_001',
    'sender': 'alerts@hdfcbank.net',
    'subject': 'Your OTP for HDFC Bank transaction',
    'date': 'Mon, 10 Feb 2026 14:31:00 +0530',
    'body': 'Your OTP is 123456. Do not share it with anyone.',
}

MOCK_UNKNOWN_SENDER_EMAIL = {
    'id': 'mock_unknown_001',
    'sender': 'noreply@somebank.com',
    'subject': 'Transaction Alert',
    'date': 'Mon, 10 Feb 2026 14:32:00 +0530',
    'body': 'Some random email body that should be ignored.',
}

MOCK_NO_MATCH_EMAIL = {
    'id': 'mock_nomatch_001',
    'sender': 'alerts@hdfcbank.net',
    'subject': 'Account Balance Update',
    'date': 'Mon, 10 Feb 2026 14:33:00 +0530',
    'body': 'Your account balance is Rs.50,000.00 as of 10-02-2026.',
}

ALL_MOCK_EMAILS = [
    MOCK_UPI_DEBIT_EMAIL,
    MOCK_UPI_P2P_EMAIL,
    MOCK_CC_DEBIT_EMAIL,
    MOCK_BLACKLISTED_EMAIL,
    MOCK_UNKNOWN_SENDER_EMAIL,
    MOCK_NO_MATCH_EMAIL,
]
