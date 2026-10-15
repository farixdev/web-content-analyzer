# -*- coding: utf-8 -*-
"""
Keyword Ranking and Cross-Site Competitor Comparison Matrix.

Analyzes text extracted across multiple competitor websites:
1. Ranks Top 20 keywords/phrases per website (exact occurrences & density).
2. Compares inter-site prominence: discovers which keywords appear across
   ALL or most competitor sites, with per-competitor breakdown and aggregate count.
"""

import re
import collections
import analyzer

# Extended web and conversational stopwords to ensure only high-value topical terms remain
WEB_STOPWORDS = analyzer.STOP | {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "has", "have", "had", "having", "his", "her", "hers", "him", "he", "she",
    "them", "theirs", "myself", "himself", "herself", "itself", "just", "than",
    "then", "there", "their", "here", "only", "such", "own", "same", "so", "too",
    "both", "through", "during", "before", "after", "above", "below", "between",
    "while", "into", "over", "under", "again", "further", "once",
    "privacy", "policy", "cookies", "cookie", "copyright", "rights", "reserved",
    "terms", "conditions", "contact", "about", "home", "search", "menu", "login",
    "sign", "email", "phone", "click", "website", "page", "read", "view",
    "learn", "get", "use", "using", "also", "like", "one", "two", "well",
    "make", "see", "us", "free", "help", "information", "support", "services",
    "service", "business", "company", "com", "www", "http", "https",
    "subscribe", "newsletter", "disclaimer", "accessibility", "all", "sitemap",
    "faqs", "faq", "notice", "accept", "decline", "manage", "preferences",
    "cart", "checkout", "account", "register", "share", "tweet", "facebook",
    "twitter", "linkedin", "instagram", "youtube", "skip", "content", "inc",
    "ltd", "corp", "llc", "designed", "powered", "read", "more", "back", "top"
}


def clean_words(text):
    """Tokenize text into lowercase alphabetic words, skipping 1-character tokens."""
    raw = re.findall(r"[A-Za-z][A-Za-z'\-]*", text.lower())
    return [w for w in raw if len(w) > 1 and not w.isdigit()]


def get_site_keywords(combined_text, top_n=20, min_word_len=3, custom_stopwords=None, ngram_filter="all"):
    """Extract and rank the Top N keywords and phrases for a single website corpus.

    Combines clean single words (unigrams) and multi-word phrases (bigrams/trigrams)
    that don't start/end with stopwords, ranked by total occurrences.
    """
    stopwords = set(WEB_STOPWORDS)
    if custom_stopwords:
        if isinstance(custom_stopwords, str):
            custom_stopwords = [w.strip().lower() for w in custom_stopwords.split(",") if w.strip()]
        stopwords.update(custom_stopwords)

    wds = clean_words(combined_text)
    total_words = len(wds)
    if total_words == 0:
        return []

    include_unigrams = ngram_filter in ("all", "single")
    include_phrases = ngram_filter in ("all", "phrases")

    # 1. Meaningful unigrams
    uni_counts = collections.Counter()
    if include_unigrams:
        unigrams = [w for w in wds if len(w) >= min_word_len and w not in stopwords]
        uni_counts = collections.Counter(unigrams)

    # 2. Bigrams (2-word phrases)
    bi_counts = collections.Counter()
    if include_phrases:
        for i in range(len(wds) - 1):
            w1, w2 = wds[i], wds[i + 1]
            if w1 not in stopwords and w2 not in stopwords and len(w1) >= 3 and len(w2) >= 3:
                bi_counts["%s %s" % (w1, w2)] += 1

    # 3. Trigrams (3-word phrases)
    tri_counts = collections.Counter()
    if include_phrases:
        for i in range(len(wds) - 2):
            w1, w2, w3 = wds[i], wds[i + 1], wds[i + 2]
            # Outer words must not be stopwords
            if w1 not in stopwords and w3 not in stopwords and len(w1) >= 3 and len(w3) >= 3:
                tri_counts["%s %s %s" % (w1, w2, w3)] += 1

    # Combine candidates
    combined_counts = collections.Counter()
    if include_unigrams:
        for word, count in uni_counts.items():
            if count >= 2:
                combined_counts[word] = count

    if include_phrases:
        for phrase, count in bi_counts.items():
            if count >= 2:
                combined_counts[phrase] = count
        for phrase, count in tri_counts.items():
            if count >= 2:
                combined_counts[phrase] = count

    ranked = []
    for rank, (term, count) in enumerate(combined_counts.most_common(top_n), start=1):
        density_pct = round((count / total_words) * 100, 2)
        ranked.append({
            "rank": rank,
            "keyword": term,
            "count": count,
            "density_pct": density_pct,
            "word_type": "phrase" if " " in term else "single",
        })

    return ranked


def build_inter_site_matrix(sites_data, top_n_cross=30, custom_stopwords=None, ngram_filter="all"):
    """Compare keywords across all scraped competitor sites.

    `sites_data` is a list of dicts:
    [
        {"domain": "site1.com", "pages_scraped": 25, "total_words": 15000, "combined_text": "..."},
        ...
    ]

    Returns:
    {
        "competitors_count": 5,
        "domains": ["site1.com", "site2.com", ...],
        "per_site_top_20": {
            "site1.com": [...],
            ...
        },
        "cross_site_keywords": [
            {
                "keyword": "point of sale",
                "used_by_count": 5,
                "used_by_pct": 100.0,
                "total_count": 482,
                "breakdown": {"site1.com": 120, "site2.com": 95, ...}
            },
            ...
        ]
    }
    """
    domains = [s["domain"] for s in sites_data]
    n_competitors = len(domains)

    # 1. Per-site top 20
    per_site_top = {}
    site_term_counts = {}  # domain -> Counter of all candidate terms

    stopwords = set(WEB_STOPWORDS)
    if custom_stopwords:
        if isinstance(custom_stopwords, str):
            custom_stopwords = [w.strip().lower() for w in custom_stopwords.split(",") if w.strip()]
        stopwords.update(custom_stopwords)

    for s in sites_data:
        dom = s["domain"]
        txt = s.get("combined_text", "")
        top20 = get_site_keywords(txt, top_n=20, custom_stopwords=stopwords, ngram_filter=ngram_filter)
        per_site_top[dom] = top20

        # Build full term counter for cross-site counting
        wds = clean_words(txt)
        counts = collections.Counter()
        # Count words
        for w in wds:
            if len(w) >= 3 and w not in stopwords:
                counts[w] += 1
        # Count bigrams
        for i in range(len(wds) - 1):
            w1, w2 = wds[i], wds[i + 1]
            if w1 not in stopwords and w2 not in stopwords and len(w1) >= 3 and len(w2) >= 3:
                counts["%s %s" % (w1, w2)] += 1
        site_term_counts[dom] = counts

    # 2. Collect candidate terms that appeared in any top 20 or appear widely
    candidate_terms = set()
    for dom, top_list in per_site_top.items():
        for item in top_list:
            candidate_terms.add(item["keyword"])

    # 3. Cross-site aggregation
    cross_results = []
    for term in candidate_terms:
        breakdown = {}
        sites_with_term = 0
        total_occurrences = 0

        for dom in domains:
            c = site_term_counts[dom].get(term, 0)
            breakdown[dom] = c
            if c > 0:
                sites_with_term += 1
            total_occurrences += c

        if sites_with_term >= 1:
            penetration_pct = round((sites_with_term / max(1, n_competitors)) * 100, 1)
            cross_results.append({
                "keyword": term,
                "used_by_count": sites_with_term,
                "used_by_pct": penetration_pct,
                "total_count": total_occurrences,
                "breakdown": breakdown,
            })

    # Sort cross-site keywords:
    # 1. Sites used by (descending)
    # 2. Total occurrences (descending)
    cross_results.sort(key=lambda x: (-x["used_by_count"], -x["total_count"]))

    return {
        "competitors_count": n_competitors,
        "domains": domains,
        "per_site_top_20": per_site_top,
        "cross_site_keywords": cross_results[:top_n_cross],
    }
