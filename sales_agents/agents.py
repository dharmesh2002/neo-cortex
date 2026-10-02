from . import crm, mailer
from .llm import ask, get_llm
from .state import SalesState

POSITIVE = ("interested", "great", "yes", "sounds good", "let's talk", "demo", "call", "pricing", "love")
NEGATIVE = ("not interested", "unsubscribe", "no thanks", "stop", "remove me", "busy")


def _log(state: SalesState, msg: str) -> list[str]:
    return [*state.get("log", []), msg]


# ── Agent 1: Find customer details ──
def find_customer_agent(state: SalesState) -> dict:
    customer = crm.find_customer(state["query"])
    msg = f"Agent1: found {customer['name']} <{customer['email']}>" if customer else "Agent1: no customer found"
    return {"customer": customer, "log": _log(state, msg)}


# ── Agent 2: Generate email and send ──
def email_agent(state: SalesState) -> dict:
    c = state["customer"]
    subject = f"Helping {c['company']} grow"
    body = (f"Hi {c['name'].split()[0]},\n\nI noticed {c['company']} works in {c['industry']}. "
            f"{c.get('notes', '')}. I'd love to show how we can help — do you have 15 minutes this week?\n\nBest regards")
    if llm := get_llm():
        body = ask(llm, f"Write a short, friendly sales email body (no subject line) to this customer: {c}") or body
    sent = mailer.send_email(c["email"], subject, body)
    return {"email_subject": subject, "email_body": body, "email_sent": sent,
            "log": _log(state, f"Agent2: email {'sent' if sent else 'FAILED'} to {c['email']}")}


# ── Agent 3: Check response ──
def check_response_agent(state: SalesState) -> dict:
    reply = mailer.fetch_reply(state["customer"]["email"])
    if not reply:
        sentiment = "none"
    else:
        text = reply.lower()
        if any(w in text for w in NEGATIVE):
            sentiment = "negative"
        elif any(w in text for w in POSITIVE):
            sentiment = "positive"
        else:
            sentiment = "neutral"
        if llm := get_llm():
            out = ask(llm, f"Classify this email reply as exactly one word: positive, negative or neutral.\n\n{reply}")
            sentiment = out.strip().lower().split()[0].strip(".") if out else sentiment
    return {"response": reply, "response_sentiment": sentiment,
            "log": _log(state, f"Agent3: response sentiment = {sentiment}")}


# ── Agent 4: Analyze potential leads ──
def analyze_leads_agent(state: SalesState) -> dict:
    c = state["customer"]
    score = {"positive": 80, "neutral": 45, "none": 20, "negative": 0}.get(state.get("response_sentiment", "none"), 20)
    if "pricing" in c.get("notes", "").lower() or "webinar" in c.get("notes", "").lower():
        score += 15  # prior engagement
    score = min(score, 100)
    rating = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    reason = f"reply sentiment={state.get('response_sentiment')}; notes='{c.get('notes', '')}'"
    return {"lead": {"customer_id": c["id"], "name": c["name"], "score": score, "rating": rating, "reason": reason},
            "log": _log(state, f"Agent4: {c['name']} is a {rating} lead (score {score})")}
