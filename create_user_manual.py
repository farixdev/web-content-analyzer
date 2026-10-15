# -*- coding: utf-8 -*-
"""
Generate a comprehensive, plain-English PDF User Manual for Mindcob Web Content Analyzer.
"""

import os
import subprocess
import base64

def generate_pdf_manual():
    # Load Mindcob Logo as base64
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
    logo_b64 = ""
    if os.path.isfile(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Mindcob Web Content Analyzer - User Manual</title>
<style>
  @page {{
    size: A4;
    margin: 16mm 14mm 18mm 14mm;
    @bottom-center {{
      content: "Page " counter(page);
    }}
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    color: #1E293B;
    background: #FFFFFF;
    line-height: 1.55;
    font-size: 11pt;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}

  .header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 2px solid #2563EB;
    padding-bottom: 12px;
    margin-bottom: 24px;
  }}

  .header img {{
    height: 42px;
    width: auto;
  }}

  .header-meta {{
    text-align: right;
    font-size: 9pt;
    color: #64748B;
  }}

  .header-meta strong {{
    color: #0F172A;
    font-size: 10pt;
    display: block;
  }}

  .title-block {{
    background: #EFF6FF;
    border-left: 5px solid #2563EB;
    padding: 16px 20px;
    border-radius: 0 8px 8px 0;
    margin-bottom: 24px;
  }}

  h1 {{
    font-size: 20pt;
    font-weight: 800;
    color: #1E3A8A;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
  }}

  .subtitle {{
    font-size: 11.5pt;
    color: #334155;
    font-weight: 500;
  }}

  h2 {{
    font-size: 14pt;
    font-weight: 700;
    color: #1E3A8A;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 6px;
    margin-top: 24px;
    margin-bottom: 12px;
    page-break-after: avoid;
  }}

  h3 {{
    font-size: 12pt;
    font-weight: 700;
    color: #0F172A;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
  }}

  p {{
    margin-bottom: 10px;
    color: #334155;
  }}

  ul, ol {{
    margin-left: 20px;
    margin-bottom: 12px;
  }}

  li {{
    margin-bottom: 6px;
    color: #334155;
  }}

  li strong {{
    color: #0F172A;
  }}

  /* Callout Card */
  .card, .card-tip, .card-note, tr {{
    page-break-inside: avoid;
    break-inside: avoid;
  }}

  .card {{
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 16px;
  }}

  .card-tip {{
    background: #F0FDF4;
    border-left: 4px solid #16A34A;
    padding: 12px 16px;
    border-radius: 0 6px 6px 0;
    margin: 14px 0;
    font-size: 10pt;
  }}

  .card-tip strong {{
    color: #15803D;
  }}

  .card-note {{
    background: #FEF3C7;
    border-left: 4px solid #D97706;
    padding: 12px 16px;
    border-radius: 0 6px 6px 0;
    margin: 14px 0;
    font-size: 10pt;
  }}

  .card-note strong {{
    color: #B45309;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0 18px 0;
    font-size: 9.5pt;
  }}

  th {{
    background: #1E3A8A;
    color: #FFFFFF;
    font-weight: 600;
    text-align: left;
    padding: 8px 10px;
    border: 1px solid #1E3A8A;
  }}

  td {{
    padding: 8px 10px;
    border: 1px solid #CBD5E1;
    color: #334155;
  }}

  tr:nth-child(even) td {{
    background: #F8FAFC;
  }}

  .badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 8pt;
    font-weight: 600;
  }}

  .badge-blue {{
    background: #EFF6FF;
    color: #2563EB;
    border: 1px solid #BFDBFE;
  }}

  .badge-green {{
    background: #ECFDF5;
    color: #059669;
    border: 1px solid #A7F3D0;
  }}

  .page-break {{
    page-break-before: always;
  }}

  .footer-note {{
    margin-top: 30px;
    border-top: 1px solid #E2E8F0;
    padding-top: 10px;
    font-size: 8.5pt;
    color: #94A3B8;
    text-align: center;
  }}

  .kbd {{
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    padding: 1px 6px;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 9pt;
    color: #0F172A;
  }}
</style>
</head>
<body>

  <!-- Top Header with Logo -->
  <div class="header">
    <img src="{logo_b64}" alt="Mindcob Logo">
    <div class="header-meta">
      <strong>Mindcob Intelligence System</strong>
      User Manual & Functionality Guide
    </div>
  </div>

  <!-- Document Title Block -->
  <div class="title-block">
    <h1>Web Content Analyzer & SEO Intelligence</h1>
    <div class="subtitle">Complete, Plain-English User Guide: How it works, what it measures, and how to use every feature.</div>
  </div>

  <!-- Section 1 -->
  <h2>1. What Is This Tool & What Does It Do?</h2>
  <p>The <strong>Mindcob Web Content Analyzer</strong> is an automated SEO intelligence tool. In plain English, it answers one simple question:</p>
  <div class="card" style="font-weight: 600; color: #1E3A8A; font-size: 11pt;">
    "When people search Google for a specific topic, what exact words, phrases, and topics are the top-ranking competitors using across their entire websites?"
  </div>

  <p>Instead of guessing what to write in an article, blog post, or service landing page, this tool scans the actual websites currently ranking on Google. It reads <strong>20 to 40+ internal pages</strong> for each competitor (not just their homepage), counts every word, and presents you with a clear roadmap of:</p>
  <ul>
    <li>Which keywords and phrases are <strong>shared by all competitors</strong> (core topics you must cover).</li>
    <li>How often each competitor uses those keywords (exact counts and percentage densities).</li>
    <li>Every single webpage that was crawled, with total word counts and direct links.</li>
    <li>Live Google autocomplete suggestions that real people are searching for.</li>
    <li>One-click publication-ready <strong>Microsoft Word reports (.docx)</strong> with embedded charts and spreadsheets (.csv) to hand directly to writers or clients.</li>
  </ul>

  <div class="card-tip">
    <strong>100% Free Organic Engine:</strong> You do NOT need any paid API keys (like Serper, Semrush, or Ahrefs). The built-in organic engine queries Google and crawls websites directly at zero cost.
  </div>

  <!-- Section 2 -->
  <h2>2. Quick Start: How to Run an Analysis in 3 Steps</h2>
  <ol>
    <li>
      <strong>Type Your Topic or Keyword:</strong> In the <em>Search Query</em> box, enter the topic you want to rank for (e.g., <code>pos system montreal</code> or <code>business voip for law firms</code>).
    </li>
    <li>
      <strong>Pick Your Target Country:</strong> Select where your target audience lives (e.g. <em>United States, Canada, United Kingdom, Australia</em>). Google search results change by country; the tool queries Google from that specific location.
    </li>
    <li>
      <strong>Click "Run Deep Analysis":</strong> The crawler starts immediately. You will see a live progress bar and a log console showing every page being scraped in real time.
    </li>
  </ol>
  <p style="margin-top: 10px;">Within 30 to 60 seconds, the crawler finishes and reveals all charts, tables, and download buttons.</p>



  <!-- Section 3 -->
  <h2>3. Detailed Explanation of Every Setting & Filter</h2>
  <p>Under the search bar, you have controls to customize how the scraper works. Here is what each setting does in simple terms:</p>

  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Setting</th>
        <th style="width: 25%;">Options</th>
        <th style="width: 50%;">What It Means In Plain English</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Competitor Sites</strong></td>
        <td><span class="badge badge-blue">3 Sites</span> <span class="badge badge-blue">5 Sites (Rec)</span> <span class="badge badge-blue">8 Sites</span></td>
        <td>How many top-ranking business websites to scrape. <strong>5 Sites</strong> is the recommended sweet spot—it gives a solid cross-industry average without taking too long.</td>
      </tr>
      <tr>
        <td><strong>Pages / Competitor</strong></td>
        <td><span class="badge badge-blue">15 Pages</span> <span class="badge badge-blue">25 Pages (Rec)</span> <span class="badge badge-blue">40 Pages</span></td>
        <td>How deep the crawler goes into each competitor's website. If you select 25 pages and 5 competitors, the tool automatically crawls up to <strong>125 pages</strong> total, reading their services, case studies, and blog posts.</td>
      </tr>
      <tr>
        <td><strong>Keyword Type (N-Gram)</strong></td>
        <td><span class="badge badge-blue">All Keywords</span> <span class="badge badge-blue">Phrases (2-3 words)</span> <span class="badge badge-blue">Single Words</span></td>
        <td>
          Controls whether the analysis looks for individual words or full search phrases:<br>
          &bull; <strong>All Keywords:</strong> Everything combined.<br>
          &bull; <strong>Phrases (2-3 words):</strong> <em>(Best for SEO)</em> Filters out generic words like "the" or "business" and reveals actual search phrases like <em>"cloud phone system"</em> or <em>"inventory management"</em>.<br>
          &bull; <strong>Single Words:</strong> Individual core terms like <em>"hardware"</em>, <em>"billing"</em>, <em>"telephony"</em>.
        </td>
      </tr>
      <tr>
        <td><strong>Crawler Speed</strong></td>
        <td><span class="badge badge-blue">Fast (8)</span> <span class="badge badge-blue">Standard (5)</span> <span class="badge badge-blue">Polite (2)</span></td>
        <td>How many web pages the scraper downloads at the exact same moment. <strong>Fast (8 workers)</strong> finishes in ~35 seconds. <strong>Polite (2 workers)</strong> crawls gently if you are scraping sensitive or smaller websites.</td>
      </tr>
      <tr>
        <td><strong>Custom Stopwords</strong> <em>(Advanced)</em></td>
        <td>Text input (comma separated)</td>
        <td>Words you want the tool to completely ignore. For example, if competitors keep repeating their own company name (e.g. <em>"telus, rogers"</em>) or boilerplate words (<em>"copyright, login, privacy"</em>), type them here to keep your report clean.</td>
      </tr>
      <tr>
        <td><strong>SERP API Key</strong> <em>(Optional)</em></td>
        <td>Serper API Key</td>
        <td><strong>Leave this blank for 100% free use!</strong> Only fill this in if you already own a paid Serper.dev API account and prefer using an official Google SERP API instead of free organic scraping.</td>
      </tr>
    </tbody>
  </table>

  <!-- Section 4 -->
  <h2>4. Understanding the Results: What the Tabs & Charts Show</h2>
  <p>Once the scan completes, you get four interactive views:</p>

  <h3>Tab 1: Keyword Dominance Matrix (The Core Feature)</h3>
  <p>This is the most powerful part of the tool. It shows which keywords are used by <strong>multiple competitors at the same time</strong>.</p>
  <ul>
    <li><strong>The Bar Chart:</strong> Shows the top 15 most frequent shared keywords across all competitors at a glance.</li>
    <li><strong>The Matrix Table:</strong> Lists every shared keyword, its <strong>Competitor Overlap</strong> (e.g., <em>"4 / 5 sites (80%)"</em>), the total number of times it was written, and exactly how many times each competitor used it.</li>
    <li><strong>Why this matters for your content:</strong> If a keyword is used by 5 out of 5 competitors, Google expects to see that topic in any page that wants to rank on page 1.</li>
    <li><strong>Search Filter Box:</strong> You can type any word into the table filter box to immediately see if competitors mentioned it and how many times.</li>
  </ul>

  <h3>Tab 2: Competitor Deep Dive</h3>
  <p>Allows you to inspect any competitor individually:</p>
  <ul>
    <li><strong>Domain Pills:</strong> Click on any competitor button (e.g., <code>competitor1.com</code>) to view their specific statistics.</li>
    <li><strong>Top 20 Keywords Chart & Table:</strong> Shows their exact highest-frequency keywords, how many times they appear, and their density percentage.</li>
    <li><strong>Crawled Pages Directory:</strong> A complete list of all 20–40 pages scraped from that competitor, their page titles, word counts, and a direct link to visit the original page.</li>
  </ul>

  <!-- Page Break -->
  <div class="page-break"></div>

  <h3>Tab 3: Google Autocomplete Suggestions</h3>
  <p>This tab displays real-time search queries scraped directly from Google's live autocomplete dropdown for your keyword.</p>
  <ul>
    <li>These chips represent related questions and search variations that real users are actively typing into Google.</li>
    <li><strong>1-Click Re-Analysis:</strong> Clicking on any suggestion chip automatically puts it into the search box and lets you run a fresh analysis for that sub-topic.</li>
  </ul>

  <h3>Tab 4: Organic SERP Results</h3>
  <p>Shows the original Google search engine results page as it appeared:</p>
  <ul>
    <li>Every ranked listing (#1, #2, #3, etc.) with title, domain, and meta snippet.</li>
    <li>Shows which websites were selected as business competitors and which links were automatically filtered out (e.g. Reddit forums, social media, or ads).</li>
  </ul>



  <!-- Section 5 -->
  <h2>5. How to Export & Download Your Reports</h2>
  <p>In the top-right corner of the Results section, you have five instant download options:</p>

  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Export Format</th>
        <th style="width: 35%;">What Is Included</th>
        <th style="width: 40%;">Best Used For</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Download in Word (.docx)</strong></td>
        <td>
          A complete, publication-grade Microsoft Word document featuring:<br>
          &bull; Executive cover header & KPI summary<br>
          &bull; High-resolution embedded dominance chart<br>
          &bull; Full keyword dominance matrix tables<br>
          &bull; Individual competitor deep-dive breakdowns
        </td>
        <td>
          <strong>Handing to writers or clients.</strong> It is 100% formatted with professional corporate styling and ready to print or email.
        </td>
      </tr>
      <tr>
        <td><strong>Download Chart PNG</strong></td>
        <td>A clean, high-resolution PNG image of the Keyword Dominance bar chart.</td>
        <td>Client presentations, slide decks, and marketing proposals.</td>
      </tr>
      <tr>
        <td><strong>Export CSV</strong></td>
        <td>Raw spreadsheet data with rank, keyword, overlap count, frequency, and per-domain breakdown.</td>
        <td>Opening in Microsoft Excel or Google Sheets for custom formulas or sorting.</td>
      </tr>
      <tr>
        <td><strong>Save HTML</strong></td>
        <td>A self-contained HTML webpage containing the interactive charts.</td>
        <td>Saving a permanent offline copy that anyone can open in any browser without installing anything.</td>
      </tr>
      <tr>
        <td><strong>Markdown</strong></td>
        <td>A clean text document with markdown headers and tables.</td>
        <td>Pasting into Notion, GitHub, Obsidian, or documentation wikis.</td>
      </tr>
    </tbody>
  </table>

  <!-- Section 6 -->
  <h2>6. Practical Tips: How to Write an Article Using This Data</h2>
  <p>Here is the exact 4-step workflow to turn this data into a top-ranking article or service page:</p>
  <ol>
    <li>
      <strong>Identify the "Must-Have" Topics (100% Overlap):</strong> Look at the Keyword Dominance Matrix table. Any keyword that has <em>4/5 or 5/5 competitor presence</em> is a core requirement. Create an <strong>H2 or H3 heading</strong> in your outline covering that topic.
    </li>
    <li>
      <strong>Match the Average Word Count:</strong> Check the <em>Total Words Parsed</em> KPI. Divide that by the number of pages to see the average page length. If competitors average 1,500 words on their top pages, aim for 1,600–1,800 words of higher-quality content.
    </li>
    <li>
      <strong>Use 2–3 Word Phrases for Natural Flow:</strong> Set the N-Gram filter to <em>Phrases (2-3 words)</em>. Work these phrases naturally into your body text and bullet points instead of stuffing single words repeatedly.
    </li>
    <li>
      <strong>Answer Google Suggestions:</strong> Grab the top 3–5 questions from the <em>Google Suggestions</em> tab and turn them into an <strong>FAQ section</strong> at the bottom of your page.
    </li>
  </ol>

  <!-- Section 7 -->
  <h2>7. Frequently Asked Questions (FAQ)</h2>
  <div class="card">
    <p><strong>Q: Why does the analysis take 30 to 60 seconds?</strong><br>
    A: Unlike basic SEO tools that only check one URL, this tool connects to Google, identifies top competitors, and crawls up to 100+ separate web pages live. Scraping and analyzing 100 pages in ~40 seconds is extraordinarily fast.</p>
    
    <p><strong>Q: What happens if a competitor website blocks crawlers?</strong><br>
    A: The engine includes automatic bot-protection bypass headers. If a specific page is strictly locked behind a firewall or captcha, the crawler politely skips that single page and continues crawling the remaining pages so your report never fails.</p>

    <p><strong>Q: Do I have to pay anything to keep this running?</strong><br>
    A: No. It is hosted on Render's 100% free cloud tier and uses organic Google scraping. There are zero subscription fees or hidden costs.</p>

    <p><strong>Q: Where is my deployed web dashboard located?</strong><br>
    A: Your live web app is accessible at: <code>https://web-content-analyzer.onrender.com/</code></p>
  </div>

  <div class="footer-note">
    Mindcob Web Content Analyzer &bull; Official User Manual &bull; Confidential & Proprietary &bull; Mindcob Intelligence
  </div>

</body>
</html>
"""

    html_file = os.path.join(os.path.dirname(__file__), "user_manual.html")
    pdf_file = os.path.join(os.path.dirname(__file__), "Mindcob_Web_Content_Analyzer_User_Manual.pdf")

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[*] HTML manual written to: {html_file}")

    # Convert to PDF using Microsoft Edge headless
    edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.isfile(edge_exe):
        edge_exe = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

    if os.path.isfile(edge_exe):
        print(f"[*] Compiling PDF using: {edge_exe} ...")
        cmd = [
            edge_exe,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_file}",
            f"file:///{os.path.abspath(html_file).replace(os.sep, '/')}"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.isfile(pdf_file) and os.path.getsize(pdf_file) > 1000:
            print(f"[SUCCESS] PDF User Manual generated successfully: {pdf_file}")
            print(f"[*] File size: {os.path.getsize(pdf_file):,} bytes")
            return pdf_file
        else:
            print(f"[!] Edge print-to-pdf output: {res.stdout} {res.stderr}")
    else:
        print("[!] Microsoft Edge not found in standard paths.")

    return None

if __name__ == "__main__":
    generate_pdf_manual()
