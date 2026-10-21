"""Reusable CSV and TSV loading helpers for searchable Parquet catalogs."""

import os
import re
import tempfile
from pathlib import Path


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_input_paths(input_paths):
    if isinstance(input_paths, (str, Path)):
        input_paths = [input_paths]

    paths = [Path(path).resolve() for path in input_paths]
    if not paths:
        raise ValueError("Provide at least one CSV or TSV input file")

    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Input file not found: {', '.join(missing)}")
    return paths


def load_delimited_files(connection, input_paths, table_name="raw"):
    """Load one or more CSV or TSV files as strings into a DuckDB table.

    DuckDB detects the delimiter independently for each input. ``union_by_name``
    permits columns to appear in different orders and leaves missing optional
    columns null.
    """
    if not IDENTIFIER_RE.fullmatch(table_name):
        raise ValueError(f"Unsafe table name: {table_name!r}")

    paths = normalize_input_paths(input_paths)
    connection.execute(
        f"""
        CREATE TEMP TABLE {table_name} AS
        SELECT *
        FROM read_csv_auto(
            ?,
            all_varchar=true,
            header=true,
            union_by_name=true,
            null_padding=true
        )
        """,
        [[str(path) for path in paths]],
    )
    return paths


def table_columns(connection, table_name="raw"):
    if not IDENTIFIER_RE.fullmatch(table_name):
        raise ValueError(f"Unsafe table name: {table_name!r}")
    return {row[0] for row in connection.execute(f"DESCRIBE {table_name}").fetchall()}


def write_table_as_parquet(connection, table_name, output_path, order_by=()):
    """Write a table through a temporary file, then atomically replace output."""
    if not IDENTIFIER_RE.fullmatch(table_name):
        raise ValueError(f"Unsafe table name: {table_name!r}")
    for column in order_by:
        if not IDENTIFIER_RE.fullmatch(column):
            raise ValueError(f"Unsafe sort column: {column!r}")

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.",
        suffix=".parquet",
        dir=output_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()

    order_sql = f" ORDER BY {', '.join(order_by)}" if order_by else ""
    try:
        connection.execute(
            f"COPY (SELECT * FROM {table_name}{order_sql}) "
            "TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 10000)",
            [str(temporary_path)],
        )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return output_path
