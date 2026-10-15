# -*- coding: utf-8 -*-
"""
Deep Multi-Page Website Crawler.

Crawls a target competitor website domain starting from its search landing page,
discovers internal links via Breadth-First Search (BFS), and extracts main
content across 20 to 40+ pages per site.
"""

import time
import re
from urllib.parse import urlparse, urljoin, urldefrag
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
try:
    import trafilatura
except ImportError:
    trafilatura = None

import analyzer

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# Extensions to skip (assets, documents, media)
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".mp3", ".mp4", ".avi",
    ".mov", ".wmv", ".css", ".js", ".json", ".xml", ".rss"
)

# Common non-content paths to skip
SKIP_PATH_PATTERNS = (
    "/cdn-cgi/", "/wp-json/", "/wp-admin/", "/wp-includes/",
    "/cart", "/checkout", "/my-account", "/login", "/register",
    "/logout", "/password-reset", "/feed", "/comments/feed"
)


def _normalize_host(netloc):
    netloc = (netloc or "").lower().split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def _is_same_domain(url, base_domain):
    """Check if `url` belongs to the same base domain or subdomain."""
    h = _normalize_host(urlparse(url).netloc)
    return h == base_domain or h.endswith("." + base_domain)


def _clean_url(url):
    """Strip fragment, query parameters that are trackers, and normalize."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    # Filter out query parameters like utm_*, fbclid, etc.
    q_pairs = []
    for pair in parsed.query.split("&"):
        if not pair:
            continue
        k = pair.split("=")[0].lower()
        if not (k.startswith("utm_") or k in ("fbclid", "gclid", "ref", "source")):
            q_pairs.append(pair)
    new_query = "&".join(q_pairs)
    clean = parsed._replace(query=new_query).geturl()
    return clean.rstrip("/") if clean.endswith("/") and parsed.path != "/" else clean


def _should_crawl(url, base_domain):
    """Check if a URL is a valid, crawlable HTML page on this domain."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    parsed = urlparse(url)
    if not _is_same_domain(url, base_domain):
        return False
    path_low = parsed.path.lower()
    if any(path_low.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if any(pat in path_low for pat in SKIP_PATH_PATTERNS):
        return False
    return True


def _extract_page_content(html, url):
    """Extract clean main text and title from HTML using trafilatura or BeautifulSoup."""
    title = ""
    text = ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(" ", strip=True)
    except Exception:
        pass

    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                favor_recall=True
            )
            if extracted and extracted.strip():
                text = extracted.strip()
        except Exception:
            pass

    if not text:
        # BeautifulSoup fallback heuristic
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                tag.decompose()
            body = soup.find("body") or soup
            text = body.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
        except Exception:
            text = ""

    return title, text


def _extract_internal_links(html, page_url, base_domain):
    """Find all valid internal links inside HTML."""
    links = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:")):
                continue
            full = urljoin(page_url, href)
            full_clean = _clean_url(full)
            if _should_crawl(full_clean, base_domain):
                links.add(full_clean)
    except Exception:
        pass
    return links


from requests.adapters import HTTPAdapter

class SiteCrawler:
    """Crawls up to `max_pages` internal pages of a website domain."""

    def __init__(self, start_url, max_pages=30, proxy=None, timeout=10, delay=0.05, max_workers=8):
        self.start_url = _clean_url(start_url)
        self.base_domain = _normalize_host(urlparse(start_url).netloc)
        self.max_pages = max(1, int(max_pages))
        self.proxy = proxy
        self.timeout = timeout
        self.delay = delay
        self.max_workers = max(1, min(int(max_workers or 8), 16))
        self.headers = {
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        if proxy:
            self.session.proxies.update(analyzer._proxies(proxy))

    def _fetch(self, url):
        """Fetch a single page, returning (html, status_code)."""
        try:
            resp = self.session.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", "").lower():
                try:
                    resp.encoding = resp.apparent_encoding or resp.encoding
                except Exception:
                    pass
                return resp.text, resp.url
        except Exception:
            pass
        return None, None

    def _fetch_worker(self, url):
        """Worker task to fetch and extract content and internal links."""
        html, final_url = self._fetch(url)
        if not html:
            return None
        title, text = _extract_page_content(html, url)
        word_count = len(analyzer.words(text)) if text else 0
        internal_links = _extract_internal_links(html, url, self.base_domain)
        return {
            "url": url,
            "final_url": final_url,
            "title": title or url,
            "text": text,
            "word_count": word_count,
            "internal_links": internal_links,
        }

    def crawl(self, progress_callback=None):
        """Run concurrent BFS crawl on the domain up to `max_pages`.

        Calls progress_callback(current_count, max_pages, current_url) as pages are completed.
        Returns a dict summarizing all crawled pages.
        """
        queue = [self.start_url]
        seen = {self.start_url}
        pages = []
        combined_texts = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while queue and len(pages) < self.max_pages:
                batch_size = min(self.max_workers, self.max_pages - len(pages), len(queue))
                batch_urls = [queue.pop(0) for _ in range(batch_size)]

                future_map = {executor.submit(self._fetch_worker, u): u for u in batch_urls}
                for future in as_completed(future_map):
                    try:
                        res = future.result()
                    except Exception:
                        res = None

                    if not res:
                        continue

                    if res["final_url"]:
                        seen.add(_clean_url(res["final_url"]))

                    if res["word_count"] >= 15 and len(pages) < self.max_pages:
                        pages.append({
                            "url": res["url"],
                            "title": res["title"],
                            "text": res["text"],
                            "word_count": res["word_count"],
                        })
                        combined_texts.append(res["text"])
                        if progress_callback:
                            progress_callback(len(pages), self.max_pages, res["url"])

                    for link in res["internal_links"]:
                        if link not in seen:
                            seen.add(link)
                            queue.append(link)

                    if len(pages) >= self.max_pages:
                        break

        combined_corpus = "\n\n".join(combined_texts)
        total_words = sum(p["word_count"] for p in pages)

        return {
            "domain": self.base_domain,
            "start_url": self.start_url,
            "pages_scraped": len(pages),
            "total_words": total_words,
            "pages": pages,
            "combined_text": combined_corpus,
        }


def crawl_site(start_url, max_pages=30, proxy=None, progress_callback=None, max_workers=8):
    """Convenience helper to crawl a single website domain."""
    crawler = SiteCrawler(start_url, max_pages=max_pages, proxy=proxy, max_workers=max_workers)
    return crawler.crawl(progress_callback=progress_callback)
