# -*- coding: utf-8 -*-
"""
Content Comparison & Keyword Gap Analyzer.

Allows uploading a draft content document (.docx or raw text) and comparing it
against the scraped competitor keyword dominance matrix. Computes keyword ratios,
identifies missing content opportunities, unique vocabulary, and outputs
both JSON for interactive charts and a downloadable Word (.docx) report.
"""

import io
import os
import re
from datetime import datetime
from collections import Counter
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

import analyzer
import keyword_matrix


def extract_text_from_docx(file_source):
    """Extract full clean text from a .docx file path or binary bytes."""
    if isinstance(file_source, (bytes, bytearray)):
        doc = docx.Document(io.BytesIO(file_source))
    else:
        doc = docx.Document(file_source)

    parts = []
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            parts.append(txt)

    for table in doc.tables:
        for row in table.rows:
            row_txt = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_txt:
                parts.append(" | ".join(row_txt))

    return "\n\n".join(parts)


def compare_content_against_competitors(doc_text, matrix_or_analysis=None, query="", doc_name="Uploaded Draft Document", matrix=None):
    """Compares user draft content against the inter-site competitor keyword matrix."""
    source = matrix if matrix is not None else matrix_or_analysis
    if isinstance(source, dict) and "matrix" in source:
        mat = source.get("matrix", {}) or {}
        competitors = source.get("competitors_data", []) or []
        if not query:
            query = source.get("query", "")
    else:
        mat = source or {}
        competitors = mat.get("competitors_data", []) or []

    matrix = mat


    doc_words = analyzer.words(doc_text)
    word_count = len(doc_words)
    if word_count == 0:
        raise ValueError("The uploaded document contains no readable text.")

    flesch = analyzer.flesch(doc_text)
    flesch_level = analyzer.flesch_band(flesch)

    # Competitor cross-site keywords from the matrix
    cross_terms = matrix.get("cross_site_terms", matrix.get("cross_site_keywords", []))
    competitors_count = max(1, matrix.get("competitors_count", len(competitors) if competitors else 5))
    avg_comp_words = round(sum(c.get("total_words", 0) for c in competitors) / max(1, len(competitors))) if competitors else 0


    comparison_rows = []
    missing_opportunities = []
    covered_keywords = []

    for term_obj in cross_terms:
        term = term_obj.get("keyword", "")
        if not term:
            continue

        comp_overlap = term_obj.get("domain_presence", term_obj.get("used_by_count", 0))
        comp_total_count = term_obj.get("total_occurrences", term_obj.get("total_count", 0))

        # Approximate average density across competitors
        comp_avg_density = term_obj.get("avg_density_pct", 0.0)
        if comp_avg_density == 0.0:
            # Estimate from occurrences vs average competitor length (~800 words)
            comp_avg_density = round((comp_total_count / max(1, competitors_count * 800)) * 100, 2)

        # Count in user document
        doc_count = analyzer.count_phrase(doc_text, term)
        doc_density = analyzer.density(doc_text, term)

        # Ratio: doc_density / max(0.01, comp_avg_density)
        if comp_avg_density > 0:
            density_ratio = round(doc_density / comp_avg_density, 2)
        else:
            density_ratio = 1.0 if doc_count > 0 else 0.0

        # Status determination
        if doc_count == 0:
            status = "Missing"
            status_badge = "badge-rose"
            status_desc = "Content Gap (Competitors target this, but missing in your doc)"
            gap_item = {
                "keyword": term,
                "competitor_overlap": f"{comp_overlap}/{competitors_count}",
                "domain_presence": comp_overlap,
                "competitor_hits": comp_total_count,
                "total_competitor_occurrences": comp_total_count,
                "target_density_pct": comp_avg_density,
                "competitor_avg_density_pct": comp_avg_density,
            }
            missing_opportunities.append(gap_item)
        elif density_ratio < 0.6:
            status = "Under-optimized"
            status_badge = "badge-amber"
            status_desc = "Present but density is lower than competitor average"
            covered_keywords.append(term)
        elif density_ratio <= 1.4:
            status = "Optimal"
            status_badge = "badge-emerald"
            status_desc = "Matches competitor target density closely"
            covered_keywords.append(term)
        else:
            status = "High Density"
            status_badge = "badge-blue"
            status_desc = "Higher density than competitor average"
            covered_keywords.append(term)

        comparison_rows.append({
            "keyword": term,
            "doc_count": doc_count,
            "user_count": doc_count,
            "doc_density_pct": doc_density,
            "user_density_pct": doc_density,
            "comp_overlap": comp_overlap,
            "domain_presence": comp_overlap,
            "comp_overlap_label": f"{comp_overlap}/{competitors_count}",
            "comp_total_hits": comp_total_count,
            "total_competitor_occurrences": comp_total_count,
            "comp_avg_density_pct": comp_avg_density,
            "competitor_avg_density_pct": comp_avg_density,
            "density_ratio": density_ratio,
            "ratio": density_ratio,
            "status": status,
            "status_badge": status_badge,
            "status_desc": status_desc,
        })

    # Sort missing opportunities by competitor overlap and hits
    missing_opportunities.sort(key=lambda x: -x["competitor_hits"])

    # Extract user document top keywords
    user_top_kw = keyword_matrix.get_site_keywords(doc_text, top_n=25)
    competitor_kw_set = {t["keyword"].lower() for t in cross_terms}
    unique_user_keywords = [
        kw for kw in user_top_kw if kw["keyword"].lower() not in competitor_kw_set
    ]

    # Calculate optimization score (percentage of competitor cross terms covered, weighted by overlap)
    total_comp_terms = len(cross_terms)
    if total_comp_terms > 0:
        covered_count = len(covered_keywords)
        raw_score = int((covered_count / total_comp_terms) * 100)
        # Bonus for optimal keywords
        optimal_count = sum(1 for r in comparison_rows if r["status"] == "Optimal")
        opt_bonus = min(15, int((optimal_count / max(1, covered_count)) * 15))
        score = min(100, max(10, raw_score + opt_bonus))
    else:
        score = 80

    # Chart datasets: Top 15 keywords
    top_chart_rows = comparison_rows[:15]
    chart_data = {
        "labels": [r["keyword"] for r in top_chart_rows],
        "user_densities": [r["doc_density_pct"] for r in top_chart_rows],
        "comp_densities": [r["comp_avg_density_pct"] for r in top_chart_rows],
        "ratios": [r["density_ratio"] for r in top_chart_rows],
    }

    return {
        "doc_name": doc_name,
        "query": query,
        "word_count": word_count,
        "flesch_reading_ease": flesch,
        "reading_level": flesch_level,
        "optimization_score": score,
        "total_competitor_keywords": total_comp_terms,
        "covered_keywords_count": len(covered_keywords),
        "missing_keywords_count": len(missing_opportunities),
        "comparison_rows": comparison_rows,
        "keyword_comparisons": comparison_rows,
        "missing_opportunities": missing_opportunities[:25],
        "content_gaps": missing_opportunities[:25],
        "unique_user_keywords": unique_user_keywords[:15],
        "chart_data": chart_data,
        "user_metrics": {
            "word_count": word_count,
            "flesch_reading_ease": flesch,
            "reading_level": flesch_level,
        },
        "competitor_averages": {
            "avg_word_count": avg_comp_words,
            "competitor_count": competitors_count,
        },
        "competitor_count": competitors_count,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
    }



def generate_comparison_docx(comparison_data, output_path="content_comparison_report.docx"):
    """Generate a publication-grade Word (.docx) report comparing user doc against competitors."""
    doc = docx.Document()

    # Document Title
    title = doc.add_paragraph()
    r_title = title.add_run("CONTENT VS. COMPETITOR KEYWORD AUDIT")
    r_title.bold = True
    r_title.font.size = Pt(20)
    r_title.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    r_sub = sub.add_run("Comprehensive Keyword Density, Ratio & Content Gap Analysis")
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Executive Summary Card Table
    meta_tbl = doc.add_table(rows=2, cols=4)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Document Name", "Word Count", "Readability", "Optimization Score"]
    values = [
        comparison_data.get("doc_name", "Draft Doc"),
        f"{comparison_data.get('word_count', 0):,} words",
        f"{comparison_data.get('flesch_reading_ease', 0):.1f} ({comparison_data.get('reading_level', 'Standard')})",
        f"{comparison_data.get('optimization_score', 0)} / 100"
    ]
    for i, h in enumerate(headers):
        cell = meta_tbl.rows[0].cells[i]
        cell.text = h
        p = cell.paragraphs[0]
        p.runs[0].bold = True
        p.runs[0].font.size = Pt(9.5)
        p.runs[0].font.color.rgb = RGBColor(0x47, 0x55, 0x69)
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F1F5F9"/>')
        cell._tc.get_or_add_tcPr().append(shd)

        val_cell = meta_tbl.rows[1].cells[i]
        val_cell.text = values[i]
        vp = val_cell.paragraphs[0]
        vp.runs[0].bold = True
        vp.runs[0].font.size = Pt(11)
        vp.runs[0].font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    doc.add_paragraph()

    # Section 1: Comparison Matrix Table
    h1 = doc.add_heading("1. Keyword Comparison & Density Ratios", level=1)
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(6)

    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_headers = ["Rank", "Keyword / Phrase", "Your Count", "Your Density", "Comp Target", "Ratio & Status"]
    for i, name in enumerate(table_headers):
        cell = table.rows[0].cells[i]
        cell.text = name
        p = cell.paragraphs[0]
        p.runs[0].bold = True
        p.runs[0].font.size = Pt(9.5)
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="2563EB"/>')
        cell._tc.get_or_add_tcPr().append(shd)

    for idx, row in enumerate(comparison_data.get("comparison_rows", [])[:35], start=1):
        tr = table.add_row()
        cells = tr.cells
        cells[0].text = str(idx)
        cells[1].text = row["keyword"]
        cells[2].text = str(row["doc_count"])
        cells[3].text = f"{row['doc_density_pct']:.2f}%"
        cells[4].text = f"{row['comp_avg_density_pct']:.2f}% ({row['comp_overlap_label']})"
        cells[5].text = f"{row['density_ratio']:.2f}x - {row['status']}"

        # Style cells
        for c_idx, c in enumerate(cells):
            cp = c.paragraphs[0]
            cp.runs[0].font.size = Pt(9)
            if c_idx == 1:
                cp.runs[0].bold = True
            if idx % 2 == 0:
                shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F8FAFC"/>')
                c._tc.get_or_add_tcPr().append(shd)

    doc.add_paragraph()

    # Section 2: Content Gaps (Missing Keywords)
    missing = comparison_data.get("missing_opportunities", [])
    if missing:
        h2 = doc.add_heading("2. Content Gaps: High-Value Keywords Missing in Your Document", level=1)
        h2.paragraph_format.space_before = Pt(14)
        h2.paragraph_format.space_after = Pt(6)

        desc = doc.add_paragraph()
        r_desc = desc.add_run(
            "These high-frequency keywords were discovered across your competitors' landing pages, "
            "but are completely absent (0 hits) in your draft document. Incorporate these to close ranking gaps:"
        )
        r_desc.font.size = Pt(9.5)
        r_desc.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

        gap_table = doc.add_table(rows=1, cols=4)
        gap_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        gap_headers = ["#", "Missing Keyword", "Competitor Penetration", "Total Competitor Occurrences"]
        for i, name in enumerate(gap_headers):
            cell = gap_table.rows[0].cells[i]
            cell.text = name
            p = cell.paragraphs[0]
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(9.5)
            p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="DC2626"/>')
            cell._tc.get_or_add_tcPr().append(shd)

        for idx, item in enumerate(missing[:20], start=1):
            gtr = gap_table.add_row()
            cells = gtr.cells
            cells[0].text = str(idx)
            cells[1].text = item["keyword"]
            cells[2].text = item["competitor_overlap"]
            cells[3].text = str(item["competitor_hits"])
            for c_idx, c in enumerate(cells):
                cp = c.paragraphs[0]
                cp.runs[0].font.size = Pt(9)
                if c_idx == 1:
                    cp.runs[0].bold = True
                    cp.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)

    doc.add_paragraph()

    # Section 3: Unique User Keywords
    unique_kws = comparison_data.get("unique_user_keywords", [])
    if unique_kws:
        h3 = doc.add_heading("3. Unique Differentiator Keywords (Exclusive to Your Draft)", level=1)
        h3.paragraph_format.space_before = Pt(14)
        h3.paragraph_format.space_after = Pt(6)

        up = doc.add_paragraph()
        r_up = up.add_run(
            "These keywords appear frequently in your draft but were not emphasized by competitors. "
            "They represent your unique branding, angle, and distinct value proposition:"
        )
        r_up.font.size = Pt(9.5)

        for u in unique_kws[:12]:
            p = doc.add_paragraph(style="List Bullet")
            pr = p.add_run(f"{u['keyword']}  ({u['count']} hits, {u['density_pct']:.2f}% density)")
            pr.font.size = Pt(9.5)

    doc.save(output_path)
    return output_path
