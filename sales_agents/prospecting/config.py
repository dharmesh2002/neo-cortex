"""Business profile for a corporate-gifting / joining-kit supplier in Gujarat."""

REGIONS = ["Ahmedabad", "Vadodara", "Sanand", "Gandhinagar", "Halol"]

# Existing good customers - used to describe the "ideal customer" lookalike.
SEED_CUSTOMERS = [
    {"name": "Maril Pharma", "sector": "Pharma"},
    {"name": "M-NIL Pharma", "sector": "Pharma"},
    {"name": "Yes Bank", "sector": "Banking"},
    {"name": "Hyundai Concept Motors", "sector": "Automotive"},
]

SECTORS = ["Pharma", "Banking", "Automotive"]

# Who buys joining kits / corporate gifts: HR (onboarding), Admin, Procurement, Marketing/Brand.
DECISION_ROLES = [
    "HR Head", "CHRO", "Head Talent Acquisition", "HR Manager",
    "Admin Head", "Head Procurement", "Purchase Manager", "Marketing Head",
]

# Starter catalog of well-known companies per region (public knowledge, verify before use).
CATALOG = [
    ("Zydus Lifesciences", "Pharma", "Ahmedabad"), ("Torrent Pharmaceuticals", "Pharma", "Ahmedabad"),
    ("Intas Pharmaceuticals", "Pharma", "Ahmedabad"), ("Alembic Pharmaceuticals", "Pharma", "Vadodara"),
    ("Cadila Pharmaceuticals", "Pharma", "Ahmedabad"), ("Sun Pharmaceutical Industries", "Pharma", "Vadodara"),
    ("Troikaa Pharmaceuticals", "Pharma", "Ahmedabad"), ("Lincoln Pharmaceuticals", "Pharma", "Ahmedabad"),
    ("Unichem Laboratories", "Pharma", "Ahmedabad"), ("Sanofi India", "Pharma", "Ahmedabad"),
    ("Bank of Baroda", "Banking", "Vadodara"), ("HDFC Bank", "Banking", "Ahmedabad"),
    ("ICICI Bank", "Banking", "Ahmedabad"), ("Axis Bank", "Banking", "Ahmedabad"),
    ("Kotak Mahindra Bank", "Banking", "Ahmedabad"), ("IDFC First Bank", "Banking", "Ahmedabad"),
    ("AU Small Finance Bank", "Banking", "Ahmedabad"), ("Bandhan Bank", "Banking", "Ahmedabad"),
    ("Tata Motors (Sanand)", "Automotive", "Sanand"), ("Maruti Suzuki (Hansalpur)", "Automotive", "Ahmedabad"),
    ("MG Motor India (Halol)", "Automotive", "Halol"), ("Honda Cars / Honda Motorcycle dealers", "Automotive", "Ahmedabad"),
    ("Hyundai dealer network", "Automotive", "Ahmedabad"),
]
