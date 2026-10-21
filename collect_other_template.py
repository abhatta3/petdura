#!/usr/bin/env python3
"""Template collector for another pet-service site (similar to Rover).
Copy pw_collect.py, change URL/selector, save to data/other_sitters.tsv,
then merge with: python build_catalog.py --input data/other_sitters.tsv \
  --output data/pet_services.parquet --mode upsert

Required TSV columns (same schema as Rover):
listing_id, source, provider_name, zip_code, city, state,
service_type, description, price_usd, price_unit, rating,
review_count, profile_url
"""
from pathlib import Path
import csv, time

OUTPUT = Path('data/other_sitters.tsv')
# Example structure — replace with actual scrape loop + JSON/HTML extraction
# For demo purposes this creates a template row you can expand.

def template_row():
    return {
        "listing_id": "other-001",
        "source": "OtherPlatform",
        "provider_name": "Example Provider",
        "zip_code": "92694",
        "city": "Irvine",
        "state": "CA",
        "service_type": "Dog Walking",
        "description": "Reliable pet walking service.",
        "price_usd": "25",
        "price_unit": "walk",
        "rating": "4.8",
        "review_count": "15",
        "profile_url": "https://otherplatform.com/providers/example",
    }

if __name__ == "__main__":
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "listing_id","source","provider_name","zip_code","city","state",
            "service_type","description","price_usd","price_unit","rating",
            "review_count","profile_url"
        ], delimiter="\t")
        writer.writeheader()
        writer.writerow(template_row())
    print("Template written to", OUTPUT)
    print("Next: adapt URL/selector in this script, run it, then merge:")
    print("python build_catalog.py --input data/other_sitters.tsv --output data/pet_services.parquet --mode upsert")
