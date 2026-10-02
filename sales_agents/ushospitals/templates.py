"""Corporate upskilling pitch for teams of business analysts. CAN-SPAM footer reused from ushealth."""
import re

from ..ushealth.templates import BUSINESS, FOOTER, SIGNATURE

WHAT = ("an applied AI program that helps healthcare business analysts, including EDI and claims-data BAs, "
        "work faster and more accurately with AI tools in their day-to-day analysis and documentation")
REMOTE = ("{business} is based in India and delivers everything online, so we can run a free workshop for your BA team "
          "or hold a 20-minute video call (Zoom or Teams) at a time that suits your time zone.")

PITCH = {
    "learning": ("Free online AI workshop for your business analyst teams",
                 "{business} runs {what}.\n\n" + REMOTE + "\n\nWho on your learning and talent team would be the right person to schedule this with?"),
    "vendor": ("Training vendor introduction - AI upskilling for business analysts",
               "{business} would like to be considered as a training vendor for {company}. We run {what}.\n\n" + REMOTE +
               "\n\nCould you point us to your vendor registration process or the right contact?"),
    "partnerships": ("Partnership idea: AI upskilling for {company} business analysts",
                     "{business} runs {what}.\n\n" + REMOTE + "\n\nWho would be the right person to talk to about partnerships or training programs?"),
    "association": ("Free webinar proposal for {company} members: AI for healthcare EDI and data analysts",
                    "{business} runs {what}.\n\nWe would like to offer {company}'s members a free 45-minute educational webinar on "
                    "using AI tools in healthcare EDI and data analysis. {business} is based in India and delivers everything online, "
                    "so we can present live at a time that suits your members' time zones, or provide a recording.\n\n"
                    "Could you let us know who handles education or events for {company}, and what a proposal should include? "
                    "I can send a one-page outline right away."),
    "general": ("Free online AI workshop for {company} business analysts",
                "{business} runs {what}.\n\n" + REMOTE + "\n\nCould you please forward this to your learning and development team "
                "or the head of business analysis? If someone there would be the right person, I'd be glad to be introduced."),
}
FOLLOWUP = ("Following up: free AI workshop for {company} business analysts",
            "A quick follow-up on my earlier note. If this isn't a priority, no problem. "
            "Otherwise I'd be glad to send a one-page program outline.")


def bucket(role: str) -> str:
    r = role.lower()
    if "learning" in r or "talent" in r:
        return "learning"
    if "vendor" in r or "procure" in r:
        return "vendor"
    if "partner" in r:
        return "partnerships"
    if "association" in r:
        return "association"
    return "general"


def build(kind: str, company: str, city: str):
    subj, body = FOLLOWUP if kind == "followup" else PITCH[kind]
    company = re.sub(r"\s*\(.*?\)", "", company).strip()
    f = {"company": company, "business": BUSINESS, "what": WHAT}
    return subj.format(**f), f"Hello {company} team,\n\n" + body.format(**f) + "\n" + SIGNATURE + FOOTER


ORDER = {"learning": 0, "vendor": 1, "partnerships": 2, "association": 3, "followup": 4, "general": 5}
