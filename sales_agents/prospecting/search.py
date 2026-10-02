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
