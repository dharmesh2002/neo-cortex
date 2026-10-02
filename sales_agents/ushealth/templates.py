"""US outreach copy. CAN-SPAM: real sender, honest subject, physical postal address, working opt-out."""
import os
import re

BUSINESS = os.getenv("BUSINESS_NAME", "Solitiq")
SENDER = os.getenv("SENDER_NAME", "Your Name")
PHONE = os.getenv("BUSINESS_PHONE", "")
WEBSITE = os.getenv("BUSINESS_WEBSITE", "")
ADDRESS = os.getenv("POSTAL_ADDRESS", "[YOUR PHYSICAL POSTAL ADDRESS]")   # required by CAN-SPAM

SIGNATURE = f"\nBest regards,\n{SENDER}\n{BUSINESS}" + (f"\n{PHONE}" if PHONE else "") + (f"\n{WEBSITE}" if WEBSITE else "")
FOOTER = (f"\n\n--\n{BUSINESS} | {ADDRESS}\n"
          f"This is a commercial email from {BUSINESS}. If you'd prefer not to hear from us, reply STOP and we will not contact you again.")

WHAT = ("an applied AI program for students and early-career professionals in healthcare data roles "
        "(such as healthcare EDI business analysts: claims and X12 transactions) that teaches them to work efficiently with AI tools")

REMOTE = ("{business} is based in India and delivers everything online, so we can host a free webinar for your students "
          "or hold a 20-minute video call (Zoom or Teams) at a time that suits your time zone.")

PITCH = {
    "career": ("Free online AI session for {company} students in healthcare data roles",
               "{business} runs {what}.\n\n" + REMOTE + "\n\nWho on your team would be the right person to schedule this with?"),
    "program": ("Free online guest session on AI for your health informatics / HIM students",
                "{business} runs {what}.\n\n" + REMOTE + "\n\nCould you point us to the right contact, or would you like our one-page "
                "curriculum outline first?"),
    "workforce": ("Online AI training partnership with {company}",
                  "{business} runs {what}.\n\n" + REMOTE + "\n\nMay we send a short program outline to your continuing education team?"),
    "association": ("Free webinar proposal for your members and student chapters",
                    "{business} runs {what}.\n\n" + REMOTE + "\n\nWho handles education or events for {company}?"),
    "general": ("Free online AI webinar for {company} students",
                "{business} runs {what}.\n\n" + REMOTE + "\n\nCould you please forward this to your career services or health "
                "informatics program team?"),
}
FOLLOWUP = ("Following up: free online AI session for {company} students",
            "A quick follow-up on my earlier note. If a webinar or short video call isn't a priority right now, no problem. "
            "Otherwise I'd be glad to send a one-page program outline.")


def bucket(role: str) -> str:
    r = role.lower()
    if "career" in r or "employer" in r:
        return "career"
    if "program" in r or "admission" in r:
        return "program"
    if "continuing" in r or "workforce" in r:
        return "workforce"
    if "association" in r:
        return "association"
    return "general"


def build(kind: str, company: str, city: str):
    subj, body = FOLLOWUP if kind == "followup" else PITCH[kind]
    company = re.sub(r"\s*\(.*?\)", "", company).strip()   # "X University (Health Informatics)" -> "X University"
    f = {"company": company, "business": BUSINESS, "what": WHAT}
    return subj.format(**f), f"Hello {company} team,\n\n" + body.format(**f) + "\n" + SIGNATURE + FOOTER


ORDER = {"career": 0, "program": 1, "workforce": 2, "association": 3, "followup": 4, "general": 5}
