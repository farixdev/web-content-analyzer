# -*- coding: utf-8 -*-
"""
Dual Database Client for Web Content Analyzer (Neon PostgreSQL & Local SQLite).

1. Cloud / Production: Connects to Neon Cloud PostgreSQL when configured.
2. Local / Offline (.exe / Standalone): Automatically creates a local `data/`
   folder with `web_analyzer.db` SQLite database when Neon DB is unreachable,
   offline, or when USE_LOCAL_DB=1 is set.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

import config

config.load_env()

DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_UrC49mziheJL@ep-plain-rain-b4q8d8ub-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)


def get_data_dir():
    """Ensure and return the persistent local data directory."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        # Fallback to user home directory if running from read-only location
        data_dir = os.path.join(os.path.expanduser("~"), ".web_content_analyzer")
        os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_sqlite_path():
    """Return the absolute path to the local SQLite database file."""
    return os.path.join(get_data_dir(), "web_analyzer.db")


def get_sqlite_conn():
    """Create a connection to the local SQLite database with Row mapping."""
    db_path = get_sqlite_path()
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _is_local_forced():
    """Check if the environment explicitly forces local SQLite mode."""
    val = os.environ.get("USE_LOCAL_DB", "").strip().lower()
    return val in ("1", "true", "yes", "sqlite")


def is_postgres_configured(db_url=None):
    """Check if PostgreSQL credentials and driver are available."""
    if _is_local_forced():
        return False
    if not HAS_PSYCOPG2:
        return False
    url = (db_url or os.environ.get("DATABASE_URL") or DEFAULT_DB_URL).strip()
    return bool(url and url.startswith("postgres"))


def get_pg_connection(db_url=None):
    """Create a psycopg2 connection to Neon PostgreSQL."""
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is not installed.")
    url = (db_url or os.environ.get("DATABASE_URL") or DEFAULT_DB_URL).strip()
    return psycopg2.connect(url, connect_timeout=8)


# ----------------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------------

def init_db(db_url=None):
    """Create necessary database tables in Neon PostgreSQL or local SQLite."""
    # 1. Try PostgreSQL if configured
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS search_analyses (
                        id SERIAL PRIMARY KEY,
                        query TEXT NOT NULL,
                        country TEXT DEFAULT 'United States',
                        engine TEXT,
                        num_competitors INTEGER DEFAULT 5,
                        pages_per_site INTEGER DEFAULT 1,
                        people_also_search JSONB DEFAULT '[]'::jsonb,
                        image_refinements JSONB DEFAULT '[]'::jsonb,
                        forum_insights JSONB DEFAULT '[]'::jsonb,
                        matrix JSONB DEFAULT '{}'::jsonb,
                        results JSONB DEFAULT '[]'::jsonb,
                        raw_summary JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS content_comparisons (
                        id SERIAL PRIMARY KEY,
                        analysis_id INTEGER REFERENCES search_analyses(id) ON DELETE SET NULL,
                        query TEXT,
                        doc_name TEXT,
                        word_count INTEGER,
                        comparison_data JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_search_analyses_created ON search_analyses(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_content_comparisons_created ON content_comparisons(created_at DESC);
                """)
            conn.commit()
            conn.close()
            return True, "Neon PostgreSQL initialized successfully."
        except Exception as e:
            print(f"[DB Notice] Could not connect to Neon PostgreSQL ({e}). Falling back to local SQLite.")

    # 2. Local SQLite Fallback
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS search_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                country TEXT DEFAULT 'United States',
                engine TEXT,
                num_competitors INTEGER DEFAULT 5,
                pages_per_site INTEGER DEFAULT 1,
                people_also_search TEXT DEFAULT '[]',
                image_refinements TEXT DEFAULT '[]',
                forum_insights TEXT DEFAULT '[]',
                matrix TEXT DEFAULT '{}',
                results TEXT DEFAULT '[]',
                raw_summary TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS content_comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER,
                query TEXT,
                doc_name TEXT,
                word_count INTEGER,
                comparison_data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_search_analyses_created ON search_analyses(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_content_comparisons_created ON content_comparisons(created_at DESC);
        """)
        conn.commit()
        conn.close()
        return True, f"Local SQLite database initialized at {get_sqlite_path()}."
    except Exception as e:
        return False, str(e)


# ----------------------------------------------------------------------------
# Search Analyses CRUD
# ----------------------------------------------------------------------------

def save_analysis(payload, db_url=None):
    """Save search analysis into Neon PostgreSQL or local SQLite."""
    query = payload.get("query", "")
    country = payload.get("country", "United States")
    engine = payload.get("engine", "google")
    num_competitors = len(payload.get("competitors_data", []))
    pages_per_site = payload.get("pages_per_site", 1)
    people_also_search = json.dumps(payload.get("people_also_search", []))
    image_refinements = json.dumps(payload.get("image_refinements", []))
    forum_insights = json.dumps(payload.get("forum_insights", []))
    matrix = json.dumps(payload.get("matrix", {}))
    results = json.dumps(payload.get("results", []))
    raw_summary = json.dumps({
        "unique_domains": payload.get("unique_domains", 0),
        "competitors_crawled": payload.get("competitors_crawled", num_competitors),
        "suggestions": payload.get("suggestions", []),
        "top_domains": payload.get("top_domains", []),
    })

    # 1. Try PostgreSQL
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO search_analyses (
                        query, country, engine, num_competitors, pages_per_site,
                        people_also_search, image_refinements, forum_insights,
                        matrix, results, raw_summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    query, country, engine, num_competitors, pages_per_site,
                    people_also_search, image_refinements, forum_insights,
                    matrix, results, raw_summary
                ))
                row = cur.fetchone()
                analysis_id = row[0] if row else None
            conn.commit()
            conn.close()
            return analysis_id
        except Exception as e:
            print("[DB Notice save_analysis PG failed]:", e)

    # 2. Local SQLite Fallback
    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO search_analyses (
                query, country, engine, num_competitors, pages_per_site,
                people_also_search, image_refinements, forum_insights,
                matrix, results, raw_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            query, country, engine, num_competitors, pages_per_site,
            people_also_search, image_refinements, forum_insights,
            matrix, results, raw_summary
        ))
        analysis_id = cur.lastrowid
        conn.commit()
        conn.close()
        return analysis_id
    except Exception as e:
        print("[DB Error save_analysis SQLite]:", e)
        return None


def list_analyses(limit=25, db_url=None):
    """List recent search analyses from Neon PostgreSQL or local SQLite."""
    # 1. Try PostgreSQL
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, query, country, engine, num_competitors, pages_per_site,
                           jsonb_array_length(COALESCE(people_also_search, '[]'::jsonb)) as pasf_count,
                           jsonb_array_length(COALESCE(image_refinements, '[]'::jsonb)) as img_count,
                           created_at
                    FROM search_analyses
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
            conn.close()
            out = []
            for r in rows:
                item = dict(r)
                if item.get("created_at"):
                    item["created_at"] = str(item["created_at"])[:19]
                item["competitors_count"] = item.get("num_competitors", 5)
                out.append(item)
            return out
        except Exception as e:
            print("[DB Notice list_analyses PG failed]:", e)

    # 2. Local SQLite Fallback
    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, query, country, engine, num_competitors, pages_per_site,
                   people_also_search, image_refinements, created_at
            FROM search_analyses
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
        out = []
        for r in rows:
            pasf_count = len(json.loads(r["people_also_search"] or "[]"))
            img_count = len(json.loads(r["image_refinements"] or "[]"))
            out.append({
                "id": r["id"],
                "query": r["query"],
                "country": r["country"],
                "engine": r["engine"],
                "competitors_count": r["num_competitors"],
                "num_competitors": r["num_competitors"],
                "pages_per_site": r["pages_per_site"],
                "pasf_count": pasf_count,
                "img_count": img_count,
                "created_at": str(r["created_at"])[:19]
            })
        return out
    except Exception as e:
        print("[DB Error list_analyses SQLite]:", e)
        return []


def get_analysis(analysis_id, db_url=None):
    """Retrieve full analysis by ID from Neon PostgreSQL or local SQLite."""
    # 1. Try PostgreSQL
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_analyses WHERE id = %s;", (analysis_id,))
                row = cur.fetchone()
            conn.close()
            if row:
                res = dict(row)
                if res.get("created_at"):
                    res["created_at"] = str(res["created_at"])[:19]
                return res
        except Exception as e:
            print("[DB Notice get_analysis PG failed]:", e)

    # 2. Local SQLite Fallback
    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM search_analyses WHERE id = ?;", (analysis_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        res = dict(row)
        for json_col in ("people_also_search", "image_refinements", "forum_insights", "matrix", "results", "raw_summary"):
            try:
                res[json_col] = json.loads(res.get(json_col) or "{}")
            except Exception:
                pass
        return res
    except Exception as e:
        print("[DB Error get_analysis SQLite]:", e)
        return None


# ----------------------------------------------------------------------------
# Content Comparisons CRUD
# ----------------------------------------------------------------------------

def save_comparison(payload, db_url=None):
    """Save content comparison into Neon PostgreSQL or local SQLite."""
    analysis_id = payload.get("analysis_id")
    query = payload.get("query", "")
    doc_name = payload.get("doc_name", "Uploaded Document")
    word_count = payload.get("word_count", 0)
    comparison_data = json.dumps(payload.get("comparison_data", {}))

    # 1. Try PostgreSQL
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO content_comparisons (
                        analysis_id, query, doc_name, word_count, comparison_data
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                """, (analysis_id, query, doc_name, word_count, comparison_data))
                row = cur.fetchone()
                comp_id = row[0] if row else None
            conn.commit()
            conn.close()
            return comp_id
        except Exception as e:
            print("[DB Notice save_comparison PG failed]:", e)

    # 2. Local SQLite Fallback
    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO content_comparisons (
                analysis_id, query, doc_name, word_count, comparison_data
            ) VALUES (?, ?, ?, ?, ?);
        """, (analysis_id, query, doc_name, word_count, comparison_data))
        comp_id = cur.lastrowid
        conn.commit()
        conn.close()
        return comp_id
    except Exception as e:
        print("[DB Error save_comparison SQLite]:", e)
        return None


def list_comparisons(limit=25, db_url=None):
    """List recent content comparisons from Neon PostgreSQL or local SQLite."""
    # 1. Try PostgreSQL
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, analysis_id, query, doc_name, word_count, comparison_data, created_at
                    FROM content_comparisons
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
            conn.close()
            out = []
            for r in rows:
                item = dict(r)
                comp = item.get("comparison_data") or {}
                if isinstance(comp, str):
                    try: comp = json.loads(comp)
                    except Exception: comp = {}
                out.append({
                    "id": item["id"],
                    "title": item.get("doc_name") or "Document",
                    "source_type": ".docx Upload" if (item.get("doc_name") or "").endswith(".docx") else "Pasted Text",
                    "word_count": item.get("word_count", 0),
                    "optimization_score": comp.get("optimization_score", 0),
                    "missing_keywords_count": len(comp.get("content_gaps") or comp.get("missing_opportunities") or []),
                    "created_at": str(item.get("created_at"))[:19]
                })
            return out
        except Exception as e:
            print("[DB Notice list_comparisons PG failed]:", e)

    # 2. Local SQLite Fallback
    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, analysis_id, query, doc_name, word_count, comparison_data, created_at
            FROM content_comparisons
            ORDER BY id DESC
            LIMIT ?;
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
        out = []
        for r in rows:
            comp = {}
            try:
                comp = json.loads(r["comparison_data"] or "{}")
            except Exception:
                pass
            out.append({
                "id": r["id"],
                "title": r["doc_name"] or "Document",
                "source_type": ".docx Upload" if (r["doc_name"] or "").endswith(".docx") else "Pasted Text",
                "word_count": r["word_count"] or 0,
                "optimization_score": comp.get("optimization_score", 0),
                "missing_keywords_count": len(comp.get("content_gaps") or comp.get("missing_opportunities") or []),
                "created_at": str(r["created_at"])[:19]
            })
        return out
    except Exception as e:
        print("[DB Error list_comparisons SQLite]:", e)
        return []


def get_comparison(comparison_id, db_url=None):
    """Retrieve full comparison by ID."""
    if is_postgres_configured(db_url):
        try:
            conn = get_pg_connection(db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM content_comparisons WHERE id = %s;", (comparison_id,))
                row = cur.fetchone()
            conn.close()
            if row:
                res = dict(row)
                if res.get("created_at"):
                    res["created_at"] = str(res["created_at"])[:19]
                return res
        except Exception as e:
            print("[DB Notice get_comparison PG failed]:", e)

    try:
        init_db()
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM content_comparisons WHERE id = ?;", (comparison_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        res = dict(row)
        try:
            res["comparison_data"] = json.loads(res.get("comparison_data") or "{}")
        except Exception:
            pass
        return res
    except Exception as e:
        print("[DB Error get_comparison SQLite]:", e)
        return None
