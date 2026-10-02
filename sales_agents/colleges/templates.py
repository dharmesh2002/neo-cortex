"""Solitiq outreach copy for college placement / training cells. Honest, no invented results."""
import os

BUSINESS = os.getenv("BUSINESS_NAME", "Solitiq")
SENDER = os.getenv("SENDER_NAME", "Your Name")
PHONE = os.getenv("BUSINESS_PHONE", "+91-XXXXXXXXXX")
WEBSITE = os.getenv("BUSINESS_WEBSITE", "")
CITY = os.getenv("BUSINESS_CITY", "Gujarat")
PROGRAMS = "BE/B.Tech (Computer/IT), BCA, MCA, BSc and MSc (Computer Science/IT)"

SIGNATURE = f"\nRegards,\n{SENDER}\n{BUSINESS}\n{PHONE}" + (f"\n{WEBSITE}" if WEBSITE else "")
OPT_OUT = "\n\nIf you'd rather not receive emails from us, just reply STOP and we won't contact you again."

PITCH = {
    "placement": ("AI skills training tie-up for {company} students",
                  "{business} runs practical AI training programs that help {programs} students build industry-relevant skills "
                  "and become job-ready.\n\nWe would like to explore a training / placement-support tie-up with {company}. "
                  "Could you please share the right person to speak with, or a convenient time for a short call?"),
    "department": ("AI upskilling programme for your Computer/IT students",
                   "{business} offers hands-on AI training for {programs} students, aligned with what employers look for today.\n\n"
                   "Could you please forward this to your Training & Placement Officer or the department head? "
                   "We can share the syllabus outline and a pilot proposal for {company}."),
    "principal": ("Industry-aligned AI training for {company}",
                  "{business} partners with colleges to upskill {programs} students in practical AI, so they stay relevant for industry roles.\n\n"
                  "We would welcome a short conversation about a tie-up with {company}. May we share a one-page proposal, "
                  "or would you suggest the right contact in your placement or training cell?"),
    "general": ("AI training tie-up proposal - {company}",
                "{business} provides practical AI training for {programs} students.\n\n"
                "Could you please pass this to the Training & Placement cell? We would like to propose a tie-up for {company}."),
}
FOLLOWUP = ("Following up: AI training tie-up for {company}",
            "A quick follow-up on my earlier note. If a tie-up isn't a priority right now, no problem at all. "
            "Otherwise I'd be glad to send our programme outline and pilot proposal.")


def bucket(role: str) -> str:
    r = role.lower()
    if "placement" in r:
        return "placement"
    if "department" in r:
        return "department"
    if "principal" in r or "leader" in r:
        return "principal"
    return "general"


def build(kind: str, company: str, city: str):
    subj, body = FOLLOWUP if kind == "followup" else PITCH[kind]
    f = {"company": company, "business": BUSINESS, "programs": PROGRAMS}
    return (subj.format(**f), f"Dear {company} team,\n\n" + body.format(**f) + "\n" + SIGNATURE + OPT_OUT)


ORDER = {"placement": 0, "department": 1, "principal": 2, "followup": 3, "general": 4}
