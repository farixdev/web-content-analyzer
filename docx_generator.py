# -*- coding: utf-8 -*-
"""
Word Document (.docx) Report Generator for Web Content Analyzer.

Generates a publication-grade Microsoft Word report (.docx) with:
1. Executive Cover & KPI Summary
2. High-Resolution Embedded Dominance Chart Image (Matplotlib)
3. Formatted Cross-Competitor Keyword Dominance Matrix Table
4. Individual Competitor Deep Dive Tables (Top 20 Keywords + Scraped Pages)
5. Google Autocomplete Search Suggestions List
"""

import os
import io
from datetime import datetime

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Corporate Blue & White Palette
COLOR_NAVY_HEX = "1E3A8A"       # Primary Headings
COLOR_BLUE_HEX = "2563EB"       # Accents / Table Headers
COLOR_LIGHT_BLUE_HEX = "EFF6FF" # Alternating row highlight / KPI box
COLOR_BORDER_HEX = "CBD5E1"     # Table Borders
COLOR_MUTED_HEX = "64748B"      # Subtitles / Secondary text


def _set_cell_background(cell, hex_color):
    """Set background color of a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set internal padding for a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)


def _generate_dominance_chart_image(terms, max_terms=15):
    """Generate high-res Matplotlib horizontal bar chart in corporate Blue & White."""
    if not terms:
        return None

    top_slice = terms[:max_terms]
    # Reverse so top item appears at top of vertical axis
    keywords = [t["keyword"] for t in reversed(top_slice)]
    counts = [t.get("total_occurrences", t.get("total_count", 0)) for t in reversed(top_slice)]

    fig, ax = plt.subplots(figsize=(8.5, max(4.0, len(keywords) * 0.35)), dpi=200)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    # Clean royal blue horizontal bars
    bars = ax.barh(keywords, counts, color="#2563EB", edgecolor="#1D4ED8", height=0.65, zorder=3)

    # Style axes
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#94A3B8")
    ax.spines["bottom"].set_color("#94A3B8")
    ax.tick_params(colors="#334155", labelsize=10)
    ax.xaxis.grid(True, linestyle="--", alpha=0.5, color="#E2E8F0", zorder=0)

    # Annotate value at end of each bar
    max_c = max(counts) if counts else 1
    for bar in bars:
        w = bar.get_width()
        ax.text(
            w + (max_c * 0.015),
            bar.get_y() + bar.get_height() / 2,
            f"{int(w):,}",
            va="center",
            ha="left",
            fontsize=9.5,
            fontweight="bold",
            color="#1E3A8A"
        )

    ax.set_title(
        "Cross-Competitor Keyword Dominance (Total Corpus Occurrences)",
        fontsize=13,
        fontweight="bold",
        color="#0F172A",
        pad=15
    )
    ax.set_xlabel("Total Frequency Across All Competitors", fontsize=10, color="#475569", labelpad=8)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_docx_report(results, output_path="report.docx"):
    """Compile comprehensive executive report into a formatted Word (.docx) document."""
    doc = docx.Document()

    # Set document margins (1 inch)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    query = results.get("query", "Competitor Intelligence")
    country = results.get("country", "Global")
    engine = "Google Serper API" if results.get("engine") == "serper" else "Free Web Engine (Direct)"
    searched_at = results.get("searched_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    competitors = results.get("competitors_data", [])
    matrix = results.get("matrix", {})
    cross_terms = matrix.get("cross_site_terms", matrix.get("cross_site_keywords", []))
    suggestions = results.get("suggestions", [])

    total_pages = sum(c.get("pages_scraped", 0) for c in competitors)
    total_words = sum(c.get("total_words", 0) for c in competitors)

    # ---------------------------------------------------------
    # 1. Header & Title Block
    # ---------------------------------------------------------
    title_p = doc.add_paragraph()
    title_run = title_p.add_run("COMPETITOR INTELLIGENCE & KEYWORD DOMINANCE REPORT")
    title_run.font.name = "Arial"
    title_run.font.size = Pt(20)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(30, 58, 138)  # Navy
    title_p.paragraph_format.space_after = Pt(4)

    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"Search Query: \"{query}\"  |  Target Market: {country}")
    sub_run.font.name = "Arial"
    sub_run.font.size = Pt(11)
    sub_run.font.bold = True
    sub_run.font.color.rgb = RGBColor(37, 99, 235)  # Blue
    sub_p.paragraph_format.space_after = Pt(2)

    meta_p = doc.add_paragraph()
    meta_run = meta_p.add_run(f"Generated: {searched_at}  |  Search Engine Mode: {engine}")
    meta_run.font.name = "Arial"
    meta_run.font.size = Pt(9.5)
    meta_run.font.color.rgb = RGBColor(100, 116, 139)
    meta_p.paragraph_format.space_after = Pt(16)

    # ---------------------------------------------------------
    # 2. Executive KPI Summary Box
    # ---------------------------------------------------------
    kpi_table = doc.add_table(rows=2, cols=4)
    kpi_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    kpi_labels = ["COMPETITORS ANALYZED", "PAGES SCRAPED", "TOTAL WORDS PARSED", "DOMINANT TERMS"]
    kpi_vals = [
        str(len(competitors)),
        str(total_pages),
        f"{total_words:,}",
        str(len(cross_terms))
    ]

    for col_idx in range(4):
        # Header row
        c_top = kpi_table.cell(0, col_idx)
        _set_cell_background(c_top, COLOR_LIGHT_BLUE_HEX)
        _set_cell_margins(c_top, top=80, bottom=40, left=100, right=100)
        p_top = c_top.paragraphs[0]
        r_top = p_top.add_run(kpi_labels[col_idx])
        r_top.font.name = "Arial"
        r_top.font.size = Pt(8.5)
        r_top.font.bold = True
        r_top.font.color.rgb = RGBColor(71, 85, 105)
        p_top.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Value row
        c_bot = kpi_table.cell(1, col_idx)
        _set_cell_background(c_bot, COLOR_LIGHT_BLUE_HEX)
        _set_cell_margins(c_bot, top=40, bottom=100, left=100, right=100)
        p_bot = c_bot.paragraphs[0]
        r_bot = p_bot.add_run(kpi_vals[col_idx])
        r_bot.font.name = "Arial"
        r_bot.font.size = Pt(16)
        r_bot.font.bold = True
        r_bot.font.color.rgb = RGBColor(30, 58, 138)
        p_bot.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # ---------------------------------------------------------
    # 3. High-Resolution Embedded Dominance Chart
    # ---------------------------------------------------------
    chart_h = doc.add_heading("1. Cross-Competitor Keyword Dominance Chart", level=1)
    chart_h.runs[0].font.name = "Arial"
    chart_h.runs[0].font.color.rgb = RGBColor(30, 58, 138)
    chart_h.paragraph_format.space_before = Pt(12)
    chart_h.paragraph_format.space_after = Pt(8)

    chart_img = _generate_dominance_chart_image(cross_terms, max_terms=15)
    if chart_img:
        chart_p = doc.add_paragraph()
        chart_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        chart_p.add_run().add_picture(chart_img, width=Inches(6.4))
        chart_p.paragraph_format.space_after = Pt(16)

    # ---------------------------------------------------------
    # 4. Keyword Dominance Matrix Table
    # ---------------------------------------------------------
    mat_h = doc.add_heading("2. Cross-Competitor Keyword Dominance Matrix", level=1)
    mat_h.runs[0].font.name = "Arial"
    mat_h.runs[0].font.color.rgb = RGBColor(30, 58, 138)
    mat_h.paragraph_format.space_before = Pt(12)
    mat_h.paragraph_format.space_after = Pt(8)

    mat_table = doc.add_table(rows=1, cols=5)
    mat_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Rank", "Keyword", "Domain Overlap", "Total Frequency", "Per-Competitor Breakdown"]

    hdr_row = mat_table.rows[0]
    for idx, text in enumerate(headers):
        cell = hdr_row.cells[idx]
        _set_cell_background(cell, COLOR_BLUE_HEX)
        _set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(text)
        r.font.name = "Arial"
        r.font.size = Pt(9.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        if idx in (0, 2, 3):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    n_comp = len(competitors)
    for rank_idx, term in enumerate(cross_terms[:30], start=1):
        row = mat_table.add_row()
        kw = term.get("keyword", "")
        overlap = term.get("domain_presence", term.get("used_by_count", 0))
        total_c = term.get("total_occurrences", term.get("total_count", 0))
        pct = round((overlap / max(1, n_comp)) * 100)
        breakdown_dict = term.get("per_domain", term.get("breakdown", {}))
        breakdown_str = ", ".join([f"{d}: {c}" for d, c in breakdown_dict.items() if c > 0])

        bg = COLOR_LIGHT_BLUE_HEX if rank_idx % 2 == 1 else "FFFFFF"

        # Col 0: Rank
        c0 = row.cells[0]
        _set_cell_background(c0, bg)
        _set_cell_margins(c0, top=60, bottom=60, left=80, right=80)
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p0.add_run(f"#{rank_idx}").font.size = Pt(9)

        # Col 1: Keyword
        c1 = row.cells[1]
        _set_cell_background(c1, bg)
        _set_cell_margins(c1, top=60, bottom=60, left=80, right=80)
        r1 = c1.paragraphs[0].add_run(kw)
        r1.font.bold = True
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = RGBColor(15, 23, 42)

        # Col 2: Domain Overlap
        c2 = row.cells[2]
        _set_cell_background(c2, bg)
        _set_cell_margins(c2, top=60, bottom=60, left=80, right=80)
        p2 = c2.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.add_run(f"{overlap} / {n_comp} ({pct}%)").font.size = Pt(9)

        # Col 3: Total Count
        c3 = row.cells[3]
        _set_cell_background(c3, bg)
        _set_cell_margins(c3, top=60, bottom=60, left=80, right=80)
        p3 = c3.paragraphs[0]
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r3 = p3.add_run(f"{total_c:,}")
        r3.font.bold = True
        r3.font.color.rgb = RGBColor(37, 99, 235)
        r3.font.size = Pt(9.5)

        # Col 4: Breakdown
        c4 = row.cells[4]
        _set_cell_background(c4, bg)
        _set_cell_margins(c4, top=60, bottom=60, left=80, right=80)
        c4.paragraphs[0].add_run(breakdown_str).font.size = Pt(8.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # ---------------------------------------------------------
    # 5. Individual Competitor Breakdowns
    # ---------------------------------------------------------
    comp_h = doc.add_heading("3. Individual Competitor Breakdowns", level=1)
    comp_h.runs[0].font.name = "Arial"
    comp_h.runs[0].font.color.rgb = RGBColor(30, 58, 138)
    comp_h.paragraph_format.space_before = Pt(12)
    comp_h.paragraph_format.space_after = Pt(8)

    for c_idx, comp in enumerate(competitors, start=1):
        dom = comp.get("domain", f"Competitor {c_idx}")
        pages_scraped = comp.get("pages_scraped", 0)
        words_count = comp.get("total_words", 0)

        site_h = doc.add_heading(f"3.{c_idx} Competitor: {dom}", level=2)
        site_h.runs[0].font.name = "Arial"
        site_h.runs[0].font.color.rgb = RGBColor(37, 99, 235)
        site_h.paragraph_format.space_before = Pt(8)
        site_h.paragraph_format.space_after = Pt(2)

        doc.add_paragraph(f"Internal Pages Scraped: {pages_scraped}  |  Total Extracted Words: {words_count:,}").paragraph_format.space_after = Pt(6)

        # Top Keywords Table
        top_kws = comp.get("top_keywords", [])[:20]
        if top_kws:
            kw_t = doc.add_table(rows=1, cols=4)
            kw_t.alignment = WD_TABLE_ALIGNMENT.CENTER
            kw_hdrs = ["#", "Top Keyword / Phrase", "Occurrences", "Corpus Density"]
            for idx, text in enumerate(kw_hdrs):
                cell = kw_t.rows[0].cells[idx]
                _set_cell_background(cell, COLOR_NAVY_HEX)
                _set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                p = cell.paragraphs[0]
                r = p.add_run(text)
                r.font.bold = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(255, 255, 255)
                if idx in (0, 2, 3):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

            for i, item in enumerate(top_kws, start=1):
                row = kw_t.add_row()
                bg = COLOR_LIGHT_BLUE_HEX if i % 2 == 1 else "FFFFFF"

                c0 = row.cells[0]
                _set_cell_background(c0, bg)
                _set_cell_margins(c0, top=40, bottom=40, left=60, right=60)
                c0.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                c0.paragraphs[0].add_run(f"#{i}").font.size = Pt(8.5)

                c1 = row.cells[1]
                _set_cell_background(c1, bg)
                _set_cell_margins(c1, top=40, bottom=40, left=60, right=60)
                r1 = c1.paragraphs[0].add_run(item.get("keyword", ""))
                r1.font.bold = True
                r1.font.size = Pt(9)

                c2 = row.cells[2]
                _set_cell_background(c2, bg)
                _set_cell_margins(c2, top=40, bottom=40, left=60, right=60)
                c2.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                c2.paragraphs[0].add_run(f"{item.get('count', 0):,}").font.size = Pt(9)

                c3 = row.cells[3]
                _set_cell_background(c3, bg)
                _set_cell_margins(c3, top=40, bottom=40, left=60, right=60)
                c3.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                c3.paragraphs[0].add_run(f"{item.get('density_pct', 0.0)}%").font.size = Pt(9)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ---------------------------------------------------------
    # 6. Google Autocomplete Search Suggestions
    # ---------------------------------------------------------
    if suggestions:
        sugg_h = doc.add_heading("4. Live Google Autocomplete Suggestions", level=1)
        sugg_h.runs[0].font.name = "Arial"
        sugg_h.runs[0].font.color.rgb = RGBColor(30, 58, 138)
        sugg_h.paragraph_format.space_before = Pt(12)
        sugg_h.paragraph_format.space_after = Pt(6)

        doc.add_paragraph(
            f"The following high-intent search queries were scraped live from Google Autocomplete for \"{query}\":"
        ).paragraph_format.space_after = Pt(6)

        for s in suggestions:
            p = doc.add_paragraph(style="List Bullet")
            r = p.add_run(s)
            r.font.name = "Arial"
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(30, 41, 59)

    doc.save(output_path)
    return output_path
