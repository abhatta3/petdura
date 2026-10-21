#!/usr/bin/env python3
"""Yelp Fusion collector for Orange County ZIPs (free tier: 500/day).
Usage: YELP_API_KEY=<key> python pw_yelp_oc.py
Writes to data/yelp_oc.tsv then merges into parquet."""
import os, csv, urllib.request, json, time
from pathlib import Path

API_KEY = os.environ.get("YELP_API_KEY")
if not API_KEY:
    raise SystemExit("Set YELP_API_KEY env var (free at yelp.com/developers)")

OUT = Path("data/yelp_oc.tsv")
# OC ZIP codes from your catalog
ZIPS = ["92694","92101","90210","92602","92620","92782","92618","92656","92691","93710","95050","95814","93301","90703","91801"]
CAT = "petstand"  # pet services category

rows = []
for z in ZIPS:
    url = f"https://api.yelp.com/v3/businesses/search?location={z}&categories={CAT}&limit=50&radius=10000"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        for b in data.get("businesses", []):
            # Build listing in same schema
            rows.append({
                "listing_id": f"yelp-{b.get('id')}",
                "source": "Yelp",
                "provider_name": b.get("name",""),
                "zip_code": z,
                "city": b.get("location",{}).get("city","OC"),
                "state": b.get("location",{}).get("state_code","CA"),
                "service_type": "Pet Care",
                "description": b.get("categories",[{}])[0].get("title","Pet service") + "; " + (b.get("review_count",0) and f"{b.get('rating')}★") or "No rating",
                "price_usd": str(b.get("price","")) if b.get("price") else "0",
                "price_unit": "visit",
                "rating": str(b.get("rating","")) or "0",
                "review_count": str(b.get("review_count","")) or "0",
                "profile_url": b.get("url",""),
            })
        print(f"{z}: +{len(data.get('businesses',[]))}")
        time.sleep(0.5)
    except Exception as e:
        print(f"{z}: ERR {e}")

with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "listing_id","source","provider_name","zip_code","city","state",
        "service_type","description","price_usd","price_unit","rating","review_count","profile_url"
    ], delimiter="\t")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"Wrote {len(rows)} OC Yelp listings to {OUT}")
print("Merge: python build_catalog.py --input data/yelp_oc.tsv --output data/pet_services.parquet --mode upsert")
