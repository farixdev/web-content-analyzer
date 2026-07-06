# -*- coding: utf-8 -*-
"""
Web Content Analyzer - engine.

Fetches any live URL, extracts the main body text, and computes a fixed set of
content-quality metrics plus on-page SEO checks. Optional Groq AI layer adds
semantic analysis (entities, intent, gaps). No AI is required for the core metrics.

The seven core metrics (word count, Flesch reading ease, keyword density, entity
density, transition-word %, passive-voice %, repeated-sentence-start %) and the
n-gram keyword mining are ported verbatim from a proven analysis script, so the
numbers match an existing manual workflow.

Usable two ways:
  - imported by the PySide6 GUI (app.py) via analyze_url(...)
  - as a CLI:  python analyzer.py https://example.com --keyword "widget shop" --md report.md

Every number is computed from the fetched text. Nothing is invented.
"""

import os
import re
import sys
import json
import argparse
import collections
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_MODEL = "openai/gpt-oss-20b"   # current Groq general model; refreshable at runtime
GROQ_BASE = "https://api.groq.com/openai/v1"

# ----------------------------------------------------------------------------
# Word lists (ported from the reference analysis script)
# ----------------------------------------------------------------------------
TRANSITIONS = set("""accordingly additionally afterward also although altogether another because before besides
briefly but consequently conversely despite earlier equally especially eventually evidently finally first firstly
former further furthermore hence however indeed instead later lastly likewise meanwhile moreover namely nevertheless
next nonetheless notably otherwise overall particularly previously rather regardless second secondly similarly since
specifically still subsequently then therefore thereafter though thus together ultimately unless unlike until whereas
while yet""".split())

IRREGULAR_PP = set("""been done gone seen made said told given taken known shown found held kept left led met paid put
run sold sent set built bought brought caught taught thought won written driven chosen broken spoken stolen frozen
drawn grown flown worn torn born begun""".split())

BE = {"is", "are", "was", "were", "be", "been", "being", "am", "get", "gets", "got", "gotten"}

STOP = set("""the a an and or but of to in on for with by from as is are be been being this that these those you your we
our they their it its at into over under up out off can could will would should may might must do does did not no new
need needs more most very much many all any each other some one two""".split())


# ----------------------------------------------------------------------------
# Text primitives
# ----------------------------------------------------------------------------
def sentences(text):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in parts if s.strip()]


def words(text):
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", text.lower())


def syllables(word):
    word = word.lower()
    groups = re.findall(r'[aeiouy]+', word)
    n = len(groups)
    if word.endswith('e') and n > 1:
        n -= 1
    return max(1, n)


def flesch(text):
    sents = sentences(text)
    wds = words(text)
    if not sents or not wds:
        return 0.0
    syl = sum(syllables(w) for w in wds)
    return round(206.835 - 1.015 * (len(wds) / len(sents)) - 84.6 * (syl / len(wds)), 1)


def flesch_band(score):
    if score >= 90:  return "Very easy (5th grade)"
    if score >= 80:  return "Easy (6th grade)"
    if score >= 70:  return "Fairly easy (7th grade)"
    if score >= 60:  return "Plain English (8th-9th grade)"
    if score >= 50:  return "Fairly difficult (10th-12th grade)"
    if score >= 30:  return "Difficult (college)"
    return "Very difficult (graduate)"


def count_phrase(text, phrase):
    wds = words(text)
    p = phrase.lower().split()
    if not p:
        return 0
    if len(p) == 1:
        return sum(1 for w in wds if w == p[0])
    c = 0
    for i in range(len(wds) - len(p) + 1):
        if wds[i:i + len(p)] == p:
            c += 1
    return c


def density(text, phrase):
    total = len(words(text))
    if total == 0 or not phrase.strip():
        return 0.0
    return round(count_phrase(text, phrase) / total * 100, 2)


def pct_transition(text):
    sents = sentences(text)
    if not sents:
        return 0.0
    hit = sum(1 for s in sents if set(words(s)) & TRANSITIONS)
    return round(hit / len(sents) * 100, 1)


def pct_same_start(text):
    sents = sentences(text)
    if not sents:
        return 0.0
    firsts = [(words(s)[0] if words(s) else "") for s in sents]
    counts = collections.Counter(firsts)
    repeated = sum(1 for f in firsts if f and counts[f] > 1)
    return round(repeated / len(sents) * 100, 1)


def pct_passive(text):
    sents = sentences(text)
    if not sents:
        return 0.0
    hit = 0
    for s in sents:
        w = words(s)
        found = False
        for i, tok in enumerate(w):
            if tok in BE:
                for j in range(i + 1, min(i + 4, len(w))):
                    cand = w[j]
                    if cand.endswith('ed') or cand in IRREGULAR_PP:
                        found = True
                        break
            if found:
                break
        if found:
            hit += 1
    return round(hit / len(sents) * 100, 1)


def ngrams(wds, n, stop):
    c = collections.Counter()
    for i in range(len(wds) - n + 1):
        g = wds[i:i + n]
        if any(x in stop or len(x) < 3 for x in g):
            continue
        c[" ".join(g)] += 1
    return c


# Capitalized words that are usually sentence-starters / function words, not
# entities. Used to trim and filter auto-extracted entity candidates.
COMMON_CAPS = set("""the a an and or but of to in on for with by from as is are be been
being this that these those you your we our us they their it its at into over under up out
off can could will would should may might must do does did not no new more most very much
many all any each other some one two first second next also however here there so if when
what why who how then thus while yet i we're it's that's here's there's get gets got""".split())


def extract_entities(text, top_n=30, min_count=2):
    """Best-effort entity extraction: proper-noun-style capitalized phrases in
    the text, ranked by frequency, each with occurrence count and density.

    Not a full NER model - a deterministic heuristic that surfaces the named
    people, orgs, products, technologies, and places a page leans on, the way the
    competitor-analysis method wants entities surfaced from competitor content.
    """
    # Runs of capitalized words separated by spaces/tabs only - never across a
    # newline, so a heading does not fuse with the next block's first word.
    raw = re.findall(r"[A-Z][A-Za-z0-9&.'\-]*(?:[ \t]+[A-Z][A-Za-z0-9&.'\-]*)*", text or "")
    surface = collections.Counter()
    for cand in raw:
        toks = cand.strip(" .,:;!?-'\"").split()
        # Trim leading sentence-starter / function words ("Our Team" -> "Team").
        while toks and toks[0].lower() in COMMON_CAPS:
            toks = toks[1:]
        if not toks or len(toks) > 4:   # >4 caps in a row is almost always noise
            continue
        low = [t.lower() for t in toks]
        if all(t in COMMON_CAPS or t in STOP for t in low):
            continue
        if len(toks) == 1 and low[0] in COMMON_CAPS:
            continue
        surface[" ".join(toks)] += 1

    results, seen = [], set()
    for cand, _ in surface.most_common(top_n * 4):
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        c = count_phrase(text, cand)
        # Single-word entities must recur to count; multi-word phrases are kept.
        if len(cand.split()) == 1 and c < min_count:
            continue
        if c < 1:
            continue
        results.append({"entity": cand, "count": c, "density_pct": density(text, cand)})
        if len(results) >= top_n:
            break
    return results


# ----------------------------------------------------------------------------
# Fetch + extract
# ----------------------------------------------------------------------------
def _proxies(proxy):
    """Normalize a proxy argument into a requests `proxies` dict (or None).

    Accepts None, an already-built dict, or a single URL string that is used
    for both http and https.
    """
    if not proxy:
        return None
    if isinstance(proxy, dict):
        return proxy
    proxy = str(proxy).strip()
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = "http://" + proxy   # bare host:port defaults to http
    return {"http": proxy, "https": proxy}


def fetch_html(url, timeout=25, proxy=None):
    """Return (final_url, html). Raises on network / non-HTML responses.

    `proxy` may be a requests-style proxies dict, a single proxy URL string
    (e.g. "http://user:pass@host:port" or "socks5://host:port"), or None.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WebContentAnalyzer/1.0; local research tool)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True,
                        proxies=_proxies(proxy))
    resp.raise_for_status()
    try:
        resp.encoding = resp.apparent_encoding or resp.encoding
    except Exception:
        pass
    ctype = resp.headers.get("Content-Type", "")
    head = resp.text[:2000].lower()
    if "html" not in ctype.lower() and "<html" not in head and "<!doctype html" not in head:
        raise ValueError("URL did not return an HTML page (Content-Type: %s)." % (ctype or "unknown"))
    return resp.url, resp.text


def extract_main_text(html, url=None):
    """Return (main_text, method). Uses trafilatura when installed, else a
    BeautifulSoup heuristic that strips boilerplate and keeps block text."""
    # Best quality: trafilatura, if the user installed it.
    try:
        import trafilatura
        txt = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True, favor_precision=True
        )
        if txt and len(txt.split()) > 50:
            return txt.strip(), "trafilatura"
    except Exception:
        pass

    # Fallback: dependency-light heuristic.
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template", "svg", "iframe"]):
        t.decompose()
    container = soup.find("main") or soup.find("article") or soup.body or soup
    for t in container.find_all(["nav", "header", "footer", "aside", "form"]):
        t.decompose()
    blocks = []
    for el in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        s = el.get_text(" ", strip=True)
        if s:
            blocks.append(s)
    text = "\n".join(blocks) if blocks else container.get_text(" ", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip(), "heuristic (install trafilatura for better extraction)"


# ----------------------------------------------------------------------------
# On-page SEO checks (full document, not just the main text)
# ----------------------------------------------------------------------------
def _meta(soup, name):
    tag = soup.find("meta", attrs={"name": re.compile("^%s$" % re.escape(name), re.I)})
    return (tag.get("content") or "").strip() if tag else ""


def analyze_seo(html, final_url):
    soup = BeautifulSoup(html, "html.parser")
    checks = []  # each: {"label","status","detail"} ; status in pass/warn/fail/info

    def add(label, status, detail):
        checks.append({"label": label, "status": status, "detail": detail})

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    tlen = len(title)
    if not title:
        add("Title tag", "fail", "Missing <title>.")
    elif tlen < 30:
        add("Title tag", "warn", "Short (%d chars). Aim for 50-60." % tlen)
    elif tlen > 65:
        add("Title tag", "warn", "Long (%d chars). May be truncated in SERPs." % tlen)
    else:
        add("Title tag", "pass", "%d chars." % tlen)

    # Meta description
    meta_desc = _meta(soup, "description")
    mlen = len(meta_desc)
    if not meta_desc:
        add("Meta description", "fail", "Missing.")
    elif mlen < 70:
        add("Meta description", "warn", "Short (%d chars). Aim for 120-160." % mlen)
    elif mlen > 165:
        add("Meta description", "warn", "Long (%d chars). May be truncated." % mlen)
    else:
        add("Meta description", "pass", "%d chars." % mlen)

    # Headings
    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    h3s = [h.get_text(" ", strip=True) for h in soup.find_all("h3")]
    # Ordered H1/H2/H3 spine in document order (the competitor "content outline").
    outline = [{"level": h.name, "text": h.get_text(" ", strip=True)}
               for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
    if len(h1s) == 0:
        add("H1", "fail", "No H1 found.")
    elif len(h1s) == 1:
        add("H1", "pass", "Exactly one H1.")
    else:
        add("H1", "warn", "%d H1 tags (usually one is best)." % len(h1s))

    # Canonical
    can = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
    canonical = (can.get("href") or "").strip() if can else ""
    add("Canonical", "pass" if canonical else "warn",
        canonical or "No canonical link element.")

    # Robots meta
    robots = _meta(soup, "robots")
    if robots and ("noindex" in robots.lower()):
        add("Robots meta", "warn", "Contains noindex: %s" % robots)
    else:
        add("Robots meta", "info", robots or "none")

    # Lang
    lang = (soup.html.get("lang") if soup.html else "") or ""
    add("HTML lang", "pass" if lang else "warn", lang or "No lang attribute on <html>.")

    # Viewport
    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    add("Viewport (mobile)", "pass" if vp else "warn",
        "present" if vp else "No viewport meta tag.")

    # Open Graph
    og_title = soup.find("meta", attrs={"property": "og:title"})
    add("Open Graph", "pass" if og_title else "info",
        "og:* tags present" if og_title else "No Open Graph tags.")

    # Images / alt
    imgs = soup.find_all("img")
    with_alt = sum(1 for i in imgs if (i.get("alt") or "").strip())
    if imgs:
        pct = round(with_alt / len(imgs) * 100)
        status = "pass" if pct >= 90 else ("warn" if pct >= 50 else "fail")
        add("Image alt text", status, "%d/%d images have alt (%d%%)." % (with_alt, len(imgs), pct))
    else:
        add("Image alt text", "info", "No images.")

    # Links internal / external
    base = urlparse(final_url).netloc
    internal = external = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")) or not href:
            continue
        netloc = urlparse(urljoin(final_url, href)).netloc
        if netloc == "" or netloc == base:
            internal += 1
        else:
            external += 1
    add("Links", "info", "%d internal, %d external." % (internal, external))

    return {
        "title": title,
        "title_length": tlen,
        "meta_description": meta_desc,
        "meta_description_length": mlen,
        "canonical": canonical,
        "robots": robots,
        "lang": lang,
        "h1": h1s,
        "h2": h2s,
        "h3": h3s,
        "outline": outline,
        "images_total": len(imgs),
        "images_with_alt": with_alt,
        "links_internal": internal,
        "links_external": external,
        "checks": checks,
    }


# ----------------------------------------------------------------------------
# Optional Groq AI layer (OpenAI-compatible endpoint)
# ----------------------------------------------------------------------------
def _parse_json_blob(s):
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(s)):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except Exception:
                            break
        return {"raw_response": s}


def groq_list_models(api_key, timeout=20):
    """Return a sorted list of live Groq model ids. Empty list on failure."""
    r = requests.get(
        GROQ_BASE + "/models",
        headers={"Authorization": "Bearer %s" % api_key},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    return sorted(m.get("id", "") for m in data if m.get("id"))


def groq_json(api_key, model, system, user, timeout=90, max_tokens=1600, temperature=0.4):
    """Generic Groq chat call that expects a single JSON object back. Returns the
    parsed dict (or {"raw_response": ...} if the model did not emit clean JSON)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }
    r = requests.post(
        GROQ_BASE + "/chat/completions",
        headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise RuntimeError("Groq API %d: %s" % (r.status_code, msg))
    return _parse_json_blob(r.json()["choices"][0]["message"]["content"])


def groq_insights(api_key, model, page_title, main_text, primary_keyword, timeout=90):
    """Ask a Groq model for a structured semantic analysis. Returns a dict."""
    text = main_text[:12000]  # cap tokens
    system = ("You are an expert SEO and content strategist. Analyze the page and reply "
              "with a single valid JSON object only. No prose, no markdown, no code fences.")
    user = (
        "Page title: %s\n"
        "Target/primary keyword: %s\n\n"
        "Analyze the web page content below and return a JSON object with EXACTLY these keys:\n"
        "  primary_topic (string)\n"
        "  search_intent (one of: informational, commercial, transactional, navigational)\n"
        "  target_audience (short string)\n"
        "  named_entities (array of up to 15 important entities: people, orgs, products, technologies, places)\n"
        "  secondary_keywords (array of up to 12 keyword phrases this page should also target)\n"
        "  content_gaps (array of up to 6 short strings: topics competitors cover that this page misses)\n"
        "  quality_notes (array of up to 6 short strings: concrete strengths and weaknesses)\n"
        "  tone (short string)\n"
        "  eeat_signals (short string on Experience/Expertise/Authoritativeness/Trust present or missing)\n\n"
        "Content:\n\"\"\"%s\"\"\""
    ) % (page_title or "(none)", primary_keyword or "(infer it)", text)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 1600,
    }
    r = requests.post(
        GROQ_BASE + "/chat/completions",
        headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code >= 400:
        # Surface Groq's own error message (e.g. model deprecated / bad key).
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise RuntimeError("Groq API %d: %s" % (r.status_code, msg))
    content = r.json()["choices"][0]["message"]["content"]
    return _parse_json_blob(content)


# ----------------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------------
def analyze_url(url, primary_keyword="", entities=None, use_ai=False,
                api_key="", model=DEFAULT_MODEL, progress=None, proxy=None,
                include_text=False):
    """Run the full pipeline and return a structured result dict.

    include_text=True adds the extracted main body text under result["main_text"]
    (used by the competitor-aggregate layer; omitted by default to keep reports lean).
    """
    log = progress if callable(progress) else (lambda m: None)
    entities = entities or []
    primary_keyword = (primary_keyword or "").strip()

    log("Fetching page...")
    final_url, html = fetch_html(url, proxy=proxy)

    log("Extracting main content...")
    main_text, method = extract_main_text(html, final_url)
    if not main_text or len(words(main_text)) < 20:
        raise ValueError("Could not extract meaningful text. The page may be "
                         "JavaScript-rendered, empty, or blocking automated requests.")

    log("Computing readability and keyword metrics...")
    wc = len(words(main_text))
    sc = len(sentences(main_text))
    top_bi = ngrams(words(main_text), 2, STOP).most_common(20)
    top_tri = ngrams(words(main_text), 3, STOP).most_common(12)

    auto_detected = False
    if not primary_keyword:
        primary_keyword = top_bi[0][0] if top_bi else (words(main_text)[0] if words(main_text) else "")
        auto_detected = True

    fl = flesch(main_text)
    metrics = {
        "extraction_method": method,
        "word_count": wc,
        "sentence_count": sc,
        "avg_sentence_length_words": round(wc / max(1, sc), 1),
        "flesch_reading_ease": fl,
        "reading_level": flesch_band(fl),
        "primary_keyword": primary_keyword,
        "primary_keyword_auto_detected": auto_detected,
        "primary_keyword_count": count_phrase(main_text, primary_keyword),
        "primary_keyword_density_pct": density(main_text, primary_keyword),
        "transition_sentence_pct": pct_transition(main_text),
        "same_start_sentence_pct": pct_same_start(main_text),
        "passive_voice_pct": pct_passive(main_text),
        "top_bigrams": [{"phrase": p, "count": c} for p, c in top_bi],
        "top_trigrams": [{"phrase": p, "count": c} for p, c in top_tri],
        "entity_densities": [
            {"entity": e, "count": count_phrase(main_text, e), "density_pct": density(main_text, e)}
            for e in entities
        ],
        "auto_entities": extract_entities(main_text, top_n=20),
    }

    log("Running on-page SEO checks...")
    seo = analyze_seo(html, final_url)

    result = {
        "url": url,
        "final_url": final_url,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics,
        "seo": seo,
    }
    if include_text:
        result["main_text"] = main_text

    if use_ai:
        if not api_key.strip():
            result["ai_error"] = "AI insights were requested but no Groq API key was provided."
        else:
            log("Requesting AI insights from Groq (%s)..." % model)
            try:
                result["ai"] = groq_insights(api_key.strip(), model, seo.get("title", ""),
                                             main_text, primary_keyword)
            except Exception as e:
                result["ai_error"] = str(e)

    log("Done.")
    return result


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------
def to_json(result):
    return json.dumps(result, indent=2, ensure_ascii=False)


def to_markdown(result):
    m = result["metrics"]
    s = result["seo"]
    out = []
    out.append("# Content Analysis Report")
    out.append("")
    out.append("URL: %s" % result["final_url"])
    out.append("Analyzed: %s" % result["analyzed_at"])
    out.append("Extraction: %s" % m["extraction_method"])
    out.append("")
    out.append("## Readability and Style")
    out.append("")
    out.append("Word count: %d" % m["word_count"])
    out.append("Sentences: %d (avg %.1f words each)" % (m["sentence_count"], m["avg_sentence_length_words"]))
    out.append("Flesch reading ease: %.1f -- %s" % (m["flesch_reading_ease"], m["reading_level"]))
    out.append("Transition-word sentences: %.1f%%" % m["transition_sentence_pct"])
    out.append("Passive-voice sentences: %.1f%%" % m["passive_voice_pct"])
    out.append("Sentences starting with a repeated word: %.1f%%" % m["same_start_sentence_pct"])
    out.append("")
    out.append("## Keywords and Entities")
    out.append("")
    tag = " (auto-detected)" if m["primary_keyword_auto_detected"] else ""
    out.append("Primary keyword%s: \"%s\" -- %d hits, density %.2f%%"
               % (tag, m["primary_keyword"], m["primary_keyword_count"], m["primary_keyword_density_pct"]))
    if m["entity_densities"]:
        out.append("")
        out.append("Entity densities:")
        for e in m["entity_densities"]:
            out.append("  - %s: %d hits, %.2f%%" % (e["entity"], e["count"], e["density_pct"]))
    out.append("")
    if m.get("auto_entities"):
        out.append("Detected entities (auto-extracted):")
        for e in m["auto_entities"][:15]:
            out.append("  - %s: %d hits, %.2f%%" % (e["entity"], e["count"], e["density_pct"]))
        out.append("")
    out.append("Top phrases (secondary-keyword candidates):")
    for b in m["top_bigrams"][:12]:
        out.append("  - %s (%d)" % (b["phrase"], b["count"]))
    out.append("")
    out.append("## On-Page SEO")
    out.append("")
    out.append("Title (%d chars): %s" % (s["title_length"], s["title"] or "(missing)"))
    out.append("Meta description (%d chars): %s" % (s["meta_description_length"], s["meta_description"] or "(missing)"))
    out.append("H1: %s" % (" | ".join(s["h1"]) or "(none)"))
    out.append("H2 count: %d   H3 count: %d" % (len(s["h2"]), len(s["h3"])))
    if s.get("outline"):
        out.append("Heading spine:")
        for h in s["outline"][:60]:
            indent = {"h1": "  ", "h2": "    ", "h3": "      "}.get(h["level"], "  ")
            out.append("%s%s %s" % (indent, h["level"].upper(), h["text"]))
    out.append("Images: %d (%d with alt)" % (s["images_total"], s["images_with_alt"]))
    out.append("Links: %d internal, %d external" % (s["links_internal"], s["links_external"]))
    out.append("Canonical: %s" % (s["canonical"] or "(none)"))
    out.append("HTML lang: %s" % (s["lang"] or "(none)"))
    out.append("")
    out.append("Checks:")
    for c in s["checks"]:
        out.append("  [%s] %s: %s" % (c["status"].upper(), c["label"], c["detail"]))
    if result.get("ai"):
        ai = result["ai"]
        out.append("")
        out.append("## AI Insights (Groq)")
        out.append("")
        for k, v in ai.items():
            if isinstance(v, list):
                out.append("%s:" % k.replace("_", " ").title())
                for item in v:
                    out.append("  - %s" % item)
            else:
                out.append("%s: %s" % (k.replace("_", " ").title(), v))
    elif result.get("ai_error"):
        out.append("")
        out.append("## AI Insights")
        out.append("")
        out.append("Not available: %s" % result["ai_error"])
    return "\n".join(out)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _cli():
    ap = argparse.ArgumentParser(description="Analyze the content of any web page.")
    ap.add_argument("url", help="Page URL to analyze")
    ap.add_argument("--keyword", default="", help="Target primary keyword (blank = auto-detect)")
    ap.add_argument("--entities", default="", help="Comma-separated entities to measure")
    ap.add_argument("--ai", action="store_true", help="Add Groq AI insights")
    ap.add_argument("--key", default=os.environ.get("GROQ_API_KEY", ""), help="Groq API key (or set GROQ_API_KEY)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Groq model id")
    ap.add_argument("--json", dest="json_out", metavar="PATH", help="Write JSON to PATH")
    ap.add_argument("--md", dest="md_out", metavar="PATH", help="Write Markdown to PATH")
    args = ap.parse_args()

    entities = [e.strip() for e in args.entities.split(",") if e.strip()]
    result = analyze_url(
        args.url, primary_keyword=args.keyword, entities=entities,
        use_ai=args.ai, api_key=args.key, model=args.model,
        progress=lambda m: print("... " + m, file=sys.stderr),
    )
    md = to_markdown(result)
    if args.md_out:
        open(args.md_out, "w", encoding="utf-8").write(md)
        print("Wrote " + args.md_out, file=sys.stderr)
    if args.json_out:
        open(args.json_out, "w", encoding="utf-8").write(to_json(result))
        print("Wrote " + args.json_out, file=sys.stderr)
    if not args.md_out and not args.json_out:
        print(md)


if __name__ == "__main__":
    _cli()
