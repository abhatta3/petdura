# Usage

## 1. Activate the environment

```bash
cd /path/to/agentic_browser_prototype
source venv/bin/activate
pip install -r requirements.txt
```

No Git repository is required.

## 2. Prepare an input file

The importer accepts comma-separated CSV files and tab-separated TSV, TAB, or
text files. It detects the delimiter for each file, so CSV and TSV inputs can
be combined in one command. Column order does not matter.

Each row represents one provider and service combination.

### Required columns

| Column | Description |
|---|---|
| `listing_id` | Stable unique record ID and upsert key |
| `source` | Name of the authorized data source |
| `provider_name` | Provider's public display name |
| `zip_code` | Five-digit service-area ZIP code |
| `city` | Service-area city |
| `state` | State abbreviation |
| `service_type` | Boarding, dog walking, drop-in visits, or another service |
| `description` | Searchable description of the service |

### Optional columns

| Column | Description |
|---|---|
| `pet_types` | Supported animals or other searchable tags |
| `price_usd` | Numeric advertised price without a dollar sign |
| `price_unit` | `per walk`, `per visit`, `per night`, and so on |
| `rating` | Numeric rating |
| `review_count` | Integer review count |
| `profile_url` | Authorized public source page |
| `collected_at` | Collection date in `YYYY-MM-DD` format |

Missing optional text fields become blank. Missing numeric fields remain null.
A missing `collected_at` value defaults to the import date.

### Minimal TSV example

```text
listing_id\tsource\tprovider_name\tzip_code\tcity\tstate\tservice_type\tdescription
local-001\tProvider submission\tSample Pet Care\t92101\tSan Diego\tCA\tDog Walking\tMorning walks for energetic dogs
```

The repository's complete example is `data/sample_pet_services.csv`.

## 3. Replace the catalog

Use replacement when the input files together contain the complete catalog:

```bash
python build_catalog.py \
  --input services.csv regional_services.tsv \
  --output data/pet_services.parquet \
  --mode replace
```

The existing Parquet file is replaced only after the new catalog passes
validation and is written successfully.

## 4. Add or update records

Use upsert for incremental files:

```bash
python build_catalog.py \
  --input daily_updates.tsv \
  --output data/pet_services.parquet \
  --mode upsert
```

An incoming `listing_id` replaces that complete existing row. A new ID is
added. Existing records absent from the update file remain unchanged. Upsert
does not delete records.

To see all command options:

```bash
python build_catalog.py --help
```

## 5. Start the web application

```bash
python app.py
```

Open <http://localhost:5050>.

The development server listens only on the local machine by default. Its
settings can be changed with environment variables:

| Variable | Default | Purpose |
|---|---:|---|
| `PET_SERVICE_PARQUET` | `data/pet_services.parquet` | Catalog file location |
| `APP_HOST` | `127.0.0.1` | Development-server bind address |
| `APP_PORT` | `5050` | Development-server port |
| `APP_DEBUG` | `false` | Flask debugging; never enable on a shared server |
| `SEARCH_RESULT_LIMIT` | `500` | Maximum results per API request, from 1 to 1000 |

For example, run against a catalog outside the application folder:

```bash
PET_SERVICE_PARQUET=/srv/pet-search/catalog.parquet python app.py
```

Use Gunicorn rather than Flask's development server on EC2. The complete
instructions are in [DEPLOYMENT.md](DEPLOYMENT.md).

- Enter a five-digit ZIP code.
- Leave the description blank to return every record in that exact ZIP.
- Enter a description to rank matching words in the provider name, service
  type, pet types, location, and description.
- Filter returned records by service and maximum rate.
- Sort by relevance, rating, review count, price, or provider name.

The current implementation searches only the exact ZIP. A ZIP-radius option is
planned but is not part of the current catalog API.

## 6. Validation rules

The import stops without replacing the existing catalog when it finds:

- a missing required column;
- an empty required value;
- duplicate `listing_id` values within the incoming files;
- a ZIP code that is not exactly five digits;
- non-numeric price, rating, or review-count values; or
- a collection date outside `YYYY-MM-DD` format.

Review the command's row counts after every import. In upsert mode it reports
how many incoming records replaced existing IDs and the final catalog size.

## 7. Run verification

```bash
python -m unittest discover -s tests -v
```

The tests cover CSV input, TSV input, mixed input files, optional columns,
replacement, upsert, exact-ZIP search, text ranking, and invalid ZIP handling.

## Reusing the importer for reagents

`tabular_ingest.py` is independent of the pet-service fields. A reagent search
tool can reuse its mixed-file loading and atomic Parquet output while defining
a reagent-specific schema and normalization step. Likely reagent fields include
stable product ID, vendor, product name, catalog number, analyte, application,
description, price, unit, and product URL.
