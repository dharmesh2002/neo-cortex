from typing import Optional, TypedDict


class Customer(TypedDict, total=False):
    id: str
    name: str
    email: str
    company: str
    industry: str
    notes: str


class Lead(TypedDict):
    customer_id: str
    name: str
    score: int
    rating: str  # hot | warm | cold
    reason: str


class SalesState(TypedDict, total=False):
    query: str                      # who to look up (name, email or company)
    customer: Optional[Customer]    # Agent 1 output
    email_subject: str              # Agent 2 output
    email_body: str
    email_sent: bool
    response: Optional[str]         # Agent 3 output (customer's reply, if any)
    response_sentiment: str         # positive | negative | neutral | none
    lead: Optional[Lead]            # Agent 4 output
    log: list[str]
