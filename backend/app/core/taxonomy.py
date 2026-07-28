TAXONOMY = {
    "HOUSING": {
        "elasticity": "fixed",
        "subcategories": ["Rent", "Maintenance/Society", "Home Repairs"],
        "confidence_threshold": 0.85,
    },
    "TRANSPORTATION": {
        "elasticity": "semi_flexible",
        "subcategories": ["Fuel", "Public Transit", "Ride Hailing", "Parking/Tolls"],
        "confidence_threshold": 0.85,
    },
    "FOOD & DINING": {
        "elasticity": "flexible",
        "subcategories": ["Groceries", "Food Delivery", "Restaurants", "Coffee/Snacks", "Canteen"],
        "confidence_threshold": 0.85,
    },
    "UTILITIES & BILLS": {
        "elasticity": "semi_flexible",
        "subcategories": ["Electricity", "Water", "Internet/Phone", "Gas", "Subscriptions"],
        "confidence_threshold": 0.85,
    },
    "FINANCIAL OBLIGATIONS": {
        "elasticity": "fixed",
        "subcategories": ["EMI - Loan", "EMI - Credit Card", "Insurance Premium", "SIP/Investment", "Bank Charges"],
        "confidence_threshold": 0.95,
    },
    "HEALTH & WELLNESS": {
        "elasticity": "semi_flexible",
        "subcategories": ["Medical/Pharmacy", "Gym/Fitness", "Personal Care", "Hospital"],
        "confidence_threshold": 0.85,
    },
    "SHOPPING": {
        "elasticity": "flexible",
        "subcategories": ["Clothing", "Electronics", "Home/Kitchen", "General", "Online Shopping"],
        "confidence_threshold": 0.85,
    },
    "ENTERTAINMENT": {
        "elasticity": "flexible",
        "subcategories": ["Subscriptions", "Movies/Events", "Gaming", "Sports"],
        "confidence_threshold": 0.85,
    },
    "EDUCATION": {
        "elasticity": "semi_flexible",
        "subcategories": ["Courses/Books", "Software/Tools"],
        "confidence_threshold": 0.85,
    },
    "TRANSFERS": {
        "elasticity": "none",
        "subcategories": ["Credit Card Payment", "Own Account Transfer", "Investment Transfer"],
        "confidence_threshold": 0.95,
        "exclude_from_spend": True,
    },
    "INCOME": {
        "elasticity": "none",
        "subcategories": ["Salary", "Freelance", "Refund", "Cashback", "Interest", "Other Income"],
        "confidence_threshold": 0.90,
        "is_income": True,
    },
    "MISCELLANEOUS": {
        "elasticity": "flexible",
        "subcategories": ["Personal", "Gifts", "Donations", "Other"],
        "confidence_threshold": 0.80,
    },
}
