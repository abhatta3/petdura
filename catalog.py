import datetime
import math
import os
import re
import tempfile
from pathlib import Path

import duckdb


ZIP_RE = re.compile(r"^\d{5}$")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "for", "i", "in", "is", "my", "need",
    "of", "on", "or", "the", "to", "with",
}


def json_safe(value):
    """Convert NaN/Infinity floats to None so payloads stay valid JSON."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    try:
        import pandas as pd
        import numpy as np
        if isinstance(value, (np.ndarray, list, tuple, dict)):
            pass  # handled by recursive branch above
        elif isinstance(value, pd.Timestamp):
            return str(value) if pd.notna(value) else None
        elif hasattr(value, '__len__') and len(value) > 1:
            pass  # array-like, skip scalar NaN check
        elif pd.isna(value) and not isinstance(value, (str, bool, int, float, list, dict, type(None))):
            return None
    except Exception:
        pass
    return value


class CatalogError(Exception):
    """Raised when there is an issue accessing or querying the catalog."""


class PetServiceCatalog:
    def __init__(self, catalog_path):
        self.catalog_path = Path(catalog_path)

    def _get_connection(self):
        return duckdb.connect(":memory:")

    def summary(self):
        if not self.catalog_path.exists():
            raise CatalogError(f"Catalog file does not exist: {self.catalog_path}")

        conn = self._get_connection()
        try:
            parquet_str = str(self.catalog_path)
            res = conn.execute(
                f"""
                SELECT
                    count(*) AS listing_count,
                    count(DISTINCT zip_code) AS zip_count,
                    count(DISTINCT service_type) AS service_type_count
                FROM read_parquet(?)
                """,
                [parquet_str],
            ).fetchone()
            return {
                "listing_count": res[0] if res else 0,
                "zip_count": res[1] if res else 0,
                "service_type_count": res[2] if res else 0,
            }
        except Exception as exc:
            raise CatalogError(f"Failed to read catalog summary: {exc}") from exc
        finally:
            conn.close()

    def service_types(self):
        if not self.catalog_path.exists():
            raise CatalogError(f"Catalog file does not exist: {self.catalog_path}")

        conn = self._get_connection()
        try:
            parquet_str = str(self.catalog_path)
            rows = conn.execute(
                """
                SELECT DISTINCT service_type
                FROM read_parquet(?)
                WHERE service_type IS NOT NULL AND service_type <> ''
                ORDER BY service_type
                """,
                [parquet_str],
            ).fetchall()
            return [row[0] for row in rows]
        except Exception as exc:
            raise CatalogError(f"Failed to read service types: {exc}") from exc
        finally:
            conn.close()

    def sources(self):
        if not self.catalog_path.exists():
            raise CatalogError(f"Catalog file does not exist: {self.catalog_path}")
        conn = self._get_connection()
        try:
            parquet_str = str(self.catalog_path)
            rows = conn.execute(
                "SELECT DISTINCT source FROM read_parquet(?) WHERE source IS NOT NULL AND source <> '' ORDER BY source",
                [parquet_str],
            ).fetchall()
            return [row[0] for row in rows]
        except Exception as exc:
            raise CatalogError(f"Failed to read sources: {exc}") from exc
        finally:
            conn.close()

    def search(self, zip_code, description="", limit=500, service_type=None, max_price=None, source=None):
        if not ZIP_RE.match(zip_code):
            raise ValueError(f"Invalid ZIP code format: {zip_code}")

        if not self.catalog_path.exists():
            raise CatalogError(f"Catalog file does not exist: {self.catalog_path}")

        tokens = [
            tok
            for tok in TOKEN_RE.findall(description.lower())
            if tok not in STOPWORDS
        ]

        conditions = ["zip_code = ?"]
        params = [str(self.catalog_path), zip_code]

        if service_type:
            conditions.append("service_type = ?")
            params.append(service_type)

        if source:
            conditions.append("source = ?")
            params.append(source)

        if max_price is not None:
            conditions.append("(price_usd IS NULL OR price_usd <= ?)")
            params.append(float(max_price))

        if tokens:
            conditions.append("(" + " OR ".join(["search_text LIKE ?" for _ in tokens]) + ")")
            params.extend(f"%{tok}%" for tok in tokens)

        query = f"""
            SELECT *
            FROM read_parquet(?)
            WHERE {" AND ".join(conditions)}
            LIMIT ?
        """
        params.append(limit)

        conn = self._get_connection()
        try:
            df = conn.execute(query, params).fetchdf()
            results = df.to_dict(orient="records")
            return json_safe(results)
        except Exception as exc:
            raise CatalogError(f"Search query failed: {exc}") from exc
        finally:
            conn.close()

    def ingest_batch(self, records):
        if not isinstance(records, list) or not records:
            raise ValueError("Records must be a non-empty list of dictionaries.")

        for i, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError(f"Record at index {i} must be a dictionary.")
            if "zip_code" not in item or not ZIP_RE.match(str(item["zip_code"])):
                raise ValueError(f"Record at index {i} must have a valid 5-digit zip_code.")

        conn = self._get_connection()
        try:
            self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
            new_df = duckdb.arrow.pa.Table.from_pylist(records)
            conn.register("incoming_records", new_df)

            with tempfile.NamedTemporaryFile(
                dir=self.catalog_path.parent, suffix=".parquet", delete=False
            ) as tmp_file:
                temp_output_path = tmp_file.name

            if self.catalog_path.exists():
                parquet_str = str(self.catalog_path)
                conn.execute(
                    f"""
                    COPY (
                        SELECT * FROM read_parquet(?)
                        UNION ALL
                        SELECT * FROM incoming_records
                    ) TO ? (FORMAT PARQUET)
                    """,
                    [parquet_str, temp_output_path],
                )
            else:
                conn.execute(
                    """
                    COPY (SELECT * FROM incoming_records) TO ? (FORMAT PARQUET)
                    """,
                    [temp_output_path],
                )

            os.replace(temp_output_path, self.catalog_path)
            return len(records)
        except Exception as exc:
            raise CatalogError(f"Batch ingestion failed: {exc}") from exc
        finally:
            conn.close()
