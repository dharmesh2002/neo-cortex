"""Email send / receive. DRY_RUN (default) avoids real network I/O.

Real mode env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, IMAP_HOST, MAIL_FROM
"""
import email
import imaplib
import os
import smtplib
from email.message import EmailMessage

DRY_RUN = os.getenv("SALES_DRY_RUN", "1") != "0"


def send_email(to: str, subject: str, body: str) -> bool:
    if DRY_RUN:
        print(f"[dry-run] To: {to}\nSubject: {subject}\n\n{body}\n")
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["MAIL_FROM"], to, subject
    msg.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    return True


def fetch_reply(from_addr: str) -> str | None:
    """Return the latest unread reply body from `from_addr`, or None."""
    if DRY_RUN:
        return os.getenv("SALES_SIMULATED_REPLY")  # e.g. "Sounds great, let's talk"
    imap = imaplib.IMAP4_SSL(os.environ["IMAP_HOST"])
    imap.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    imap.select("INBOX")
    _, data = imap.search(None, "UNSEEN", "FROM", f'"{from_addr}"')
    ids = data[0].split()
    if not ids:
        imap.logout()
        return None
    _, msg_data = imap.fetch(ids[-1], "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])
    body = msg.get_payload(decode=True) if not msg.is_multipart() else msg.get_payload(0).get_payload(decode=True)
    imap.logout()
    return (body or b"").decode(errors="replace")
