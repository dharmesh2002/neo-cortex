from typing import TypedDict


class Company(TypedDict, total=False):
    name: str
    sector: str
    city: str
    source: str
    score: int


class Contact(TypedDict, total=False):
    company: str
    role: str
    name: str          # only if found in a public source; may be empty
    source_url: str    # where it was found / where to verify
    confidence: str    # high | medium | lookup


class ProspectState(TypedDict, total=False):
    sectors: list[str]
    regions: list[str]
    profile: str                 # ideal-customer description
    companies: list[Company]
    contacts: list[Contact]
    report_path: str
    log: list[str]
