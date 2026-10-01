"""Customer store. Reads customers.json (list of Customer dicts) if present,
otherwise uses a small built-in sample. Swap for a real CRM/DB as needed."""
import json
import os

_SAMPLE = [
    {"id": "c1", "name": "Priya Sharma", "email": "priya@acme.com", "company": "Acme Corp",
     "industry": "Retail", "notes": "Asked about pricing last month"},
    {"id": "c2", "name": "John Miller", "email": "john@globex.com", "company": "Globex",
     "industry": "Manufacturing", "notes": "Attended our webinar"},
]


def load_customers() -> list[dict]:
    path = os.getenv("CUSTOMERS_FILE", os.path.join(os.path.dirname(__file__), "customers.json"))
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return _SAMPLE


def find_customer(query: str) -> dict | None:
    q = query.strip().lower()
    for c in load_customers():
        if q in (c["email"].lower(), c["id"].lower()) or q in c["name"].lower() or q in c["company"].lower():
            return c
    return None
