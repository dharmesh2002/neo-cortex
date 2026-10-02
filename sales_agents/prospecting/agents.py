import json
import re

from ..llm import ask, get_llm
from . import config
from .search import find_website, linkedin_lookup_url, web_search
from .webscan import role_of, scan_site
from .state import ProspectState


def _log(s: ProspectState, m: str) -> list[str]:
    return [*s.get("log", []), m]


# ── Agent A: Understand the ideal customer from existing good customers ──
def profile_agent(s: ProspectState) -> dict:
    sectors = s.get("sectors") or config.SECTORS
    regions = s.get("regions") or config.REGIONS
    seeds = ", ".join(f"{c['name']} ({c['sector']})" for c in config.SEED_CUSTOMERS)
    profile = (f"Mid/large employers in {', '.join(regions)} within {', '.join(sectors)} that hire regularly "
               f"(joining kits) and buy corporate gifts. Lookalikes of: {seeds}.")
    return {"sectors": sectors, "regions": regions, "profile": profile,
            "log": _log(s, "ProfileAgent: ideal customer profile built")}


def _load_companies_csv() -> dict:
    """Optional companies.csv in the current folder. Columns: name,sector,city,size,website (only name is required)."""
    import csv
    import os
    out = {}
    if not os.path.exists("companies.csv"):
        return out
    with open("companies.csv", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("name"):
                continue
            out[row["name"].lower()] = {"name": row["name"], "sector": row.get("sector") or "Other",
                                        "city": row.get("city") or "Gujarat", "source": "companies.csv",
                                        "size": row.get("size") or "Unknown", "website": row.get("website", "")}
    print(f"  loaded {len(out)} companies from companies.csv")
    return out


# ── Agent B: Discover target companies ──
def discover_agent(s: ProspectState) -> dict:
    found: dict[str, dict] = {}
    for size, catalog in (("Large", config.CATALOG), ("Medium", config.MID_CATALOG)):   # offline starter lists
        for name, sector, city in catalog:
            if sector in s["sectors"] and city in s["regions"]:
                found[name.lower()] = {"name": name, "sector": sector, "city": city, "source": "catalog",
                                       "size": size, "website": config.WEBSITES.get(name, "")}
    found.update(_load_companies_csv())                              # your own list wins

    llm = get_llm()
    for sector in s["sectors"]:
        for city in s["regions"][:2]:
            for r in web_search(f"top {sector} companies in {city} Gujarat hiring employees", 5):
                if llm:
                    out = ask(llm, "From this search result, list company names (JSON array of strings) that are "
                                   f"{sector} companies with offices/plants in {city}. Only names explicitly in the text.\n"
                                   f"{r['title']}\n{r['content'][:1500]}")
                    m = re.search(r"\[.*\]", out, re.S)
                    try:
                        names = [n for n in json.loads(m.group()) if isinstance(n, str)] if m else []
                    except ValueError:
                        names = []
                    for nm in names:
                        found.setdefault(nm.lower(), {"name": nm, "sector": sector, "city": city, "source": r["url"]})
    companies = list(found.values())
    for c in companies:
        c.setdefault("size", "Unknown")
    if s.get("sizes"):
        want = {x.lower() for x in s["sizes"]}
        companies = [c for c in companies if c["size"].lower() in want]
    return {"companies": companies, "log": _log(s, f"DiscoverAgent: {len(companies)} companies")}


# ── Agent C: Find decision makers (public sources only) ──
def decision_maker_agent(s: ProspectState) -> dict:
    llm = get_llm()
    contacts = []
    for c in s["companies"]:
        for role in config.DECISION_ROLES[:3]:  # HR Head, CHRO, Talent Acquisition
            hit = None
            for r in (web_search(f'"{role}" "{c["name"]}" {c["city"]}', 2) if llm else []):
                if llm:
                    out = ask(llm, f'Does this text name the current {role} of {c["name"]}? Reply with only the '
                                   f'person\'s name, or NONE.\n{r["title"]}\n{r["content"][:1200]}').strip()
                    if out and out.upper() != "NONE" and len(out) < 60:
                        hit = {"company": c["name"], "role": role, "name": out,
                               "source_url": r["url"], "confidence": "medium"}
                        break
            contacts.append(hit or {"company": c["name"], "role": role, "name": "",
                                    "source_url": linkedin_lookup_url(c["name"], role, c["city"]),
                                    "confidence": "lookup"})
    return {"contacts": contacts, "log": _log(s, f"DecisionMakerAgent: {len(contacts)} contact targets")}


# ── Agent C2: Public contact sheet from company websites ──
def website_contact_agent(s: ProspectState) -> dict:
    import json
    import os
    sites = dict(config.WEBSITES)
    if os.path.exists("websites.json"):  # user overrides / additions
        sites.update(json.load(open("websites.json", encoding="utf-8")))
    from concurrent.futures import ThreadPoolExecutor

    def work(c):
        url = sites.get(c["name"]) or c.get("website") or find_website(c["name"])  # find_website validates the domain
        if not url:
            return c, None, None
        print(f"  scanning {url}")
        return c, url, scan_site(url, delay=0.3)

    sheet = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, s["companies"]))
    for c, url, res in results:
        if not url:
            sheet.append({"company": c["name"], "type": "website", "value": "", "role": "website not found - add it to companies.csv", "source_url": ""})
            continue
        for email, page in res["emails"]:
            sheet.append({"company": c["name"], "type": "email", "value": email, "role": role_of(email), "source_url": page})
        for tel, page in res["phones"]:
            sheet.append({"company": c["name"], "type": "phone", "value": tel, "role": "General", "source_url": page})
        if not res["emails"]:
            sheet.append({"company": c["name"], "type": "website", "value": url, "role": "no public email found", "source_url": url})
    return {"company_contacts": sheet, "log": _log(s, f"WebsiteContactAgent: {len(sheet)} public contact entries")}


# ── Agent D: Score and rank companies ──
def rank_agent(s: ProspectState) -> dict:
    named = {}
    for ct in s["contacts"]:
        named[ct["company"]] = named.get(ct["company"], 0) + (1 if ct["name"] else 0)
    for c in s["companies"]:
        score = 50 + 10 * named.get(c["name"], 0)
        if c["city"] in ("Ahmedabad", "Vadodara"):
            score += 15
        if c["sector"] in ("Pharma", "Banking"):  # proven sectors
            score += 10
        c["score"] = min(score, 100)
    s["companies"].sort(key=lambda c: -c["score"])
    return {"companies": s["companies"], "log": _log(s, "RankAgent: companies scored")}


# ── Export ──
def export_node(s: ProspectState) -> dict:
    import csv
    from datetime import datetime
    rank = {c["name"]: c for c in s["companies"]}
    rows = [["score", "company", "size", "sector", "city", "target_role", "person_name", "verify_at", "confidence"]]
    for ct in sorted(s["contacts"], key=lambda x: -rank[x["company"]]["score"]):
        c = rank[ct["company"]]
        rows.append([c["score"], c["name"], c.get("size", ""), c["sector"], c["city"], ct["role"], ct["name"],
                     ct["source_url"], ct["confidence"]])
    _write_contacts(s)
    path = "prospects.csv"
    try:
        f = open(path, "w", newline="", encoding="utf-8-sig")
    except PermissionError:  # file open in Excel - save under a new name instead
        path = f"prospects_{datetime.now():%Y%m%d_%H%M%S}.csv"
        print(f"prospects.csv is open in another program; saving to {path} instead.")
        f = open(path, "w", newline="", encoding="utf-8-sig")
    with f:
        csv.writer(f).writerows(rows)
    return {"report_path": path, "log": _log(s, f"Export: wrote {path}")}


def _write_contacts(s: ProspectState) -> None:
    import csv
    try:
        with open("company_contacts.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["company", "type", "value", "role", "source_url"])
            for r in s.get("company_contacts", []):
                w.writerow([r["company"], r["type"], r["value"], r["role"], r["source_url"]])
    except PermissionError:
        print("company_contacts.csv is open in another program - close it and run again.")
