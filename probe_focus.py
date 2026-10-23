#!/usr/bin/env python3
"""Focused probe: BringFido DOM structure + Google Maps tbm=map JSON."""
import time, json, re
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

def gmaps_direct():
    url = "https://www.google.com/search?tbm=map&hl=en&gl=us&q=pet+services+in+92694"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        body = page.evaluate("() => document.body.innerText")
        b.close()
    print("GMAPS direct body len:", len(body))
    print(body[:1500])
    open("/tmp/gmap_direct.txt", "w").write(body)

def bringfido_dom():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(user_agent=UA, locale="en-US", viewport={"width": 1440, "height": 900})
        resp = page.goto("https://www.bringfido.com/service/?location=92694",
                         wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        # Dump interesting elements
        info = page.evaluate("""() => {
            const out = {};
            const anchors = [...document.querySelectorAll('a')].map(a => a.getAttribute('href')).filter(Boolean);
            out.uniqueHrefPatterns = [...new Set(anchors.map(h => h.split('?')[0].replace(/\\d+/g,'#')))].slice(0,40);
            out.anchorCount = anchors.length;
            out.bodyText = document.body.innerText.slice(0, 1500);
            const imgs = [...document.querySelectorAll('img')].map(i => i.src).filter(s => s.includes('photos.bringfido')).slice(0,5);
            out.imgs = imgs;
            return out;
        }""")
        b.close()
    print("BF anchors:", info["anchorCount"])
    print("BF href patterns:", info["uniqueHrefPatterns"])
    print("BF body:", info["bodyText"][:800].replace("\n", " | "))

gmaps_direct()
bringfido_dom()
