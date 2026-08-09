import json
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.app_setting import AppSetting
from app.models.classification_rule import ClassificationRule

# Stable IDs preserve upgrades while the fresh-install display data remains
# synthetic and contains no developer account identifiers.
SAVINGS_ACCOUNT_ID = "a7c223b3-a64b-556e-b027-a33d4a454cc6"
CC_ACCOUNT_ID = "6ce995d8-1227-5f2b-a8f0-90414defb6ac"


def seed_accounts(db: Session) -> None:
    existing = db.query(Account).count()
    if existing > 0:
        return

    accounts = [
        Account(
            id=SAVINGS_ACCOUNT_ID,
            bank="HDFC",
            account_type="savings",
            last_4_digits="0000",
            nickname="Example HDFC Savings",
            is_active=True,
        ),
        Account(
            id=CC_ACCOUNT_ID,
            bank="HDFC",
            account_type="credit_card",
            last_4_digits="0001",
            nickname="Example HDFC Credit Card",
            is_active=True,
        ),
    ]
    db.add_all(accounts)
    db.commit()


def seed_app_settings(db: Session) -> None:
    defaults = {
        "user_timezone": "Asia/Kolkata",
        "last_gmail_history_id": "",
        "last_ingestion_run": "",
        "pin_hash": "",
        "is_first_run": "true",
        "polling_interval_minutes": "15",
        "nightly_batch_hour": "23",
        "nightly_batch_minute": "59",
        "developer_mode": "false",
        "backup_directory": "./backups",
        "auto_ingestion_enabled": "true",
        "ingestion_frequency_minutes": "15",
        "manual_ingestion_running": "",
        "sync_status": "",
        "sync_progress_processed": "0",
        "sync_progress_total": "0",
        "sync_result": "",
        "sync_error": "",
        "llm_web_search": "false",
        "enable_embeddings": "false",
        "allow_network_access": "false",
        "license_key": "",
        "license_tier": "free",
        "license_status": "inactive",
        "license_verified_at": "",
        "license_monthly_credits": "0",
        "license_topup_credits": "0",
        "sender_account_mappings": json.dumps(
            [
                {
                    "sender_pattern": "alerts@hdfcbank.net",
                    "parser_profile": "hdfc_savings",
                    "account_id": SAVINGS_ACCOUNT_ID,
                },
                {
                    "sender_pattern": "alerts@hdfcbank.bank.in",
                    "parser_profile": "hdfc_credit",
                    "account_id": CC_ACCOUNT_ID,
                },
            ],
            separators=(",", ":"),
            sort_keys=True,
        ),
    }

    for key, value in defaults.items():
        existing = db.query(AppSetting).filter_by(key=key).first()
        if existing is None:
            db.add(AppSetting(key=key, value=value))

    db.commit()


def seed_classification_rules(db: Session) -> None:
    existing = db.query(ClassificationRule).count()
    if existing > 0:
        return

    rules = [
        # FOOD & DINING
        ('contains', 'SWIGGY', 'FOOD & DINING', 'Food Delivery', 10),
        ('contains', 'ZOMATO', 'FOOD & DINING', 'Food Delivery', 10),
        ('contains', 'DOMINOS', 'FOOD & DINING', 'Food Delivery', 10),
        ('contains', 'MCDONALDS', 'FOOD & DINING', 'Restaurants', 10),
        ('contains', 'MC DONALDS', 'FOOD & DINING', 'Restaurants', 10),
        ('contains', 'STARBUCKS', 'FOOD & DINING', 'Coffee/Snacks', 10),
        ('contains', 'DUNZO', 'FOOD & DINING', 'Groceries', 20),
        ('contains', 'BLINKIT', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'BIGBASKET', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'BIG BASKET', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'ZEPTO', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'INSTAMART', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'DMART', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'SHOPPYMART', 'FOOD & DINING', 'Groceries', 10),
        ('contains', 'SAARYODAY FOODS', 'FOOD & DINING', 'Canteen', 10),
        ('contains', 'CUT COFFEE', 'FOOD & DINING', 'Coffee/Snacks', 10),
        ('contains', 'ABCOFFEE', 'FOOD & DINING', 'Coffee/Snacks', 10),
        ('contains', 'BRAHMINS KITCHEN', 'FOOD & DINING', 'Restaurants', 10),
        ('contains', 'SOJITZ VENDING', 'FOOD & DINING', 'Coffee/Snacks', 10),
        # TRANSPORTATION
        ('contains', 'UBER', 'TRANSPORTATION', 'Ride Hailing', 10),
        ('contains', 'OLA', 'TRANSPORTATION', 'Ride Hailing', 10),
        ('contains', 'RAPIDO', 'TRANSPORTATION', 'Ride Hailing', 10),
        ('contains', 'METRO', 'TRANSPORTATION', 'Public Transit', 20),
        ('contains', 'FASTAG', 'TRANSPORTATION', 'Parking/Tolls', 10),
        ('contains', 'PETROL', 'TRANSPORTATION', 'Fuel', 10),
        ('contains', 'IOCL', 'TRANSPORTATION', 'Fuel', 10),
        ('contains', 'HP FUEL', 'TRANSPORTATION', 'Fuel', 10),
        ('contains', 'BPCL', 'TRANSPORTATION', 'Fuel', 10),
        # SHOPPING
        ('contains', 'AMAZON', 'SHOPPING', 'General', 10),
        ('contains', 'AMAZON PAY', 'SHOPPING', 'Online Shopping', 8),
        ('contains', 'FLIPKART', 'SHOPPING', 'General', 10),
        ('contains', 'MYNTRA', 'SHOPPING', 'Clothing', 10),
        ('contains', 'AJIO', 'SHOPPING', 'Clothing', 10),
        ('contains', 'NYKAA', 'SHOPPING', 'General', 10),
        ('contains', 'CROMA', 'SHOPPING', 'Electronics', 10),
        # ENTERTAINMENT
        ('contains', 'NETFLIX', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'SPOTIFY', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'HOTSTAR', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'JIOHOTSTAR', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'PRIME VIDEO', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'YOUTUBE', 'ENTERTAINMENT', 'Subscriptions', 10),
        ('contains', 'BOOKMYSHOW', 'ENTERTAINMENT', 'Movies/Events', 10),
        ('contains', 'PVR', 'ENTERTAINMENT', 'Movies/Events', 10),
        ('contains', 'PVR INOX', 'ENTERTAINMENT', 'Movies/Events', 8),
        ('contains', 'INOX', 'ENTERTAINMENT', 'Movies/Events', 10),
        ('contains', 'SUPERCELL', 'ENTERTAINMENT', 'Gaming', 10),
        ('contains', 'JP BADMINTON', 'ENTERTAINMENT', 'Sports', 10),
        ('contains', 'PLAYO', 'ENTERTAINMENT', 'Sports', 10),
        # UTILITIES & BILLS
        ('contains', 'AIRTEL', 'UTILITIES & BILLS', 'Internet/Phone', 10),
        ('contains', 'JIO', 'UTILITIES & BILLS', 'Internet/Phone', 10),
        ('contains', 'VODAFONE', 'UTILITIES & BILLS', 'Internet/Phone', 10),
        ('contains', 'ATRIA CONVERGENCE', 'UTILITIES & BILLS', 'Internet/Phone', 10),
        ('contains', 'BESCOM', 'UTILITIES & BILLS', 'Electricity', 10),
        ('contains', 'ELECTRICITY', 'UTILITIES & BILLS', 'Electricity', 20),
        ('contains', 'BANGALORE ELECTRICIT', 'UTILITIES & BILLS', 'Electricity', 10),
        ('contains', 'BANGALORE WATER', 'UTILITIES & BILLS', 'Water', 10),
        ('contains', 'CHATGPT', 'UTILITIES & BILLS', 'Subscriptions', 10),
        ('contains', 'CLAUDE.AI', 'UTILITIES & BILLS', 'Subscriptions', 10),
        ('contains', 'OLLAMA', 'UTILITIES & BILLS', 'Subscriptions', 10),
        ('contains', 'SHOPIFY COMMERCE', 'UTILITIES & BILLS', 'Subscriptions', 10),
        ('contains', 'APPLE MEDIA SERVICES', 'UTILITIES & BILLS', 'Subscriptions', 10),
        # FINANCIAL OBLIGATIONS
        ('contains', 'EMI', 'FINANCIAL OBLIGATIONS', 'EMI - Loan', 20),
        ('contains', 'INSURANCE', 'FINANCIAL OBLIGATIONS', 'Insurance Premium', 20),
        ('contains', 'LIC', 'FINANCIAL OBLIGATIONS', 'Insurance Premium', 10),
        ('contains', 'MUTUAL FUND', 'FINANCIAL OBLIGATIONS', 'SIP/Investment', 10),
        ('contains', 'ZERODHA', 'FINANCIAL OBLIGATIONS', 'SIP/Investment', 10),
        ('contains', 'GROWW', 'FINANCIAL OBLIGATIONS', 'SIP/Investment', 10),
        ('contains', 'DC INTL POS TXN MARKUP', 'FINANCIAL OBLIGATIONS', 'Bank Charges', 10),
        # HEALTH & WELLNESS
        ('contains', 'PHARMACY', 'HEALTH & WELLNESS', 'Medical/Pharmacy', 20),
        ('contains', 'APOLLO', 'HEALTH & WELLNESS', 'Medical/Pharmacy', 10),
        ('contains', 'MEDPLUS', 'HEALTH & WELLNESS', 'Medical/Pharmacy', 10),
        ('contains', 'CULT.FIT', 'HEALTH & WELLNESS', 'Gym/Fitness', 10),
        ('contains', 'SRI DURGA MEDICALS', 'HEALTH & WELLNESS', 'Medical/Pharmacy', 10),
        ('contains', 'RADHA RAMAN HOSPITAL', 'HEALTH & WELLNESS', 'Hospital', 10),
        ('contains', 'KRIPA SURGICALS', 'HEALTH & WELLNESS', 'Medical/Pharmacy', 10),
        # EDUCATION
        ('contains', 'UDEMY', 'EDUCATION', 'Courses/Books', 10),
        ('contains', 'COURSERA', 'EDUCATION', 'Courses/Books', 10),
        # TRANSFERS
        ('contains', 'CRED', 'TRANSFERS', 'Credit Card Payment', 10),
        ('contains', 'BILLDESK', 'TRANSFERS', 'Credit Card Payment', 10),
        ('contains', 'CREDIT CARD PAYMENT', 'TRANSFERS', 'Credit Card Payment', 10),
        # INCOME (salary sources from user's statement)
        ('contains', 'RSM US INTEGRATED', 'INCOME', 'Salary', 10),
    ]

    for rule_type, pattern, category, subcategory, priority in rules:
        db.add(ClassificationRule(
            rule_type=rule_type,
            pattern=pattern,
            category=category,
            subcategory=subcategory,
            priority=priority,
            is_system=True,
            is_active=True,
        ))

    db.commit()


def run_seeds(db: Session) -> None:
    seed_accounts(db)
    seed_app_settings(db)
    seed_classification_rules(db)
