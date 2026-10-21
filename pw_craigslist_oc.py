#!/usr/bin/env python3
"""Craigslist OC pet-service collector — works with plain HTML.
Run: source venv/bin/activate && python pw_craigslist_oc.py
Output: data/craigslist_oc.tsv → merge with build_catalog.py --mode upsert"""
import urllib.request, csv, re, time
from pathlib import Path

OUT = Path("data/craigslist_oc.tsv")
URL = "https://oc.craigslist.org/search/sss?query=dog+walking&zip=92694"

with urllib.request.urlopen(URL, timeout=15) as resp:
    html = resp.read().decode('utf-8', 'ignore')

results = re.findall(
    r'<li[^>]*class="cl-static-search-result"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>.*?<div[^>]*class="title"[^>]*>([^<]+)</div>.*?<div[^>]*class="price"[^>]*>\$([^<]+)</div>.*?<div[^>]*class="location"[^>]*>([^<]+)</div>',
    html, re.DOTALL)

rows = []
for url_link, title, price, loc in results[:30]:
    # Clean location (strip extra whitespace, take first part)
    city = loc.split(',')[0].strip() if ',' in loc else loc.strip()
    if not city: city = "Orange County"
    rows.append({
        "listing_id": f"craigslist-{url_link.split('/')[-1] or 'oc'}",
        "source": "Craigslist",
        "provider_name": title[:60].strip(),
        "zip_code": "92694",
        "city": city,
        "state": "CA",
        "service_type": "Dog Walking",
        "description": f"Listed on Craigslist: {title[:100]}",
        "price_usd": price.replace(",",""),
        "price_unit": "visit",
        "rating": "0",
        "review_count": "0",
        "profile_url": "https://www.craigslist.org" + url_link if url_link.startswith('/') else url_link,
    })

with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "listing_id","source","provider_name","zip_code","city","state",
        "service_type","description","price_usd","price_unit","rating","review_count","profile_url"
    ], delimiter="\t")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"Wrote {len(rows)} Craigslist OC listings to {OUT}")
print("Merge: python build_catalog.py --input data/craigslist_oc.tsv --output data/pet_services.parquet --mode upsert")
