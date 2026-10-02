"""Collect PUBLIC generic contact details (emails/phones/contact pages) from a company's own website."""
import re
import time
import urllib.request
from urllib.parse import unquote, urljoin, urlparse

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


def _site_key(host: str) -> str:
    """'healthy.kaiserpermanente.org' -> 'kaiserpermanente'; 'abc.ac.in' -> 'abc'."""
    parts = host.split(":")[0].split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "ac", "org", "gov", "edu", "com", "net", "nic"):
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else parts[0]


def scan_site(base_url: str, delay: float = 1.0, paths=None, generic=None, same_domain_only: bool = False) -> dict:
    """Return {emails: [(email, page)], phones: [(phone, page)], pages: [urls that loaded]}.
    same_domain_only=True keeps only addresses on the organisation's own domain (drops other orgs, .gov, gmail)."""
    host = urlparse(base_url).netloc.replace("www.", "")
    key = _site_key(host)
    paths, generic = paths or PATHS, generic or GENERIC
    emails, phones, pages = {}, {}, []
    for path in paths:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            html = _fetch(url)
        except Exception:
            continue
        pages.append(url)
        text = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S | re.I)
        text = text.replace("[at]", "@").replace("(at)", "@").replace("&#64;", "@")
        for e in EMAIL_RE.findall(text):
            e = re.sub(r"^[^a-z0-9]+", "", unquote(e).lower().rstrip("."))   # "%20name@x" -> "name@x"
            if not e or e.endswith(BAD_EXT):
                continue
            local, _, dom = e.partition("@")
            on_own_domain = key in dom
            if same_domain_only:
                if on_own_domain:
                    emails.setdefault(e, url)
            elif on_own_domain or any(g in local for g in generic):   # own domain, or role-style address
                emails.setdefault(e, url)
        for tel in re.findall(r"tel:([+\d\s()-]{8,20})", html):
            if sum(c.isdigit() for c in tel) >= 10:                  # drop cut-off numbers like "866-707-"
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
