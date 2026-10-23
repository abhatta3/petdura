"""Validate catalog profile URLs: flag dead (404 / no such page) links.

Rover returns 403 (Cloudflare) for real member pages, and 404 for dead ones --
so we use the HTTP status from a real browser to tell them apart.
Results are written to data/link_check.csv and broken listing_ids to
data/broken_listing_ids.txt so clean_catalog can drop them.
"""
import argparse
import csv
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import duckdb
from playwright.sync_api import sync_playwright

PARQUET = Path(__file__).resolve().parent / "data/pet_services.parquet"
DATA = Path(__file__).resolve().parent / "data"
OUT_CSV = DATA / "link_check.csv"
OUT_IDS = DATA / "broken_listing_ids.txt"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.37 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.37")


def load_rows(limit=0, only_source=""):
    conn = duckdb.connect(":memory:")
    p = str(PARQUET.resolve())
    sql = f"SELECT listing_id, source, provider_name, zip_code, profile_url FROM read_parquet('{p}')"
    if only_source:
        sql += f" WHERE source = '{only_source}'"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def is_rover(url):
    return "rover.com" in url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only-source", default="")
    args = ap.parse_args()

    rows = load_rows(args.limit, args.only_source)
    if args.only_source:
        rows = [r for r in rows if r[1] == args.only_source]
    # unique urls -> listing_ids affected
    url_to_ids = {}
    for lid, src, name, zc, url in rows:
        url_to_ids.setdefault(url, []).append(lid)
    urls = list(url_to_ids.keys())
    print(f"Checking {len(urls)} unique URLs across {len(rows)} rows", flush=True)

    results = []
    broken_ids = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, url in enumerate(urls):
            status = None
            err = ""
            try:
                ctx = browser.new_context(user_agent=UA, locale="en-US")
                page = ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status = resp.status if resp else 0
                if status == 200:
                    # Cloudflare challenge pages sometimes return 200
                    body = page.inner_text("body")[:400].lower()
                    if "performing security verification" in body or "just a moment" in body:
                        status = 403
                    elif "404" in body and ("couldn't" in body or "not found" in body):
                        status = 404
                ctx.close()
            except Exception as e:
                err = str(e)[:120]
                status = 0
            dead = status in (404, 410) or status == 0
            results.append((url, status, "BROKEN" if dead else "ok", err))
            if dead:
                broken_ids.extend(url_to_ids[url])
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(urls)} checked, broken={len(set(broken_ids))}", flush=True)
                with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["profile_url", "status", "result", "error"])
                    w.writerows(results)
                OUT_IDS.write_text("\n".join(sorted(set(broken_ids))), encoding="utf-8")
            time.sleep(0.4)
        browser.close()

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["profile_url", "status", "result", "error"])
        w.writerows(results)
    OUT_IDS.write_text("\n".join(sorted(set(broken_ids))), encoding="utf-8")
    n_broken = len(set(broken_ids))
    print(f"DONE: {len(urls)} urls checked, {n_broken} listing_ids broken -> {OUT_IDS}")


if __name__ == "__main__":
    main()
