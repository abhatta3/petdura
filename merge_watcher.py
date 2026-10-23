#!/usr/bin/env python3
"""Watch the multi-source TSV outputs and merge new rows into the parquet.

Merges every time at least --threshold new TSV rows have appeared since the
last merge. Uses clean_catalog.clean() so the incoming rows get the same
normalization (NaN -> None, URL validation, truncation) as the main catalog,
then rewrites data/pet_services.parquet with the exact production schema.
"""
import argparse, csv, sys, time, datetime
from pathlib import Path

import duckdb

from clean_catalog import clean

DATA = Path("data")
PARQUET = DATA / "pet_services.parquet"
SOURCES = ["yellowpages", "bringfido", "yelp", "googlemaps"]
LOG = Path("/tmp/merge_watcher.log")
PROGRESS = Path("/tmp/multi_source_progress.log")

PARQUET_COLUMNS = [
    "listing_id", "source", "provider_name", "zip_code", "city", "state",
    "service_type", "pet_types", "price_usd", "price_unit", "rating",
    "review_count", "description", "profile_url", "collected_at", "search_text",
]


def log(msg):
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def tsv_paths():
    return [DATA / f"{s}_multi.tsv" for s in SOURCES if (DATA / f"{s}_multi.tsv").exists()]


def count_tsv_rows():
    total = 0
    for p in tsv_paths():
        try:
            with p.open("r", encoding="utf-8") as f:
                total += max(0, sum(1 for _ in f) - 1)
        except Exception:
            pass
    return total


def read_tsv_rows():
    rows = []
    for p in tsv_paths():
        try:
            with p.open("r", encoding="utf-8") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    row["_tsv"] = p.name
                    rows.append(row)
        except Exception:
            pass
    return rows


def merge():
    conn = duckdb.connect(":memory:")
    parquet_str = str(PARQUET.resolve())
    existing_cols = [r[0] for r in conn.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [parquet_str]).fetchall()]
    existing = conn.execute("SELECT * FROM read_parquet(?)", [parquet_str]).fetchall()
    existing_ids = {r[0] for r in existing}

    new_rows = read_tsv_rows()
    if not new_rows:
        conn.close()
        return 0, 0

    # Normalize incoming rows (same rules as clean_catalog)
    cleaned = clean(new_rows, existing_cols)
    fresh = [r for r in cleaned if r.get("listing_id") and r["listing_id"] not in existing_ids]
    if not fresh:
        conn.close()
        return len(new_rows), 0

    conn.execute("CREATE TABLE incoming AS SELECT * FROM read_parquet(?) LIMIT 0", [parquet_str])
    placeholders = ", ".join("?" for _ in existing_cols)
    insert = f"INSERT INTO incoming ({', '.join(existing_cols)}) VALUES ({placeholders})"

    now = datetime.date.today()
    payload = []
    for r in fresh:
        row = dict(r)
        row.setdefault("pet_types", None)
        row["collected_at"] = now
        text = " ".join([
            str(row.get("provider_name") or ""),
            str(row.get("zip_code") or ""),
            str(row.get("city") or ""),
            str(row.get("state") or ""),
            str(row.get("service_type") or ""),
            str(row.get("description") or ""),
        ]).lower()
        row["search_text"] = text
        payload.append(tuple(row.get(c) for c in existing_cols))

    conn.executemany(insert, payload)
    conn.execute(
        f"COPY (SELECT * FROM incoming UNION ALL SELECT * FROM read_parquet('{parquet_str}')) "
        f"TO '{parquet_str}' (FORMAT PARQUET)"
    )
    final = conn.execute("SELECT count(*) FROM read_parquet(?)", [parquet_str]).fetchone()[0]
    srcs = conn.execute(
        "SELECT source, count(*) FROM read_parquet(?) GROUP BY 1 ORDER BY 2 DESC", [parquet_str]).fetchall()
    conn.close()
    return len(new_rows), final, srcs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=100)
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    merged_total = 0
    while True:
        tsv_rows = count_tsv_rows()
        pending = tsv_rows - merged_total
        if pending >= args.threshold:
            try:
                res = merge()
                if len(res) == 3:
                    _, final, srcs = res
                    merged_total = tsv_rows
                    log(f"MERGED new_rows_seen={tsv_rows} parquet_rows={final} sources={srcs}")
                    PROGRESS.write_text(
                        f"parquet_rows={final}\ntsv_rows={tsv_rows}\nsources={srcs}\n")
                else:
                    log(f"MERGED no new unique rows (tsv_rows={tsv_rows})")
                    merged_total = tsv_rows
            except Exception as e:
                log(f"MERGE ERROR: {e}")
        else:
            PROGRESS.write_text(f"pending_rows={pending} (threshold {args.threshold})\ntsv_rows={tsv_rows}\n")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
