# Web Content Analyzer

Two modes in one app:

1. **Analyze a single URL** - point it at a page you already know. It fetches the
   page, pulls the main body text, and reports content-quality metrics plus
   on-page SEO. Optional Groq AI adds a semantic layer.
2. **Search Google by country** - type a keyword, pick a country, and it queries
   Google *as if* searched from that country (via Google's locale parameters and
   an optional proxy), parses the ranked results, and can deep-analyze the top
   pages with the same engine used in mode 1.

Runs as a PySide6 desktop app or a command-line tool from the same engine.

Four files do the work:

- `analyzer.py` - the page engine (fetch, extract, metrics, entities, SEO, Groq,
  reports, CLI).
- `search.py` - the Google-search engine (country targeting, proxy, SERP parsing,
  competitor aggregate, reports, CLI). Reuses `analyzer.py` for per-page deep-dives.
- `brief_doc.py` - turns a competitor brief into a writer-ready outline `.docx`
  (page-type detection, Groq-generated headings, real density tables).
- `app.py` - the PySide6 GUI. Imports all three. A **Mode** dropdown at the top
  switches between "Analyze a single URL" and "Search Google by country".

## What it measures (no AI needed)

Core content metrics, computed from the extracted text:

- Word count, sentence count, average sentence length
- Flesch reading ease + a plain-language reading level
- Primary keyword density (auto-detected if you leave the keyword blank)
- Entity density for any terms you list
- Transition-word sentence %
- Passive-voice sentence %
- Repeated sentence-start %
- Top 2- and 3-word phrases (secondary-keyword candidates)

On-page SEO, read from the full HTML:

- Title and meta-description length checks
- H1 count, H2/H3 inventory
- Canonical, robots meta, `lang`, viewport, Open Graph
- Image alt-text coverage
- Internal vs external link counts

Each SEO item is graded pass / warn / fail against conventional thresholds.

## Do you need an AI API? No - it is optional

Everything above is deterministic (no key, no cost, works offline once fetched).
Groq only adds what is hard to compute: named-entity extraction, search-intent
classification, secondary-keyword and content-gap suggestions, tone, and E-E-A-T
notes. Leave AI off and the tool is fully functional; turn it on for the extra
layer. If you want AI, Groq is a good pick (fast, OpenAI-compatible, generous free
tier).

## Step 1 - Install

Python 3.9+.

```
cd web-content-analyzer
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

`trafilatura` in requirements is optional but recommended - it gives much cleaner
main-content extraction. Without it, the tool falls back to a BeautifulSoup
heuristic that still works on most content pages.

## Step 2 - Run the desktop app

```
python app.py
```

1. Paste a URL.
2. (Optional) Type a primary keyword. Leave it blank to auto-detect from the top phrase.
3. (Optional) List entities to measure, comma-separated.
4. Click **Analyze**. Results fill six tabs: Overview, Readability & Style,
   Keywords & Entities, On-Page SEO, AI Insights, Raw JSON.
5. **Export Markdown** or **Export JSON** to save the report.

The fetch and analysis run on a background thread, so the window stays responsive.

## Step 3 (optional) - Turn on Groq AI

1. Get a key at https://console.groq.com (free tier available).
2. In the app, tick **Use Groq AI insights** and paste the key, or set an env var
   before launching so the field pre-fills:

   ```
   # macOS / Linux
   export GROQ_API_KEY="gsk_..."
   # Windows PowerShell
   $env:GROQ_API_KEY="gsk_..."
   ```

3. Click **Refresh models** to pull the live model list straight from Groq and
   pick one. This matters: Groq rotates and deprecates models often (its Llama
   chat models were deprecated; general-purpose workloads now use
   `openai/gpt-oss-120b` or the smaller, faster `openai/gpt-oss-20b`, which is the
   default here). Refreshing keeps the list current so a deprecation never breaks
   the tool.

The key is never written to disk. It stays in the field (or your env var) for the
session only.

## Command-line use (scriptable / batch)

Same engine, no GUI:

```
# Print a report to the terminal
python analyzer.py https://example.com --keyword "coffee grinder"

# Save Markdown and JSON
python analyzer.py https://example.com --md report.md --json report.json

# Measure specific entities
python analyzer.py https://example.com --entities "espresso, burr, grind size"

# With AI (uses GROQ_API_KEY, or pass --key)
python analyzer.py https://example.com --ai --model openai/gpt-oss-20b
```

Loop it over a list of URLs from your shell to batch-analyze a whole site.

## Search Google by country (mode 2)

In the app, switch the **Mode** dropdown to **Search Google by country**, then:

1. Type a **Search query** (the keyword you want to rank-check).
2. Pick a **Country** - the results come back the way Google would show them to
   someone searching from there.
3. **Results to collect** - how many organic results to pull (1-30).
4. **Deep-analyze top N** - `0` = just the ranked list; higher = also run the full
   page analyzer (readability, keywords, on-page SEO, optional Groq) on the top N
   result pages and fold the numbers into the report.
5. **SERP API key (Serper)** (recommended) - paste a free key from
   [serper.dev](https://serper.dev). When set, results come through the Serper
   API and **there is no CAPTCHA**. Leave blank to scrape Google directly.
6. **Proxy** (optional, only matters for direct scraping) -
   `http://user:pass@host:port` or `socks5://host:port`. SOCKS proxies need
   `pip install "requests[socks]"`.
7. Click **Analyze**. The **Search Results** tab shows the ranked list, snippets,
   most-present domains, and (if requested) per-page metrics. **Export Markdown /
   JSON** saves it.

Same thing from the command line:

```
# Ranked results for a keyword, as searched from Germany
python search.py "kaffeemühle test" --country "Germany" --num 10

# Reliable, no CAPTCHA: go through the Serper API (free key from serper.dev)
python search.py "best crm software" --country "United Kingdom" --serper-key "YOUR_KEY" --deep 3 --md serp-report.md

# (or set it once)   PowerShell:  $env:SERPER_API_KEY="YOUR_KEY"

# Deep-analyze the top 3 result pages through a proxy (direct-scrape path)
python search.py "kaffeemühle" --country "Germany" --deep 3 \
  --proxy "http://user:pass@de.proxy.example:8000" --md serp-report.md

# List every supported country
python search.py --list-countries
```

### Competitor brief (aggregate research across the top results)

When **Deep-analyze top N** is set (3-5 is typical), the tool does not just analyze
each result page on its own - it aggregates them into a **Competitor Brief** tab,
the same competitor-research layer that SEO outline workflows expect:

- **Averages across the analyzed competitors** - word count, Flesch reading ease,
  primary-keyword density, transition-word %, passive-voice %, repeated-sentence-
  start %. Every competitor is measured against the *same* primary keyword (your
  search query), so the numbers are comparable.
- **Secondary keywords across the whole competitor set** - top bigrams/trigrams
  mined from the combined body text, each with how many competitors use it and its
  average density.
- **Entities across the competitor set** - proper-noun phrases auto-extracted from
  the competitor content (people, orgs, products, technologies, places), each with
  document frequency and average density.
- **Target densities** - single-figure targets for the primary keyword, each top
  secondary keyword, and each entity, derived from the competitor averages.
- **Per-competitor heading spine** - the H1/H2/H3 outline in document order, so you
  can see each competitor's content structure.

All of it exports with **Export Markdown / JSON**. From the CLI it is the same:
`python search.py "ai consulting" --country "Australia" --deep 5 --serper-key KEY --md brief.md`.

Single-URL mode also now surfaces **auto-extracted entities** (Keywords & Entities
tab) and the **heading spine** (On-Page SEO tab).

This covers the *measurable* competitor-analysis step those SEO workflows run
(readability, densities, transition/passive/same-start %, secondary keywords,
entities, heading spines, target densities).

### Export a writer-ready outline (.docx)

With a competitor brief on screen, click **Export Brief (.docx)** (or use
`--docx` on the CLI) to generate a writer-ready page outline, the same deliverable
the partner-led SEO outline workflows produce.

**Brand profiles.** Set **Brief brand** to a known brand and it applies that
brand's rules; any other name uses a generic partner-led profile.

- **Intelinova** - Australia, CTA "Talk To Expert", a Services middle section,
  page types: Service, Location, Industry.
- **CanComCo** - Canada, CTA "Get A Quote", a Features section (top 10 on
  service/location, most-relevant 6 on industry) or an Add-ons section for internet
  products, the `service_noun` in the disclaimer, and the required "Which areas do
  you serve in {location}?" first FAQ on location pages. Page types: Service,
  Location, Industry, Vendor, Comparison, Blog.

**Page type** is detected from the research (Groq classifies it) or forced with the
**Brief page type** dropdown / `--page-type` (service, location, industry, vendor,
comparison, blog). The doc structure follows the selected type exactly.

**The measurable tables come from the real research**: primary keyword + target
density, secondary keywords + densities, and entities + densities. When a Groq key
is present the entities and secondary keywords are **semantically extracted from
the competitor text** (so lowercase domain terms like "point of sale" or "payment
processing" are caught, not just capitalized names), and each term's density is
**computed** from the corpus - never guessed. Only genuine competitor pages feed
the aggregate; social, forum, marketplace, review, and directory results are
skipped.

**The section headings are generated with Groq**, grounded in those real
competitor terms - pains, features/add-ons/services, benefits or use cases, USPs,
and FAQs (plus the type-specific spines for vendor, comparison, and blog). Every
heading is 3 to 5 words; body copy is left for the writer. Without a Groq key it
falls back to headings derived from the research (plainer but valid).

**House style**: the instructions block (partner-led disclaimer + Grammarly goals),
plain black text, bold headers, bullets, two-column tables, brand CTA. No emojis,
no em dashes.

```
# CanComCo POS location page, Canada, Groq-enriched research + AI headings
python search.py "pos system montreal" --country "Canada" --deep 5 --serper-key KEY \
  --key GROQ_KEY --brand "CanComCo" --docx outline.docx

# Intelinova AI-consulting service page, Australia
python search.py "ai consulting" --country "Australia" --deep 5 --serper-key KEY \
  --key GROQ_KEY --brand "Intelinova" --docx outline.docx
```

Outline only - a human writer fills every section. The final body copy and polish
still belong in the dedicated writing workflow; this produces the structured,
research-backed outline it starts from.

### How the "country" is honoured

- **Free, no proxy:** Google's own locale parameters - `gl` (country), `hl`
  (language), the local `google.<tld>` domain, and a matching `Accept-Language`
  header. This gives the localized *ranking* for that country and is enough for
  most SEO checks.
- **With a proxy:** requests exit from an IP in that country, so Google sees a
  genuine local visitor. More authentic and much less likely to be blocked - but
  you must supply the proxy.

### Important: Google blocks automated *scraping* - the fix is the SERP API

Google serves a CAPTCHA / "unusual traffic" page to scripted queries after a
handful of requests from the same IP. You cannot reliably code your way *past*
that page - it is designed to defeat exactly that. When it happens, the direct
scraper stops with a clear message rather than returning garbage.

The real fix is to **not scrape at all** and instead pull Google's results through
an official data API, which never shows a CAPTCHA:

- **Serper.dev is built in.** Get a free key (~2,500 searches) at
  <https://serper.dev>, paste it into the **SERP API key** field (or set
  `SERPER_API_KEY`), and the tool queries through the API with the same country
  targeting. This is the recommended path for anything beyond occasional use.
- Alternatively, a **good residential country proxy** in the Proxy field reduces
  (does not eliminate) blocking on the direct-scrape path.
- Other SERP APIs (SerpApi, DataForSEO) work the same way - `serper_search()` in
  `search.py` is a ~20-line template to copy for a different provider.

The engine actually used is recorded in every report (`engine: serper` vs
`engine: google-direct`).

## How it fits together

```
Mode 1:  URL   --> fetch_html() --> extract_main_text() --> metrics + analyze_seo() --> [groq_insights()] --> result dict --> to_markdown() / to_json()
Mode 2:  query --> google_search(country, proxy) --> ranked results --> [analyze_url() per top page] --> search dict --> search.to_markdown() / to_json()
```

`analyze_url()` (in `analyzer.py`) and `search_and_analyze()` (in `search.py`) are
the two entry points the GUI and CLI call. Each returns one structured dict;
everything downstream (tabs, exports) reads from that dict. The search dict carries
`"mode": "search"` so the GUI and exporter know which renderer to use.

## Extending it

- **New metric**: write a function in `analyzer.py` that takes text, add its output
  to the `metrics` dict in `analyze_url()`, then show it in `readability_html()` (or
  another tab builder) in `app.py`.
- **New SEO check**: add an `add(label, status, detail)` call inside `analyze_seo()`.
- **Different AI provider**: `groq_insights()` uses the plain OpenAI-compatible
  contract, so swapping `GROQ_BASE` and the key targets any OpenAI-style endpoint.
- **Batch tab**: the CLI already batches; a GUI batch view would loop `analyze_url()`
  over a URL list and collect the dicts.

## Limits (so results are read correctly)

- **JavaScript-rendered pages**: the tool reads server-delivered HTML. Sites that
  build their content client-side (some SPAs) may return little text. For those,
  add a headless-browser fetch (Playwright) in `fetch_html()`.
- **Extraction is heuristic** unless `trafilatura` is installed; odd page layouts
  can pull in stray text. Install trafilatura for best results.
- **Passive-voice and transition detection are rule-based** approximations, not a
  full parser - fast and consistent, but not perfect. Treat them as directional.
- **Some sites block automated requests** (403 / bot walls). That is the site's
  choice, not a bug in the tool.
