# -*- coding: utf-8 -*-
"""
Forum & Community Discussion Scraper & Question Analyzer.

Finds top 10 to 20 forum threads (Reddit, Quora, specialized forums, StackExchange,
Spiceworks, etc.) for a search query, crawls the discussion pages, strips
headers/footers, extracts real user questions, and classifies search intent.
"""

import re
import requests
from urllib.parse import urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import analyzer
import crawler

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

FORUM_DOMAINS = (
    "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
    "spiceworks.com", "discourse.org", "community.", "forum.", "forums.",
    "groups.google.com", "news.ycombinator.com", "trustpilot.com", "cnet.com/forums",
    "digitalpoint.com", "blackhatworld.com", "warriorforum.com", "bogleheads.org"
)


def _detect_platform(url):
    """Identify the platform brand from the forum URL."""
    host = urlparse(url).netloc.lower()
    if "reddit.com" in host:
        return "Reddit"
    if "quora.com" in host:
        return "Quora"
    if "stackoverflow.com" in host:
        return "Stack Overflow"
    if "spiceworks.com" in host:
        return "Spiceworks Community"
    if "stackexchange.com" in host:
        return "StackExchange"
    if "news.ycombinator.com" in host:
        return "Hacker News"
    return "Industry Forum"


def _is_forum_url(url):
    """Check if URL belongs to a discussion forum or community."""
    u_low = url.lower()
    if any(fd in u_low for fd in FORUM_DOMAINS):
        return True
    path = urlparse(url).path.lower()
    if any(kw in path for kw in ("/forum", "/forums", "/thread", "/topic", "/discussion", "/questions/", "/community")):
        return True
    return False


def _extract_questions_from_text(text, max_questions=5):
    """Extract natural inquisitive sentences (what, how, why, which, is, can, etc.)."""
    if not text:
        return []
    # Split by sentence terminators
    sentences = re.split(r"[.?!]\s+|\n+", text)
    questions = []
    seen = set()

    question_starter = re.compile(
        r"^(what|why|how|which|who|where|when|can|is|are|do|does|should|could|would|anyone|has anybody|best)\b",
        re.IGNORECASE
    )

    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 15 or len(s_clean) > 200:
            continue
        low = s_clean.lower()
        if question_starter.match(s_clean) or s.endswith("?") or "recommend" in low or "thoughts on" in low or "vs" in low:
            norm = " ".join(s_clean.split())
            if not norm.endswith("?"):
                norm += "?"
            if norm.lower() not in seen:
                seen.add(norm.lower())
                questions.append(norm)
                if len(questions) >= max_questions:
                    break
    return questions


def _categorize_intent(question_text):
    """Categorize question intent into actionable SEO and buyer intent themes."""
    low = question_text.lower()
    if any(k in low for k in ("price", "cost", "cheap", "expensive", "fee", "rate", "$", "budget", "quote")):
        return "Pricing & Cost"
    if any(k in low for k in ("best", "recommend", "top", "favorite", "choice", "worth it")):
        return "Recommendations & Best Options"
    if any(k in low for k in ("vs", "or", "difference", "compare", "alternative", "switch")):
        return "Comparison & Alternatives"
    if any(k in low for k in ("how to", "setup", "install", "configure", "integrate", "guide", "tutorial")):
        return "Setup & Integration"
    if any(k in low for k in ("issue", "problem", "broken", "bug", "support", "down", "error", "fail", "slow")):
        return "Troubleshooting & Common Issues"
    if any(k in low for k in ("feature", "support", "work with", "allow", "inventory", "hardware", "scanner")):
        return "Features & Hardware Requirements"
    return "General Experience & Inquiries"


def _search_forum_urls(query, country="United States", top_n=15, proxy=None, serper_key=""):
    """Find top forum URLs for a query using Serper API or Bing search."""
    forum_query = f"{query} forum OR site:reddit.com OR site:quora.com"
    urls = []
    seen = set()

    # 1. Try Serper API if key available
    if serper_key:
        try:
            r = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                json={"q": forum_query, "num": min(max(top_n + 5, 10), 30)},
                timeout=15
            )
            if r.status_code == 200:
                for item in r.json().get("organic", []):
                    link = item.get("link", "")
                    if link and _is_forum_url(link) and link not in seen:
                        seen.add(link)
                        urls.append({
                            "url": link,
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", "")
                        })
                        if len(urls) >= top_n:
                            break
        except Exception:
            pass

    # 2. Bing fallback
    if len(urls) < top_n:
        try:
            headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
            proxies = analyzer._proxies(proxy)
            for first in (1, 11, 21):
                if len(urls) >= top_n:
                    break
                url = f"https://www.bing.com/search?q={quote_plus(forum_query)}&first={first}"
                resp = requests.get(url, headers=headers, proxies=proxies, timeout=12)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("li.b_algo"):
                    h2 = item.select_one("h2 a")
                    if not h2:
                        continue
                    href = h2.get("href", "").strip()
                    if "/ck/a?!" in href and "&u=" in href:
                        import search
                        href = search._decode_bing_url(href)
                    if href.startswith(("http://", "https://")) and _is_forum_url(href) and href not in seen:
                        seen.add(href)
                        snip_el = item.select_one(".b_caption p") or item.select_one("p")
                        urls.append({
                            "url": href,
                            "title": h2.get_text(strip=True),
                            "snippet": snip_el.get_text(strip=True) if snip_el else ""
                        })
                        if len(urls) >= top_n:
                            break
        except Exception:
            pass

    return urls[:top_n]


def _scrape_forum_thread(target, proxy=None, timeout=10):
    """Scrape a forum thread, strictly stripping headers and footers, extracting questions."""
    url = target["url"]
    headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
    proxies = analyzer._proxies(proxy)
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", "").lower():
            title, text = crawler._extract_page_content(resp.text, url)
            questions = _extract_questions_from_text(text, max_questions=4)
            # Add thread title as a key question if it contains an interrogation
            if target["title"] and ("?" in target["title"] or any(k in target["title"].lower() for k in ("what", "how", "best", "vs", "which", "recommend"))):
                t_clean = target["title"].split(" - ")[0].split(" : ")[0].split(" | ")[0].strip()
                if not t_clean.endswith("?"):
                    t_clean += "?"
                if t_clean not in questions:
                    questions.insert(0, t_clean)

            return {
                "platform": _detect_platform(url),
                "title": target["title"] or title or url,
                "url": url,
                "snippet": target["snippet"],
                "word_count": len(analyzer.words(text)) if text else 0,
                "questions": questions,
                "sample_text": text[:400] if text else target["snippet"],
            }
    except Exception:
        pass
    # Fallback to snippet if fetch fails (e.g. strict Cloudflare block on specific forum)
    snip_questions = _extract_questions_from_text(target["snippet"])
    if target["title"] and not snip_questions:
        snip_questions = [target["title"]]
    return {
        "platform": _detect_platform(url),
        "title": target["title"] or url,
        "url": url,
        "snippet": target["snippet"],
        "word_count": len(analyzer.words(target["snippet"])),
        "questions": snip_questions,
        "sample_text": target["snippet"],
    }


def analyze_forum_discussions(query, country="United States", top_n=15, proxy=None, serper_key="", progress=None):
    """Scrapes top 10-20 forums for a search query and synthesizes audience questions and intent."""
    log = progress if callable(progress) else (lambda m: None)
    top_n = max(5, min(int(top_n or 15), 25))
    log("Discovering top %d forum & community discussions for '%s'..." % (top_n, query))

    forum_targets = _search_forum_urls(query, country=country, top_n=top_n, proxy=proxy, serper_key=serper_key)
    if not forum_targets:
        log("No public forum discussions indexed for this query.")
        return {
            "query": query,
            "total_forums_found": 0,
            "threads": [],
            "aggregated_questions": [],
            "intent_themes": [],
        }

    log("Found %d forum discussions. Scraping questions & audience pain points..." % len(forum_targets))
    threads = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_scrape_forum_thread, t, proxy): t for t in forum_targets}
        for future in as_completed(future_map):
            try:
                res = future.result()
                if res:
                    threads.append(res)
            except Exception:
                pass

    # Sort threads so Reddit/Quora appear cleanly
    threads.sort(key=lambda t: (0 if t["platform"] in ("Reddit", "Quora") else 1, t["title"]))

    # Aggregate all unique questions
    aggregated_questions = []
    seen_q = set()
    intent_counts = {}

    for t in threads:
        for q in t.get("questions", []):
            norm = q.lower().strip()
            if norm not in seen_q and len(norm) > 12:
                seen_q.add(norm)
                cat = _categorize_intent(q)
                intent_counts[cat] = intent_counts.get(cat, 0) + 1
                aggregated_questions.append({
                    "question": q,
                    "platform": t["platform"],
                    "category": cat,
                    "source_title": t["title"],
                    "url": t["url"],
                })

    # Sort intent themes by frequency
    sorted_intents = sorted(
        [{"theme": k, "count": v} for k, v in intent_counts.items()],
        key=lambda x: -x["count"]
    )

    log("Extracted %d unique audience questions across %d forums." % (len(aggregated_questions), len(threads)))

    return {
        "query": query,
        "total_forums_found": len(threads),
        "threads": threads,
        "aggregated_questions": aggregated_questions[:40],
        "intent_themes": sorted_intents,
    }
