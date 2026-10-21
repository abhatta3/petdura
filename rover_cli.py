#!/usr/bin/env python3
"""Rover collector CLI.

Two modes:
  add     - collect zip x service search pages; ADD listings that are not in the
            catalog yet, and refresh fields on ones that are.
  update  - collect the same search pages but ONLY refresh fields on listings
            that already exist in the catalog. Never adds a new listing_id.

Both modes upsert into the Parquet catalog and checkpoint periodically so no
collected data is lost if the run is interrupted.

Examples
--------
    python3 rover_cli.py add
    python3 rover_cli.py add --zips 92101,90210 --services boarding,dog-walking
    python3 rover_cli.py update
    python3 rover_cli.py update --limit 200 --checkpoint 50
    python3 rover_cli.py status
"""
import argparse
import csv
import json
import re
import signal
import sys
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from build_catalog import build_catalog

DEFAULT_PARQUET = Path('data/pet_services.parquet')
DEFAULT_TSV = Path('data/rover_ca_sitters.tsv')
FIELDS = [
    'listing_id', 'source', 'provider_name', 'zip_code', 'city', 'state',
    'service_type', 'description', 'price_usd', 'price_unit', 'rating',
    'review_count', 'profile_url', 'search_business_name', 'verified_status',
]
SERVICE_SLUGS = {
    'overnight-boarding': 'Boarding',
    'dog-walking': 'Dog Walking',
    'day-care': 'Doggy Day Care',
    'house-sitting': 'House Sitting',
    'drop-in-visits': 'Drop-In Visits',
}
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15'
)


# --------------------------------------------------------------------------
# catalog helpers
# --------------------------------------------------------------------------
def load_catalog(parquet_path, tsv_path):
    """Return (records_by_id, existing_ids). Records are dicts keyed by listing_id."""
    records = {}
    if tsv_path.exists():
        with tsv_path.open('r', encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                records[row['listing_id']] = row
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        for row in df.to_dict('records'):
            rid = str(row.get('listing_id') or '')
            if not rid:
                continue
            rec = {k: ('' if pd.isna(v) else str(v)) for k, v in row.items()}
            records.setdefault(rid, rec)
    return records, set(records)


def save_catalog(records, tsv_path, parquet_path, reason=''):
    """Write TSV + upsert parquet. Returns parquet count or None on failure."""
    try:
        with tsv_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t',
                                    extrasaction='ignore')
            writer.writeheader()
            for rec in records.values():
                writer.writerow({k: rec.get(k, '') for k in FIELDS})
        report = build_catalog(tsv_path, parquet_path, mode='upsert')
        print(f'  [checkpoint {reason}] parquet={report["final_count"]} '
              f'replaced={report["replaced_count"]}', flush=True)
        return report['final_count']
    except Exception as e:
        print(f'  [checkpoint FAILED {reason}] {e}', flush=True)
        return None


# --------------------------------------------------------------------------
# scraping
# --------------------------------------------------------------------------
def extract_sitters(html):
    """Pull the sitter array out of Rover's embedded initial data.

    The payload contains many "results" arrays (cities, breeds, ...). The
    sitters array is the largest one whose entries carry a personOpk key.
    """
    idx = html.find('__ROVER_INITIAL_DATA__ = ')
    if idx == -1:
        return []
    start = idx + len('__ROVER_INITIAL_DATA__ = ')
    end = html.find(';</script>', start)
    if end == -1:
        return []
    chunk = html[start:end]
    best = []
    for m in re.finditer(r'"results"\s*:\s*\[', chunk):
        si = m.end() - 1
        depth = 0
        ei = si
        for i, ch in enumerate(chunk[si:], si):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    ei = i + 1
                    break
        try:
            arr = json.loads(chunk[si:ei])
        except Exception:
            continue
        if (arr and len(arr) > len(best)
                and isinstance(arr[0], dict) and 'personOpk' in arr[0]):
            best = arr
    return best


def listing_fields(s):
    """Normalise a raw sitter object into catalog fields."""
    return {
        'provider_name': s.get('shortName') or '',
        'zip_code': s.get('zip') or '',
        'city': s.get('city') or '',
        'state': (s.get('state') or 'CA').upper(),
        'description': (s.get('description') or s.get('title') or '')
                        .replace('\n', ' ').replace('\r', ' '),
        'price_usd': str(s.get('price')) if s.get('price') else '0',
        'price_unit': s.get('priceUnit') or 'night',
        'rating': str(s.get('ratingsAverage')) if s.get('ratingsAverage') else '0',
        'review_count': (str(s.get('reviewsCount'))
                         if s.get('reviewsCount') is not None else '0'),
        'profile_url': s.get('webUrl') or '',
    }


def apply_update(rec, fields):
    """Write refreshed values onto an existing record. Returns True if changed."""
    changed = False
    for key, val in fields.items():
        if not val:
            continue
        old = str(rec.get(key, '') or '').strip()
        new = str(val).strip()
        if old != new:
            rec[key] = new
            changed = True
    return changed


# --------------------------------------------------------------------------
# main collect loop
# --------------------------------------------------------------------------
def run(args):
    records, existing_ids = load_catalog(args.parquet, args.tsv)
    print(f'Loaded {len(records)} existing listings '
          f'({args.mode} mode)', flush=True)

    zips = args.zips
    services = [(s, SERVICE_SLUGS[s]) for s in args.services]
    total_pages = len(zips) * len(services)
    print(f'Plan: {len(zips)} zips x {len(services)} services = '
          f'{total_pages} pages', flush=True)

    added = 0
    updated = 0
    pages = 0
    last_ckpt = 0
    stopping = False

    def on_signal(signum, frame):
        nonlocal stopping
        stopping = True
        print(f'\n[signal {signum}] finishing current page then saving...',
              flush=True)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not args.headed,
                args=['--disable-blink-features=AutomationControlled',
                      '--no-sandbox', '--disable-setuid-sandbox'],
            )
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                viewport={'width': 1440, 'height': 900},
                locale='en-US',
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

            for slug, s_name in services:
                for z in zips:
                    if stopping:
                        break
                    url = (f'https://www.rover.com/search/?service_type={slug}'
                           f'&location={z}&location_type=zip-code')
                    try:
                        page.goto(url, wait_until='domcontentloaded',
                                  timeout=args.timeout * 1000)
                        time.sleep(args.settle)
                        sitters = extract_sitters(page.content())
                        if not sitters:
                            time.sleep(2)
                            sitters = extract_sitters(page.content())

                        page_new = page_upd = 0
                        for s in sitters:
                            opk = s.get('personOpk')
                            if not opk:
                                continue
                            lid = f'rover-{opk}-{slug}'
                            fields = listing_fields(s)
                            if lid in existing_ids:
                                if apply_update(records[lid], fields):
                                    page_upd += 1
                                continue
                            if args.mode == 'update':
                                # update mode never introduces new listings
                                continue
                            fields.update({
                                'listing_id': lid,
                                'source': 'Rover',
                                'service_type': s_name,
                                'search_business_name':
                                    f"Rover - {fields.get('provider_name', '')}",
                                'verified_status': 'True',
                            })
                            records[lid] = fields
                            existing_ids.add(lid)
                            page_new += 1

                        added += page_new
                        updated += page_upd
                        pages += 1
                        if page_new or page_upd:
                            print(f'{s_name} {z}: {len(sitters)} results '
                                  f'-> +{page_new} new, ~{page_upd} updated '
                                  f'(totals: +{added} new, {updated} updated)',
                                  flush=True)
                    except Exception as e:
                        print(f'  ERROR {s_name} {z}: {str(e)[:100]}', flush=True)

                    if args.checkpoint and (added + updated) - last_ckpt >= args.checkpoint:
                        n = save_catalog(records, args.tsv, args.parquet, 'auto')
                        if n:
                            last_ckpt = added + updated
                    time.sleep(args.delay)

                    if args.limit and pages >= args.limit:
                        print(f'--limit {args.limit} reached', flush=True)
                        break
                if stopping or (args.limit and pages >= args.limit):
                    break
            browser.close()
    finally:
        n = save_catalog(records, args.tsv, args.parquet, 'final')

    print(f'\nDONE  added={added}  updated={updated}  '
          f'catalog={n if n else "?"}  (was {len(records) - added} before)',
          flush=True)
    return 0


def status(args):
    df = pd.read_parquet(args.parquet)
    print(f'Parquet      : {args.parquet}')
    print(f'Records      : {len(df)}')
    print(f'Unique zips  : {df["zip_code"].nunique()}')
    print(f'Services     : {df["service_type"].value_counts().to_dict()}')
    print(f'States       : {df["state"].value_counts().head(5).to_dict()}')
    print(f'Last built   : {df["collected_at"].max() if "collected_at" in df.columns else "?"}')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='Collect and maintain the Rover pet-service Parquet catalog.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('mode', choices=['add', 'update', 'status'],
                    help='add: collect new listings | update: refresh existing '
                         'listings only | status: show catalog summary')
    ap.add_argument('--parquet', type=Path, default=DEFAULT_PARQUET)
    ap.add_argument('--tsv', type=Path, default=DEFAULT_TSV)
    ap.add_argument('--zips', nargs='+', default=None,
                    help='zip codes to sweep (default: built-in CA list)')
    ap.add_argument('--services', nargs='+', default=None,
                    choices=list(SERVICE_SLUGS),
                    help='service types (default: all five)')
    ap.add_argument('--checkpoint', type=int, default=100,
                    help='save parquet every N changed records (0 = off)')
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after N search pages (0 = no limit)')
    ap.add_argument('--delay', type=float, default=2.0,
                    help='seconds between requests')
    ap.add_argument('--settle', type=float, default=3.0,
                    help='seconds to wait for the page to render')
    ap.add_argument('--timeout', type=int, default=30,
                    help='navigation timeout in seconds')
    ap.add_argument('--headed', action='store_true', default=True,
                    help='run a visible browser (default; needed for Cloudflare)')
    ap.add_argument('--headless', dest='headed', action='store_false',
                    help='run headless (usually blocked by Cloudflare)')
    args = ap.parse_args()

    if args.mode == 'status':
        return status(args)

    if not args.zips:
        args.zips = default_zips()
    if not args.services:
        args.services = list(SERVICE_SLUGS)
    return run(args)


def default_zips():
    return [
        '92602', '92603', '92604', '92606', '92610', '92612', '92614',
        '92617', '92618', '92620', '92624', '92625', '92626', '92627',
        '92629', '92630', '92637', '92646', '92647', '92648', '92649',
        '92651', '92653', '92655', '92656', '92657', '92660', '92661',
        '92662', '92663', '92672', '92673', '92675', '92677', '92679',
        '92683', '92685', '92688', '92691', '92692', '92694', '92701',
        '92703', '92704', '92705', '92706', '92707', '92708', '92780',
        '92782', '92801', '92802', '92804', '92805', '92806', '92807',
        '92808', '92821', '92831', '92832', '92833', '92835', '92840',
        '92841', '92843', '92844', '92845', '92865', '92866', '92867',
        '92868', '92869', '92870', '92886', '92887', '90001', '90012',
        '90028', '90045', '90210', '90291', '90401', '90640', '90703',
        '90802', '91101', '91304', '91403', '91744', '91801', '92101',
        '92103', '92109', '92115', '92122', '92037', '92024', '92064',
        '92121', '94102', '94107', '94110', '94103', '94105', '94107',
        '94110', '94111', '94114', '94115', '94117', '94118', '94121',
        '94122', '94123', '94124', '94129', '94131', '94132', '94133',
        '94134', '94158', '94159', '94177', '94301', '94501', '94601',
        '95050', '95110', '94043', '94025', '94062', '94065', '95814',
        '95816', '95825', '93710', '93301', '93720',
    ]


if __name__ == '__main__':
    sys.exit(main())
