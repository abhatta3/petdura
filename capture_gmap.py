#!/usr/bin/env python3
"""Capture one Google Maps tbm=map payload to /tmp for offline parser work."""
import time
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

captured = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    def on_resp(r):
        try:
            if "tbm=map" in r.url:
                captured.append(r.text())
        except Exception:
            pass

    page.on("response", on_resp)
    page.goto("https://www.google.com/maps/search/pet+services+in+92694",
              wait_until="domcontentloaded", timeout=45000)
    time.sleep(8)
    try:
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(3)
    except Exception:
        pass
    b.close()

if captured:
    open("/tmp/gmap_payload.txt", "w").write(captured[0])
    print("saved", len(captured[0]), "bytes")
else:
    print("nothing captured")
