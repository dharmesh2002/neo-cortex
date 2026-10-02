from typing import TypedDict


class Company(TypedDict, total=False):
    name: str
    sector: str
    city: str
    source: str
    size: str          # Large | Medium | (from your file)
    website: str
    score: int


class Contact(TypedDict, total=False):
    company: str
    role: str
    name: str          # only if found in a public source; may be empty
    source_url: str    # where it was found / where to verify
    confidence: str    # high | medium | lookup


class ProspectState(TypedDict, total=False):
    sectors: list[str]
    sizes: list[str]             # e.g. ['Medium']; empty = all
    regions: list[str]
    profile: str                 # ideal-customer description
    companies: list[Company]
    contacts: list[Contact]
    company_contacts: list[dict]  # public emails/phones from company websites
    report_path: str
    log: list[str]
