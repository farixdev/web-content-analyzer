# -*- coding: utf-8 -*-
"""
Chrome Browser Session Scraper for Google Search and Competitor Pages.

Provides bot-detection bypass using:
1. Genuine Chrome browser instance via Selenium with persistent profile / user-data-dir
2. Optional curl_cffi Chrome-124 TLS/HTTP2 fingerprint impersonation
3. Proxy support for HTTP, HTTPS, and SOCKS5
"""

import os
import sys
import time
import re
from urllib.parse import urlparse, quote_plus
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


def _get_chrome_profile_dir():
    """Persistent directory for Chrome user profile to store solved CAPTCHAs and cookies."""
    app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    profile_dir = os.path.join(app_data, "WebAnalyzer_ChromeProfile")
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


def create_chrome_driver(headless=True, proxy=None):
    """Create a configured Chrome WebDriver with stealth flags."""
    if not HAS_SELENIUM:
        raise RuntimeError("Selenium is not installed.")

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Use persistent profile so cookies and solved challenges are retained
    profile_dir = _get_chrome_profile_dir()
    opts.add_argument(f"--user-data-dir={profile_dir}")

    # Configure proxy if supplied
    if proxy:
        proxy_clean = proxy.replace("socks5h://", "socks5://")
        opts.add_argument(f"--proxy-server={proxy_clean}")

    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=opts)
    # Hide navigator.webdriver
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })
    except Exception:
        pass

    return driver


def fetch_google_with_chrome(query, country_info, proxy=None, timeout=20):
    """Fetch Google Search page using Chrome session.
    
    Returns (html, current_url, is_captcha).
    """
    domain = country_info.get("domain", "www.google.com")
    gl = country_info.get("gl", "us")
    hl = country_info.get("hl", "en")
    url = f"https://{domain}/search?q={quote_plus(query)}&gl={gl}&hl={hl}&pws=0"

    driver = None
    try:
        driver = create_chrome_driver(headless=True, proxy=proxy)
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        time.sleep(1.8)

        html = driver.page_source
        is_captcha = "sorry/index" in driver.current_url or "recaptcha" in html.lower() or "unusual traffic" in html.lower()
        return html, driver.current_url, is_captcha
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_with_cffi(url, headers=None, proxy=None, timeout=15):
    """Fetch using curl_cffi with Chrome-124 browser TLS/JA3 impersonation."""
    if not HAS_CURL_CFFI:
        return None
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    try:
        resp = cffi_requests.get(
            url,
            headers=headers,
            proxies=proxies,
            impersonate="chrome124",
            timeout=timeout,
            verify=False
        )
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None
