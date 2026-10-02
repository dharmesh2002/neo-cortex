"""Automated outreach to public company inboxes.

  python -m sales_agents.outreach.run [--profile colleges]   # preview only (nothing is sent)
  python -m sales_agents.outreach.run --send          # really send (needs SMTP env + SALES_DRY_RUN=0)
  python -m sales_agents.outreach.run --check-replies # read replies, update leads.csv, honour STOP
Options: --limit N (default 25/day)  --roles hr,procurement,general
"""
import argparse
import csv
import os
from datetime import date, datetime, timedelta

from .. import mailer
from ..agents import NEGATIVE, POSITIVE
from . import templates as _gifting
from ..colleges import templates as _colleges
from ..ushealth import templates as _us
from ..ushospitals import templates as _hosp

FOLLOWUP_AFTER_DAYS = 5

# One outreach engine, several businesses. `--profile` picks files + email copy.
PROFILES = {
    "gifting": dict(contacts="company_contacts.csv", meta="companies.csv", sent="sent_log.csv", unsub="unsubscribe.txt",
                    leads="leads.csv", preview="outbox_preview.csv", bucket=_gifting.bucket, build=_gifting.build,
                    order={"hr": 0, "procurement": 1, "followup": 2, "general": 3}, roles="hr,procurement,general"),
    "colleges": dict(contacts="college_contacts.csv", meta="colleges.csv", sent="sent_log_colleges.csv",
                     unsub="unsubscribe_colleges.txt", leads="leads_colleges.csv", preview="outbox_preview_colleges.csv",
                     bucket=_colleges.bucket, build=_colleges.build, order=_colleges.ORDER,
                     roles="placement,department,principal,general"),
    "ushealth": dict(contacts="us_contacts.csv", meta="institutions_us.csv", sent="sent_log_us.csv",
                     unsub="unsubscribe_us.txt", leads="leads_us.csv", preview="outbox_preview_us.csv",
                     bucket=_us.bucket, build=_us.build, order=_us.ORDER,
                     roles="career,program,workforce,association,general",
                     require_env=["POSTAL_ADDRESS"]),   # CAN-SPAM: physical postal address in every email
    "ushospitals": dict(contacts="hospital_contacts.csv", meta="hospitals_us.csv", sent="sent_log_hospitals.csv",
                        unsub="unsubscribe_hospitals.txt", leads="leads_hospitals.csv", preview="outbox_preview_hospitals.csv",
                        bucket=_hosp.bucket, build=_hosp.build, order=_hosp.ORDER,
                        roles="learning,vendor,partnerships,association,general", require_env=["POSTAL_ADDRESS"]),
}
P = PROFILES["gifting"]


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _unsub() -> set:
    u = P["unsub"]
    return {l.strip().lower() for l in open(u, encoding="utf-8")} if os.path.exists(u) else set()


def _meta() -> dict:
    return {r["name"].lower(): r for r in _read(P["meta"])}


def plan(limit: int, roles: set, only: list = None) -> list[dict]:
    contacts = [r for r in _read(P["contacts"]) if r["type"] == "email"]
    sent = {}
    for r in _read(P["sent"]):
        sent.setdefault(r["email"].lower(), []).append(r)
    contacted = {r["company"] for r in _read(P["sent"])}
    replied_orgs = {r["company"] for r in _read(P["sent"]) if r["status"] == "replied"}   # anyone there replied -> no follow-ups
    if only:                                   # --only "WEDI,HFMA": restrict to organisations whose name matches
        contacts = [c for c in contacts if any(o.lower() in c["company"].lower() for o in only)]
    blocked, meta, out = _unsub(), _meta(), []
    for c in contacts:
        email = c["value"].lower()
        kind = P["bucket"](c["role"])
        if email in blocked or kind not in roles:
            continue
        history = sent.get(email, [])
        city = meta.get(c["company"].lower(), {}).get("city", "")
        if not history:
            if c["company"] in contacted:       # already wrote to another inbox of this company
                continue
            stage = kind
        elif c["company"] in replied_orgs:
            continue
        elif len(history) == 1 and datetime.fromisoformat(history[0]["date"]).date() <= date.today() - timedelta(days=FOLLOWUP_AFTER_DAYS) \
                and history[0]["status"] != "replied":
            stage = "followup"
        else:
            continue
        subject, body = P["build"](stage, c["company"], city)
        out.append({"email": email, "company": c["company"], "stage": stage, "subject": subject, "body": body})
    # HR / procurement first, generic last
    out.sort(key=lambda x: P["order"][x["stage"]])
    seen, uniq = set(), []                       # one mail per company per run
    for x in out:
        if x["company"] not in seen:
            seen.add(x["company"]); uniq.append(x)
    return uniq[:limit]


def send_all(limit: int, roles: set, really_send: bool, only: list = None):
    batch = plan(limit, roles, only)
    preview = P["preview"]
    try:
        f = open(preview, "w", newline="", encoding="utf-8-sig")
    except PermissionError:      # file is open in Excel - save under a new name instead
        preview = preview.replace(".csv", f"_{datetime.now():%H%M%S}.csv")
        print(f"{P['preview']} is open in another program (close it in Excel); saving to {preview} instead.")
        f = open(preview, "w", newline="", encoding="utf-8-sig")
    with f:
        w = csv.DictWriter(f, fieldnames=["email", "company", "stage", "subject", "body"])
        w.writeheader(); w.writerows(batch)
    print(f"{len(batch)} emails planned -> {preview}")
    if not really_send:
        print("Preview only. Review the file, then run with --send to send.")
        return
    missing = [k for k in P.get("require_env", []) if not os.getenv(k)]
    if missing and not mailer.DRY_RUN:
        raise SystemExit(f"Refusing to send: set {', '.join(missing)} first (US law requires a physical address in commercial email).")
    if mailer.DRY_RUN:
        print("SALES_DRY_RUN is on, so NOTHING is really sent and the sent log is not updated.\n"
              "Set SALES_DRY_RUN=0 plus SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_FROM to send for real.")
        return
    new = not os.path.exists(P["sent"])
    with open(P["sent"], "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["email", "company", "stage", "date", "status"])
        for m in batch:
            try:
                mailer.send_email(m["email"], m["subject"], m["body"])
                w.writerow([m["email"], m["company"], m["stage"], datetime.now().isoformat(timespec="seconds"), "sent"])
                f.flush()
                import time; time.sleep(20)       # slow drip: looks human, protects sender reputation
            except Exception as e:
                print(f"  FAILED {m['email']}: {e}")


def check_replies():
    rows = _read(P["sent"])
    leads = {r["email"]: r for r in _read(P["leads"])}
    for r in rows:
        email = r["email"]
        reply = mailer.fetch_reply(email)
        if not reply:
            continue
        t = reply.lower()
        if "stop" in t.split() or any(w in t for w in NEGATIVE):
            with open(P["unsub"], "a", encoding="utf-8") as f:
                f.write(email + "\n")
            sentiment, score = "negative", 0
        elif any(w in t for w in POSITIVE):
            sentiment, score = "positive", 85
        else:
            sentiment, score = "neutral", 50
        leads[email] = {"email": email, "company": r["company"], "sentiment": sentiment,
                        "score": score, "rating": "hot" if score >= 70 else "warm" if score >= 40 else "cold",
                        "reply": reply.strip()[:300].replace("\n", " ")}
        print(f"  {r['company']}: {sentiment}")
    if leads:
        with open(P["leads"], "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["email", "company", "sentiment", "score", "rating", "reply"])
            w.writeheader(); w.writerows(sorted(leads.values(), key=lambda x: -int(x["score"])))
        print(f"wrote {P['leads']}")


def add_contact(email: str, company: str, role: str, source: str):
    """Add an address you found by hand (e.g. on the organisation's own contact page)."""
    path = P["contacts"]
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["company", "type", "value", "role", "source_url", "city"])
        w.writerow([company, "email", email.strip().lower(), role, source, ""])
    print(f"added {email} for {company} ({role}) -> {path}")


def mark_sent(emails: list, company: str):
    """Record emails you sent by hand, so follow-up timing and de-duplication work."""
    new = not os.path.exists(P["sent"])
    with open(P["sent"], "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["email", "company", "stage", "date", "status"])
        for e in emails:
            w.writerow([e.strip().lower(), company, "manual", datetime.now().isoformat(timespec="seconds"), "sent"])
    print(f"recorded {len(emails)} manual email(s) for {company}")


def mark_replied(emails: list):
    rows = _read(P["sent"])
    hit = {e.strip().lower() for e in emails}
    for r in rows:
        if r["email"].lower() in hit:
            r["status"] = "replied"
    with open(P["sent"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["email", "company", "stage", "date", "status"])
        w.writeheader(); w.writerows(rows)
    print(f"marked as replied: {', '.join(sorted(hit))} (no follow-ups will be planned)")


def status():
    rows = _read(P["sent"])
    if not rows:
        print("Nothing sent yet.")
        return
    print(f"{'EMAIL':38} {'COMPANY':30} {'SENT':10} {'DAYS':>4}  NEXT STEP")
    for r in rows:
        d = (date.today() - datetime.fromisoformat(r["date"]).date()).days
        if r["status"] == "replied":
            nxt = "Replied - continue the conversation by hand"
        elif d >= FOLLOWUP_AFTER_DAYS:
            nxt = "Follow-up due now (run the agent preview)"
        else:
            nxt = f"Wait - follow-up in {FOLLOWUP_AFTER_DAYS - d} day(s)"
        print(f"{r['email'][:37]:38} {r['company'][:29]:30} {r['date'][:10]:10} {d:>4}  {nxt}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--check-replies", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--add-contact", default=None, help="an email you found by hand; use with --company, --role, --source")
    ap.add_argument("--role", default="General", help="role label for --add-contact (e.g. General, Partnerships, Learning & Talent)")
    ap.add_argument("--source", default="added by hand", help="page where you found the address")
    ap.add_argument("--mark-sent", default=None, help="comma-separated emails you sent by hand")
    ap.add_argument("--company", default="", help="organisation name for --mark-sent")
    ap.add_argument("--mark-replied", default=None, help="comma-separated emails that replied")
    ap.add_argument("--status", action="store_true", help="show what was sent and what to do next")
    ap.add_argument("--profile", choices=list(PROFILES), default="gifting")
    ap.add_argument("--roles", default=None)
    ap.add_argument("--only", default=None, help='comma-separated organisation names, e.g. "WEDI,HFMA,AAPC"')
    a = ap.parse_args()
    P = PROFILES[a.profile]
    a.roles = a.roles or P["roles"]
    if a.add_contact:
        add_contact(a.add_contact, a.company or "(unknown)", a.role, a.source)
    elif a.mark_sent:
        mark_sent(a.mark_sent.split(","), a.company or "(unknown)")
    elif a.mark_replied:
        mark_replied(a.mark_replied.split(","))
    elif a.status:
        status()
    elif a.check_replies:
        check_replies()
    else:
        send_all(a.limit, set(a.roles.split(",")), a.send, [x.strip() for x in a.only.split(",")] if a.only else None)
