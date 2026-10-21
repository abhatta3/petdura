import argparse
from datetime import date
from pathlib import Path

import duckdb

from tabular_ingest import load_delimited_files, table_columns, write_table_as_parquet


REQUIRED_COLUMNS = {
    "listing_id",
    "source",
    "provider_name",
    "zip_code",
    "city",
    "state",
    "service_type",
    "description",
}

OPTIONAL_COLUMNS = {
    "pet_types",
    "price_usd",
    "price_unit",
    "rating",
    "review_count",
    "profile_url",
    "collected_at",
}


def _add_missing_optional_columns(connection):
    present = table_columns(connection)
    for column in sorted(OPTIONAL_COLUMNS.difference(present)):
        connection.execute(f"ALTER TABLE raw ADD COLUMN {column} VARCHAR")


def _validate_raw(connection):
    columns = table_columns(connection)
    missing = REQUIRED_COLUMNS.difference(columns)
    if missing:
        raise ValueError(f"Input is missing columns: {', '.join(sorted(missing))}")

    _add_missing_optional_columns(connection)
    row_count = connection.execute("SELECT count(*) FROM raw").fetchone()[0]
    if not row_count:
        raise ValueError("Input contains no service rows")

    for column in sorted(REQUIRED_COLUMNS):
        empty_count = connection.execute(
            f"SELECT count(*) FROM raw WHERE nullif(trim({column}), '') IS NULL"
        ).fetchone()[0]
        if empty_count:
            raise ValueError(f"{empty_count} row(s) have an empty {column}")

    duplicates = connection.execute(
        """
        SELECT trim(listing_id), count(*)
        FROM raw
        GROUP BY trim(listing_id)
        HAVING count(*) > 1
        ORDER BY count(*) DESC, trim(listing_id)
        LIMIT 5
        """
    ).fetchall()
    if duplicates:
        values = ", ".join(f"{listing_id} ({count})" for listing_id, count in duplicates)
        raise ValueError(f"Duplicate listing_id values in input: {values}")

    invalid_zip_count = connection.execute(
        "SELECT count(*) FROM raw WHERE NOT regexp_full_match(trim(zip_code), '[0-9]{5}')"
    ).fetchone()[0]
    if invalid_zip_count:
        raise ValueError(f"{invalid_zip_count} row(s) have an invalid five-digit ZIP code")

    for column, data_type in (
        ("price_usd", "DOUBLE"),
        ("rating", "DOUBLE"),
        ("review_count", "INTEGER"),
    ):
        invalid_count = connection.execute(
            f"""
            SELECT count(*)
            FROM raw
            WHERE nullif(trim({column}), '') IS NOT NULL
              AND try_cast(trim({column}) AS {data_type}) IS NULL
            """
        ).fetchone()[0]
        if invalid_count:
            raise ValueError(f"{invalid_count} row(s) have a non-numeric {column}")

    invalid_date_count = connection.execute(
        """
        SELECT count(*)
        FROM raw
        WHERE nullif(trim(collected_at), '') IS NOT NULL
          AND try_cast(trim(collected_at) AS DATE) IS NULL
        """
    ).fetchone()[0]
    if invalid_date_count:
        raise ValueError(
            f"{invalid_date_count} row(s) have collected_at outside YYYY-MM-DD format"
        )

    return row_count


def _normalize(connection):
    connection.execute(
        """
        CREATE TEMP TABLE incoming AS
        SELECT
            trim(listing_id) AS listing_id,
            trim(source) AS source,
            trim(provider_name) AS provider_name,
            trim(zip_code) AS zip_code,
            trim(city) AS city,
            upper(trim(state)) AS state,
            trim(service_type) AS service_type,
            coalesce(trim(pet_types), '') AS pet_types,
            try_cast(nullif(trim(price_usd), '') AS DOUBLE) AS price_usd,
            coalesce(trim(price_unit), '') AS price_unit,
            try_cast(nullif(trim(rating), '') AS DOUBLE) AS rating,
            try_cast(nullif(trim(review_count), '') AS INTEGER) AS review_count,
            trim(description) AS description,
            coalesce(trim(profile_url), '') AS profile_url,
            coalesce(
                try_cast(nullif(trim(collected_at), '') AS DATE),
                current_date
            ) AS collected_at,
            lower(concat_ws(
                ' ', provider_name, zip_code, city, state, service_type,
                pet_types, description
            )) AS search_text
        FROM raw
        """
    )


def build_catalog(input_paths, output_path, mode="replace"):
    if mode not in {"replace", "upsert"}:
        raise ValueError("mode must be 'replace' or 'upsert'")

    output_path = Path(output_path).resolve()
    with duckdb.connect() as connection:
        resolved_inputs = load_delimited_files(connection, input_paths)
        incoming_count = _validate_raw(connection)
        _normalize(connection)

        replaced_count = 0
        if mode == "upsert" and output_path.is_file():
            replaced_count = connection.execute(
                """
                SELECT count(*)
                FROM read_parquet(?) existing
                INNER JOIN incoming USING (listing_id)
                """,
                [str(output_path)],
            ).fetchone()[0]
            connection.execute(
                """
                CREATE TEMP TABLE final_catalog AS
                SELECT existing.*
                FROM read_parquet(?) existing
                WHERE listing_id NOT IN (SELECT listing_id FROM incoming)
                UNION ALL BY NAME
                SELECT * FROM incoming
                """,
                [str(output_path)],
            )
        else:
            connection.execute("CREATE TEMP TABLE final_catalog AS SELECT * FROM incoming")

        final_count = connection.execute(
            "SELECT count(*) FROM final_catalog"
        ).fetchone()[0]
        write_table_as_parquet(
            connection,
            "final_catalog",
            output_path,
            order_by=("zip_code", "service_type", "provider_name"),
        )

    return {
        "input_files": [str(path) for path in resolved_inputs],
        "incoming_count": incoming_count,
        "replaced_count": replaced_count,
        "final_count": final_count,
        "output_path": str(output_path),
        "built_on": date.today().isoformat(),
        "mode": mode,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build or update the pet-service Parquet catalog from one or more "
            "comma-separated or tab-separated files."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        nargs="+",
        type=Path,
        help="One or more CSV, TSV, TAB, or delimited text files",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("replace", "upsert"),
        default="replace",
        help="Replace the catalog or update rows by listing_id (default: replace)",
    )
    args = parser.parse_args()

    report = build_catalog(args.input, args.output, mode=args.mode)
    print(
        f"Read {report['incoming_count']} rows from {len(report['input_files'])} file(s); "
        f"replaced {report['replaced_count']}; wrote {report['final_count']} rows "
        f"to {report['output_path']}"
    )


if __name__ == "__main__":
    main()
