# -*- coding: utf-8 -*-
"""
Web Content Analyzer - Local Modern Web Application Server.

Provides a 100% reliable, zero-DLL, zero-crash web UI in your default browser.
Supports 100% free organic search (no Serper API key needed) as well as optional Serper.
"""

import os
import sys
import json
import time
import socket
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import csv
import config
import search
import dashboard_renderer
import docx_generator

# Global In-Memory State
STATE_LOCK = threading.Lock()
state = {
    "status": "idle",       # "idle", "running", "complete", "error"
    "progress": 0,
    "step": "Ready",
    "logs": ["[System] Web Content Analyzer is ready. Free search mode active."],
    "error": None,
    "results": None,
    "dashboard_html": "",
    "report_md": "",
    "docx_path": "report.docx",
    "csv_path": "report.csv",
}


def save_csv_report(results, output_path="report.csv"):
    """Export Dominance Matrix and Competitor Keywords to a clean CSV."""
    matrix = results.get("matrix", {})
    cross_terms = matrix.get("cross_site_terms", matrix.get("cross_site_keywords", []))
    competitors = results.get("competitors_data", [])

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["=== CROSS-COMPETITOR KEYWORD DOMINANCE MATRIX ==="])
        writer.writerow(["Rank", "Keyword", "Domain Overlap", "Total Frequency", "Per Domain Breakdown"])
        for idx, t in enumerate(cross_terms, start=1):
            bd = t.get("per_domain", t.get("breakdown", {}))
            bd_str = " | ".join(f"{d}: {c}" for d, c in bd.items() if c > 0)
            writer.writerow([
                idx,
                t.get("keyword", ""),
                f"{t.get('domain_presence', t.get('used_by_count', 0))} / {len(competitors)}",
                t.get("total_occurrences", t.get("total_count", 0)),
                bd_str
            ])
        writer.writerow([])
        writer.writerow(["=== PER-COMPETITOR TOP 20 KEYWORDS ==="])
        for c in competitors:
            writer.writerow([f"Domain: {c.get('domain')}", f"Pages Scraped: {c.get('pages_scraped')}", f"Total Words: {c.get('total_words')}"])
            writer.writerow(["Rank", "Keyword", "Count", "Density %"])
            for idx, kw in enumerate(c.get("top_keywords", []), start=1):
                writer.writerow([idx, kw.get("keyword"), kw.get("count"), f"{kw.get('density_pct')}%"])
            writer.writerow([])
    return output_path


def update_state(**kwargs):
    with STATE_LOCK:
        for k, v in kwargs.items():
            state[k] = v


def append_log(message):
    with STATE_LOCK:
        state["logs"].append(message)
        # Cap log history to latest 300 entries
        if len(state["logs"]) > 300:
            state["logs"] = state["logs"][-300:]


def run_analysis_worker(params):
    """Background worker for competitor search, deep crawling, and matrix synthesis."""
    try:
        update_state(
            status="running",
            progress=5,
            step="Initializing competitor discovery...",
            logs=["[System] Starting analysis for '%s' in %s..." % (params["query"], params["country"])],
            error=None,
            results=None,
        )

        def progress_callback(msg):
            append_log(msg)
            # Dynamic progress inference
            lower = msg.lower()
            if "suggestion" in lower:
                update_state(progress=12, step="Scraping Google Autocomplete suggestions...")
            elif "searching" in lower or "direct" in lower or "bing" in lower or "serper" in lower:
                update_state(progress=22, step="Filtering organic competitor SERPs...")
            elif "deep-crawling" in lower:
                # e.g., "[1/3] Deep-crawling fbi.gov (up to 25 pages)..."
                update_state(step=msg.split("...")[-2] if "..." in msg else msg)
                # Compute approximate progress between 25% and 80%
                try:
                    if "[" in msg and "/" in msg and "]" in msg:
                        part = msg.split("[")[1].split("]")[0]
                        curr, tot = part.split("/")
                        pct = 25 + int((int(curr) / max(1, int(tot))) * 55)
                        update_state(progress=min(pct, 80))
                except Exception:
                    pass
            elif "keyword matrix" in lower or "synthesizing" in lower:
                update_state(progress=86, step="Synthesizing Top 20 keywords & dominance matrix...")
            elif "dashboard" in lower or "charts" in lower:
                update_state(progress=94, step="Compiling interactive visual dashboard...")

        # Load environment variables (.env) if present
        config.load_env()
        serper_key = (params.get("serper_key") or os.environ.get("SERPER_API_KEY", "")).strip()
        custom_stopwords = params.get("custom_stopwords", "")
        ngram_filter = params.get("ngram_filter", "all")
        max_workers = int(params.get("max_workers", 8))

        # Run Deep Crawl Orchestrator
        results = search.search_and_deep_crawl(
            query=params["query"],
            country=params.get("country", "United States"),
            num_results=params.get("num_results", 15),
            pages_per_site=params.get("pages_per_site", 25),
            max_competitors=params.get("max_competitors", 5),
            proxy=params.get("proxy") or None,
            serper_key=serper_key,
            progress=progress_callback,
            custom_stopwords=custom_stopwords,
            ngram_filter=ngram_filter,
            max_workers=max_workers,
        )

        # Generate Export Files
        progress_callback("Rendering standalone export dashboard...")
        dashboard_payload = {
            "query": results["query"],
            "country": results["country"],
            "suggestions": results.get("suggestions", []),
            "competitors_data": results.get("competitors_data", []),
            "matrix": results.get("matrix", {}),
            "serp_results": results.get("serp_results", []),
        }
        dash_html = dashboard_renderer.render_dashboard_html(dashboard_payload)
        rep_md = search.to_markdown(results)

        # Save to disk as convenience
        try:
            with open("dashboard.html", "w", encoding="utf-8") as f:
                f.write(dash_html)
            with open("report.md", "w", encoding="utf-8") as f:
                f.write(rep_md)
        except Exception as e:
            progress_callback("Warning: could not save files to disk: %s" % e)

        # Generate Word Document (.docx) Report
        try:
            progress_callback("Compiling publication-grade Word Report with charts (.docx)...")
            docx_path = docx_generator.generate_docx_report(results, "report.docx")
            update_state(docx_path=docx_path)
            progress_callback("Word document (.docx) ready for download.")
        except Exception as e:
            progress_callback("Notice: Word doc generation error: %s" % e)

        # Generate CSV Spreadsheet Report
        try:
            csv_path = save_csv_report(results, "report.csv")
            update_state(csv_path=csv_path)
        except Exception as e:
            pass

        update_state(
            status="complete",
            progress=100,
            step="Analysis completed successfully!",
            results=results,
            dashboard_html=dash_html,
            report_md=rep_md,
        )
        append_log("[System] Analysis complete! All reports (HTML, Word DOCX, Markdown, CSV) ready.")

    except Exception as e:
        err_msg = str(e)
        update_state(
            status="error",
            progress=0,
            step="Error encountered during analysis.",
            error=err_msg,
        )
        append_log("[ERROR] %s" % err_msg)


class WebAppHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for the Web Content Analyzer single-page web app."""

    def log_message(self, fmt, *args):
        # Suppress noisy standard HTTP access logs in console
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. Main Application Dashboard
        if path == "/" or path == "/index.html":
            template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
            if not os.path.isfile(template_path):
                self.send_error(404, "templates/index.html not found")
                return
            with open(template_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. Local Assets (e.g. chart.umd.min.js)
        if path.startswith("/assets/"):
            filename = os.path.basename(path)
            asset_path = os.path.join(os.path.dirname(__file__), "assets", filename)
            if os.path.isfile(asset_path):
                with open(asset_path, "rb") as f:
                    content = f.read()
                mime = "application/javascript" if filename.endswith(".js") else "text/plain"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(404, "Asset not found")
            return

        # 3. API: Polling Crawl Progress
        if path == "/api/progress":
            with STATE_LOCK:
                data = {
                    "status": state["status"],
                    "progress": state["progress"],
                    "step": state["step"],
                    "logs": state["logs"][-60:],  # return latest 60 lines
                    "error": state["error"],
                }
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4. API: Get Completed Results
        if path == "/api/results":
            with STATE_LOCK:
                data = state["results"] or {}
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 5. Export: Download Standalone HTML Dashboard
        if path == "/api/export/html":
            with STATE_LOCK:
                html_content = state["dashboard_html"]
            if not html_content and os.path.isfile("dashboard.html"):
                with open("dashboard.html", "r", encoding="utf-8") as f:
                    html_content = f.read()
            data = (html_content or "<h1>No analysis run yet</h1>").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="dashboard.html"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # 6. Export: Download Markdown Report
        if path == "/api/export/md":
            with STATE_LOCK:
                md_content = state["report_md"]
            if not md_content and os.path.isfile("report.md"):
                with open("report.md", "r", encoding="utf-8") as f:
                    md_content = f.read()
            data = (md_content or "# No analysis run yet\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="report.md"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # 7. Export: Download Word Document Report (.docx) with embedded charts
        if path == "/api/export/docx":
            docx_path = "report.docx"
            if not os.path.isfile(docx_path) and state.get("results"):
                try:
                    docx_generator.generate_docx_report(state["results"], docx_path)
                except Exception:
                    pass
            if os.path.isfile(docx_path):
                with open(docx_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                self.send_header("Content-Disposition", 'attachment; filename="competitor_intelligence_report.docx"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "No Word document report available. Run an analysis first.")
            return

        # 8. Export: Download CSV Spreadsheet
        if path == "/api/export/csv":
            csv_path = "report.csv"
            if not os.path.isfile(csv_path) and state.get("results"):
                try:
                    save_csv_report(state["results"], csv_path)
                except Exception:
                    pass
            if os.path.isfile(csv_path):
                with open(csv_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="competitor_keywords.csv"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "No CSV report available. Run an analysis first.")
            return

        # 9. Export: High-Resolution Chart PNG Image
        if path == "/api/export/chart":
            results = state.get("results")
            if results:
                terms = results.get("matrix", {}).get("cross_site_terms", results.get("matrix", {}).get("cross_site_keywords", []))
                buf = docx_generator._generate_dominance_chart_image(terms, max_terms=20)
                if buf:
                    data = buf.getvalue()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Disposition", 'attachment; filename="keyword_dominance_chart.png"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_error(404, "Chart image could not be generated.")
            return

        self.send_error(404, "Page not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: Start Analysis
        if path == "/api/analyze":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                params = json.loads(body)
            except Exception:
                self.send_error(400, "Invalid JSON payload")
                return

            query = (params.get("query") or "").strip()
            if not query:
                self.send_error(400, "Query is required")
                return

            with STATE_LOCK:
                if state["status"] == "running":
                    self.send_response(409)
                    self.end_headers()
                    self.wfile.write(b'{"error": "An analysis is already in progress"}')
                    return

            # Start worker in separate thread
            worker_thread = threading.Thread(target=run_analysis_worker, args=(params,), daemon=True)
            worker_thread.start()

            resp = json.dumps({"ok": True, "message": "Analysis started"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_error(404, "Endpoint not found")


def find_free_port(start_port=5050):
    """Find a free TCP port to bind to."""
    port = start_port
    while port < start_port + 50:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            port += 1
    return start_port


def start_server(port=None, auto_open=None, host=None):
    """Start the Web Content Analyzer HTTP server and launch the browser."""
    # Detect cloud/container environment (Render, Hugging Face Spaces, Railway, Koyeb, etc.)
    env_port = os.environ.get("PORT")
    is_cloud = bool(env_port or os.environ.get("RENDER") or os.environ.get("SPACE_ID") or os.environ.get("DYNO"))

    if host is None:
        # In cloud environments, bind to 0.0.0.0 to accept external traffic
        host = "0.0.0.0" if is_cloud else "127.0.0.1"

    if port is None:
        if env_port:
            try:
                port = int(env_port)
            except ValueError:
                port = 5050
        else:
            port = find_free_port(5050)

    if auto_open is None:
        # Do not try to launch a desktop browser window on headless cloud servers
        auto_open = not is_cloud

    server = HTTPServer((host, port), WebAppHandler)
    display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    url = f"http://{display_host}:{port}"

    print("=" * 64)
    print("      MINDCOB WEB CONTENT ANALYZER - WEB DASHBOARD")
    print("=" * 64)
    print(f"[*] Server running on: {host}:{port}")
    print(f"[*] Access URL: {url}")
    print("[*] 100% Free Search Support: Serper API key is optional.")
    if auto_open:
        print("[*] Opening Web Dashboard in your default browser...")
    print("[*] Press Ctrl+C in this console to stop the server.")
    print("=" * 64)

    if auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Web Content Analyzer server...")
        server.server_close()


if __name__ == "__main__":
    start_server()

