"""Plain, honest outreach copy. No named person needed: addressed to the team behind a public inbox."""
import os
import re

BUSINESS = os.getenv("BUSINESS_NAME", "Your Company Name")
SENDER = os.getenv("SENDER_NAME", "Your Name")
PHONE = os.getenv("BUSINESS_PHONE", "+91-XXXXXXXXXX")
WEBSITE = os.getenv("BUSINESS_WEBSITE", "")
CITY = os.getenv("BUSINESS_CITY", "Ahmedabad")

SIGNATURE = f"\nRegards,\n{SENDER}\n{BUSINESS}, {CITY}\n{PHONE}" + (f"\n{WEBSITE}" if WEBSITE else "")
OPT_OUT = "\n\nIf you'd rather not receive emails from us, just reply STOP and we won't contact you again."

PITCH = {
    "hr": ("Joining kits for your new hires",
           "We make branded joining / welcome kits for new employees (bags, diaries, bottles, apparel and more), "
           "customised with your logo and delivered in {city} and across Gujarat.\n\n"
           "Could you share who handles onboarding kits at {company}, or let us send a short catalogue and sample pricing?"),
    "procurement": ("Corporate gifting supplier for {company}",
                    "We are a corporate gifting and branded merchandise supplier based in {city}. "
                    "We would like to be considered as a vendor for {company}'s gifting and onboarding-kit requirements.\n\n"
                    "Could you point us to your vendor registration process or the right person to send our catalogue to?"),
    "general": ("Corporate gifts and joining kits - {company}",
                "We supply customised corporate gifts and employee joining kits to companies in {city} and Gujarat.\n\n"
                "Would it be possible to forward this to your HR or purchase team? Happy to share a catalogue and sample pricing."),
}
FOLLOWUP = ("Following up: gifting / joining kits for {company}",
            "Just a quick follow-up on my earlier note. If this isn't relevant for {company}, no problem. "
            "Otherwise, I'd be glad to send our catalogue and sample pricing.")


def bucket(role: str) -> str:
    r = role.lower()
    if "hr" in r or "career" in r or "recruit" in r or "talent" in r:
        return "hr"
    if "procure" in r or "vendor" in r:
        return "procurement"
    return "general"


def build(kind: str, company: str, city: str):
    subj, body = FOLLOWUP if kind == "followup" else PITCH[kind]
    company = re.sub(r"\s*\(.*?\)", "", company).strip()
    f = {"company": company, "city": city or CITY}
    return (subj.format(**f),
            f"Dear {company} team,\n\n" + body.format(**f) + "\n" + SIGNATURE + OPT_OUT)
