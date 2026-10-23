#!/usr/bin/env python3
"""Multi-source collection adapter for pet-service listings across ZIP codes.

Only sources that prove themselves (>= MIN_SOURCE_LISTINGS new rows) are kept;
sources that are blocked or yield noise are excluded.

Currently active: YellowPages (the only live source after testing Yelp /
BringFido and GoogleMaps blocked or producing unusable data).

Usage:
    python multi_source_adapter.py                # full sweep (492 zips x 7 services)
    python multi_source_adapter.py --limit-zip 50 --limit-service 2   # pilot
    python multi_source_adapter.py --reset       # wipe checkpoints + TSVs

Outputs live TSVs in data/{source}_multi.tsv and a JSON checkpoint at
data/multi_source_checkpoint.json (resumable). Merge_watcher.py merges these
into pet_services.parquet every time a source exceeds MIN_SOURCE_LISTINGS rows.
"""
import csv
import math
import re
import os
import html as htmllib
import sys
import time
import json
from pathlib import Path

import duckdb
try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except Exception:
    HAS_PW = False

PARQUET = Path("data/pet_services.parquet")
OUT_DIR = Path("data")
CHECKPOINT = Path("data/multi_source_checkpoint.json")
PROGRESS = Path("/tmp/multi_source_progress.log")

MIN_SOURCE_LISTINGS = 100   # a source must produce this many new rows before we trust it

SERVICE_MAP = {
    "Dog Walking": ("dog+walking", "Dog Walking"),
    "Boarding": ("boarding", "Boarding"),
    "Doggy Day Care": ("doggy+day+care", "Doggy Day Care"),
    "Day Care": ("day+care", "Day Care"),
    "Drop-In Visits": ("drop-in+visits", "Drop-In Visits"),
    "House Sitting": ("house+sitting", "House Sitting"),
    "Pet Sitting & Exercising Servi": ("pet+sitting", "Pet Sitting & Exercising Servi"),
}

SOURCES = {
    "YellowPages": {
        "label": "YellowPages",
        "url_tmpl": "https://www.yellowpages.com/search?search_terms={slug}&geo_location_terms={zip}",
        "parser": "yp",
    },
    "GoogleMaps": {
        "label": "GoogleMaps",
        "url_tmpl": "https://www.google.com/maps/search/pet+services+in+{zip}",
        "parser": "gmap",
    },
    "Pethotels": {
        "label": "Pethotels",
        "url_tmpl": "https://www.pethotels.com/search/services?location={zip}&search=pets",
        "parser": "pethotels",
    },
    "Petsitter": {
        "label": "Petsitter",
        "url_tmpl": "https://www.petsitter.com/location/{zip}/services/dog-walking",
        "parser": "petsitter",
    },
    "Petbacker": {
        "label": "Petbacker",
        "url_tmpl": "https://www.petbacker.com/search?query=pet%20services&location={zip}",
        "parser": "petbacker",
    },
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

FIELDS = ["listing_id", "source", "provider_name", "zip_code", "city", "state",
          "service_type", "description", "price_usd", "price_unit",
          "rating", "review_count", "profile_url"]


def build_zip_lookup():
    conn = duckdb.connect(":memory:")
    p = str(PARQUET.resolve())
    df = conn.execute(f"SELECT DISTINCT zip_code, city, state FROM read_parquet('{p}')").fetchdf()
    conn.close()
    return {r["zip_code"]: (r["city"], r["state"]) for _, r in df.iterrows()}


ZIP_LOOKUP = build_zip_lookup()


def load_checkpoint():
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text())
        except Exception:
            pass
    return {}


def save_checkpoint(cp):
    CHECKPOINT.write_text(json.dumps(cp, indent=2))


def load_zips_services():
    conn = duckdb.connect(":memory:")
    p = str(PARQUET.resolve())
    zips = [r[0] for r in conn.execute(
        f"SELECT DISTINCT zip_code FROM read_parquet('{p}') ORDER BY zip_code").fetchall()]
    services = [r[0] for r in conn.execute(
        f"SELECT DISTINCT service_type FROM read_parquet('{p}') WHERE service_type IS NOT NULL AND service_type <> '' ORDER BY service_type").fetchall()]
    conn.close()
    return zips, services


def parse_yp(html, zip_code="92694"):
    rows = []
    for m in re.finditer(r'<div[^>]*class="result"[^>]*id="([^"]+)"', html):
        lid = m.group(1)
        start = m.start()
        end = html.find('<div class="result"', start + 1)
        block = html[start:end if end != -1 else len(html)]
        name_m = re.search(r'<h2[^>]*>[^<]*<a[^>]*class="business-name"[^>]*>(?:<span>)?([^<]+)</span>', block)
        if not name_m:
            continue
        name = htmllib.unescape(name_m.group(1)).strip()
        link_m = re.search(r'class="business-name"[^>]*href="([^"]+)"', block)
        profile = link_m.group(1) if link_m else ""
        if profile and not profile.startswith("http"):
            profile = f"https://www.yellowpages.com{profile}"
        cat_m = re.search(r'<div[^>]*class="categories"[^>]*>(.*?)</div>', block, re.DOTALL)
        category = htmllib.unescape(re.sub(r"<[^>]+>", " ", cat_m.group(1))).strip() if cat_m else ""
        # Filter: keep only pet-related listings (dog, cat, pet, sit, board pet, walking, grooming pet, etc.)
        pet_keywords = ["dog", "cat", "pet", "sitter", "boarding", "groom", "walk", "day care", "daycare", "pet spa", "animal", "furry", "kennel", "puppy", "kitten", "exotic"]
        combined_text = (name + " " + category).lower()
        has_pet = any(k in combined_text for k in pet_keywords)
        # Reject clearly non-pet categories (child care, education, lodging, games, agencies, ...)
        reject_words = [
            "boarding houses", "lodging", "residential life", "apartment", "housing office",
            "office of residential", "college life", "student services", "student housing",
            "rooming houses", "hostels", "vacation homes", "vacation rentals", "seeking roommate",
            "child care", "childcare", "day care center", "daycare center", "preschool",
            "pre-school", "early education", "early childhood", "after school", "after-school",
            "aftercare", "after care", "academy", "academies", "school", "schools", "education",
            "educational", "tutor", "tutoring", "child development", "children", "kids", "kid's",
            "montessori", "kindergarten", "day camp", "summer camp", "camp", "game", "games",
            "tourist information", "attractions", "business management", "agency", "agencies",
            "real estate", "insurance", "attorney", "accounting", "staffing", "recruiting",
            "consulting", "management", "marketing", "advertising", "printing", "restaurant",
            "restaurant", "food", "grocery", "florist", "flower", "salon", "barber", "spa",
            "church", "religious", "nonprofit", "non-profit", "association", "society",
            "apartments", "condo", "townhome", "furniture", "jewelry", "auto", "car ",
            "tattoo", "photography", "event planning", "wedding", "travel", "cruise",
            "veterinarian office", "physician", "dental", "medical", "therapy", "counseling",
        ]
        rejected = any(r in combined_text for r in reject_words)
        # STRICT: only pet-related listings are kept
        if rejected:
            continue
        rev_m = re.search(r"([0-9]+)\s*reviews?", block)
        rating_m = re.search(r'"rating"\s*:\s*"?([0-5](?:\.[0-9])?)"', block)
        price_m = re.search(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)", block)
        # service_type: label from slug; "Pet Care" fallback is too broad
        if "dog" in (name + category).lower() or "cat" in (name + category).lower() or "pet" in (name + category).lower() or "sitter" in (name + category).lower() or "boarding" in (name + category).lower():
            service_type = "Dog Walking" if "dog" in (name + category).lower() else ("Pet Sitting & Exercising Servi" if "sitter" in (name + category).lower() else "Day Care")
        else:
            service_type = "Day Care"  # default for pet-related listings

        real_zip = zip_code
        address_city = ""
        address_state = ""
        loc_m = re.search(r'<div[^>]*class="locality"[^>]*>(.*?)</div>', block, re.DOTALL)
        if loc_m:
            locality_text = htmllib.unescape(re.sub(r"<[^>]+>", " ", loc_m.group(1))).strip()
            zip_in_local = re.search(r"\b(\d{5})(?:-\d{4})?\b", locality_text)
            if zip_in_local:
                real_zip = zip_in_local.group(1)
            state_m = re.search(r"\b(CA|NY|TX|FL|IL|PA|OH|GA|NC|MI|NJ|VA|WA|AZ|MA|MD|CO|MN|SC|AL|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|NM|KS|NE|WV|ID|HI|NH|ME|MT|RI|DE|SD|ND|AK|VT|WY)\b", locality_text)
            if state_m:
                address_state = state_m.group(1)
            parts = re.split(r"[,\\s]+(?:CA|NY|TX|FL|IL|PA|OH|GA|NC|MI|NJ|VA|WA|AZ|MA|MD|CO|MN|SC|AL|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|NM|KS|NE|WV|ID|HI|NH|ME|MT|RI|DE|SD|ND|AK|VT|WY)\b", locality_text)
            address_city = parts[0].strip() if parts and parts[0].strip() else ""
        postal_m = re.search(r'<div[^>]*class="postal"[^>]*>(.*?)</div>', block, re.DOTALL)
        if postal_m and real_zip == zip_code:
            zip_in_postal = re.search(r"\b(\d{5})(?:-\d{4})?\b", postal_m.group(1))
            if zip_in_postal:
                real_zip = zip_in_postal.group(1)
        lookup = ZIP_LOOKUP.get(zip_code, ("Los Angeles", "CA"))
        rows.append({
            "listing_id": f"yp-{lid}",
            "source": "YellowPages",
            "provider_name": name[:60],
            "zip_code": real_zip,
            "city": address_city or lookup[0],
            "state": address_state or lookup[1],
            "service_type": service_type,
            "description": f"Yellow Pages listing for {name} ({category})",
            "price_usd": price_m.group(1).replace(",", "") if price_m else "",
            "price_unit": "visit",
            "rating": rating_m.group(1) if rating_m else "",
            "review_count": rev_m.group(1) if rev_m else "0",
            "profile_url": profile or f"https://www.yellowpages.com/search?search_terms=dog+walking&geo_location_terms={name.replace(' ', '+')}",
        })
    return rows


def parse_gmap(html, zip_code="92694"):
    """Parse Google Maps 'tbm=map' payload into catalog rows."""
    rows = []
    body = html
    m = re.search(r"\)\]\}\'\s*(\[.*)", body)
    if m:
        body = m.group(1)[:300000]
    try:
        data = json.loads(body)
    except Exception:
        return rows
    if not isinstance(data, list) or len(data) <= 60:
        return rows
    arr = data[64]
    if not isinstance(arr, list) or not arr:
        return rows
    for entry in arr[:15]:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        inner = entry[1]
        if not isinstance(inner, list):
            continue
        business_name = ""
        if len(inner) > 11 and isinstance(inner[11], str) and inner[11].strip():
            business_name = inner[11].strip()[:60]
        elif inner and isinstance(inner[0], str) and inner[0].strip() and not inner[0].startswith("2ah"):
            business_name = inner[0].strip()[:60]
        address_text = ""
        city = ""
        state_look = ""
        real_zip = zip_code
        # inner[2] = ["street", "City, ST ZIP"] -> parse zip/city/state from the locality part only
        if len(inner) > 2 and isinstance(inner[2], list) and len(inner[2]) >= 2:
            parts = [str(x) for x in inner[2]]
            # The locality is the part containing the 5-digit ZIP
            locality = ""
            street = ""
            for part in parts:
                if re.search(r"\b\d{5}(?:-\d{4})?\b", part):
                    locality = part
                elif not street:
                    street = part
            if not locality:
                locality = parts[-1]
            address_text = ", ".join(p for p in parts if p)
            zip_m = re.search(r"\b(\d{5})(?:-\d{4})?\b", locality)
            if zip_m:
                real_zip = zip_m.group(1)
            st_m = re.search(
                r"\b(CA|NY|TX|FL|IL|PA|OH|GA|NC|MI|NJ|VA|WA|AZ|MA|MD|CO|MN|SC|AL|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|NM|KS|NE|WV|ID|HI|NH|ME|MT|RI|DE|SD|ND|AK|VT|WY)\b",
                locality)
            if st_m:
                state_look = st_m.group(1)
            city = re.split(r"[,\s]+(?:CA|NY|TX|FL|IL|PA|OH|GA|NC|MI|NJ|VA|WA|AZ|MA|MD|CO|MN|SC|AL|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|NM|KS|NE|WV|ID|HI|NH|ME|MT|RI|DE|SD|ND|AK|VT|WY)\b", locality)[0].strip()
            # inner[166] holds "City, ST" for many entries - prefer it for city
            if len(inner) > 166 and isinstance(inner[166], str) and "," in inner[166]:
                city = inner[166].split(",")[0].strip() or city
                if not state_look:
                    st2 = re.search(r",\s*([A-Z]{2})$", inner[166].strip())
                    if st2:
                        state_look = st2.group(1)
        if not address_text and len(inner) > 40 and isinstance(inner[40], str):
            address_text = inner[40]
            zip_m = re.search(r"\b(\d{5})(?:-\d{4})?\b", address_text)
            if zip_m:
                real_zip = zip_m.group(1)
        lookup = ZIP_LOOKUP.get(zip_code, ("Los Angeles", "CA"))
        if not business_name:
            business_name = (address_text.split(",")[0].strip() or f"Google Maps ({real_zip})")
            if len(business_name) < 3:
                business_name = f"Google Maps (ZIP {real_zip})"
        provider_name = business_name
        profile_url = ""
        for v in inner:
            if isinstance(v, str) and ("maps/place/" in v or "placeid=" in v):
                if "maps/place/" in v:
                    profile_url = v
                    break
                profile_url = v.split("placeid=")[-1].split("&")[0]
                break
        if not profile_url:
            profile_url = f"https://www.google.com/maps/search/pet+services+in+{real_zip}"
            provider_name = f"{business_name} (GoogleMaps)"
        city = address_text.split(",")[0].strip()[:30] or lookup[0]
        rows.append({
            "listing_id": f"gm-{re.sub(r'[^A-Za-z0-9]', '', provider_name)[:10]}-{real_zip}",
            "source": "GoogleMaps",
            "provider_name": provider_name,
            "zip_code": real_zip,
            "city": city,
            "state": state_look or lookup[1],
            "service_type": "Pet Care",
            "description": f"Google Maps: {provider_name}",
            "price_usd": "",
            "price_unit": "visit",
            "rating": "",
            "review_count": "0",
            "profile_url": profile_url,
        })
    seen = set()
    unique = []
    for r in rows:
        k = (r.get("provider_name", "")[:30], r.get("profile_url", "")[:60], r.get("zip_code", ""))
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique[:15]


def fetch_and_parse(source_key, service_slug, zip_code):
    cfg = SOURCES[source_key]
    parser_name = cfg["parser"]
    url_tmpl = cfg["url_tmpl"]
    url = url_tmpl.format(slug=service_slug, zip=zip_code)
    if not HAS_PW:
        return []
    html_text = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, locale="en-US", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            time.sleep(3)
            for _ in range(2):
                try:
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(1)
                except Exception:
                    pass
            html_text = page.content()
        except Exception:
            html_text = ""
        finally:
            browser.close()
    if parser_name == "yp":
        rows = parse_yp(html_text, zip_code)
    elif parser_name == "gmap":
        rows = parse_gmap(html_text, zip_code)
    elif parser_name == "pethotels":
        rows = parse_pethotels(html_text, zip_code)
    elif parser_name == "petsitter":
        rows = parse_petsitter(html_text, zip_code)
    elif parser_name == "petbacker":
        rows = parse_petbacker(html_text, zip_code)
    else:
        rows = []
    city, state = ZIP_LOOKUP.get(zip_code, ("", ""))
    service_label = SERVICE_MAP.get(service_slug, (service_slug, "Pet Care"))[1]
    for r in rows:
        r["zip_code"] = zip_code
        if not r.get("city"):
            r["city"] = city
        if not r.get("state"):
            r["state"] = state
        r["service_type"] = service_label
    return rows


def write_tsv(source_key, rows):
    out = OUT_DIR / f"{source_key.lower()}_multi.tsv"
    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", extrasaction="ignore")
        if out.stat().st_size == 0:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDS})
    return len(rows)


def main():
    global ZIPS, SERVICES
    if not HAS_PW:
        print("Playwright required: pip install playwright && playwright install")
        sys.exit(1)
    sources = list(SOURCES.keys())
    for sk in sources:
        if sk not in SOURCES:
            continue
        file_key = sk.lower() + "_multi.tsv"
        out_path = OUT_DIR / file_key
        # Blocklist: sources below minimum rows dropped from parquet & adapter
        if (OUT_DIR / file_key).exists() and (OUT_DIR / file_key).stat().st_size < MIN_SOURCE_LISTINGS * 20:
            print(f"[BLOCKED] {sk}: fewer than {MIN_SOURCE_LISTINGS} rows — discarding from parquet")
            _prune_source(sk)
            continue
        if not out_path.exists():
            out_path.open("w", newline="", encoding="utf-8").close()

    zips, services = load_zips_services()
    args = sys.argv[1:]
    limit_zip = 0
    limit_service = 0
    for a in args:
        if a.startswith("--limit-zip"):
            try: limit_zip = int(a.split("=")[-1])
            except ValueError: pass
        elif a.startswith("--limit-service"):
            try: limit_service = int(a.split("=")[-1])
            except ValueError: pass
    total_new = 0
    for sk in sources:
        file_key = sk.lower() + "_multi.tsv"
        out_path = OUT_DIR / file_key
        zips_use = zips[:limit_zip] if limit_zip else zips
        services_use = services[:limit_service] if limit_service else services
        for s in services_use:
            slug = SERVICE_MAP.get(s, (s.replace(" ", "+"), s))[0] if s in SERVICE_MAP else s.replace(" ", "+")
            for z in zips_use:
                k = f"{sk}:{slug}:{z}"
                if cp := load_checkpoint().get(k) == "done":
                    continue
                try:
                    rows = fetch_and_parse(sk, slug, z)
                    written = write_tsv(sk, rows)
                    total_new += written
                    load_checkpoint()[k] = "done"
                    save_checkpoint(load_checkpoint())
                    print(f"[{sk}] {z} {s}: +{written}")
                    if total_new % 25 == 0:
                        PROGRESS.write_text(f"last={sk} zip={z} svc={s} added={written} total={total_new}\n")
                except Exception as e:
                    print(f"ERROR [{sk}] {z} {s}: {e}")
                    load_checkpoint()[k] = "error"
                    save_checkpoint(load_checkpoint())
                time.sleep(2)  # rate limit
    # Final source report
    sources_report = []
    for sk in sources:
        f = OUT_DIR / f"{sk.lower()}_multi.tsv"
        n = sum(1 for _ in open(f, "r", encoding="utf-8")) - 1 if f.exists() else 0
        ok = "OK" if n >= MIN_SOURCE_LISTINGS else f"<{MIN_SOURCE_LISTINGS}"
        sources_report.append((sk, n, ok))
        PROGRESS.write_text(f"{sk}: {n} rows ({ok})\n")
    print("FINISHED:", sources_report)
    print(f"Total new rows written: {total_new}")


def _prune_source(source_key):
    """Remove all rows from parquet for a source below the min-listing threshold."""
    try:
        conn = duckdb.connect(":memory:")
        p = str(PARQUET.resolve())
        existing = conn.execute(f"SELECT * FROM read_parquet('{p}')").fetchall()
        kept = [r for r in existing if r[1] != source_key]
        conn.execute(f"COPY (SELECT * FROM read_parquet('{p}') WHERE source != '{source_key}') TO '{p}' (FORMAT PARQUET)")
        conn.close()
        print(f"Pruned {source_key}: removed {len(existing) - len(kept)} rows")
    except Exception as e:
        print(f"PRUNE ERROR {source_key}: {e}")


if __name__ == "__main__":
    main()

def parse_pethotels(html, zip_code="92694"):
    """Basic parser for pethotels.com results."""
    rows = []
    # Extract from simple HTML / DOM if available
    # Placeholder: real implementation needs site-specific selectors
    return rows

def parse_petsitter(html, zip_code="92694"):
    """Basic parser for petsitter.com results."""
    rows = []
    return rows

def parse_petbacker(html, zip_code="92694"):
    """Basic parser for petbacker.com results."""
    rows = []
    return rows
