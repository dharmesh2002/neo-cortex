"""Automated outreach to public company inboxes.

  python -m sales_agents.outreach.run                 # preview only (nothing is sent)
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
from .templates import bucket, build

SENT, UNSUB, LEADS, PREVIEW = "sent_log.csv", "unsubscribe.txt", "leads.csv", "outbox_preview.csv"
FOLLOWUP_AFTER_DAYS = 5


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _unsub() -> set:
    return {l.strip().lower() for l in open(UNSUB, encoding="utf-8")} if os.path.exists(UNSUB) else set()


def _meta() -> dict:
    return {r["name"].lower(): r for r in _read("companies.csv")}


def plan(limit: int, roles: set) -> list[dict]:
    contacts = [r for r in _read("company_contacts.csv") if r["type"] == "email"]
    sent = {}
    for r in _read(SENT):
        sent.setdefault(r["email"].lower(), []).append(r)
    contacted = {r["company"] for r in _read(SENT)}
    blocked, meta, out = _unsub(), _meta(), []
    for c in contacts:
        email = c["value"].lower()
        kind = bucket(c["role"])
        if email in blocked or kind not in roles:
            continue
        history = sent.get(email, [])
        city = meta.get(c["company"].lower(), {}).get("city", "")
        if not history:
            if c["company"] in contacted:       # already wrote to another inbox of this company
                continue
            stage = kind
        elif len(history) == 1 and datetime.fromisoformat(history[0]["date"]).date() <= date.today() - timedelta(days=FOLLOWUP_AFTER_DAYS) \
                and history[0]["status"] != "replied":
            stage = "followup"
        else:
            continue
        subject, body = build(stage, c["company"], city)
        out.append({"email": email, "company": c["company"], "stage": stage, "subject": subject, "body": body})
    # HR / procurement first, generic last
    order = {"hr": 0, "procurement": 1, "followup": 2, "general": 3}
    out.sort(key=lambda x: order[x["stage"]])
    seen, uniq = set(), []                       # one mail per company per run
    for x in out:
        if x["company"] not in seen:
            seen.add(x["company"]); uniq.append(x)
    return uniq[:limit]


def send_all(limit: int, roles: set, really_send: bool):
    batch = plan(limit, roles)
    with open(PREVIEW, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "company", "stage", "subject", "body"])
        w.writeheader(); w.writerows(batch)
    print(f"{len(batch)} emails planned -> {PREVIEW}")
    if not really_send:
        print("Preview only. Review the file, then run with --send to send.")
        return
    if mailer.DRY_RUN:
        print("SALES_DRY_RUN is on, so NOTHING is really sent and sent_log.csv is not updated.\n"
              "Set SALES_DRY_RUN=0 plus SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_FROM to send for real.")
        return
    new = not os.path.exists(SENT)
    with open(SENT, "a", newline="", encoding="utf-8") as f:
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
    rows = _read(SENT)
    leads = {r["email"]: r for r in _read(LEADS)}
    for r in rows:
        email = r["email"]
        reply = mailer.fetch_reply(email)
        if not reply:
            continue
        t = reply.lower()
        if "stop" in t.split() or any(w in t for w in NEGATIVE):
            with open(UNSUB, "a", encoding="utf-8") as f:
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
        with open(LEADS, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["email", "company", "sentiment", "score", "rating", "reply"])
            w.writeheader(); w.writerows(sorted(leads.values(), key=lambda x: -int(x["score"])))
        print(f"wrote {LEADS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--check-replies", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--roles", default="hr,procurement,general")
    a = ap.parse_args()
    if a.check_replies:
        check_replies()
    else:
        send_all(a.limit, set(a.roles.split(",")), a.send)
