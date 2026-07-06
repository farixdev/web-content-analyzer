# -*- coding: utf-8 -*-
"""
Google search front-end for the Web Content Analyzer.

Turns a keyword + country into a Google results page "as if" searched from that
country, parses the organic results, and (optionally) runs the existing per-page
analyzer (analyzer.analyze_url) on the top results to build a combined report.

Two ways a country is honoured:
  1. Google's own locale parameters -- gl (country), hl (interface language),
     the local google.<tld> domain, and a matching Accept-Language header.
     Free, no proxy, gives the localized *ranking* for that country.
  2. An optional proxy whose exit IP is in that country. More authentic (Google
     sees a local visitor) and helps avoid blocks -- but you must supply it.

Reality check: Google actively blocks automated queries. Plain scraping works for
occasional use and then hits a CAPTCHA / "unusual traffic" wall. For volume, put a
good country proxy in the proxy field, or swap google_search() for a SERP API
(Serper.dev / SerpApi) -- the rest of this file (parsing consumers, orchestrator,
reporting) stays the same.
"""

import re
import sys
import json
import argparse
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

import analyzer  # reuse fetch/extract/metrics/SEO/AI and to_json


# ----------------------------------------------------------------------------
# Country table: name -> Google locale settings
#   gl     : geolocation country code Google biases results toward
#   hl     : interface / results language
#   domain : local Google domain (reinforces locale)
#   accept : Accept-Language header sent with the request
# ----------------------------------------------------------------------------
COUNTRIES = {
    "United States":        {"gl": "us", "hl": "en",    "domain": "www.google.com",    "accept": "en-US,en;q=0.9"},
    "United Kingdom":       {"gl": "uk", "hl": "en-GB", "domain": "www.google.co.uk",  "accept": "en-GB,en;q=0.9"},
    "Canada":               {"gl": "ca", "hl": "en",    "domain": "www.google.ca",     "accept": "en-CA,en;q=0.9,fr-CA;q=0.8"},
    "Canada (French)":      {"gl": "ca", "hl": "fr",    "domain": "www.google.ca",     "accept": "fr-CA,fr;q=0.9,en;q=0.8"},
    "Australia":            {"gl": "au", "hl": "en",    "domain": "www.google.com.au", "accept": "en-AU,en;q=0.9"},
    "Ireland":              {"gl": "ie", "hl": "en",    "domain": "www.google.ie",     "accept": "en-IE,en;q=0.9"},
    "New Zealand":          {"gl": "nz", "hl": "en",    "domain": "www.google.co.nz",  "accept": "en-NZ,en;q=0.9"},
    "India":                {"gl": "in", "hl": "en",    "domain": "www.google.co.in",  "accept": "en-IN,en;q=0.9,hi;q=0.8"},
    "Pakistan":             {"gl": "pk", "hl": "en",    "domain": "www.google.com.pk", "accept": "en-PK,en;q=0.9,ur;q=0.8"},
    "Germany":              {"gl": "de", "hl": "de",    "domain": "www.google.de",     "accept": "de-DE,de;q=0.9,en;q=0.8"},
    "France":               {"gl": "fr", "hl": "fr",    "domain": "www.google.fr",     "accept": "fr-FR,fr;q=0.9,en;q=0.8"},
    "Spain":                {"gl": "es", "hl": "es",    "domain": "www.google.es",     "accept": "es-ES,es;q=0.9,en;q=0.8"},
    "Italy":                {"gl": "it", "hl": "it",    "domain": "www.google.it",     "accept": "it-IT,it;q=0.9,en;q=0.8"},
    "Netherlands":          {"gl": "nl", "hl": "nl",    "domain": "www.google.nl",     "accept": "nl-NL,nl;q=0.9,en;q=0.8"},
    "Belgium":              {"gl": "be", "hl": "nl",    "domain": "www.google.be",     "accept": "nl-BE,nl;q=0.9,fr;q=0.8,en;q=0.7"},
    "Portugal":             {"gl": "pt", "hl": "pt-PT", "domain": "www.google.pt",     "accept": "pt-PT,pt;q=0.9,en;q=0.8"},
    "Switzerland":          {"gl": "ch", "hl": "de",    "domain": "www.google.ch",     "accept": "de-CH,de;q=0.9,fr;q=0.8,en;q=0.7"},
    "Austria":              {"gl": "at", "hl": "de",    "domain": "www.google.at",     "accept": "de-AT,de;q=0.9,en;q=0.8"},
    "Sweden":               {"gl": "se", "hl": "sv",    "domain": "www.google.se",     "accept": "sv-SE,sv;q=0.9,en;q=0.8"},
    "Norway":               {"gl": "no", "hl": "no",    "domain": "www.google.no",     "accept": "nb-NO,nb;q=0.9,en;q=0.8"},
    "Denmark":              {"gl": "dk", "hl": "da",    "domain": "www.google.dk",     "accept": "da-DK,da;q=0.9,en;q=0.8"},
    "Finland":              {"gl": "fi", "hl": "fi",    "domain": "www.google.fi",     "accept": "fi-FI,fi;q=0.9,en;q=0.8"},
    "Poland":               {"gl": "pl", "hl": "pl",    "domain": "www.google.pl",     "accept": "pl-PL,pl;q=0.9,en;q=0.8"},
    "Turkey":               {"gl": "tr", "hl": "tr",    "domain": "www.google.com.tr", "accept": "tr-TR,tr;q=0.9,en;q=0.8"},
    "Russia":               {"gl": "ru", "hl": "ru",    "domain": "www.google.ru",     "accept": "ru-RU,ru;q=0.9,en;q=0.8"},
    "Ukraine":              {"gl": "ua", "hl": "uk",    "domain": "www.google.com.ua", "accept": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7"},
    "Brazil":               {"gl": "br", "hl": "pt-BR", "domain": "www.google.com.br", "accept": "pt-BR,pt;q=0.9,en;q=0.8"},
    "Mexico":               {"gl": "mx", "hl": "es",    "domain": "www.google.com.mx", "accept": "es-MX,es;q=0.9,en;q=0.8"},
    "Argentina":            {"gl": "ar", "hl": "es",    "domain": "www.google.com.ar", "accept": "es-AR,es;q=0.9,en;q=0.8"},
    "Chile":                {"gl": "cl", "hl": "es",    "domain": "www.google.cl",     "accept": "es-CL,es;q=0.9,en;q=0.8"},
    "Colombia":             {"gl": "co", "hl": "es",    "domain": "www.google.com.co", "accept": "es-CO,es;q=0.9,en;q=0.8"},
    "Japan":                {"gl": "jp", "hl": "ja",    "domain": "www.google.co.jp",  "accept": "ja-JP,ja;q=0.9,en;q=0.8"},
    "South Korea":          {"gl": "kr", "hl": "ko",    "domain": "www.google.co.kr",  "accept": "ko-KR,ko;q=0.9,en;q=0.8"},
    "China":                {"gl": "cn", "hl": "zh-CN", "domain": "www.google.com",    "accept": "zh-CN,zh;q=0.9,en;q=0.8"},
    "Hong Kong":            {"gl": "hk", "hl": "zh-HK", "domain": "www.google.com.hk", "accept": "zh-HK,zh;q=0.9,en;q=0.8"},
    "Taiwan":               {"gl": "tw", "hl": "zh-TW", "domain": "www.google.com.tw", "accept": "zh-TW,zh;q=0.9,en;q=0.8"},
    "Singapore":            {"gl": "sg", "hl": "en",    "domain": "www.google.com.sg", "accept": "en-SG,en;q=0.9,zh;q=0.8"},
    "Malaysia":             {"gl": "my", "hl": "en",    "domain": "www.google.com.my", "accept": "en-MY,en;q=0.9,ms;q=0.8"},
    "Indonesia":            {"gl": "id", "hl": "id",    "domain": "www.google.co.id",  "accept": "id-ID,id;q=0.9,en;q=0.8"},
    "Thailand":             {"gl": "th", "hl": "th",    "domain": "www.google.co.th",  "accept": "th-TH,th;q=0.9,en;q=0.8"},
    "Vietnam":              {"gl": "vn", "hl": "vi",    "domain": "www.google.com.vn", "accept": "vi-VN,vi;q=0.9,en;q=0.8"},
    "Philippines":          {"gl": "ph", "hl": "en",    "domain": "www.google.com.ph", "accept": "en-PH,en;q=0.9,tl;q=0.8"},
    "United Arab Emirates": {"gl": "ae", "hl": "en",    "domain": "www.google.ae",     "accept": "en-AE,en;q=0.9,ar;q=0.8"},
    "Saudi Arabia":         {"gl": "sa", "hl": "ar",    "domain": "www.google.com.sa", "accept": "ar-SA,ar;q=0.9,en;q=0.8"},
    "Egypt":                {"gl": "eg", "hl": "ar",    "domain": "www.google.com.eg", "accept": "ar-EG,ar;q=0.9,en;q=0.8"},
    "South Africa":         {"gl": "za", "hl": "en",    "domain": "www.google.co.za",  "accept": "en-ZA,en;q=0.9"},
    "Nigeria":              {"gl": "ng", "hl": "en",    "domain": "www.google.com.ng", "accept": "en-NG,en;q=0.9"},
    "Israel":               {"gl": "il", "hl": "en",    "domain": "www.google.co.il",  "accept": "en-IL,en;q=0.9,he;q=0.8"},
    "Greece":               {"gl": "gr", "hl": "el",    "domain": "www.google.gr",     "accept": "el-GR,el;q=0.9,en;q=0.8"},
    "Czechia":              {"gl": "cz", "hl": "cs",    "domain": "www.google.cz",     "accept": "cs-CZ,cs;q=0.9,en;q=0.8"},
    "Romania":              {"gl": "ro", "hl": "ro",    "domain": "www.google.ro",     "accept": "ro-RO,ro;q=0.9,en;q=0.8"},
}

DEFAULT_COUNTRY = "United States"

# Serper.dev - an official Google-results API. Paste a key and Google is queried
# through the API instead of scraped, so there is no CAPTCHA / "unusual traffic"
# wall. Free tier ~2,500 searches. Sign up: https://serper.dev
SERPER_URL = "https://google.serper.dev/search"

# A current desktop-Chrome UA. Google is likelier to serve parseable HTML to a
# "real" browser string than to an obvious bot UA.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Hosts that appear in organic-looking anchors but are not real results.
_SKIP_HOST_SUBSTR = ("google.", "gstatic.", "googleusercontent.", "youtube.com/redirect",
                     "webcache.googleusercontent")


def country_names():
    """Sorted list of supported country labels (for a dropdown)."""
    return sorted(COUNTRIES.keys())


def _registrable(host):
    """Lowercase host with a single leading 'www.' removed (prefix, not chars)."""
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


# Social / forum / marketplace / review / directory / video hosts that are never
# a genuine same-type competitor page. Deep analysis skips these so the aggregate
# reflects real competitor content, not Reddit/YouTube/directory noise.
JUNK_HOST_SUBSTR = (
    "facebook.", "instagram.", "twitter.", "x.com", "linkedin.", "youtube.",
    "youtu.be", "tiktok.", "pinterest.", "reddit.", "quora.", "medium.com",
    "wikipedia.", "amazon.", "ebay.", "etsy.", "aliexpress.", "yelp.",
    "tripadvisor.", "glassdoor.", "indeed.", "trustpilot.", "g2.com",
    "capterra.", "getapp.", "softwareadvice.", "clutch.co", "yellowpages.",
    "bbb.org", "crunchbase.", "producthunt.", "news.", "wikihow.",
)


def _is_competitor(url):
    """True if the URL looks like a genuine competitor page (not social/junk)."""
    host = urlparse(url).netloc.lower()
    return not any(j in host for j in JUNK_HOST_SUBSTR)


# ----------------------------------------------------------------------------
# Result-URL cleanup
# ----------------------------------------------------------------------------
def _clean_result_url(href, domain):
    """Resolve a Google anchor href to the real destination URL, or "" to skip."""
    if not href:
        return ""
    href = href.strip()
    # Google's redirect wrapper: /url?q=<real>&sa=...
    if href.startswith("/url?") or href.startswith("/url%3F"):
        q = parse_qs(urlparse(href).query)
        href = (q.get("q") or q.get("url") or [""])[0]
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = urljoin("https://%s/" % domain, href)
    if not href.startswith(("http://", "https://")):
        return ""
    host = urlparse(href).netloc.lower()
    if any(s in host for s in _SKIP_HOST_SUBSTR):
        return ""
    return href


def _looks_blocked(html):
    low = html.lower()
    markers = ("unusual traffic", "/sorry/", "captcha",
               "detected unusual", "not a robot", "enablejs")
    return any(m in low for m in markers)


# ----------------------------------------------------------------------------
# SERP parsing (best-effort, resilient to Google's shifting class names)
# ----------------------------------------------------------------------------
def _parse_results(html, domain, want):
    """Extract organic results as [{position,title,url,domain,snippet}]."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    # Strategy: every organic result has an <h3> title inside an <a href>.
    # Walk the h3s in document order (that order is the ranking order).
    for h3 in soup.find_all("h3"):
        a = h3.find_parent("a", href=True)
        if not a:
            continue
        url = _clean_result_url(a.get("href", ""), domain)
        if not url:
            continue
        key = url.split("#")[0]
        if key in seen:
            continue

        title = h3.get_text(" ", strip=True)
        if not title:
            continue

        snippet = _snippet_for(a, title)
        seen.add(key)
        results.append({
            "position": len(results) + 1,
            "title": title,
            "url": url,
            "domain": _registrable(urlparse(url).netloc),
            "snippet": snippet,
        })
        if len(results) >= want:
            break
    return results


def _snippet_for(anchor, title, max_len=320):
    """Climb from the result anchor to the enclosing result block and pull the
    descriptive text, with the title removed. Heuristic but usually close."""
    block = anchor
    for _ in range(5):
        parent = block.parent
        if parent is None:
            break
        block = parent
        text = block.get_text(" ", strip=True)
        # A result block's text is meaningfully longer than just the title.
        if len(text) > len(title) + 40:
            body = text.replace(title, " ", 1)
            body = re.sub(r"\s+", " ", body).strip(" -|·—")
            if body:
                return body[:max_len].strip()
    return ""


# ----------------------------------------------------------------------------
# The search call
# ----------------------------------------------------------------------------
def google_search(query, country=DEFAULT_COUNTRY, num=10, proxy=None, timeout=25):
    """Query Google as if from `country` and return a list of organic results.

    Raises RuntimeError with a clear message if Google blocks the request.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Empty search query.")
    loc = COUNTRIES.get(country) or COUNTRIES[DEFAULT_COUNTRY]

    # Ask for a few extra so that after we drop ads / non-result anchors we
    # still have `num` clean organic results.
    ask = min(max(num + 5, 10), 50)
    params = "q=%s&num=%d&gl=%s&hl=%s&pws=0&safe=off" % (
        quote_plus(query), ask, loc["gl"], loc["hl"])
    url = "https://%s/search?%s" % (loc["domain"], params)

    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": loc["accept"],
        "Referer": "https://%s/" % loc["domain"],
    }
    # CONSENT / SOCS cookies skip the EU "before you continue" interstitial that
    # otherwise replaces the results page with a consent form.
    cookies = {"CONSENT": "YES+cb", "SOCS": "CAI"}

    try:
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=timeout,
                            allow_redirects=True, proxies=analyzer._proxies(proxy))
    except requests.exceptions.ProxyError as e:
        raise RuntimeError("Proxy connection failed: %s" % e)
    except requests.exceptions.RequestException as e:
        raise RuntimeError("Network error contacting Google: %s" % e)

    if resp.status_code == 429 or "/sorry/" in resp.url:
        raise RuntimeError(
            "Google blocked this request (rate-limited / CAPTCHA). "
            "Slow down, use a country proxy, or switch to a SERP API.")
    resp.raise_for_status()

    try:
        resp.encoding = resp.apparent_encoding or resp.encoding
    except Exception:
        pass
    html = resp.text

    results = _parse_results(html, loc["domain"], num)
    if not results:
        if _looks_blocked(html):
            raise RuntimeError(
                "Google returned a CAPTCHA / 'unusual traffic' page instead of "
                "results. Use a good country proxy or a SERP API for reliable access.")
        raise RuntimeError(
            "No organic results were parsed. Either the query genuinely has none, "
            "or Google changed its result markup. (Country: %s)" % country)
    return results


def serper_search(query, country=DEFAULT_COUNTRY, num=10, api_key="", timeout=30):
    """Query Google via the Serper.dev API. Same result shape as google_search().

    No CAPTCHA is possible here - Serper returns Google's results as JSON. The
    country is honoured through the same gl/hl codes used for direct scraping.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Empty search query.")
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("No Serper API key provided.")
    loc = COUNTRIES.get(country) or COUNTRIES[DEFAULT_COUNTRY]

    payload = {"q": query, "gl": loc["gl"], "hl": loc["hl"], "num": min(max(num, 10), 100)}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    try:
        r = requests.post(SERPER_URL, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RuntimeError("Network error contacting Serper: %s" % e)

    if r.status_code in (401, 403):
        raise RuntimeError("Serper rejected the API key (HTTP %d). Check the key / your credit balance." % r.status_code)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except Exception:
            msg = r.text
        raise RuntimeError("Serper API error %d: %s" % (r.status_code, msg))

    organic = r.json().get("organic", []) or []
    results = []
    for item in organic:
        link = (item.get("link") or "").strip()
        if not link.startswith(("http://", "https://")):
            continue
        results.append({
            "position": len(results) + 1,
            "title": (item.get("title") or "").strip(),
            "url": link,
            "domain": _registrable(urlparse(link).netloc),
            "snippet": (item.get("snippet") or "").strip(),
        })
        if len(results) >= num:
            break
    if not results:
        raise RuntimeError("Serper returned no organic results for this query.")
    return results


# ----------------------------------------------------------------------------
# Competitor aggregate ("brief"): average the deep-analyzed pages and mine the
# combined corpus, matching the outline skills' competitor-analysis method.
# ----------------------------------------------------------------------------
def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def _term_stats(term, texts, combined):
    """Real, computed stats for a term across the competitor corpus."""
    used, dens = 0, []
    for txt in texts:
        if analyzer.count_phrase(txt, term) > 0:
            used += 1
        dens.append(analyzer.density(txt, term))
    return {"used_by_competitors": used, "avg_density_pct": _avg(dens),
            "corpus_count": analyzer.count_phrase(combined, term)}


def _groq_enrich(query, combined, texts, api_key, model, log):
    """Ask Groq to name the real secondary keywords and (categorized) entities the
    competitor pages actually use, then COMPUTE each term's density from the
    corpus. Groq decides *what* the terms are (it catches lowercase domain terms
    a capitalized-phrase heuristic misses); the numbers stay measured, not guessed.

    Also detects page type, product, service noun, and location from the content.
    Returns None on any failure so the heuristic aggregate stands.
    """
    system = (
        "You are an SEO competitor analyst. From the competitor page content, "
        "extract the REAL terms these pages target. Reply with one valid JSON "
        "object only, no prose, no code fences. Use lowercase for terms that are "
        "normally lowercase (for example 'point of sale', 'payment processing'); "
        "keep proper nouns and acronyms cased correctly (for example 'WEB-SRM', "
        "'Moneris'). Do not invent terms the content does not use."
    )
    user = (
        "Primary keyword: %s\n\n"
        "Return a JSON object with EXACTLY these keys:\n"
        "  page_type (one of: service, location, industry, vendor, comparison, blog)\n"
        "  product (short name of the core product/service, e.g. 'business internet', 'POS', 'SIP trunking')\n"
        "  service_noun (short noun phrase naming the service for a disclaimer line)\n"
        "  location (the target city/region if the keyword is local, else empty string)\n"
        "  secondary_keywords (array of up to 10 real secondary search phrases the pages target)\n"
        "  entities (array of up to 24 domain terms the pages use: products, features, "
        "technologies, vendors, standards, places, buyer concerns; grouped by theme, "
        "related ones adjacent)\n\n"
        "Competitor content (combined):\n\"\"\"%s\"\"\""
    ) % (query, combined[:12000])

    try:
        log("Enriching entities and keywords with Groq...")
        data = analyzer.groq_json(api_key, model, system, user, temperature=0.2)
    except Exception as e:
        log("Groq enrichment skipped: %s" % e)
        return None
    if not isinstance(data, dict) or "raw_response" in data:
        return None

    def rows(items, key):
        out, seen = [], set()
        for it in (items or []):
            term = str(it).strip()
            k = term.lower()
            if not term or k in seen:
                continue
            seen.add(k)
            st = _term_stats(term, texts, combined)
            row = {key: term}
            row.update(st)
            out.append(row)
        return out

    secondary = rows(data.get("secondary_keywords"), "phrase")
    entities = rows(data.get("entities"), "entity")
    if not secondary and not entities:
        return None
    return {
        "page_type": (data.get("page_type") or "").strip().lower(),
        "product": (data.get("product") or "").strip(),
        "service_noun": (data.get("service_noun") or "").strip(),
        "location": (data.get("location") or "").strip(),
        "secondary_keywords": secondary,
        "entities": entities,
    }


def _aggregate_competitors(query, deep_results, api_key="", model=analyzer.DEFAULT_MODEL, log=None):
    """Build the aggregate block from the deep-analyzed competitor results.

    Averages every per-page metric. For the secondary keywords and entities it
    prefers Groq-grounded semantic extraction (accurate, catches lowercase domain
    terms) with densities COMPUTED from the corpus; if no Groq key or the call
    fails, it falls back to the deterministic n-gram + capitalized-phrase method.
    Returns None if nothing could be analyzed.
    """
    log = log if callable(log) else (lambda m: None)
    texts, metric_rows = [], []
    for r in deep_results:
        a = r.get("analysis")
        if not a:
            continue
        metric_rows.append(a["metrics"])
        txt = a.get("main_text", "")
        if txt:
            texts.append(txt)
    if not metric_rows:
        return None

    averages = {
        "word_count": round(_avg([m["word_count"] for m in metric_rows])),
        "flesch_reading_ease": _avg([m["flesch_reading_ease"] for m in metric_rows]),
        "primary_keyword_density_pct": _avg([m["primary_keyword_density_pct"] for m in metric_rows]),
        "transition_sentence_pct": _avg([m["transition_sentence_pct"] for m in metric_rows]),
        "same_start_sentence_pct": _avg([m["same_start_sentence_pct"] for m in metric_rows]),
        "passive_voice_pct": _avg([m["passive_voice_pct"] for m in metric_rows]),
    }

    combined = "\n".join(texts)
    allwords = analyzer.words(combined)

    # Deterministic baseline (always computed; also the no-key fallback).
    secondary = []
    for phrase, corpus_count in (analyzer.ngrams(allwords, 2, analyzer.STOP).most_common(25)
                                 + analyzer.ngrams(allwords, 3, analyzer.STOP).most_common(15)):
        st = _term_stats(phrase, texts, combined)
        secondary.append({"phrase": phrase, **st})
    entities = []
    for e in analyzer.extract_entities(combined, top_n=25):
        st = _term_stats(e["entity"], texts, combined)
        entities.append({"entity": e["entity"], **st})

    semantic = {}
    if (api_key or "").strip() and combined.strip():
        enriched = _groq_enrich(query, combined, texts, api_key.strip(), model, log)
        if enriched:
            secondary = enriched["secondary_keywords"] or secondary
            entities = enriched["entities"] or entities
            semantic = {k: enriched[k] for k in ("page_type", "product", "service_noun", "location")}

    secondary_sorted = sorted(secondary, key=lambda s: (-s["used_by_competitors"], -s["corpus_count"]))
    entities_sorted = sorted(entities, key=lambda e: (-e["used_by_competitors"], -e["corpus_count"]))
    targets = {
        "primary": {"keyword": query, "target_density_pct": averages["primary_keyword_density_pct"]},
        "secondary": [{"phrase": s["phrase"], "target_density_pct": s["avg_density_pct"]}
                      for s in secondary_sorted[:10]],
        "entities": [{"entity": e["entity"], "target_density_pct": e["avg_density_pct"]}
                     for e in entities_sorted[:20]],
    }

    agg = {
        "competitors_analyzed": len(metric_rows),
        "primary_keyword": query,
        "enriched": bool(semantic),
        "averages": averages,
        "secondary_keywords": secondary,
        "entities": entities,
        "targets": targets,
    }
    agg.update(semantic)
    return agg


# ----------------------------------------------------------------------------
# Orchestrator: search -> (optional) deep-analyze top results -> report dict
# ----------------------------------------------------------------------------
def search_and_analyze(query, country=DEFAULT_COUNTRY, num_results=10, deep_n=0,
                       entities=None, use_ai=False, api_key="",
                       model=analyzer.DEFAULT_MODEL, proxy=None, progress=None,
                       serper_key=""):
    """Run a country-targeted Google search and build a combined report dict.

    Engine choice: if `serper_key` is set, results come through the Serper.dev
    API (no CAPTCHA); otherwise Google is scraped directly (proxy honoured).

    deep_n > 0 runs the existing per-page analyzer (analyzer.analyze_url) on the
    top `deep_n` results, routed through the same proxy, and attaches each result
    under its "analysis" key. Per-page failures are captured, never fatal.
    """
    log = progress if callable(progress) else (lambda m: None)
    loc = COUNTRIES.get(country) or COUNTRIES[DEFAULT_COUNTRY]
    serper_key = (serper_key or "").strip()

    if serper_key:
        engine = "serper"
        log("Searching Google via Serper API (%s) ..." % country)
        results = serper_search(query, country, num=num_results, api_key=serper_key)
    else:
        engine = "google-direct"
        log("Searching Google directly (%s) ..." % country)
        results = google_search(query, country, num=num_results, proxy=proxy)

    deep_n = max(0, min(int(deep_n or 0), len(results)))
    # Deep-analyze only genuine competitor pages (skip social/forum/marketplace/
    # review/directory hits) so the aggregate reflects real competitor content.
    genuine = [r for r in results if _is_competitor(r["url"])]
    targets = genuine[:deep_n] if deep_n else []
    skipped = len(results[:deep_n]) - len(targets) if deep_n else 0
    if skipped > 0:
        log("Skipped %d non-competitor result(s) (social/marketplace/etc.)." % skipped)
    for i, r in enumerate(targets):
        log("Analyzing competitor %d/%d: %s" % (i + 1, len(targets), r["domain"]))
        try:
            # Measure every competitor against the SAME primary keyword (the query),
            # the way the competitor-analysis method requires.
            r["analysis"] = analyzer.analyze_url(
                r["url"], primary_keyword=query, entities=entities, use_ai=use_ai,
                api_key=api_key, model=model, proxy=proxy, include_text=True,
            )
        except Exception as e:
            r["analysis_error"] = str(e)

    aggregate = None
    if targets:
        aggregate = _aggregate_competitors(query, targets, api_key=api_key, model=model, log=log)
        # The raw text was only needed to build the aggregate; drop it to keep reports lean.
        for r in targets:
            a = r.get("analysis")
            if a:
                a.pop("main_text", None)

    # SERP-level summary
    domains = [r["domain"] for r in results]
    domain_counts = {}
    for d in domains:
        domain_counts[d] = domain_counts.get(d, 0) + 1
    top_domains = sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    log("Done.")
    return {
        "mode": "search",
        "engine": engine,
        "query": query,
        "country": country,
        "gl": loc["gl"],
        "hl": loc["hl"],
        "google_domain": loc["domain"],
        "proxy_used": bool(proxy),
        "searched_at": datetime.now().isoformat(timespec="seconds"),
        "result_count": len(results),
        "deep_analyzed": len(targets),
        "unique_domains": len(domain_counts),
        "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "aggregate": aggregate,
        "results": results,
    }


# ----------------------------------------------------------------------------
# Reporting for a search report (JSON reuses analyzer.to_json)
# ----------------------------------------------------------------------------
def to_json(result):
    return analyzer.to_json(result)


def to_markdown(result):
    out = []
    out.append("# Google Search Analysis")
    out.append("")
    out.append("Query: %s" % result["query"])
    out.append("Country: %s  (gl=%s, hl=%s, %s)" % (
        result["country"], result["gl"], result["hl"], result["google_domain"]))
    out.append("Engine: %s" % result.get("engine", "google-direct"))
    out.append("Proxy used: %s" % ("yes" if result["proxy_used"] else "no"))
    out.append("Searched: %s" % result["searched_at"])
    out.append("Results: %d   Unique domains: %d   Deep-analyzed: %d" % (
        result["result_count"], result["unique_domains"], result["deep_analyzed"]))
    out.append("")

    if result["top_domains"]:
        out.append("## Most-present domains")
        out.append("")
        for d in result["top_domains"][:10]:
            out.append("  - %s (%d)" % (d["domain"], d["count"]))
        out.append("")

    agg = result.get("aggregate")
    if agg:
        a = agg["averages"]
        out.append("## Competitor aggregate (%d pages)" % agg["competitors_analyzed"])
        out.append("")
        out.append("Averages across the analyzed competitors:")
        out.append("  - Word count: %d" % a["word_count"])
        out.append("  - Flesch reading ease: %.1f" % a["flesch_reading_ease"])
        out.append("  - Primary keyword density: %.2f%%" % a["primary_keyword_density_pct"])
        out.append("  - Transition-word sentences: %.1f%%" % a["transition_sentence_pct"])
        out.append("  - Sentences starting with a repeated word: %.1f%%" % a["same_start_sentence_pct"])
        out.append("  - Passive-voice sentences: %.1f%%" % a["passive_voice_pct"])
        out.append("")

        t = agg["targets"]
        out.append("### Target densities (single figures, from the averages)")
        out.append("")
        out.append("  - Primary: \"%s\" -> %.2f%%" % (t["primary"]["keyword"], t["primary"]["target_density_pct"]))
        if t["secondary"]:
            out.append("  Secondary keywords:")
            for s in t["secondary"]:
                out.append("    - %s -> %.2f%%" % (s["phrase"], s["target_density_pct"]))
        if t["entities"]:
            out.append("  Entities:")
            for e in t["entities"]:
                out.append("    - %s -> %.2f%%" % (e["entity"], e["target_density_pct"]))
        out.append("")

        out.append("### Secondary keywords across competitors (phrase / used-by / corpus count / avg density)")
        out.append("")
        for s in agg["secondary_keywords"]:
            out.append("  - %s  (%d/%d competitors, %d hits, %.2f%%)" % (
                s["phrase"], s["used_by_competitors"], agg["competitors_analyzed"],
                s["corpus_count"], s["avg_density_pct"]))
        out.append("")

        out.append("### Entities across competitors (entity / used-by / corpus count / avg density)")
        out.append("")
        for e in agg["entities"]:
            out.append("  - %s  (%d/%d competitors, %d hits, %.2f%%)" % (
                e["entity"], e["used_by_competitors"], agg["competitors_analyzed"],
                e["corpus_count"], e["avg_density_pct"]))
        out.append("")

    out.append("## Ranked results")
    out.append("")
    for r in result["results"]:
        out.append("%d. %s" % (r["position"], r["title"]))
        out.append("   %s" % r["url"])
        if r.get("snippet"):
            out.append("   %s" % r["snippet"])
        if r.get("analysis"):
            m = r["analysis"]["metrics"]
            s = r["analysis"]["seo"]
            out.append("   [deep] words: %d | Flesch: %.1f (%s) | primary kw density: %.2f%% | transition: %.1f%% | passive: %.1f%% | same-start: %.1f%%" % (
                m["word_count"], m["flesch_reading_ease"], m["reading_level"],
                m["primary_keyword_density_pct"], m["transition_sentence_pct"],
                m["passive_voice_pct"], m["same_start_sentence_pct"]))
            spine = s.get("outline") or []
            if spine:
                out.append("   Heading spine:")
                for h in spine[:40]:
                    indent = {"h1": "     ", "h2": "       ", "h3": "         "}.get(h["level"], "     ")
                    out.append("%s%s  %s" % (indent, h["level"].upper(), h["text"]))
        elif r.get("analysis_error"):
            out.append("   [deep] failed: %s" % r["analysis_error"])
        out.append("")
    return "\n".join(out)


# ----------------------------------------------------------------------------
# CLI:  python search.py "best coffee grinder" --country "Germany" --deep 3
# ----------------------------------------------------------------------------
def _cli():
    ap = argparse.ArgumentParser(description="Search Google from a chosen country and analyze the results.")
    ap.add_argument("query", nargs="?", help="Search query / keyword")
    ap.add_argument("--country", default=DEFAULT_COUNTRY, help="Country to search from (see --list-countries)")
    ap.add_argument("--num", type=int, default=10, help="Number of results to collect")
    ap.add_argument("--deep", type=int, default=0, help="Deep-analyze the top N result pages with the page analyzer")
    ap.add_argument("--proxy", default="", help="Proxy URL, e.g. http://user:pass@host:port or socks5://host:port")
    ap.add_argument("--serper-key", dest="serper_key", default="", help="Serper.dev API key (or set SERPER_API_KEY) - avoids the CAPTCHA")
    ap.add_argument("--entities", default="", help="Comma-separated entities to measure in deep-analyzed pages")
    ap.add_argument("--ai", action="store_true", help="Add Groq AI insights to deep-analyzed pages")
    ap.add_argument("--key", default="", help="Groq API key (or set GROQ_API_KEY)")
    ap.add_argument("--model", default=analyzer.DEFAULT_MODEL, help="Groq model id")
    ap.add_argument("--json", dest="json_out", metavar="PATH", help="Write JSON to PATH")
    ap.add_argument("--md", dest="md_out", metavar="PATH", help="Write Markdown to PATH")
    ap.add_argument("--docx", dest="docx_out", metavar="PATH", help="Write a writer-ready outline .docx (needs --deep >= 1)")
    ap.add_argument("--brand", default="Intelinova", help="Brand for the outline .docx (Intelinova, CanComCo, or any name)")
    ap.add_argument("--page-type", dest="page_type", default="",
                    choices=["", "service", "location", "industry", "vendor", "comparison", "blog"],
                    help="Force the outline page type (default: auto-detect from the research)")
    ap.add_argument("--list-countries", action="store_true", help="Print supported countries and exit")
    args = ap.parse_args()

    if args.list_countries:
        for name in country_names():
            print(name)
        return

    if not args.query:
        ap.error("a search query is required (or pass --list-countries)")

    import os
    groq_key = args.key or os.environ.get("GROQ_API_KEY", "")
    entities = [e.strip() for e in args.entities.split(",") if e.strip()]
    result = search_and_analyze(
        args.query, country=args.country, num_results=args.num, deep_n=args.deep,
        entities=entities, use_ai=args.ai, api_key=groq_key,
        model=args.model, proxy=args.proxy.strip() or None,
        serper_key=args.serper_key or os.environ.get("SERPER_API_KEY", ""),
        progress=lambda m: print("... " + m, file=sys.stderr),
    )
    md = to_markdown(result)
    if args.md_out:
        open(args.md_out, "w", encoding="utf-8").write(md)
        print("Wrote " + args.md_out, file=sys.stderr)
    if args.json_out:
        open(args.json_out, "w", encoding="utf-8").write(to_json(result))
        print("Wrote " + args.json_out, file=sys.stderr)
    if args.docx_out:
        import brief_doc
        path = brief_doc.generate_brief_docx(
            result, args.docx_out, brand=args.brand, api_key=groq_key,
            model=args.model, page_type=(args.page_type or None),
            progress=lambda m: print("... " + m, file=sys.stderr))
        print("Wrote " + path, file=sys.stderr)
    if not args.md_out and not args.json_out and not args.docx_out:
        print(md)


if __name__ == "__main__":
    _cli()
