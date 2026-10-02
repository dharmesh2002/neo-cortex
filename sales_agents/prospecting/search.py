"""Web search via Tavily if TAVILY_API_KEY is set; otherwise returns []."""
import os
from urllib.parse import quote_plus


_warned = False


def web_search(query: str, n: int = 5) -> list[dict]:
    """Tavily search. Never raises: on a bad key/network error it warns once and returns []."""
    global _warned
    key = os.getenv("TAVILY_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        return []
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": query, "max_results": n}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("results", [])  # each: title, url, content
    except urllib.error.HTTPError as e:
        if not _warned:
            hint = " - check TAVILY_API_KEY (no quotes/spaces, starts with 'tvly-')" if e.code in (401, 403) else ""
            print(f"WARNING: web search failed (HTTP {e.code}){hint}. Continuing without web search.")
            _warned = True
    except Exception as e:
        if not _warned:
            print(f"WARNING: web search failed ({e}). Continuing without web search.")
            _warned = True
    return []


def linkedin_lookup_url(company: str, role: str, city: str) -> str:
    """A manual LinkedIn people-search link the user can open and verify."""
    q = quote_plus(f"{role} {company} {city}")
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


_BAD_DOMAINS = ("linkedin", "facebook", "indiamart", "justdial", "wikipedia", "mapquest", "twitter", "instagram",
                "youtube", "glassdoor", "naukri", "ambitionbox", "zaubacorp", "tofler", "crunchbase", "google",
                "bing", "yelp", "tradeindia", "alibaba", "sulekha", "moneycontrol", "economictimes")


def find_website(name: str) -> str | None:
    """Official-site lookup via search. Accepts a result ONLY if the company name's first word is in the domain."""
    import re
    from urllib.parse import urlparse
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in ("the", "of", "and", "india", "ltd", "pvt", "limited")]
    if not words:
        return None
    key = words[0]
    if len(key) < 4:
        return None
    for r in web_search(f"{name} official website", 5):
        host = urlparse(r["url"]).netloc.lower().replace("www.", "")
        if key in host and not any(b in host for b in _BAD_DOMAINS):
            return f"{urlparse(r['url']).scheme}://{urlparse(r['url']).netloc}"
    return None
