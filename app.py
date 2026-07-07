# -*- coding: utf-8 -*-
"""
Web Content Analyzer - PySide6 desktop GUI.

Thin front end over analyzer.py. All fetching / analysis / Groq calls run in a
background QThread so the window never freezes. Run:  python app.py
"""

import os
import sys

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QComboBox, QLabel, QGroupBox, QTabWidget,
    QTextBrowser, QProgressBar, QFileDialog, QMessageBox, QSizePolicy,
    QStackedWidget, QSpinBox,
)

import analyzer
import search
import brief_doc
import config


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
    parts.append(_row("Results", "%d  (%d unique domains, %d deep-analyzed)"
                      % (r["result_count"], r["unique_domains"], r["deep_analyzed"])))
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
                "<b>Use Groq AI insights</b> and paste an API key to enable them.</p>")
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


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Content Analyzer")
        self.resize(940, 720)
        self.last_result = None
        self.threads = []  # keep refs so QThreads aren't garbage-collected

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # --- Mode selector ---
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode"))
        self.mode_cmb = QComboBox()
        self.mode_cmb.addItems(["Analyze a single URL", "Search Google by country"])
        self.mode_cmb.currentIndexChanged.connect(self.on_mode_changed)
        mode_row.addWidget(self.mode_cmb, 1)
        root.addLayout(mode_row)

        # --- Inputs (stacked: URL page / Search page) ---
        self.input_stack = QStackedWidget()

        # Page 0: single-URL inputs
        url_page = QWidget()
        url_form = QFormLayout(url_page)
        url_form.setLabelAlignment(Qt.AlignRight)
        self.url_in = QLineEdit(); self.url_in.setPlaceholderText("https://example.com/page")
        self.kw_in = QLineEdit(); self.kw_in.setPlaceholderText("leave blank to auto-detect")
        self.ent_in = QLineEdit(); self.ent_in.setPlaceholderText("optional, comma-separated: pricing, support, api")
        url_form.addRow("URL", self.url_in)
        url_form.addRow("Primary keyword", self.kw_in)
        url_form.addRow("Entities to measure", self.ent_in)
        self.input_stack.addWidget(url_page)

        # Page 1: Google-search inputs
        search_page = QWidget()
        search_form = QFormLayout(search_page)
        search_form.setLabelAlignment(Qt.AlignRight)
        self.query_in = QLineEdit(); self.query_in.setPlaceholderText("keyword or phrase to search on Google")
        self.country_cmb = QComboBox()
        self.country_cmb.addItems(search.country_names())
        self.country_cmb.setCurrentText(search.DEFAULT_COUNTRY)
        self.num_spin = QSpinBox(); self.num_spin.setRange(1, 30); self.num_spin.setValue(10)
        self.deep_spin = QSpinBox(); self.deep_spin.setRange(0, 30); self.deep_spin.setValue(0)
        self.deep_spin.setToolTip("Run the full page analyzer on the top N results (0 = SERP only).")
        self.sent_in = QLineEdit(); self.sent_in.setPlaceholderText("optional, measured only in deep-analyzed pages")
        self.proxy_in = QLineEdit()
        self.proxy_in.setPlaceholderText("optional: http://user:pass@host:port  or  socks5://host:port")
        self.serper_in = QLineEdit(os.environ.get("SERPER_API_KEY", ""))
        self.serper_in.setEchoMode(QLineEdit.Password)
        self.serper_in.setPlaceholderText("recommended: free key from serper.dev  ->  no CAPTCHA")
        self.brand_in = QComboBox(); self.brand_in.setEditable(True)
        self.brand_in.addItems(["Intelinova", "CanComCo"])
        self.brand_in.setToolTip("Brand for the exported outline .docx. Known brands "
                                 "(Intelinova, CanComCo) apply their CTA, disclaimer, and page types.")
        self.ptype_cmb = QComboBox()
        self.ptype_cmb.addItems(["Auto-detect", "Service", "Location Service", "Industry",
                                 "Vendor", "Comparison", "Blog"])
        self.ptype_cmb.setToolTip("Page type for the exported outline .docx (Auto-detect uses the research).")
        search_form.addRow("Search query", self.query_in)
        search_form.addRow("Country", self.country_cmb)
        search_form.addRow("Results to collect", self.num_spin)
        search_form.addRow("Deep-analyze top N", self.deep_spin)
        search_form.addRow("Entities (deep pages)", self.sent_in)
        search_form.addRow("SERP API key (Serper)", self.serper_in)
        search_form.addRow("Proxy", self.proxy_in)
        search_form.addRow("Brief brand", self.brand_in)
        search_form.addRow("Brief page type", self.ptype_cmb)
        self.input_stack.addWidget(search_page)

        root.addWidget(self.input_stack)

        # --- AI group ---
        ai_box = QGroupBox("AI insights (optional - Groq)")
        ai_l = QFormLayout(ai_box)
        self.ai_chk = QCheckBox("Use Groq AI insights")
        self.key_in = QLineEdit(os.environ.get("GROQ_API_KEY", ""))
        self.key_in.setEchoMode(QLineEdit.Password)
        self.key_in.setPlaceholderText("gsk_...  (or set GROQ_API_KEY env var)")
        self.model_cmb = QComboBox(); self.model_cmb.setEditable(True)
        self.model_cmb.addItem(analyzer.DEFAULT_MODEL)
        self.refresh_btn = QPushButton("Refresh models")
        self.refresh_btn.clicked.connect(self.on_refresh_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_cmb, 1)
        model_row.addWidget(self.refresh_btn)
        model_w = QWidget(); model_w.setLayout(model_row)
        ai_l.addRow(self.ai_chk)
        ai_l.addRow("API key", self.key_in)
        ai_l.addRow("Model", model_w)
        root.addWidget(ai_box)

        # --- Analyze button + progress ---
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Analyze")
        self.run_btn.setMinimumHeight(38)
        f = self.run_btn.font(); f.setBold(True); self.run_btn.setFont(f)
        self.run_btn.clicked.connect(self.on_analyze)
        run_row.addWidget(self.run_btn, 1)
        self.md_btn = QPushButton("Export Markdown"); self.md_btn.setEnabled(False)
        self.json_btn = QPushButton("Export JSON"); self.json_btn.setEnabled(False)
        self.brief_btn = QPushButton("Export Brief (.docx)"); self.brief_btn.setEnabled(False)
        self.brief_btn.setToolTip("Search mode: build a writer-ready outline .docx from the Competitor Brief.")
        self.md_btn.clicked.connect(lambda: self.export("md"))
        self.json_btn.clicked.connect(lambda: self.export("json"))
        self.brief_btn.clicked.connect(self.on_export_brief)
        run_row.addWidget(self.md_btn)
        run_row.addWidget(self.json_btn)
        run_row.addWidget(self.brief_btn)
        root.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#57606a")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        # --- Results (stacked: URL tabs / Search tabs) ---
        self.results_stack = QStackedWidget()

        self.tabs = QTabWidget()
        self.views = {}
        for name in ["Overview", "Readability & Style", "Keywords & Entities",
                     "On-Page SEO", "AI Insights", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.views[name] = tb
            self.tabs.addTab(tb, name)
        self.results_stack.addWidget(self.tabs)

        self.search_tabs = QTabWidget()
        self.search_views = {}
        for name in ["Search Results", "Competitor Brief", "Raw JSON"]:
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            self.search_views[name] = tb
            self.search_tabs.addTab(tb, name)
        self.results_stack.addWidget(self.search_tabs)

        root.addWidget(self.results_stack, 1)

        self.setCentralWidget(central)
        self.url_in.returnPressed.connect(self.on_analyze)
        self.query_in.returnPressed.connect(self.on_analyze)

    # ---- Mode switching ----
    def on_mode_changed(self, index):
        self.input_stack.setCurrentIndex(index)
        self.results_stack.setCurrentIndex(index)

    # ---- Analyze ----
    def on_analyze(self):
        use_ai = self.ai_chk.isChecked()
        api_key = self.key_in.text().strip()
        if use_ai and not api_key:
            QMessageBox.warning(self, "Missing key", "AI insights are on but no Groq API key is set.")
            return
        model = self.model_cmb.currentText().strip() or analyzer.DEFAULT_MODEL

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
            params = {
                "query": query,
                "country": self.country_cmb.currentText(),
                "num_results": self.num_spin.value(),
                "deep_n": self.deep_spin.value(),
                "entities": [e.strip() for e in self.sent_in.text().split(",") if e.strip()],
                "use_ai": use_ai, "api_key": api_key, "model": model,
                "proxy": self.proxy_in.text().strip() or None,
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
        self.status.setText(msg)

    @Slot(dict)
    def on_result(self, result):
        self.last_result = result
        if result.get("mode") == "search":
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
        # The outline .docx is only meaningful for a search with a competitor brief.
        self.brief_btn.setEnabled(bool(result.get("mode") == "search" and result.get("aggregate")))
        self._set_busy(False)

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
            "model": self.model_cmb.currentText().strip() or analyzer.DEFAULT_MODEL,
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
            self.status.setText("Working...")

    def _drop_thread(self, thread):
        self.threads = [(t, w) for (t, w) in self.threads if t is not thread]
        thread.deleteLater()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Web Content Analyzer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
