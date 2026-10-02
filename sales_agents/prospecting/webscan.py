"""Collect PUBLIC generic contact details (emails/phones/contact pages) from a company's own website."""
import re
import time
import urllib.request
from urllib.parse import urljoin, urlparse

PATHS = ["", "/contact", "/contact-us", "/contactus", "/careers", "/vendor", "/vendor-registration", "/procurement"]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:\(?0?\d{2,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,6}")
GENERIC = ("hr", "career", "recruit", "talent", "procure", "purchase", "vendor", "supplier", "sourcing",
           "admin", "info", "contact", "marketing", "corporate", "enquiry", "inquiry", "csr")
BAD_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (contact-sheet bot)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if "html" not in r.headers.get("Content-Type", "html"):
            return ""
        return r.read(1_500_000).decode("utf-8", errors="ignore")


def scan_site(base_url: str, delay: float = 1.0) -> dict:
    """Return {emails: [(email, page)], phones: [(phone, page)], pages: [urls that loaded]}."""
    host = urlparse(base_url).netloc.replace("www.", "")
    emails, phones, pages = {}, {}, []
    for path in PATHS:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            html = _fetch(url)
        except Exception:
            continue
        pages.append(url)
        text = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S | re.I)
        text = text.replace("[at]", "@").replace("(at)", "@").replace("&#64;", "@")
        for e in EMAIL_RE.findall(text):
            e = e.lower().rstrip(".")
            if e.endswith(BAD_EXT):
                continue
            local, _, dom = e.partition("@")
            # keep company-domain addresses, or role-style addresses
            if host.split(".")[0] in dom or any(g in local for g in GENERIC):
                emails.setdefault(e, url)
        for tel in re.findall(r"tel:([+\d\s()-]{8,20})", html):
            phones.setdefault(tel.strip(), url)
        time.sleep(delay)
    return {"emails": list(emails.items()), "phones": list(phones.items()), "pages": pages}


def role_of(email: str) -> str:
    local = email.split("@")[0]
    for g, label in (("hr", "HR"), ("career", "HR / Careers"), ("recruit", "HR / Recruitment"), ("talent", "HR / Talent"),
                     ("procure", "Procurement"), ("purchase", "Procurement"), ("vendor", "Procurement / Vendor"),
                     ("supplier", "Procurement / Vendor"), ("sourcing", "Procurement"), ("admin", "Admin"),
                     ("marketing", "Marketing"), ("csr", "CSR")):
        if g in local:
            return label
    return "General"
