"""Web search via Tavily if TAVILY_API_KEY is set; otherwise returns []."""
import os
from urllib.parse import quote_plus


def web_search(query: str, n: int = 5) -> list[dict]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return []
    import json
    import urllib.request
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"api_key": key, "query": query, "max_results": n}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("results", [])  # each: title, url, content


def linkedin_lookup_url(company: str, role: str, city: str) -> str:
    """A manual LinkedIn people-search link the user can open and verify."""
    q = quote_plus(f"{role} {company} {city}")
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"
