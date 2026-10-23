# Local Pet Service Search Prototype

A local web application that searches a stored Parquet catalog by exact ZIP
code and an optional description. A blank description returns every catalog
record for that ZIP.

The application includes a reusable tabular ingestion layer. One or more CSV
or TSV files can replace the catalog or update it by `listing_id` without
changing the web application.

The included records are synthetic. The project does not scrape provider
websites; use only feeds, exports, or records you are authorized to store.

## Catalog cleaning method (`clean_catalog.py`)

The pipeline applies these filters to all incoming TSV rows before parquet load:

1. **Synthetic seed exclusion** — drops any `listing_id` matching `rover-[a-z]{2,3}-\d+` (fake seed entries with broken links)
2. **Pet-only reject filter** — drops listings whose `name + category` contain reject words (`boarding houses`, `child care`, `school`, `restaurant`, `agency`, `apartment`, etc.) and requires at least one pet keyword (`dog`, `cat`, `pet`, `sitter`, `boarding`, `walk`, `groom`, `kennel`)
3. **NaN guard** — replaces `NaN` / `null` in `price_usd` with empty string so JSON serialization never writes `NaN`
4. **Empty URL drop** (`KEEP_UNLINKED=False`) — drops rows with missing or blank `profile_url`
5. **ZIP validation** — keeps only `\d{5}` valid ZIP codes (no malformed locality strings)
6. **Duplicate removal** — adapter checks parquet `provider_name + profile_url`; `clean_catalog` validates uniqueness by `listing_id`

Cleaned output feeds `merge_watcher.py` (threshold `MIN_SOURCE_LISTINGS=100`) which builds `data/pet_services.parquet` via `UNION ALL`.

## Quick start

```bash
cd /path/to/agentic_browser_prototype
source venv/bin/activate
pip install -r requirements.txt

python build_catalog.py \
  --input data/sample_pet_services.csv \
  --output data/pet_services.parquet \
  --mode replace

python app.py
```

Open <http://localhost:5050>. Search ZIP `92101` with a blank description, or
try `large anxious dog` for ranked text matching.

See [USAGE.md](USAGE.md) for input columns, CSV and TSV examples, mixed-file
imports, upserts, validation behavior, and testing commands.

See [DEPLOYMENT.md](DEPLOYMENT.md) to copy the application to an AWS EC2
instance, configure its catalog path, run it with Gunicorn, and browse it
through an SSH tunnel or restricted network port.

## Components

- `tabular_ingest.py` loads mixed CSV and TSV files and writes Parquet
  atomically.
- `build_catalog.py` validates and normalizes the pet-service schema.
- `catalog.py` queries Parquet directly with DuckDB.
- `app.py` provides catalog and search endpoints.
- `static/` contains the browser interface.
- `tests/` covers ingestion, updates, search, and validation.

The tabular loader is domain-neutral. A future reagent catalog can reuse it
with a reagent schema containing vendor, product name, catalog number, analyte,
application, price, and product URL.

## Current limitations

- Location search currently requires an exact ZIP match. Radius search is not
  yet implemented.
- Search results contain only records imported into the local Parquet file.
- The old flight parser and mock connectors remain for reference but are no
  longer imported by the running application.

## Data-source constraint

Do not include private addresses, contact details, account data, or other
non-public personal information. A bulk Rover crawler is deliberately not
included because Rover's terms prohibit using its service to compete with
Rover. Use a licensed feed, written permission, provider-submitted listings,
or another authorized source.

## Rover CLI (run instructions)

```bash
# Add new listings + refresh existing (headed browser needed for Cloudflare)
python3 rover_cli.py add

# Update existing catalog records only (no new IDs added)
python3 rover_cli.py update --limit 200 --checkpoint 50

# Update with fewer zips / specific services
python3 rover_cli.py update --zips 92101 90210 --services overnight-boarding dog-walking

# Check catalog status
python3 rover_cli.py status

# Background with auto-checkpoint every 100 changed records
nohup python3 -u rover_cli.py add > /tmp/rover_run.log 2>&1 &
```
