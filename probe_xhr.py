#!/usr/bin/env python3
"""Probe XHR/JSON endpoints used by BringFido and Google Maps."""
import time, json
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

def probe(url, label, keyword_filter=("service", "listing", "business", "place", "result", "search")):
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if not any(k in resp.url.lower() for k in keyword_filter):
                    return
                body = resp.text()
                if len(body) < 200:
                    return
                captured.append((resp.url[:160], len(body), body[:1500]))
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(6)
        try:
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(2)
        except Exception:
            pass
        browser.close()

    print(f"\n===== {label} =====")
    print(f"captured {len(captured)} json responses")
    for u, n, b in captured[:6]:
        print(f"--- {u} ({n} bytes)")
        print("   ", b[:400].replace("\n", " "))

probe("https://www.bringfido.com/service/?location=92694", "BRINGFIDO")
probe("https://www.google.com/maps/search/pet+services+in+92694", "GOOGLE MAPS")
