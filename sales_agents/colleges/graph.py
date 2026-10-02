"""LangGraph pipeline: load colleges -> find websites -> scan public contacts -> export."""
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..prospecting.search import find_website, linkedin_lookup_url
from ..prospecting.webscan import scan_site
from . import config as _c_cfg
from .roles import role_of as _c_role
from ..ushealth import config as _u_cfg
from ..ushospitals import config as _h_cfg
from ..ushospitals.roles import role_of as _h_role
from ..ushealth.roles import role_of as _u_role

# One scanner, several audiences. Pick with: python -m sales_agents.colleges.graph [colleges|ushealth]
PROFILES = {
    "colleges": dict(input="colleges.csv", contacts="college_contacts.csv", targets="college_targets.csv",
                     cfg=_c_cfg, role_of=_c_role),
    "ushealth": dict(input="institutions_us.csv", contacts="us_contacts.csv", targets="us_targets.csv",
                     cfg=_u_cfg, role_of=_u_role, same_domain=True),
    "ushospitals": dict(input="hospitals_us.csv", contacts="hospital_contacts.csv", targets="hospital_targets.csv",
                        cfg=_h_cfg, role_of=_h_role, same_domain=True),
}
PROF = PROFILES["colleges"]


class CollegeState(TypedDict, total=False):
    colleges: list[dict]
    contacts: list[dict]
    log: list[str]


def _log(s, m):
    return [*s.get("log", []), m]


def load_node(s: CollegeState) -> dict:
    path = PROF["input"]
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found - run from the neo-cortex folder.")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip().lower(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if os.path.exists("websites.json"):
        extra = json.load(open("websites.json", encoding="utf-8"))
        for r in rows:
            r["website"] = r.get("website") or extra.get(r["name"], "")
    return {"colleges": [r for r in rows if r.get("name")], "log": _log(s, f"Load: {len(rows)} colleges")}


def website_node(s: CollegeState) -> dict:
    def work(c):
        if not c.get("website"):
            c["website"] = find_website(c["name"]) or ""     # validated: name must appear in the domain
        return c
    with ThreadPoolExecutor(max_workers=8) as pool:
        cols = list(pool.map(work, s["colleges"]))
    found = sum(1 for c in cols if c["website"])
    return {"colleges": cols, "log": _log(s, f"Websites: {found}/{len(cols)} known")}


def scan_node(s: CollegeState) -> dict:
    def work(c):
        if not c["website"]:
            return c, None
        print(f"  scanning {c['website']}")
        return c, scan_site(c["website"], delay=0.3, paths=PROF["cfg"].PATHS, generic=PROF["cfg"].KEYWORDS,
                         same_domain_only=PROF.get("same_domain", False))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, s["colleges"]))
    out = []
    for c, res in results:
        base = {"company": c["name"], "city": c.get("city", ""), "type": c.get("type", "")}
        if res is None:
            out.append({**base, "kind": "website", "value": "", "role": "website not found - add it to the input CSV", "source_url": ""})
            continue
        for email, page in res["emails"]:
            out.append({**base, "kind": "email", "value": email, "role": PROF["role_of"](email), "source_url": page})
        for tel, page in res["phones"]:
            out.append({**base, "kind": "phone", "value": tel, "role": "General", "source_url": page})
        if not res["emails"]:
            out.append({**base, "kind": "website", "value": c["website"], "role": "no public email found", "source_url": c["website"]})
    return {"contacts": out, "log": _log(s, f"Scan: {sum(1 for x in out if x['kind'] == 'email')} public emails found")}


def export_node(s: CollegeState) -> dict:
    def save(path, rows, header):
        try:
            f = open(path, "w", newline="", encoding="utf-8-sig")
        except PermissionError:
            print(f"{path} is open in another program - close it and run again.")
            return
        with f:
            w = csv.writer(f); w.writerow(header); w.writerows(rows)
    # `type` column is named like the gifting framework so the same outreach agent can read it
    save(PROF["contacts"],
         [[c["company"], c["kind"], c["value"], c["role"], c["source_url"], c["city"]] for c in s["contacts"]],
         ["company", "type", "value", "role", "source_url", "city"])
    lookups = []
    for c in s["colleges"]:
        for role in PROF["cfg"].TARGET_ROLES:
            lookups.append([c["name"], c.get("city", ""), role, linkedin_lookup_url(c["name"], role, c.get("city", ""))])
    save(PROF["targets"], lookups, ["college", "city", "target_role", "linkedin_search"])
    return {"log": _log(s, f"Export: {PROF['contacts']}, {PROF['targets']}")}


def build_graph():
    g = StateGraph(CollegeState)
    g.add_node("load", load_node); g.add_node("websites", website_node)
    g.add_node("scan", scan_node); g.add_node("export", export_node)
    g.add_edge(START, "load"); g.add_edge("load", "websites"); g.add_edge("websites", "scan")
    g.add_edge("scan", "export"); g.add_edge("export", END)
    return g.compile()


def run() -> CollegeState:
    return build_graph().invoke({"log": []})


if __name__ == "__main__":
    PROF = PROFILES[sys.argv[1] if len(sys.argv) > 1 else "colleges"]
    print("\n".join(run()["log"]))
