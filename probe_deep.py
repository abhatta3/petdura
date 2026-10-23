#!/usr/bin/env python3
"""Deep probe: BringFido DOM + Google Maps tbm=map payload structure."""
import time, json, re
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0.1 Safari/605.1.15")

def bringfido():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        page.goto("https://www.bringfido.com/service/?location=92694",
                  wait_until="networkidle", timeout=60000)
        time.sleep(5)
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 1200)")
            time.sleep(1200)
        html = page.content()
        open("/tmp/bf_full.html", "w").write(html)
        # Look for anchor patterns
        links = page.eval_on_selector_all(
            "a[href*='/service/'], a[href*='/business/'], a[href*='/provider/']",
            "els => els.slice(0,15).map(e => e.getAttribute('href'))")
        print("BringFido candidate links:", links[:10])
        for cls in ["business-card", "listing", "service-card", "card", "provider", "business"]:
            n = page.eval_on_selector_all(f".{cls}", "els => els.length")
            if n:
                print(f"  .{cls} -> {n}")
        txt = page.inner_text("body")[:600]
        print("BODY TEXT:", txt.replace("\n", " | ")[:600])
        b.close()

def gmaps():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()
        payloads = []
        def on_resp(r):
            try:
                if "tbm=map" in r.url and "json" in r.headers.get("content-type", ""):
                    payloads.append(r.text())
            except Exception:
                pass
        page.on("response", on_resp)
        page.goto("https://www.google.com/maps/search/pet+services+in+92694",
                  wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        b.close()
    if not payloads:
        print("GMAPS: no payload")
        return
    raw = payloads[0]
    open("/tmp/gmap_payload.txt", "w").write(raw)
    print("GMAPS payload len:", len(raw))
    body = raw.split("\n", 1)[-1]
    try:
        data = json.loads(body)
    except Exception as e:
        print("parse fail:", e); return
    print("top-level type:", type(data), "len:", len(data))
    # Business entries usually live in data[0][1] / data[3]
    def walk(obj, depth=0, path=""):
        """Find dicts that look like places."""
        if isinstance(obj, list):
            for i, v in enumerate(obj[:60]):
                walk(v, depth+1, f"{path}[{i}]")
        elif isinstance(obj, dict):
            if "name" in obj and isinstance(obj.get("name"), str):
                print("PLACE at", path, {k: obj[k] for k in list(obj)[:8] if not isinstance(obj[k], (list, dict))})
            for k, v in list(obj.items())[:25]:
                walk(v, depth+1, f"{path}.{k}")
    walk(data)

bringfido()
gmaps()
