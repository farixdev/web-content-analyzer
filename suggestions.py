# -*- coding: utf-8 -*-
"""
Google Autocomplete / Search Suggestions Scraper.

Fetches live Google search suggestions for a given keyword, country, and language
using Google's completion service (no API key required).
"""

from urllib.parse import quote_plus
import requests

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
DEFAULT_COUNTRY = "United States"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


def get_google_suggestions(query, country=DEFAULT_COUNTRY, proxy=None, timeout=10):
    """Fetch live Google search suggestions for `query` in `country`.

    Returns a list of suggestion strings.
    """
    query = (query or "").strip()
    if not query:
        return []

    try:
        import search
        loc = search.COUNTRIES.get(country) or search.COUNTRIES.get(DEFAULT_COUNTRY, {"gl": "us", "hl": "en"})
    except Exception:
        loc = {"gl": "us", "hl": "en", "accept": "en-US,en;q=0.9"}
    gl = loc.get("gl", "us")
    hl = loc.get("hl", "en")

    params = {
        "client": "chrome",
        "q": query,
        "gl": gl,
        "hl": hl,
    }

    headers = {
        "User-Agent": _UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": loc.get("accept", "en-US,en;q=0.9"),
    }

    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    try:
        resp = requests.get(SUGGEST_URL, params=params, headers=headers,
                            proxies=proxies, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            # Format is typically: [query, [suggestions, ...], [types, ...], ...]
            if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                return [str(s).strip() for s in data[1] if str(s).strip()]
    except Exception:
        pass

    # Fallback to firefox endpoint format
    try:
        params["client"] = "firefox"
        resp = requests.get(SUGGEST_URL, params=params, headers=headers,
                            proxies=proxies, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                return [str(s).strip() for s in data[1] if str(s).strip()]
    except Exception:
        pass

    return []
