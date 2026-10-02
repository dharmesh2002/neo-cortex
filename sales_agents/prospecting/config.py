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
    ("MG Motor India (Halol)", "Automotive", "Halol"),
    # Add specific dealerships here (e.g. Hyundai / Honda dealers) together with their website in websites.json.
]

# Official websites (verify - set your own in websites.json {"Company Name": "https://..."} to override).
WEBSITES = {
    "Zydus Lifesciences": "https://www.zyduslife.com", "Torrent Pharmaceuticals": "https://www.torrentpharma.com",
    "Intas Pharmaceuticals": "https://www.intaspharma.com", "Alembic Pharmaceuticals": "https://www.alembicpharmaceuticals.com",
    "Cadila Pharmaceuticals": "https://www.cadilapharma.com", "Sun Pharmaceutical Industries": "https://sunpharma.com",
    "Troikaa Pharmaceuticals": "https://www.troikaa.com", "Lincoln Pharmaceuticals": "https://www.lincolnpharma.com",
    "Unichem Laboratories": "https://www.unichemlabs.com", "Sanofi India": "https://www.sanofi.in",
    "Bank of Baroda": "https://www.bankofbaroda.in", "HDFC Bank": "https://www.hdfcbank.com",
    "ICICI Bank": "https://www.icicibank.com", "Axis Bank": "https://www.axisbank.com",
    "Kotak Mahindra Bank": "https://www.kotak.com", "IDFC First Bank": "https://www.idfcfirstbank.com",
    "AU Small Finance Bank": "https://www.aubank.in", "Bandhan Bank": "https://bandhanbank.com",
    "Tata Motors (Sanand)": "https://www.tatamotors.com", "Maruti Suzuki (Hansalpur)": "https://www.marutisuzuki.com",
    "MG Motor India (Halol)": "https://www.mgmotor.co.in",
}

# Medium-scale starter list from general knowledge - NOT verified. Check size/city/status before outreach.
# Websites are intentionally blank; the agent only accepts a site it can validate, or one you supply.
MID_CATALOG = [
    ("Concord Biotech", "Pharma", "Ahmedabad"), ("Dishman Carbogen Amcis", "Pharma", "Ahmedabad"),
    ("Sotac Pharmaceuticals", "Pharma", "Ahmedabad"), ("Ami Lifesciences", "Pharma", "Vadodara"),
    ("Sterling Biotech", "Pharma", "Vadodara"), ("Baroda Gujarat Gramin Bank", "Banking", "Vadodara"),
    ("Ahmedabad Mercantile Co-operative Bank", "Banking", "Ahmedabad"),
    ("Kalupur Commercial Co-operative Bank", "Banking", "Ahmedabad"),
    ("Nutan Nagarik Sahakari Bank", "Banking", "Ahmedabad"),
    ("Gujarat State Co-operative Bank", "Banking", "Ahmedabad"),
]
