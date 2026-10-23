#!/usr/bin/env python3
"""Clean and dedupe the Pet Service Parquet catalog.

Removes development junk and normalizes fields:
  - synthetic demo rows (sources: Yelp, OtherPlatform) with fake profile URLs
  - Craigslist 'for sale' retail items that are not pet-care services
  - duplicate listing_ids (first occurrence kept)
  - blank / non-http profile URLs
  - extra whitespace, over-long descriptions, odd ratings and prices

Usage:
    python clean_catalog.py [--in data/pet_services.parquet] [--out data/pet_services.parquet]
"""
import argparse
import csv
import math
import re
from pathlib import Path

import duckdb

DESC_MAX = 160
EXCLUDED_SOURCES = {"Yelp", "OtherPlatform", "Craigslist", "Facebook Marketplace"}


RETAIL_NOISE = re.compile(
    r"(?i)\b(for sale|antique|stroller|motorcycle|vacating|trailer|tractor|"
    r"furniture|appliance|iphone|laptop|refrigerator)\b"
)
VALID_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
KEEP_UNLINKED = False  # drop listings without a valid profile URL


def clean(rows, columns):
    out, seen = [], set()
    for row in rows:
        listing_id = str(row.get("listing_id") or "").strip()
        if not listing_id or listing_id in seen:
            continue
        source = str(row.get("source") or "").strip()
        if source in EXCLUDED_SOURCES:
            continue
        # Drop synthetic Rover seed/demo entries (rover.com 404 links)
        if source == "Rover" and re.search(r"rover-[a-z]{2,3}-\d+", listing_id):
            continue
        provider = re.sub(r"\s+", " ", str(row.get("provider_name") or "")).strip()
        description = re.sub(r"\s+", " ", str(row.get("description") or "")).strip()
        if source == "Craigslist" and RETAIL_NOISE.search(provider + " " + description):
            continue
        zip_code = str(row.get("zip_code") or "").strip()
        if not re.fullmatch(r"\d{5}", zip_code):
            continue
        price = row.get("price_usd")
        try:
            price = round(float(price), 2) if price is not None and str(price).strip() != "" else None
        except (TypeError, ValueError):
            price = None
        if price is not None and (price < 0 or math.isnan(price) or math.isinf(price)):
            price = None
        rating = row.get("rating")
        try:
            rating = round(float(rating), 2) if rating is not None and str(rating).strip() != "" else None
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            if math.isnan(rating) or math.isinf(rating):
                rating = None
            else:
                rating = min(max(rating, 0.0), 5.0)
        reviews = row.get("review_count")
        try:
            reviews = int(reviews) if reviews is not None and str(reviews).strip() != "" else None
        except (TypeError, ValueError):
            reviews = None
        if reviews is not None and (not isinstance(reviews, int) or math.isnan(float(reviews)) or math.isinf(float(reviews))):
            reviews = None
        profile = str(row.get("profile_url") or "").strip()
        if profile and not VALID_URL.match(profile):
            profile = ""
        # Drop non-pet / boarding-house / lodging listings from YellowPages/other sources
        combined_text = (provider + " " + (description or "") + " " + str(row.get("service_type") or "")).lower()
        reject_words = ("boarding houses", "lodging", "residential life", "apartment", "housing office", "office of residential", "college life", "student services", "student housing", "room and boarding home")
        if any(r in combined_text for r in reject_words):
            continue  # skip this record
        # Drop listings we cannot link to (no valid contact URL)
        if not profile and not KEEP_UNLINKED:
            continue
        row = dict(row)
        row.update({
            "listing_id": listing_id,
            "source": source,
            "provider_name": provider,
            "zip_code": zip_code,
            "city": re.sub(r"\s+", " ", str(row.get("city") or "")).strip(),
            "state": str(row.get("state") or "").strip().upper(),
            "service_type": re.sub(r"\s+", " ", str(row.get("service_type") or "")).strip(),
            "description": description[:DESC_MAX],
            "price_usd": price,
            "price_unit": str(row.get("price_unit") or "").strip(),
            "rating": rating,
            "review_count": reviews,
            "profile_url": profile,
            "pet_types": re.sub(r"\s+", " ", str(row.get("pet_types") or "")).strip(),
        })
        seen.add(listing_id)
        out.append(row)
    return out


def main():
    parser = argparse.ArgumentParser(description="Clean the pet-service catalog.")
    parser.add_argument("--in", dest="src", default="data/pet_services.parquet")
    parser.add_argument("--out", dest="dst", default="data/pet_services.parquet")
    args = parser.parse_args()

    conn = duckdb.connect()
    columns = [row[0] for row in conn.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [args.src]).fetchall()]
    rows = [dict(zip(columns, r)) for r in conn.execute(
        "SELECT * FROM read_parquet(?)", [args.src]).fetchall()]
    print(f"Raw rows: {len(rows)}")

    cleaned = clean(rows, columns)
    print(f"Cleaned rows: {len(cleaned)}")

    conn.execute(
        f"CREATE OR REPLACE TEMP TABLE clean_catalog AS "
        f"SELECT * FROM read_parquet('{args.src}') LIMIT 0"
    )
    placeholders = ", ".join("?" for _ in columns)
    insert = f"INSERT INTO clean_catalog ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(insert, [tuple(row.get(c) for c in columns) for row in cleaned])

    conn.execute(
        f"COPY (SELECT * FROM clean_catalog) TO '{args.dst}' (FORMAT PARQUET)"
    )

    final = conn.execute("SELECT count(*) FROM read_parquet(?)", [args.dst]).fetchone()[0]
    sources = conn.execute(
        "SELECT source, count(*) FROM read_parquet(?) GROUP BY 1 ORDER BY 2 DESC",
        [args.dst]).fetchall()
    no_url = conn.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE profile_url IS NULL OR profile_url = ''",
        [args.dst]).fetchone()[0]
    print(f"Final rows: {final}")
    print("Sources:", sources)
    print("Rows without a contact link:", no_url)
    conn.close()


if __name__ == "__main__":
    main()
