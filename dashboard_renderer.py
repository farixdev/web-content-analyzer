# -*- coding: utf-8 -*-
"""
Interactive Analytics Dashboard Renderer for QWebEngineView.

Generates a standalone, modern HTML5/JS dashboard using Chart.js to visualize:
- Cross-site competitor keyword dominance (bar charts & penetration)
- Per-website Top 20 keywords with exact occurrences and densities
- Google Autocomplete search suggestion chips
- Multi-page crawl inventory per competitor
"""

import json
import html


def render_dashboard_html(data):
    """Render the analytics data into an interactive, sleek HTML dashboard.

    `data` structure:
    {
        "query": "john doe",
        "country": "United States",
        "suggestions": ["john doe meaning", "john doe tv show", ...],
        "competitors_data": [
            {
                "domain": "example.com",
                "start_url": "https://example.com",
                "pages_scraped": 24,
                "total_words": 18450,
                "pages": [{"title": "...", "url": "...", "word_count": 450}, ...]
            },
            ...
        ],
        "matrix": {
            "competitors_count": 4,
            "domains": ["site1.com", "site2.com"],
            "per_site_top_20": {"site1.com": [...], ...},
            "cross_site_keywords": [...]
        }
    }
    """
    json_data = json.dumps(data)

    query = html.escape(data.get("query", ""))
    country = html.escape(data.get("country", ""))
    suggestions = data.get("suggestions", [])
    matrix = data.get("matrix", {})
    domains = matrix.get("domains", [])
    cross_kw = matrix.get("cross_site_keywords", [])
    per_site = matrix.get("per_site_top_20", {})
    competitors = data.get("competitors_data", [])

    total_pages = sum(c.get("pages_scraped", 0) for c in competitors)
    total_words = sum(c.get("total_words", 0) for c in competitors)

    # Load local Chart.js bundle for 100% offline standalone operation
    import os
    local_chart_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "chart.umd.min.js")
    chart_script_tag = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>'
    if os.path.isfile(local_chart_path):
        try:
            with open(local_chart_path, "r", encoding="utf-8") as f:
                chart_code = f.read()
                if chart_code.strip():
                    chart_script_tag = f"<script>{chart_code}</script>"
        except Exception:
            pass

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Deep Competitor & Keyword Intelligence</title>
  {chart_script_tag}
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(255, 255, 255, 0.12);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.25);
      --secondary: #818cf8;
      --accent: #34d399;
      --accent-rose: #fb7185;
      --badge-bg: rgba(56, 189, 248, 0.12);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}

    body {{
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(56, 189, 248, 0.07) 0%, transparent 40%),
        radial-gradient(circle at 85% 85%, rgba(129, 140, 248, 0.07) 0%, transparent 40%);
      color: var(--text-main);
      padding: 24px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}

    /* Header Bar */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }}

    .header-left h1 {{
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .header-meta {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }}

    .header-meta span {{
      color: var(--text-main);
      font-weight: 600;
    }}

    /* Stats Grid */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}

    .stat-card {{
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px 20px;
      transition: all 0.2s ease;
    }}

    .stat-card:hover {{
      border-color: var(--card-hover);
      transform: translateY(-2px);
    }}

    .stat-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
    }}

    .stat-value {{
      font-size: 26px;
      font-weight: 700;
      color: var(--text-main);
      margin-top: 4px;
    }}

    .stat-sub {{
      font-size: 12px;
      color: var(--primary);
      margin-top: 2px;
    }}

    /* Google Suggestions Bar */
    .suggestions-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px 20px;
      margin-bottom: 24px;
    }}

    .suggestions-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
    }}

    .suggestions-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .chip {{
      background: var(--badge-bg);
      border: 1px solid rgba(56, 189, 248, 0.2);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: default;
      transition: all 0.2s;
    }}

    .chip:hover {{
      background: rgba(56, 189, 248, 0.25);
      border-color: var(--primary);
      transform: translateY(-1px);
    }}

    /* Section Layout */
    .section {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 22px;
      margin-bottom: 24px;
    }}

    .section-title {{
      font-size: 17px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .section-desc {{
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 18px;
    }}

    /* Charts Container */
    .chart-container {{
      position: relative;
      width: 100%;
      height: 380px;
      margin-bottom: 16px;
    }}

    /* Interactive Site Selector Tabs */
    .site-tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      overflow-x: auto;
      padding-bottom: 6px;
    }}

    .site-tab {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.2s;
    }}

    .site-tab:hover {{
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.08);
    }}

    .site-tab.active {{
      background: var(--primary);
      color: #0b0f19;
      border-color: var(--primary);
      box-shadow: 0 0 12px var(--primary-glow);
    }}

    /* Data Tables */
    .table-container {{
      width: 100%;
      overflow-x: auto;
      margin-top: 14px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}

    th {{
      background: rgba(255, 255, 255, 0.03);
      color: var(--text-muted);
      font-weight: 600;
      padding: 10px 14px;
      border-bottom: 1px solid var(--card-border);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
    }}

    td {{
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text-main);
    }}

    tr:hover td {{
      background: rgba(255, 255, 255, 0.02);
    }}

    .rank-badge {{
      display: inline-block;
      width: 22px;
      height: 22px;
      line-height: 22px;
      text-align: center;
      border-radius: 50%;
      font-size: 11px;
      font-weight: 700;
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
    }}

    .rank-1 {{ background: #fbbf24; color: #000; }}
    .rank-2 {{ background: #94a3b8; color: #000; }}
    .rank-3 {{ background: #b45309; color: #fff; }}

    .bar-bg {{
      width: 100%;
      background: rgba(255, 255, 255, 0.06);
      height: 6px;
      border-radius: 3px;
      overflow: hidden;
      margin-top: 4px;
    }}

    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--primary), var(--secondary));
      border-radius: 3px;
    }}

    /* Accordion for Crawled Pages */
    details {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      margin-bottom: 8px;
      padding: 10px 14px;
    }}

    summary {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text-main);
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      user-select: none;
    }}

    summary:hover {{
      color: var(--primary);
    }}

    .page-list {{
      margin-top: 12px;
      font-size: 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .page-item {{
      display: flex;
      justify-content: space-between;
      padding: 4px 8px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.2);
    }}

    .page-item a {{
      color: var(--primary);
      text-decoration: none;
      max-width: 80%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .page-item a:hover {{
      text-decoration: underline;
    }}

    .page-words {{
      color: var(--text-muted);
    }}
  </style>
</head>
<body>

  <!-- Top Header -->
  <div class="header">
    <div class="header-left">
      <h1>Deep Competitor & Keyword Intelligence</h1>
      <div class="header-meta">
        Target Keyword: <span>"{query}"</span> &bull; 
        Country: <span>{country}</span> &bull; 
        Depth: <span>{len(competitors)} Competitor Sites Scraped</span>
      </div>
    </div>
  </div>

  <!-- Key Metrics Row -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Competitors Analyzed</div>
      <div class="stat-value">{len(competitors)}</div>
      <div class="stat-sub">Clean organic business sites</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Pages Crawled</div>
      <div class="stat-value">{total_pages}</div>
      <div class="stat-sub">~{round(total_pages / max(1, len(competitors)))} pages per site</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Corpus Size</div>
      <div class="stat-value">{total_words:,}</div>
      <div class="stat-sub">Total extracted words</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Shared Keywords</div>
      <div class="stat-value">{len(cross_kw)}</div>
      <div class="stat-sub">Common across competitor set</div>
    </div>
  </div>

  <!-- Google Autocomplete Suggestions -->
  {"".join([f'''
  <div class="suggestions-card">
    <div class="suggestions-title">
      <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
        <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
      </svg>
      Google Live Autocomplete Suggestions ({len(suggestions)})
    </div>
    <div class="suggestions-chips">
      {"".join(f'<div class="chip">{html.escape(s)}</div>' for s in suggestions)}
    </div>
  </div>
  ''' if suggestions else ''])}

  <!-- Section 1: Inter-Site Cross Competitor Dominance -->
  <div class="section">
    <div class="section-title">
      <span>Inter-Site Keyword Dominance</span>
      <span style="font-size:12px; font-weight:400; color:var(--text-muted)">Shared Across Multiple Competitors</span>
    </div>
    <div class="section-desc">
      Keywords and phrases that appear across the most competitor websites, ranked by cross-site penetration and total frequency.
    </div>

    <div class="chart-container">
      <canvas id="crossSiteChart"></canvas>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Shared Keyword / Phrase</th>
            <th>Competitor Penetration</th>
            <th>Total Occurrences</th>
            <th>Per-Competitor Breakdown</th>
          </tr>
        </thead>
        <tbody>
          {"".join([f'''
          <tr>
            <td><span class="rank-badge {'rank-' + str(idx) if idx <= 3 else ''}">{idx}</span></td>
            <td><b style="color:var(--primary)">{html.escape(k["keyword"])}</b></td>
            <td>
              <span>{k["used_by_count"]} / {len(competitors)} sites ({k["used_by_pct"]}%)</span>
              <div class="bar-bg"><div class="bar-fill" style="width:{k['used_by_pct']}%"></div></div>
            </td>
            <td><b>{k["total_count"]}</b> hits</td>
            <td style="color:var(--text-muted); font-size:12px">
              {" &bull; ".join(f'{d}: {cnt}' for d, cnt in k.get("breakdown", {}).items() if cnt > 0)}
            </td>
          </tr>
          ''' for idx, k in enumerate(cross_kw[:15], start=1)])}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Section 2: Individual Website Deep Analysis (Top 20 Keywords) -->
  <div class="section">
    <div class="section-title">
      <span>Per-Website Top 20 Keyword Breakdown</span>
    </div>
    <div class="section-desc">
      Explore the top 20 most frequent keywords discovered across all crawled pages for each individual competitor website.
    </div>

    <!-- Site Selector Tabs -->
    <div class="site-tabs" id="siteTabs">
      {"".join([f'''
      <div class="site-tab {'active' if idx == 0 else ''}" onclick="selectSite('{dom}')">{dom}</div>
      ''' for idx, dom in enumerate(domains)])}
    </div>

    <div class="chart-container" style="height:320px;">
      <canvas id="siteChart"></canvas>
    </div>

    <div class="table-container">
      <table id="siteKeywordsTable">
        <thead>
          <tr>
            <th># Rank</th>
            <th>Keyword / Phrase</th>
            <th>Type</th>
            <th>Total Occurrences Across Crawl</th>
            <th>Corpus Density</th>
          </tr>
        </thead>
        <tbody id="siteTableBody">
          <!-- Dynamically populated via JS -->
        </tbody>
      </table>
    </div>
  </div>

  <!-- Section 3: Crawled Pages Inventory -->
  <div class="section">
    <div class="section-title">
      <span>Crawled Pages Inventory ({total_pages} Pages)</span>
    </div>
    <div class="section-desc">
      Review the exact internal pages crawled and indexed for each competitor domain.
    </div>

    {"".join([f'''
    <details>
      <summary>
        <span><b>{comp["domain"]}</b> ({comp.get("pages_scraped", 0)} pages, {comp.get("total_words", 0):,} words)</span>
        <span style="color:var(--primary); font-size:12px">View Pages &darr;</span>
      </summary>
      <div class="page-list">
        {"".join([f'''
        <div class="page-item">
          <a href="{html.escape(p["url"])}" target="_blank">{html.escape(p.get("title") or p["url"])}</a>
          <span class="page-words">{p.get("word_count", 0)} words</span>
        </div>
        ''' for p in comp.get("pages", [])])}
      </div>
    </details>
    ''' for comp in competitors])}
  </div>

  <!-- Embedded Data & Chart Script -->
  <script>
    const DATA = {json_data};
    const CROSS_KEYWORDS = {json.dumps(cross_kw[:15])};
    const PER_SITE = {json.dumps(per_site)};
    const DOMAINS = {json.dumps(domains)};

    let currentSite = DOMAINS.length > 0 ? DOMAINS[0] : "";
    let crossChart = null;
    let siteChart = null;

    // Initialize Cross Site Dominance Chart
    function initCrossChart() {{
      const ctx = document.getElementById('crossSiteChart');
      if (!ctx || !window.Chart) return;

      const labels = CROSS_KEYWORDS.map(k => k.keyword);
      const dataCounts = CROSS_KEYWORDS.map(k => k.total_count);
      const dataPenetration = CROSS_KEYWORDS.map(k => k.used_by_pct);

      crossChart = new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [{{
            label: 'Total Hits Across Competitors',
            data: dataCounts,
            backgroundColor: 'rgba(56, 189, 248, 0.75)',
            borderColor: '#38bdf8',
            borderWidth: 1,
            borderRadius: 6,
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              labels: {{ color: '#94a3b8', font: {{ size: 12 }} }}
            }},
            tooltip: {{
              callbacks: {{
                afterLabel: function(context) {{
                  const item = CROSS_KEYWORDS[context.dataIndex];
                  return 'Competitors: ' + item.used_by_count + '/' + DATA.competitors_data.length + ' (' + item.used_by_pct + '%)';
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }},
              grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}
            }},
            y: {{
              ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }},
              grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}
            }}
          }}
        }}
      }});
    }}

    // Update Per-Site Top 20 Chart & Table
    function updateSiteView(domain) {{
      currentSite = domain;
      const keywords = PER_SITE[domain] || [];

      // Update Tabs active class
      const tabs = document.querySelectorAll('.site-tab');
      tabs.forEach(t => {{
        if (t.innerText.trim() === domain) {{
          t.classList.add('active');
        }} else {{
          t.classList.remove('active');
        }}
      }});

      // Update Chart
      const ctx = document.getElementById('siteChart');
      if (ctx && window.Chart) {{
        const labels = keywords.map(k => k.keyword);
        const counts = keywords.map(k => k.count);

        if (siteChart) {{
          siteChart.destroy();
        }}

        siteChart = new Chart(ctx, {{
          type: 'bar',
          data: {{
            labels: labels,
            datasets: [{{
              label: 'Occurrences in ' + domain,
              data: counts,
              backgroundColor: 'rgba(129, 140, 248, 0.75)',
              borderColor: '#818cf8',
              borderWidth: 1,
              borderRadius: 6
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {{
              legend: {{
                labels: {{ color: '#94a3b8', font: {{ size: 12 }} }}
              }}
            }},
            scales: {{
              x: {{
                ticks: {{ color: '#94a3b8' }},
                grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}
              }},
              y: {{
                ticks: {{ color: '#cbd5e1', font: {{ size: 11 }} }},
                grid: {{ display: false }}
              }}
            }}
          }}
        }});
      }}

      // Update Table Body
      const tbody = document.getElementById('siteTableBody');
      if (tbody) {{
        tbody.innerHTML = '';
        keywords.forEach((k, idx) => {{
          const tr = document.createElement('tr');
          const rankClass = idx === 0 ? 'rank-1' : (idx === 1 ? 'rank-2' : (idx === 2 ? 'rank-3' : ''));
          tr.innerHTML = `
            <td><span class="rank-badge ${{rankClass}}">${{idx + 1}}</span></td>
            <td><b style="color:var(--text-main)">${{escapeHtml(k.keyword)}}</b></td>
            <td><span style="color:var(--text-muted); font-size:12px;">${{k.word_type}}</span></td>
            <td><b>${{k.count}}</b> hits</td>
            <td>${{k.density_pct}}%</td>
          `;
          tbody.appendChild(tr);
        }});
      }}
    }}

    function selectSite(domain) {{
      updateSiteView(domain);
    }}

    function escapeHtml(text) {{
      const div = document.createElement('div');
      div.innerText = text;
      return div.innerHTML;
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      initCrossChart();
      if (DOMAINS.length > 0) {{
        updateSiteView(DOMAINS[0]);
      }}
    }});
  </script>
</body>
</html>
"""
