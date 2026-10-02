"""Semi-automatic LinkedIn helper. YOU click Connect/Send; this does the planning and writing.

  python -m sales_agents.outreach.linkedin --today [--n 5]
      -> today's to-do: next people to find, plus follow-ups that are due (reads linkedin_shortlist.csv)
  python -m sales_agents.outreach.linkedin --msg --name "Jane Doe" --company "Availity" --role "Director of Business Analysis"
      -> ready-to-paste connection note, thank-you message and follow-up for that person
Dates in the sheet: type them as YYYY-MM-DD (e.g. 2026-10-05).
"""
import argparse
import csv
import os
from datetime import date, datetime

SHEET = "linkedin_shortlist.csv"
FOLLOWUP_DAYS = 5
SENDER = os.getenv("SENDER_NAME", "Your Name").split()[0]


def _date(s: str):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def messages(name: str, company: str, role: str) -> dict:
    first = (name or "there").split()[0]
    return {
        "1. Connection note (under 300 characters)":
            f"Hi {first}, I run Solitiq, an applied AI program that helps healthcare EDI and claims business analysts work "
            f"faster with AI tools. I'd value connecting and hearing how {company} approaches upskilling. - {SENDER}",
        "2. After they accept":
            f"Thanks for connecting, {first}. We help healthcare BA teams, especially EDI and claims analysts, use AI tools to "
            f"speed up analysis and documentation. We deliver online, and I'd be glad to run a free 45-minute workshop for your "
            f"team, or have a 20-minute video call at a time that suits you. Would either be useful? {SENDER}, Solitiq",
        f"3. Follow-up after {FOLLOWUP_DAYS}-7 days of silence":
            f"Hi {first}, just a quick follow-up in case my earlier message got buried. Happy to send a one-page outline of "
            f"the workshop if that's easier. Thanks, {SENDER}",
    }


def today(n: int):
    if not os.path.exists(SHEET):
        raise SystemExit(f"{SHEET} not found - run from the neo-cortex folder (git pull first).")
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8-sig")))
    now = date.today()
    due, fresh, waiting = [], [], 0
    for r in rows:
        sent = _date(r.get("connect_sent_date", ""))
        if r.get("replied", "").strip():
            continue
        if sent:
            days = (now - sent).days
            if days >= FOLLOWUP_DAYS:
                due.append((days, r))
            else:
                waiting += 1
        elif not r.get("person_name", "").strip() and len(fresh) < n:
            fresh.append(r)
    print(f"=== Today ({now}) ===\n")
    print(f"A) FOLLOW-UPS DUE ({len(due)})")
    for days, r in due:
        who = r.get("person_name") or "(name?)"
        print(f"   - {who} @ {r['company']} - connected {days} days ago -> send message 3"
              f"{'' if r.get('accepted', '').strip() else ' (not accepted yet: just wait, or send a plain follow-up)'}")
    if not due:
        print("   none")
    print(f"\nB) FIND AND CONNECT WITH {len(fresh)} NEW PEOPLE (open the link, pick one matching title, fill the sheet)")
    for r in fresh:
        print(f"   [P{r['priority']}] {r['company']} - {r['target_role']}\n        {r['linkedin_search']}")
    print(f"\nC) WAITING for replies: {waiting}")
    print("\nFor ready-to-paste messages for a person: python -m sales_agents.outreach.linkedin --msg --name \"Jane Doe\" "
          "--company \"Company\" --role \"Their title\"")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--msg", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument("--company", default="your company")
    ap.add_argument("--role", default="")
    a = ap.parse_args()
    if a.msg:
        for title, text in messages(a.name, a.company, a.role).items():
            print(f"\n{title}\n{'-' * 60}\n{text}")
    else:
        today(a.n)
