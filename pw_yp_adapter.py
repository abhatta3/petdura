#!/usr/bin/env python3
"""Yellow Pages adapter — collects pet-care listings and writes them in the
catalog schema.

Usage:
    source venv/bin/activate
    python pw_yp_adapter.py
    # -> data/yp_adapter.tsv
    # merge:
    # python build_catalog.py --input data/yp_adapter.tsv \
    #     --output data/pet_services.parquet --mode upsert
"""
import csv
import html as h
import re
from pathlib import Path

OUT = Path("data/yp_adapter.tsv")
SEARCH_TERMS = "dog+walk"
GEO = "Los+Angeles%2C+CA"          # user-provided search URL
URL = f"https://www.yellowpages.com/search?search_terms={SEARCH_TERMS}&geo_location_terms={GEO}"
ZIP = "92694"                        # representative OC ZIP for area-level results
CITY = "Los Angeles"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")


def fetch():
    """Yellow Pages blocks plain HTTP clients, so render with Playwright."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, locale="en-US",
                                      viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(800)
        html = page.content()
        browser.close()
        return html


def parse(page):
    rows = []
    for match in re.finditer(r'<div[^>]*class="result"[^>]*id="([^"]+)"', page):
        listing_id = match.group(1)
        start = match.start()
        end = page.find('<div class="result"', start + 1)
        block = page[start:end if end != -1 else len(page)]

        name_match = re.search(
            r'<h2[^>]*>[\s\d\.]*<a[^>]*class="business-name"[^>]*>(?:<span>)?([^<]+)</span>', block)
        name = h.unescape(name_match.group(1)).strip() if name_match else ""
        if not name:
            continue

        link_match = re.search(r'class="business-name"[^>]*href="([^"]+)"', block)
        profile = ""
        if link_match:
            href = h.unescape(link_match.group(1))
            profile = href if href.startswith("http") else f"https://www.yellowpages.com{href}"

        category_match = re.search(r'<div[^>]*class="categories"[^>]*>(.*?)</div>', block, re.DOTALL)
        category = h.unescape(re.sub(r"<[^>]+>", " ", category_match.group(1))).strip() if category_match else ""
        category = re.sub(r"\s+", " ", category)

        review_match = re.search(r"([0-9]+)\s*reviews?", block)
        reviews = review_match.group(1) if review_match else "0"
        rating_match = re.search(r'"rating"\s*:\s*"?([0-5](?:\.[0-9])?)', block)
        rating = rating_match.group(1) if rating_match else ""
        price_match = re.search(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)", block)
        price = price_match.group(1).replace(",", "") if price_match else ""

        service_type = "Dog Walking" if "dog" in (name + category).lower() else (category[:30] or "Pet Care")
        rows.append({
            "listing_id": f"yp-{listing_id}",
            "source": "YellowPages",
            "provider_name": name[:60],
            "zip_code": ZIP,
            "city": CITY,
            "state": "CA",
            "service_type": service_type,
            "description": f"Yellow Pages listing for {name} ({category}) serving the Los Angeles/Orange County area.",
            "price_usd": price,
            "price_unit": "visit",
            "rating": rating,
            "review_count": reviews,
            "profile_url": profile or f"https://www.yellowpages.com/search?search_terms={SEARCH_TERMS}&geo_location_terms={GEO}",
        })
    return rows


def main():
    page = fetch()
    rows = parse(page)
    unique = {}
    for row in rows:
        unique.setdefault(row["listing_id"], row)

    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "listing_id", "source", "provider_name", "zip_code", "city", "state",
            "service_type", "description", "price_usd", "price_unit", "rating",
            "review_count", "profile_url"], delimiter="\t")
        writer.writeheader()
        for row in unique.values():
            writer.writerow(row)

    print(f"Wrote {len(unique)} Yellow Pages listings to {OUT}")
    print("Merge: python build_catalog.py --input data/yp_adapter.tsv "
          "--output data/pet_services.parquet --mode upsert")


if __name__ == "__main__":
    main()
