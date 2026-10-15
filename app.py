# -*- coding: utf-8 -*-
"""
Web Content Analyzer - PySide6 desktop GUI.

Thin front end over analyzer.py. All fetching / analysis / Groq calls run in a
background QThread so the window never freezes. Run:  python app.py
"""

import os
import sys
import time

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QComboBox, QLabel, QGroupBox, QTabWidget,
    QTextBrowser, QProgressBar, QFileDialog, QMessageBox, QPlainTextEdit,
    QStackedWidget, QSpinBox, QListWidget, QFrame, QGraphicsDropShadowEffect,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

import analyzer
import search
import brief_doc
import config
import llm


def resource_path(rel):
    """Absolute path to a bundled resource, working both in dev and when frozen
    into a PyInstaller .exe (where data files live under sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _env_path():
    """Where to read/write the .env — next to the .exe when frozen, else the
    module directory."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def save_keys_to_env(mapping):
    """Merge KEY=VALUE pairs into the tool's .env, preserving other lines.
    A blank value removes that key. Returns the path written."""
    path = _env_path()
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, seen = [], set()
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in mapping:
                seen.add(k)
                if mapping[k]:
                    out.append("%s=%s" % (k, mapping[k]))
                continue
        out.append(line)
    for k, v in mapping.items():
        if k not in seen and v:
            out.append("%s=%s" % (k, v))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    return path


# ----------------------------------------------------------------------------
# Background workers
# ----------------------------------------------------------------------------
class AnalyzeWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.p = params

    @Slot()
    def run(self):
        try:
            result = analyzer.analyze_url(
                url=self.p["url"],
                primary_keyword=self.p["keyword"],
                entities=self.p["entities"],
                use_ai=self.p["use_ai"],
                api_key=self.p["api_key"],
                model=self.p["model"],
                progress=self.progress.emit,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SearchWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.p = params

    @Slot()
    def run(self):
        try:
            if self.p.get("deep_crawl"):
                result = search.search_and_deep_crawl(
                    query=self.p["query"],
                    country=self.p["country"],
                    num_results=self.p["num_results"],
                    pages_per_site=self.p["pages_per_site"],
                    max_competitors=self.p["max_competitors"],
                    proxy=self.p["proxy"],
                    serper_key=self.p["serper_key"],
                    progress=self.progress.emit,
                )
            else:
                result = search.search_and_analyze(
                    query=self.p["query"],
                    country=self.p["country"],
                    num_results=self.p["num_results"],
                    deep_n=self.p["deep_n"],
                    entities=self.p["entities"],
                    use_ai=self.p["use_ai"],
                    api_key=self.p["api_key"],
                    model=self.p["model"],
                    proxy=self.p["proxy"],
                    serper_key=self.p["serper_key"],
                    progress=self.progress.emit,
                )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BriefDocWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.p = params

    @Slot()
    def run(self):
        try:
            path = brief_doc.generate_brief_docx(
                self.p["result"], self.p["path"], brand=self.p["brand"],
                api_key=self.p["api_key"], model=self.p["model"],
                page_type=self.p["page_type"], progress=self.progress.emit,
            )
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


class ModelsWorker(QObject):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    @Slot()
    def run(self):
        try:
            self.finished.emit(analyzer.groq_list_models(self.api_key))
        except Exception as e:
            self.error.emit(str(e))


# ----------------------------------------------------------------------------
# HTML rendering helpers for the result tabs
# ----------------------------------------------------------------------------
STATUS_DOT = {
    "pass": ("#1a7f37", "PASS"),
    "warn": ("#9a6700", "WARN"),
    "fail": ("#cf222e", "FAIL"),
    "info": ("#57606a", "INFO"),
}


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _row(k, v):
    return "<tr><td style='padding:3px 14px 3px 0;color:#57606a'>%s</td><td style='padding:3px 0'><b>%s</b></td></tr>" % (_esc(k), _esc(v))


def overview_html(r):
    m, s = r["metrics"], r["seo"]
    rows = [
        _row("Final URL", r["final_url"]),
        _row("Analyzed", r["analyzed_at"]),
        _row("Extraction", m["extraction_method"]),
        _row("Word count", m["word_count"]),
        _row("Flesch reading ease", "%.1f  (%s)" % (m["flesch_reading_ease"], m["reading_level"])),
        _row("Primary keyword", "%s%s" % (m["primary_keyword"], "  (auto)" if m["primary_keyword_auto_detected"] else "")),
        _row("Keyword density", "%.2f%%  (%d hits)" % (m["primary_keyword_density_pct"], m["primary_keyword_count"])),
        _row("Title", "%s  (%d chars)" % (s["title"] or "(missing)", s["title_length"])),
        _row("H1 / H2 / H3", "%d / %d / %d" % (len(s["h1"]), len(s["h2"]), len(s["h3"]))),
    ]
    return "<table>%s</table>" % "".join(rows)


def readability_html(r):
    m = r["metrics"]
    rows = [
        _row("Word count", m["word_count"]),
        _row("Sentences", "%d  (avg %.1f words)" % (m["sentence_count"], m["avg_sentence_length_words"])),
        _row("Flesch reading ease", "%.1f" % m["flesch_reading_ease"]),
        _row("Reading level", m["reading_level"]),
        _row("Transition-word sentences", "%.1f%%" % m["transition_sentence_pct"]),
        _row("Passive-voice sentences", "%.1f%%" % m["passive_voice_pct"]),
        _row("Repeated sentence starts", "%.1f%%" % m["same_start_sentence_pct"]),
    ]
    note = ("<p style='color:#57606a'>Conventional editorial targets: Flesch above 50-60, "
            "transitions ~30% of sentences, passive voice under 10%, and few consecutive "
            "sentences starting with the same word.</p>")
    return ("<table>%s</table>" % "".join(rows)) + note


def keywords_html(r):
    m = r["metrics"]
    parts = []
    tag = " (auto-detected)" if m["primary_keyword_auto_detected"] else ""
    parts.append("<p>Primary keyword%s: <b>%s</b> - %d hits, density <b>%.2f%%</b></p>"
                 % (tag, _esc(m["primary_keyword"]), m["primary_keyword_count"], m["primary_keyword_density_pct"]))
    if m["entity_densities"]:
        parts.append("<p><b>Entity densities</b></p><table>")
        parts.append("<tr><td style='color:#57606a;padding-right:14px'>Entity</td>"
                     "<td style='color:#57606a;padding-right:14px'>Hits</td>"
                     "<td style='color:#57606a'>Density</td></tr>")
        for e in m["entity_densities"]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td style='padding-right:14px'>%d</td>"
                         "<td>%.2f%%</td></tr>" % (_esc(e["entity"]), e["count"], e["density_pct"]))
        parts.append("</table>")
    if m.get("auto_entities"):
        parts.append("<p><b>Detected entities</b> (auto-extracted)</p><table>")
        parts.append("<tr><td style='color:#57606a;padding-right:14px'>Entity</td>"
                     "<td style='color:#57606a;padding-right:14px'>Hits</td>"
                     "<td style='color:#57606a'>Density</td></tr>")
        for e in m["auto_entities"]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td style='padding-right:14px'>%d</td>"
                         "<td>%.2f%%</td></tr>" % (_esc(e["entity"]), e["count"], e["density_pct"]))
        parts.append("</table>")
    parts.append("<p><b>Top phrases</b> (secondary-keyword candidates)</p><table>")
    for b in m["top_bigrams"]:
        parts.append("<tr><td style='padding-right:14px'>%s</td><td>%d</td></tr>" % (_esc(b["phrase"]), b["count"]))
    parts.append("</table>")
    if m["top_trigrams"]:
        parts.append("<p><b>Top 3-word phrases</b></p><table>")
        for b in m["top_trigrams"]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td>%d</td></tr>" % (_esc(b["phrase"]), b["count"]))
        parts.append("</table>")
    return "".join(parts)


def seo_html(r):
    s = r["seo"]
    parts = ["<table>"]
    for c in s["checks"]:
        color, label = STATUS_DOT.get(c["status"], ("#57606a", "INFO"))
        parts.append(
            "<tr><td style='padding:3px 10px 3px 0'><span style='color:%s'>&#9679;</span> "
            "<b>%s</b></td><td style='padding:3px 10px 3px 0;color:%s'>%s</td>"
            "<td style='padding:3px 0;color:#57606a'>%s</td></tr>"
            % (color, label, _esc(c["label"]), color, _esc(c["detail"]))
        )
    parts.append("</table>")
    spine = s.get("outline") or []
    if spine:
        parts.append("<p><b>Heading spine</b> (H1/H2/H3 in order)</p>")
        for h in spine[:60]:
            pad = {"h1": 0, "h2": 16, "h3": 32}.get(h["level"], 0)
            parts.append("<div style='margin-left:%dpx;color:#57606a'><b>%s</b> %s</div>"
                         % (pad, h["level"].upper(), _esc(h["text"])))
    elif s["h2"]:
        parts.append("<p><b>H2 headings</b></p><ul>")
        for h in s["h2"][:25]:
            parts.append("<li>%s</li>" % _esc(h))
        parts.append("</ul>")
    return "".join(parts)


def search_results_html(r):
    parts = []
    parts.append("<table>")
    parts.append(_row("Query", r["query"]))
    parts.append(_row("Country", "%s  (gl=%s, hl=%s)" % (r["country"], r["gl"], r["hl"])))
    parts.append(_row("Google domain", r["google_domain"]))
    parts.append(_row("Engine", "Serper API (no CAPTCHA)" if r.get("engine") == "serper" else "Direct scrape"))
    parts.append(_row("Proxy used", "yes" if r["proxy_used"] else "no"))
    parts.append(_row("Searched", r["searched_at"]))
    res_line = "%d" % r.get("result_count", len(r.get("results", [])))
    if r.get("competitors_crawled"):
        res_line += " (%d unique domains, %d sites deep-crawled)" % (r.get("unique_domains", 0), r["competitors_crawled"])
    else:
        res_line += " (%d unique domains, %d deep-analyzed)" % (r.get("unique_domains", 0), r.get("deep_analyzed", 0))
    parts.append(_row("Results", res_line))
    parts.append("</table>")

    if r["top_domains"]:
        parts.append("<p><b>Most-present domains</b></p><table>")
        for d in r["top_domains"][:10]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td>%d</td></tr>"
                         % (_esc(d["domain"]), d["count"]))
        parts.append("</table>")

    parts.append("<hr><p><b>Ranked results</b></p>")
    for res in r["results"]:
        parts.append(
            "<p style='margin:10px 0 2px'><b>%d.</b> "
            "<a href='%s'>%s</a><br>"
            "<span style='color:#1a7f37'>%s</span>"
            % (res["position"], _esc(res["url"]), _esc(res["title"]), _esc(res["url"])))
        if res.get("snippet"):
            parts.append("<br><span style='color:#57606a'>%s</span>" % _esc(res["snippet"]))
        if res.get("analysis"):
            m = res["analysis"]["metrics"]
            s = res["analysis"]["seo"]
            parts.append(
                "<br><span style='color:#0969da'>[deep] words %d &middot; Flesch %.1f (%s) "
                "&middot; primary kw %.2f%% &middot; transition %.1f%% &middot; passive %.1f%% "
                "&middot; same-start %.1f%%</span>"
                % (m["word_count"], m["flesch_reading_ease"], m["reading_level"],
                   m["primary_keyword_density_pct"], m["transition_sentence_pct"],
                   m["passive_voice_pct"], m["same_start_sentence_pct"]))
            spine = s.get("outline") or []
            if spine:
                items = []
                for h in spine[:40]:
                    pad = {"h1": 0, "h2": 16, "h3": 32}.get(h["level"], 0)
                    items.append("<div style='margin-left:%dpx;color:#57606a'>"
                                 "<b>%s</b> %s</div>"
                                 % (pad, h["level"].upper(), _esc(h["text"])))
                parts.append("<div style='margin:4px 0 0 8px'>%s</div>" % "".join(items))
        elif res.get("analysis_error"):
            parts.append("<br><span style='color:#cf222e'>[deep] failed: %s</span>"
                         % _esc(res["analysis_error"]))
        parts.append("</p>")
    return "".join(parts)


def aggregate_html(r):
    agg = r.get("aggregate")
    if not agg:
        return ("<p style='color:#57606a'>No competitor brief. Set "
                "<b>Deep-analyze top N</b> to 3-5 and search again to build the "
                "aggregate research (averages, target densities, secondary keywords, entities).</p>")
    a = agg["averages"]
    parts = []
    parts.append("<p><b>Competitor aggregate</b> - averages across %d analyzed pages "
                 "for <b>%s</b></p>" % (agg["competitors_analyzed"], _esc(agg["primary_keyword"])))
    meta = []
    if agg.get("enriched"):
        meta.append("entities and keywords: Groq-enriched (real densities)")
    else:
        meta.append("entities and keywords: heuristic (add a Groq key for semantic extraction)")
    if agg.get("page_type"):
        meta.append("detected page type: %s" % _esc(agg["page_type"]))
    if agg.get("product"):
        meta.append("product: %s" % _esc(agg["product"]))
    parts.append("<p style='color:#57606a'>%s</p>" % " &middot; ".join(meta))
    parts.append("<table>")
    parts.append(_row("Avg word count", a["word_count"]))
    parts.append(_row("Avg Flesch reading ease", "%.1f" % a["flesch_reading_ease"]))
    parts.append(_row("Avg primary keyword density", "%.2f%%" % a["primary_keyword_density_pct"]))
    parts.append(_row("Avg transition-word sentences", "%.1f%%" % a["transition_sentence_pct"]))
    parts.append(_row("Avg repeated sentence starts", "%.1f%%" % a["same_start_sentence_pct"]))
    parts.append(_row("Avg passive-voice sentences", "%.1f%%" % a["passive_voice_pct"]))
    parts.append("</table>")

    t = agg["targets"]
    parts.append("<hr><p><b>Target densities</b> (single figures, from the averages)</p>")
    parts.append("<p>Primary: <b>%s</b> &rarr; <b>%.2f%%</b></p>"
                 % (_esc(t["primary"]["keyword"]), t["primary"]["target_density_pct"]))
    if t["secondary"]:
        parts.append("<p><b>Secondary keyword targets</b></p><table>")
        for s in t["secondary"]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td>%.2f%%</td></tr>"
                         % (_esc(s["phrase"]), s["target_density_pct"]))
        parts.append("</table>")
    if t["entities"]:
        parts.append("<p><b>Entity targets</b></p><table>")
        for e in t["entities"]:
            parts.append("<tr><td style='padding-right:14px'>%s</td><td>%.2f%%</td></tr>"
                         % (_esc(e["entity"]), e["target_density_pct"]))
        parts.append("</table>")

    n = agg["competitors_analyzed"]
    parts.append("<hr><p><b>Secondary keywords across competitors</b> "
                 "(phrase &middot; used-by &middot; hits &middot; avg density)</p><table>")
    parts.append("<tr><td style='color:#57606a;padding-right:14px'>Phrase</td>"
                 "<td style='color:#57606a;padding-right:14px'>Used by</td>"
                 "<td style='color:#57606a;padding-right:14px'>Hits</td>"
                 "<td style='color:#57606a'>Avg density</td></tr>")
    for s in agg["secondary_keywords"]:
        parts.append("<tr><td style='padding-right:14px'>%s</td><td style='padding-right:14px'>%d/%d</td>"
                     "<td style='padding-right:14px'>%d</td><td>%.2f%%</td></tr>"
                     % (_esc(s["phrase"]), s["used_by_competitors"], n, s["corpus_count"], s["avg_density_pct"]))
    parts.append("</table>")

    parts.append("<hr><p><b>Entities across competitors</b> "
                 "(entity &middot; used-by &middot; hits &middot; avg density)</p><table>")
    parts.append("<tr><td style='color:#57606a;padding-right:14px'>Entity</td>"
                 "<td style='color:#57606a;padding-right:14px'>Used by</td>"
                 "<td style='color:#57606a;padding-right:14px'>Hits</td>"
                 "<td style='color:#57606a'>Avg density</td></tr>")
    for e in agg["entities"]:
        parts.append("<tr><td style='padding-right:14px'>%s</td><td style='padding-right:14px'>%d/%d</td>"
                     "<td style='padding-right:14px'>%d</td><td>%.2f%%</td></tr>"
                     % (_esc(e["entity"]), e["used_by_competitors"], n, e["corpus_count"], e["avg_density_pct"]))
    parts.append("</table>")
    return "".join(parts)


def ai_html(r):
    if r.get("ai_error"):
        return "<p style='color:#9a6700'>AI insights not available:<br>%s</p>" % _esc(r["ai_error"])
    ai = r.get("ai")
    if not ai:
        return ("<p style='color:#57606a'>AI insights are off. Tick "
                "<b>Use AI insights</b> and paste an API key (Groq, OpenRouter, "
                "Anthropic or Gemini) to enable them.</p>")
    if "raw_response" in ai and len(ai) == 1:
        return "<pre style='white-space:pre-wrap'>%s</pre>" % _esc(ai["raw_response"])
    parts = []
    for k, v in ai.items():
        title = k.replace("_", " ").title()
        if isinstance(v, list):
            parts.append("<p><b>%s</b></p><ul>" % _esc(title))
            for item in v:
                parts.append("<li>%s</li>" % _esc(item))
            parts.append("</ul>")
        else:
            parts.append("<p><b>%s:</b> %s</p>" % (_esc(title), _esc(v)))
    return "".join(parts)


def deep_crawl_summary_html(r):
    parts = []
    matrix = r.get("matrix", {})
    competitors = r.get("competitors_data", [])
    suggs = r.get("suggestions", [])
    cross_kw = matrix.get("cross_site_keywords", [])
    per_site = matrix.get("per_site_top_20", {})

    parts.append("<p><b>Deep Competitor & Whole-Site Multi-Page Crawl Intelligence</b></p>")
    parts.append("<table>")
    parts.append(_row("Query", r.get("query", "")))
    parts.append(_row("Country", "%s (gl=%s, hl=%s)" % (r.get("country", ""), r.get("gl", ""), r.get("hl", ""))))
    parts.append(_row("Competitors Crawled", len(competitors)))
    total_pages = sum(c.get("pages_scraped", 0) for c in competitors)
    total_words = sum(c.get("total_words", 0) for c in competitors)
    parts.append(_row("Total Pages Scraped", "%d across all sites" % total_pages))
    parts.append(_row("Total Words Scraped", "%d words" % total_words))
    parts.append("</table>")

    if suggs:
        parts.append("<hr><p><b>Google Autocomplete Suggestions (%d)</b></p><p>" % len(suggs))
        parts.append(" &bull; ".join("<code>%s</code>" % _esc(s) for s in suggs))
        parts.append("</p>")

    if cross_kw:
        parts.append("<hr><p><b>Top Inter-Site Keywords (Shared Across Competitors)</b></p><table>")
        parts.append("<tr><td style='color:#57606a;padding-right:14px'><b>Keyword / Phrase</b></td>"
                     "<td style='color:#57606a;padding-right:14px'><b>Used By Sites</b></td>"
                     "<td style='color:#57606a'><b>Total Occurrences</b></td></tr>")
        for k in cross_kw[:20]:
            parts.append("<tr><td style='padding-right:14px'><b>%s</b></td>"
                         "<td style='padding-right:14px'>%d/%d (%s%%)</td>"
                         "<td>%d</td></tr>" % (
                             _esc(k["keyword"]), k["used_by_count"], len(competitors),
                             k["used_by_pct"], k["total_count"]))
        parts.append("</table>")

    if per_site:
        parts.append("<hr><p><b>Per-Website Top 20 Keywords</b></p>")
        for dom, kws in per_site.items():
            parts.append("<details style='margin-bottom:8px;'><summary><b>%s</b> (Top %d keywords)</summary>" % (_esc(dom), len(kws)))
            parts.append("<table style='margin-top:6px;'>")
            parts.append("<tr><td style='color:#57606a;padding-right:14px'>#</td>"
                         "<td style='color:#57606a;padding-right:14px'>Keyword</td>"
                         "<td style='color:#57606a;padding-right:14px'>Hits</td>"
                         "<td style='color:#57606a'>Density</td></tr>")
            for idx, k in enumerate(kws[:20], start=1):
                parts.append("<tr><td style='padding-right:14px'>%d</td>"
                             "<td style='padding-right:14px'>%s</td>"
                             "<td style='padding-right:14px'>%d</td>"
                             "<td>%.2f%%</td></tr>" % (idx, _esc(k["keyword"]), k["count"], k["density_pct"]))
            parts.append("</table></details>")

    return "".join(parts)


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Content Analyzer 2.0 — Mindcob")
        self.resize(1180, 820)
        self.last_result = None
        self.threads = []  # keep refs so QThreads aren't garbage-collected

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        main = QWidget()
        main.setObjectName("mainArea")
        m = QVBoxLayout(main)
        m.setContentsMargins(20, 18, 20, 14)
        m.setSpacing(12)
        m.addWidget(self._build_toolbar())
        m.addWidget(self._build_content(), 1)
        m.addWidget(self._build_log())
        m.addLayout(self._build_footer())
        outer.addWidget(main, 1)

        # populate the nav for the current mode, then wire selection
        self._populate_nav(self.mode_cmb.currentIndex())
        self.nav.currentRowChanged.connect(self._on_nav)

        self.url_in.returnPressed.connect(self.on_analyze)
        self.query_in.returnPressed.connect(self.on_analyze)
        self.set_status("Ready. Pick a mode, enter a URL or search query, then Analyze.")

    # ---- shadow helper --------------------------------------------------- #
    def _shadow(self, w, blur=20, y=4, alpha=22):
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(blur)
        eff.setOffset(0, y)
        eff.setColor(QColor(18, 28, 46, alpha))
        w.setGraphicsEffect(eff)

    # ---- sidebar --------------------------------------------------------- #
    def _build_sidebar(self):
        bar = QWidget()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(226)
        v = QVBoxLayout(bar)
        v.setContentsMargins(14, 18, 14, 14)
        v.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(11)
        logo = QLabel("WA")
        logo.setObjectName("logo")
        logo.setFixedSize(40, 40)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(logo)
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        t1 = QLabel("Web Content")
        t1.setObjectName("brandTitle")
        t2 = QLabel("Analyzer")
        t2.setObjectName("brandSub")
        bcol.addWidget(t1)
        bcol.addWidget(t2)
        brand.addLayout(bcol)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(16)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        v.addWidget(self.nav, 1)

        foot = QLabel("MINDCOB")
        foot.setObjectName("brand")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(foot)
        return bar

    # ---- toolbar (mode + input + analyze) -------------------------------- #
    def _build_toolbar(self):
        card = QFrame()
        card.setObjectName("toolbar")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(11)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.addWidget(QLabel("Mode:"))
        self.mode_cmb = QComboBox()
        self.mode_cmb.addItems(["Analyze a single URL", "Search Google by country"])
        self.mode_cmb.currentIndexChanged.connect(self.on_mode_changed)
        mode_row.addWidget(self.mode_cmb, 1)
        v.addLayout(mode_row)

        self.input_stack = QStackedWidget()
        self.input_stack.addWidget(self._build_url_page())
        self.input_stack.addWidget(self._build_search_page())
        v.addWidget(self.input_stack)

        act = QHBoxLayout()
        self.run_btn = QPushButton("Analyze")
        self.run_btn.setObjectName("primary")
        self.run_btn.setMinimumHeight(38)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_analyze)
        act.addWidget(self.run_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        act.addWidget(self.progress)
        act.addStretch(1)
        v.addLayout(act)

        self._shadow(card)
        return card

    # ---- content (nav-driven stack) -------------------------------------- #
    def _build_content(self):
        card = QFrame()
        card.setObjectName("contentCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        self.content_stack = QStackedWidget()

        self.views = {}
        self._url_nav = []
        for name in ["Overview", "Readability & Style", "Keywords & Entities",
                     "On-Page SEO", "AI Insights", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.views[name] = tb
            self._url_nav.append((name, self.content_stack.addWidget(tb)))

        self.search_views = {}
        self._search_nav = []

        # Interactive Visual Analytics (Charts) via QWebEngineView
        self.chart_view = QWebEngineView()
        self.search_views["Visual Analytics (Charts)"] = self.chart_view
        self._search_nav.append(("Visual Analytics (Charts)", self.content_stack.addWidget(self.chart_view)))

        for name in ["Search Results", "Competitor Brief", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.search_views[name] = tb
            self._search_nav.append((name, self.content_stack.addWidget(tb)))

        page = QWidget()
        pv = QVBoxLayout(page)
        pv.setContentsMargins(12, 12, 12, 12)
        pv.addWidget(self._build_settings_group())
        pv.addStretch(1)
        self._settings_idx = self.content_stack.addWidget(page)

        cl.addWidget(self.content_stack)
        self._set_placeholder()
        return card

    # ---- nav <-> content wiring ------------------------------------------ #
    def _populate_nav(self, mode_index):
        sections = self._url_nav if mode_index == 0 else self._search_nav
        self._nav_map = [idx for _n, idx in sections] + [self._settings_idx]
        self.nav.blockSignals(True)
        self.nav.clear()
        for name, _idx in sections:
            self.nav.addItem(name)
        self.nav.addItem("Settings")
        self.nav.setCurrentRow(0)
        self.nav.blockSignals(False)
        self.content_stack.setCurrentIndex(self._nav_map[0])

    def _on_nav(self, row):
        m = getattr(self, "_nav_map", [])
        if 0 <= row < len(m):
            self.content_stack.setCurrentIndex(m[row])

    # ---- input ----------------------------------------------------------- #
    def _build_input_group(self):
        box = QGroupBox("Input  —  analyze one URL, or search Google by country")
        lay = QVBoxLayout(box)
        lay.setSpacing(12)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.addWidget(QLabel("Mode:"))
        self.mode_cmb = QComboBox()
        self.mode_cmb.addItems(["Analyze a single URL", "Search Google by country"])
        self.mode_cmb.currentIndexChanged.connect(self.on_mode_changed)
        mode_row.addWidget(self.mode_cmb, 1)
        lay.addLayout(mode_row)

        self.input_stack = QStackedWidget()
        self.input_stack.addWidget(self._build_url_page())
        self.input_stack.addWidget(self._build_search_page())
        lay.addWidget(self.input_stack)
        return box

    def _build_url_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(11)
        g.setColumnStretch(1, 1)

        g.addWidget(QLabel("URL:"), 0, 0)
        self.url_in = QLineEdit()
        self.url_in.setPlaceholderText("https://example.com/page")
        g.addWidget(self.url_in, 0, 1)

        g.addWidget(QLabel("Primary keyword:"), 1, 0)
        self.kw_in = QLineEdit()
        self.kw_in.setPlaceholderText("leave blank to auto-detect")
        g.addWidget(self.kw_in, 1, 1)

        g.addWidget(QLabel("Entities to measure:"), 2, 0)
        self.ent_in = QLineEdit()
        self.ent_in.setPlaceholderText("optional, comma-separated: pricing, support, api")
        g.addWidget(self.ent_in, 2, 1)
        return page

    def _build_search_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(11)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        g.addWidget(QLabel("Search query:"), 0, 0)
        self.query_in = QLineEdit()
        self.query_in.setPlaceholderText("keyword to search on Google, e.g. 'john doe' or 'pos system'")
        g.addWidget(self.query_in, 0, 1, 1, 3)

        g.addWidget(QLabel("Country:"), 1, 0)
        self.country_cmb = QComboBox()
        self.country_cmb.addItems(search.country_names())
        self.country_cmb.setCurrentText(search.DEFAULT_COUNTRY)
        g.addWidget(self.country_cmb, 1, 1)

        g.addWidget(QLabel("Proxy:"), 1, 2)
        self.search_proxy_in = QLineEdit()
        self.search_proxy_in.setPlaceholderText("optional: http://user:pass@host:port or socks5://host:port")
        g.addWidget(self.search_proxy_in, 1, 3)

        g.addWidget(QLabel("SERP Results (10-20):"), 2, 0)
        self.num_spin = QSpinBox()
        self.num_spin.setRange(5, 30)
        self.num_spin.setValue(10)
        self.num_spin.setToolTip("How many organic Google results to pull (filters out Reddit/Quora/ads).")
        g.addWidget(self.num_spin, 2, 1)

        g.addWidget(QLabel("Pages per site (20-40):"), 2, 2)
        self.crawl_pages_spin = QSpinBox()
        self.crawl_pages_spin.setRange(5, 50)
        self.crawl_pages_spin.setValue(25)
        self.crawl_pages_spin.setToolTip("Crawl internal links across each competitor domain (at least 20 to 40 pages).")
        g.addWidget(self.crawl_pages_spin, 2, 3)

        g.addWidget(QLabel("Competitors to crawl:"), 3, 0)
        self.comp_sites_spin = QSpinBox()
        self.comp_sites_spin.setRange(1, 10)
        self.comp_sites_spin.setValue(4)
        self.comp_sites_spin.setToolTip("Number of clean competitor websites to deep-crawl.")
        g.addWidget(self.comp_sites_spin, 3, 1)

        self.deep_crawl_chk = QCheckBox("Deep multi-page crawl & build Top 20 keywords + inter-site matrix")
        self.deep_crawl_chk.setChecked(True)
        g.addWidget(self.deep_crawl_chk, 3, 2, 1, 2)
        return page

    # ---- action row ------------------------------------------------------ #
    def _build_action_row(self):
        row = QHBoxLayout()
        self.run_btn = QPushButton("Analyze")
        self.run_btn.setObjectName("primary")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_analyze)
        row.addWidget(self.run_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        row.addWidget(self.progress)
        row.addStretch(1)

        self.options_btn = QPushButton("Settings")
        self.options_btn.setObjectName("ghost")
        self.options_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.options_btn.clicked.connect(self._toggle_settings)
        row.addWidget(self.options_btn)
        return row

    def _toggle_settings(self):
        show = not self._settings_box.isVisible()
        self._settings_box.setVisible(show)
        self.options_btn.setText("Hide settings" if show else "Settings")
        # Force the central layout to recompute immediately — otherwise hiding
        # the panel leaves the log/footer clipped until the next window resize.
        lay = self.centralWidget().layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()

    # ---- provider handling ---------------------------------------------- #
    _KEY_PLACEHOLDERS = {
        "groq": "gsk_…   free key at console.groq.com",
        "openrouter": "sk-or-…   your OpenRouter key",
        "anthropic": "sk-ant-…   your Anthropic (Claude) key",
        "gemini": "AIza…   Gemini key at aistudio.google.com",
    }

    def _provider(self):
        return llm.PROVIDERS[self.provider_cmb.currentIndex()]

    def _apply_provider_placeholder(self):
        self.key_in.setPlaceholderText(
            self._KEY_PLACEHOLDERS.get(self._provider(), ""))

    def _on_provider_changed(self, _index):
        # stash the key shown for the OLD provider, load the new provider's key
        self._llm_keys[self._active_provider] = self.key_in.text().strip()
        new = self._provider()
        self._active_provider = new
        self.key_in.setText(self._llm_keys.get(new, ""))
        self._apply_provider_placeholder()
        self.model_cmb.clear()
        self.model_cmb.addItems(llm.suggested_models(new))
        self.set_status("AI provider: %s — model set to %s"
                        % (llm.PROVIDER_LABELS[new], self.model_cmb.currentText()))

    def _save_keys(self):
        try:
            self._llm_keys[self._active_provider] = self.key_in.text().strip()
            mapping = {llm.ENV_KEYS[p]: self._llm_keys.get(p, "")
                       for p in llm.PROVIDERS}
            mapping["SERPER_API_KEY"] = self.serper_in.text().strip()
            path = save_keys_to_env(mapping)
            self.set_status("Keys saved to %s — they'll load automatically." % path)
        except Exception as e:
            QMessageBox.critical(self, "Could not save keys", str(e))

    # ---- settings / keys ------------------------------------------------- #
    def _build_settings_group(self):
        box = QGroupBox("Keys, model and options  ·  AI provider, SERP key, brief export")
        g = QGridLayout(box)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(11)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        self.ai_chk = QCheckBox(
            "Use AI insights  (Groq · OpenRouter · Anthropic · Gemini)")
        g.addWidget(self.ai_chk, 0, 0, 1, 4)

        # Remember one key per provider so switching never loses another.
        self._llm_keys = {p: os.environ.get(llm.ENV_KEYS[p], "")
                          for p in llm.PROVIDERS}
        self._active_provider = next(
            (p for p in llm.PROVIDERS if self._llm_keys[p]), "groq")

        g.addWidget(QLabel("AI provider:"), 1, 0)
        self.provider_cmb = QComboBox()
        self.provider_cmb.addItems([llm.PROVIDER_LABELS[p] for p in llm.PROVIDERS])
        self.provider_cmb.setCurrentIndex(llm.PROVIDERS.index(self._active_provider))
        self.provider_cmb.currentIndexChanged.connect(self._on_provider_changed)
        g.addWidget(self.provider_cmb, 1, 1)

        g.addWidget(QLabel("Model:"), 1, 2)
        self.model_cmb = QComboBox()
        self.model_cmb.setEditable(True)
        self.model_cmb.addItems(llm.suggested_models(self._active_provider))
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip(
            "Fetch the live model list for the current provider and key.")
        self.refresh_btn.clicked.connect(self.on_refresh_models)
        _mrow = QHBoxLayout()
        _mrow.setContentsMargins(0, 0, 0, 0)
        _mrow.setSpacing(8)
        _mrow.addWidget(self.model_cmb, 1)
        _mrow.addWidget(self.refresh_btn)
        _mw = QWidget()
        _mw.setLayout(_mrow)
        g.addWidget(_mw, 1, 3)

        g.addWidget(QLabel("API key:"), 2, 0)
        self.key_in = QLineEdit(self._llm_keys[self._active_provider])
        self.key_in.setEchoMode(QLineEdit.Password)
        g.addWidget(self.key_in, 2, 1, 1, 2)
        self.savekeys_btn = QPushButton("Save keys")
        self.savekeys_btn.setToolTip(
            "Store every key in this tool's .env so they load automatically next time.")
        self.savekeys_btn.clicked.connect(self._save_keys)
        g.addWidget(self.savekeys_btn, 2, 3)
        self._apply_provider_placeholder()

        g.addWidget(QLabel("SERP API key (Serper):"), 3, 0)
        self.serper_in = QLineEdit(os.environ.get("SERPER_API_KEY", ""))
        self.serper_in.setEchoMode(QLineEdit.Password)
        self.serper_in.setPlaceholderText("recommended: free key from serper.dev  →  no CAPTCHA")
        g.addWidget(self.serper_in, 3, 1, 1, 3)

        g.addWidget(QLabel("Proxy:"), 4, 0)
        self.proxy_in = QLineEdit()
        self.proxy_in.setPlaceholderText("optional: http://user:pass@host:port  or  socks5://host:port")
        g.addWidget(self.proxy_in, 4, 1, 1, 3)

        g.addWidget(QLabel("Brief brand:"), 5, 0)
        self.brand_in = QComboBox()
        self.brand_in.setEditable(True)
        self.brand_in.addItems(["Intelinova", "CanComCo"])
        self.brand_in.setToolTip("Brand for the exported outline .docx. Known brands "
                                 "(Intelinova, CanComCo) apply their CTA, disclaimer, and page types.")
        g.addWidget(self.brand_in, 5, 1)

        g.addWidget(QLabel("Brief page type:"), 5, 2)
        self.ptype_cmb = QComboBox()
        self.ptype_cmb.addItems(["Auto-detect", "Service", "Location Service", "Industry",
                                 "Vendor", "Comparison", "Blog"])
        self.ptype_cmb.setToolTip("Page type for the exported outline .docx (Auto-detect uses the research).")
        g.addWidget(self.ptype_cmb, 5, 3)

        hint = QLabel(
            "Tip: with no AI key you still get full readability, keyword, entity "
            "and on-page SEO analysis. Add a key from any one provider — Groq "
            "(free), OpenRouter, Anthropic (Claude) or Google Gemini — for AI "
            "insights and semantic competitor briefs. The provider is detected "
            "from the key automatically. A free Serper key gives real Google "
            "results with no CAPTCHA. Brand and page type only affect the "
            "exported outline .docx.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        g.addWidget(hint, 6, 0, 1, 4)
        return box

    # ---- tabs ------------------------------------------------------------ #
    def _build_tabs(self):
        self.results_stack = QStackedWidget()

        self.tabs = QTabWidget()
        self.views = {}
        for name in ["Overview", "Readability & Style", "Keywords & Entities",
                     "On-Page SEO", "AI Insights", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.views[name] = tb
            self.tabs.addTab(tb, name.replace("&", "&&"))  # && = literal &
        self.results_stack.addWidget(self.tabs)

        self.search_tabs = QTabWidget()
        self.search_views = {}
        for name in ["Search Results", "Competitor Brief", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.search_views[name] = tb
            self.search_tabs.addTab(tb, name.replace("&", "&&"))
        self.results_stack.addWidget(self.search_tabs)

        self._set_placeholder()
        return self.results_stack

    def _build_log(self):
        self.log_pane = QPlainTextEdit()
        self.log_pane.setObjectName("log")
        self.log_pane.setReadOnly(True)
        self.log_pane.setMaximumHeight(88)
        self.log_pane.setPlaceholderText("Activity log…")
        return self.log_pane

    # ---- footer ---------------------------------------------------------- #
    def _build_footer(self):
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("status")
        row.addWidget(self.status, 1)

        self.html_btn = QPushButton("Export HTML Dashboard")
        self.html_btn.setEnabled(False)
        self.html_btn.setToolTip("Export the interactive visual charts dashboard to a standalone .html file.")
        self.html_btn.clicked.connect(self.on_export_html)

        self.md_btn = QPushButton("Export Markdown")
        self.md_btn.setEnabled(False)
        self.json_btn = QPushButton("Export JSON")
        self.json_btn.setEnabled(False)
        self.brief_btn = QPushButton("Export Brief (.docx)")
        self.brief_btn.setEnabled(False)
        self.brief_btn.setToolTip("Search mode: build a writer-ready outline .docx from the Competitor Brief.")
        self.md_btn.clicked.connect(lambda: self.export("md"))
        self.json_btn.clicked.connect(lambda: self.export("json"))
        self.brief_btn.clicked.connect(self.on_export_brief)
        for b in (self.html_btn, self.md_btn, self.json_btn, self.brief_btn):
            row.addWidget(b)
        return row

    # ---- status / log helpers ------------------------------------------- #
    def set_status(self, text):
        self.status.setText(text)

    def _log(self, msg):
        self.set_status(msg)
        self.log_pane.appendPlainText("%s  %s" % (time.strftime("%H:%M:%S"), msg))

    def _set_placeholder(self):
        intro = (
            "<div style='color:#888;font-family:Segoe UI;padding:24px'>"
            "<h2 style='color:#1B2430'>Web Content Analyzer</h2>"
            "<p>Pick a mode above, then press <b>Analyze</b>:</p>"
            "<ul>"
            "<li><b>Analyze a single URL</b> — extraction, readability &amp; style, "
            "keyword / entity densities, on-page SEO checks, and optional Groq AI "
            "insights for one page.</li>"
            "<li><b>Search Google by country</b> — collect ranked results for a "
            "query, deep-analyze the top N, and build a competitor brief you can "
            "export as a writer-ready outline .docx.</li>"
            "</ul>"
            "<p style='color:#98A2AF'>API keys are optional and live under "
            "<b>Settings</b>. It reports insights only — it never edits "
            "your content.</p>"
            "</div>")
        self.views["Overview"].setHtml(intro)
        self.search_views["Search Results"].setHtml(intro)
        if hasattr(self, "chart_view"):
            self.chart_view.setHtml(
                "<!DOCTYPE html><html><body style='background:#090d16;color:#94a3b8;"
                "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:90vh;margin:0;'>"
                "<div style='text-align:center;max-width:540px;padding:30px;border:1px solid rgba(255,255,255,0.08);"
                "border-radius:14px;background:rgba(18,24,38,0.7);backdrop-filter:blur(10px);'>"
                "<h2 style='color:#38bdf8;font-size:22px;margin-bottom:10px;'>Deep Competitor & Keyword Intelligence</h2>"
                "<p style='color:#cbd5e1;font-size:14px;margin-bottom:14px;'>Google Search &bull; Auto-Filter Noise &bull; Multi-Page Crawler &bull; Cross-Site Keyword Matrix</p>"
                "<p style='color:#64748b;font-size:12px;line-height:1.6;'>Enter a keyword above (e.g. <code>pos system</code> or <code>john doe</code>), "
                "select your country, and press <b>Analyze</b> to generate interactive Chart.js graphs, Top 20 keywords per website, and cross-competitor overlap rankings.</p>"
                "</div></body></html>"
            )

    # ---- Mode switching ----
    def on_mode_changed(self, index):
        self.input_stack.setCurrentIndex(index)
        self._populate_nav(index)

    # ---- Analyze ----
    def on_analyze(self):
        use_ai = self.ai_chk.isChecked()
        api_key = self.key_in.text().strip()
        if use_ai and not api_key:
            QMessageBox.warning(
                self, "Missing key",
                "AI insights are on but no API key is set. Paste a Groq, "
                "OpenRouter, Anthropic or Gemini key under Settings, or "
                "untick “Use AI insights”.")
            return
        model = self.model_cmb.currentText().strip() or llm.default_model(self._provider())

        if self.mode_cmb.currentIndex() == 0:
            url = self.url_in.text().strip()
            if not url:
                QMessageBox.warning(self, "Missing URL", "Enter a URL to analyze.")
                return
            params = {
                "url": url,
                "keyword": self.kw_in.text().strip(),
                "entities": [e.strip() for e in self.ent_in.text().split(",") if e.strip()],
                "use_ai": use_ai, "api_key": api_key, "model": model,
            }
            worker = AnalyzeWorker(params)
        else:
            query = self.query_in.text().strip()
            if not query:
                QMessageBox.warning(self, "Missing query", "Enter a search query.")
                return
            proxy_val = self.search_proxy_in.text().strip() or self.proxy_in.text().strip() or None
            is_deep_crawl = self.deep_crawl_chk.isChecked()
            params = {
                "query": query,
                "country": self.country_cmb.currentText(),
                "num_results": self.num_spin.value(),
                "deep_crawl": is_deep_crawl,
                "pages_per_site": self.crawl_pages_spin.value(),
                "max_competitors": self.comp_sites_spin.value(),
                "deep_n": 0,
                "entities": [],
                "use_ai": use_ai, "api_key": api_key, "model": model,
                "proxy": proxy_val,
                "serper_key": self.serper_in.text().strip(),
            }
            worker = SearchWorker(params)

        self._set_busy(True)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_result)
        worker.error.connect(self.on_error)
        for sig in (worker.finished, worker.error):
            sig.connect(thread.quit)
            sig.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._drop_thread(thread))
        self.threads.append((thread, worker))
        thread.start()

    @Slot(str)
    def on_progress(self, msg):
        self._log(msg)

    @Slot(dict)
    def on_result(self, result):
        self.last_result = result
        if result.get("mode") == "deep_crawl":
            if "dashboard_html" in result:
                self.chart_view.setHtml(result["dashboard_html"])
            self.search_views["Search Results"].setHtml(search_results_html(result))
            self.search_views["Competitor Brief"].setHtml(deep_crawl_summary_html(result))
            self.search_views["Raw JSON"].setPlainText(search.to_json(result))
            self.status.setText("Done: %d competitor sites crawled for \"%s\" (%s)"
                                % (result.get("competitors_crawled", 0), result["query"], result["country"]))
            self.nav.setCurrentRow(0)
            self.content_stack.setCurrentIndex(self._nav_map[0])
        elif result.get("mode") == "search":
            self.search_views["Search Results"].setHtml(search_results_html(result))
            self.search_views["Competitor Brief"].setHtml(aggregate_html(result))
            self.search_views["Raw JSON"].setPlainText(search.to_json(result))
            self.status.setText("Done: %d results for \"%s\" (%s)"
                                % (result["result_count"], result["query"], result["country"]))
        else:
            self.views["Overview"].setHtml(overview_html(result))
            self.views["Readability & Style"].setHtml(readability_html(result))
            self.views["Keywords & Entities"].setHtml(keywords_html(result))
            self.views["On-Page SEO"].setHtml(seo_html(result))
            self.views["AI Insights"].setHtml(ai_html(result))
            self.views["Raw JSON"].setPlainText(analyzer.to_json(result))
            self.status.setText("Done: %s" % result["final_url"])
        self.md_btn.setEnabled(True)
        self.json_btn.setEnabled(True)
        self.html_btn.setEnabled(bool(result.get("dashboard_html")))
        # The outline .docx is only meaningful for a search with a competitor brief.
        self.brief_btn.setEnabled(bool(result.get("mode") == "search" and result.get("aggregate")))
        self._set_busy(False)

    def on_export_html(self):
        r = self.last_result
        if not r or not r.get("dashboard_html"):
            QMessageBox.information(self, "No Dashboard", "Run a deep search crawl first to generate the visual dashboard.")
            return
        query_slug = "".join(c if c.isalnum() else "_" for c in r.get("query", "dashboard")).strip("_")
        default_name = f"dashboard_{query_slug}.html"
        path, _ = QFileDialog.getSaveFileName(self, "Export HTML Dashboard", default_name, "HTML Files (*.html)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(r["dashboard_html"])
            self.set_status("Saved interactive HTML dashboard to %s" % path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    @Slot(str)
    def on_error(self, msg):
        self._set_busy(False)
        self.status.setText("Error.")
        QMessageBox.critical(self, "Analysis failed", msg)

    # ---- Model refresh ----
    def on_refresh_models(self):
        key = self.key_in.text().strip()
        if not key:
            QMessageBox.warning(self, "Missing key", "Enter your Groq API key first.")
            return
        self.refresh_btn.setEnabled(False)
        self.status.setText("Fetching live model list...")
        thread = QThread()
        worker = ModelsWorker(key)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_models)
        worker.error.connect(self.on_models_error)
        for sig in (worker.finished, worker.error):
            sig.connect(thread.quit)
            sig.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._drop_thread(thread))
        self.threads.append((thread, worker))
        thread.start()

    @Slot(list)
    def on_models(self, models):
        self.refresh_btn.setEnabled(True)
        if not models:
            self.status.setText("No models returned.")
            return
        current = self.model_cmb.currentText()
        self.model_cmb.clear()
        self.model_cmb.addItems(models)
        if current in models:
            self.model_cmb.setCurrentText(current)
        self.status.setText("Loaded %d models." % len(models))

    @Slot(str)
    def on_models_error(self, msg):
        self.refresh_btn.setEnabled(True)
        self.status.setText("Model list failed.")
        QMessageBox.critical(self, "Could not list models", msg)

    # ---- Export ----
    def export(self, kind):
        if not self.last_result:
            return
        is_search = self.last_result.get("mode") == "search"
        mod = search if is_search else analyzer
        base = "search-report" if is_search else "content-report"
        if kind == "md":
            text = mod.to_markdown(self.last_result)
            path, _ = QFileDialog.getSaveFileName(self, "Save Markdown", base + ".md", "Markdown (*.md)")
        else:
            text = mod.to_json(self.last_result)
            path, _ = QFileDialog.getSaveFileName(self, "Save JSON", base + ".json", "JSON (*.json)")
        if path:
            try:
                open(path, "w", encoding="utf-8").write(text)
                self.status.setText("Saved %s" % path)
            except Exception as e:
                QMessageBox.critical(self, "Save failed", str(e))

    # ---- Outline .docx export ----
    def on_export_brief(self):
        r = self.last_result
        if not r or r.get("mode") != "search" or not r.get("aggregate"):
            QMessageBox.warning(self, "No brief", "Run a search with 'Deep-analyze top N' set "
                                "to 3-5 first, so a competitor brief exists.")
            return
        brand = self.brand_in.currentText().strip() or "Intelinova"
        pt_map = {"Auto-detect": None, "Service": "service",
                  "Location Service": "location", "Industry": "industry",
                  "Vendor": "vendor", "Comparison": "comparison", "Blog": "blog"}
        page_type = pt_map.get(self.ptype_cmb.currentText())
        default_name = brief_doc.default_filename(r, brand, page_type or brief_doc.detect_page_type(r["query"]))
        path, _ = QFileDialog.getSaveFileName(self, "Save Outline (.docx)", default_name, "Word (*.docx)")
        if not path:
            return

        params = {
            "result": r, "path": path, "brand": brand,
            "api_key": self.key_in.text().strip(),
            "model": self.model_cmb.currentText().strip() or llm.default_model(self._provider()),
            "page_type": page_type,
        }
        self._set_busy(True)
        thread = QThread()
        worker = BriefDocWorker(params)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_brief_done)
        worker.error.connect(self.on_error)
        for sig in (worker.finished, worker.error):
            sig.connect(thread.quit)
            sig.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._drop_thread(thread))
        self.threads.append((thread, worker))
        thread.start()

    @Slot(str)
    def on_brief_done(self, path):
        self._set_busy(False)
        self.status.setText("Saved outline: %s" % path)
        QMessageBox.information(self, "Brief saved", "Outline document saved:\n%s" % path)

    # ---- helpers ----
    def _set_busy(self, busy):
        self.run_btn.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self._log("Working…")

    def _drop_thread(self, thread):
        self.threads = [(t, w) for (t, w) in self.threads if t is not thread]
        thread.deleteLater()


STYLE = """
QWidget { color: #1F2733; font-size: 13px; }
QMainWindow, QMainWindow > QWidget { background: #F1F3F7; }

#mainArea { background: #F1F3F7; }

/* ---- sidebar ---- */
#sidebar { background: #FFFFFF; border-right: 1px solid #E9EDF3; }
#logo { background: #2E7DF2; color: #FFFFFF; border-radius: 11px;
        font-size: 15px; font-weight: 700; }
#brandTitle { font-size: 15px; font-weight: 800; color: #1B2430; }
#brandSub   { font-size: 12px; font-weight: 600; color: #8A94A2; }
#brand      { font-size: 10px; font-weight: 700; letter-spacing: 2px;
              color: #C4CBD6; }
QListWidget#nav { background: transparent; border: 0; outline: 0; }
QListWidget#nav::item {
    padding: 10px 12px; margin: 2px 0; border-radius: 9px;
    color: #5B6572; font-weight: 600;
}
QListWidget#nav::item:hover    { background: #F1F6FC; color: #2E7DF2; }
QListWidget#nav::item:selected { background: #2E7DF2; color: #FFFFFF; }

/* ---- toolbar + content cards ---- */
#toolbar, #contentCard {
    background: #FFFFFF; border: 1px solid #E9EDF3; border-radius: 14px;
}

/* ---- cards ---- */
QGroupBox {
    background: #FFFFFF; border: 1px solid #E6EAF0; border-radius: 14px;
    margin-top: 8px; padding: 18px 18px 16px 18px; font-weight: 500;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 16px; top: -2px; padding: 0 6px; color: #96A0AE;
    font-size: 11px; font-weight: 600;
}

/* ---- inputs ---- */
QLineEdit, QComboBox, QSpinBox {
    background: #FFFFFF; border: 1px solid #DCE2EA; border-radius: 9px;
    padding: 9px 12px; min-height: 18px;
    selection-background-color: #2E7DF2; selection-color: #FFFFFF;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #C3CCD8; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 2px solid #2E7DF2; padding: 8px 11px; }
QLineEdit::placeholder { color: #A7B0BC; }
QComboBox QAbstractItemView {
    background: #FFFFFF; border: 1px solid #E6EAF0; border-radius: 9px;
    padding: 4px; outline: 0;
    selection-background-color: #EAF2FE; selection-color: #1B2430;
}

/* ---- buttons ---- */
QPushButton {
    background: #FFFFFF; color: #46515F; border: 1px solid #DCE2EA;
    border-radius: 9px; padding: 8px 15px; font-weight: 600;
}
QPushButton:hover   { background: #F5F8FC; border-color: #C3CCD8; }
QPushButton:pressed { background: #EBF1F8; }
QPushButton:disabled{ color: #B4BCC7; background: #F6F8FB; border-color: #EAEEF3; }
QPushButton#primary {
    background: #2E7DF2; color: #FFFFFF; border: 0; padding: 11px 26px;
    font-weight: 700; font-size: 14px;
}
QPushButton#primary:hover    { background: #2571E8; }
QPushButton#primary:pressed  { background: #1C66DC; }
QPushButton#primary:disabled { background: #B6CEF6; color: #F3F7FE; }
QPushButton#ghost {
    background: transparent; color: #6C7788; border: 0; font-weight: 600;
    padding: 8px 12px;
}
QPushButton#ghost:hover { color: #2E7DF2; background: transparent; }

/* ---- checkboxes ---- */
QCheckBox { spacing: 8px; color: #46515F; padding: 3px 0; }

/* ---- tabs ---- */
QTabWidget::pane {
    border: 1px solid #E6EAF0; border-radius: 14px; background: #FFFFFF;
    top: -1px;
}
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent; color: #808A98; padding: 9px 15px;
    margin: 0 1px; border: 0; border-bottom: 2px solid transparent;
    font-weight: 600; font-size: 12px;
}
QTabBar::tab:hover    { color: #2E7DF2; }
QTabBar::tab:selected { color: #1C66DC; border-bottom: 2px solid #2E7DF2; }

/* ---- report surface (inside the white content card) ---- */
QTextBrowser { background: transparent; border: 0; padding: 12px 18px; }

/* ---- progress ---- */
QProgressBar { border: 0; border-radius: 6px; background: #DEE4EC; height: 6px;
               text-align: center; }
QProgressBar::chunk { background: #2E7DF2; border-radius: 6px; }

/* ---- log ---- */
QPlainTextEdit#log {
    background: #FBFCFE; color: #6C7788; border: 1px solid #EAEEF3;
    border-radius: 11px; padding: 6px 8px;
    font-family: Consolas, monospace; font-size: 11px;
}

/* ---- labels ---- */
#hint   { color: #98A2AF; font-size: 12px; }
#status { color: #66707E; }

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: #D2DAE4; border-radius: 5px;
                              min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #A9BAD2; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ---- tooltip ---- */
QToolTip { background: #1B2430; color: #F1F3F7; border: 0; padding: 6px 9px;
           border-radius: 7px; }
"""


def main():
    config.load_env()
    if "--desktop" in sys.argv:
        app = QApplication(sys.argv)
        app.setApplicationName("Web Content Analyzer")
        app.setStyle("Fusion")
        QApplication.setFont(QFont("Segoe UI", 10))
        app.setStyleSheet(STYLE)
        _icon = resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(_icon):
            app.setWindowIcon(QIcon(_icon))
        win = MainWindow()
        if "--selftest" in sys.argv:
            from PySide6.QtCore import QTimer
            win.show()
            def _clean_quit():
                win.close()
                app.quit()
            QTimer.singleShot(500, _clean_quit)
            return app.exec()
        win.show()
        sys.exit(app.exec())
    else:
        import web_server
        web_server.start_server()


if __name__ == "__main__":
    main()
