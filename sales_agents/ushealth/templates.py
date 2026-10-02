"""US outreach copy. CAN-SPAM: real sender, honest subject, physical postal address, working opt-out."""
import os

BUSINESS = os.getenv("BUSINESS_NAME", "Solitiq")
SENDER = os.getenv("SENDER_NAME", "Your Name")
PHONE = os.getenv("BUSINESS_PHONE", "")
WEBSITE = os.getenv("BUSINESS_WEBSITE", "")
ADDRESS = os.getenv("POSTAL_ADDRESS", "[YOUR PHYSICAL POSTAL ADDRESS]")   # required by CAN-SPAM

SIGNATURE = f"\nBest regards,\n{SENDER}\n{BUSINESS}" + (f"\n{PHONE}" if PHONE else "") + (f"\n{WEBSITE}" if WEBSITE else "")
FOOTER = (f"\n\n--\n{BUSINESS} | {ADDRESS}\n"
          "This is a business email. If you'd prefer not to hear from us, reply STOP and we will not contact you again.")

WHAT = ("an applied AI program for students and early-career professionals in healthcare data roles "
        "(such as healthcare EDI business analysts: claims and X12 transactions) that teaches them to work efficiently with AI tools")

PITCH = {
    "career": ("AI upskilling for {company} students heading into healthcare data roles",
               "{business} runs {what}.\n\nWe'd like to offer {company}'s students a free intro session or webinar, "
               "and discuss a partnership. Who is the best person on your team to speak with?"),
    "program": ("AI skills for your health informatics / HIM students",
                "{business} runs {what}.\n\nWe'd welcome the chance to share the curriculum outline with you, and to host a guest session "
                "for {company} students if it's a fit. Could you point us to the right contact, or let us know if you'd like the outline?"),
    "workforce": ("Healthcare AI training - partnership with {company}",
                  "{business} runs {what}.\n\nWe are looking for training partners such as {company}'s continuing education team. "
                  "May we send a short program outline?"),
    "association": ("Guest webinar proposal on AI for healthcare data roles",
                    "{business} runs {what}.\n\nWe'd like to offer your members and student chapters a free educational webinar. "
                    "Who handles education or events for {company}?"),
    "general": ("Healthcare AI training partnership - {company}",
                "{business} runs {what}.\n\nCould you please forward this to your career services or health informatics program team? "
                "We'd like to offer students a free intro session."),
}
FOLLOWUP = ("Following up: AI training for {company} students",
            "A quick follow-up on my earlier note. If this isn't a priority, no problem. "
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
    f = {"company": company, "business": BUSINESS, "what": WHAT}
    return subj.format(**f), f"Hello {company} team,\n\n" + body.format(**f) + "\n" + SIGNATURE + FOOTER


ORDER = {"career": 0, "program": 1, "workforce": 2, "association": 3, "followup": 4, "general": 5}
