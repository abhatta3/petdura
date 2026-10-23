#!/usr/bin/env python3
"""Quick probe of new multi-source URLs for parser development."""
import time, re, html
from pathlib import Path
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

SOURCES = {
    "yelp": ("https://www.yelp.com/search?find_desc={service}&find_loc={zip}", "Yelp"),
    "bringfido": ("https://www.bringfido.com/service/?location={zip}", "BringFido"),
    "gmap": ("https://www.google.com/maps/search/pet+services+in+{zip}", "GoogleMaps"),
    "yellowpages": ("https://www.yellowpages.com/search?search_terms={service}&geo_location_terms={zip}", "YellowPages"),
}

def probe(source_key, service_slug="dog+walking", zip_code="92694"):
    url_tmpl, label = SOURCES[source_key]
    # For Yelp / YellowPages use service slug; for BringFido / GMap generic
    url = url_tmpl.format(service=service_slug.replace(" ", "+"), zip=zip_code)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 900})
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            html_text = page.content()[:4000]
        except Exception as e:
            html_text = f"ERROR: {e}"
        finally:
            browser.close()
    # Save snippet
    out = Path(f"/tmp/probe_{source_key}.html")
    out.write_text(html_text, encoding="utf-8")
    # Show snippet around first business/name pattern
    snippet = html_text[:1200]
    print(f"\n=== {label} (URL: {url[:100]}...) ===")
    print("Snippet (first 700 chars):")
    print(snippet[:700])
    return html_text

if __name__ == "__main__":
    # Probe Yelp with generic pet sitting (works for any ZIP demo)
    probe("yelp", service_slug="pet+sitting", zip_code="92694")
    probe("bringfido", zip_code="92694")
    probe("gmap", zip_code="92694")
    probe("yellowpages", service_slug="dog+walking", zip_code="92694")
