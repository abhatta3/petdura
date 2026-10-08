import re
from pathlib import Path

import duckdb


ZIP_RE = re.compile(r"^\d{5}$")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "for", "i", "in", "is", "my", "need",
    "of", "or", "pet", "please", "service", "services", "the", "to",
    "with",
}


class CatalogError(RuntimeError):
    pass


def _description_tokens(description):
    return [
        token
        for token in TOKEN_RE.findall(description.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


class PetServiceCatalog:
    def __init__(self, parquet_path):
        self.parquet_path = Path(parquet_path)

    def _require_catalog(self):
        if not self.parquet_path.is_file():
            raise CatalogError(
                "Catalog is unavailable. Build it or set PET_SERVICE_PARQUET "
                "to an existing Parquet file."
            )

    def summary(self):
        self._require_catalog()
        with duckdb.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    count(*) AS listing_count,
                    count(DISTINCT zip_code) AS zip_count,
                    min(zip_code) AS first_zip,
                    max(zip_code) AS last_zip,
                    cast(max(collected_at) AS VARCHAR) AS latest_collection
                FROM read_parquet(?)
                """,
                [str(self.parquet_path)],
            ).fetchone()

        return {
            "listing_count": row[0],
            "zip_count": row[1],
            "first_zip": row[2],
            "last_zip": row[3],
            "latest_collection": row[4],
        }

    def search(self, zip_code, description="", limit=500):
        self._require_catalog()
        if not ZIP_RE.fullmatch(zip_code):
            raise ValueError("Enter a five-digit ZIP code.")

        tokens = list(dict.fromkeys(_description_tokens(description)))
        score_terms = [
            "CASE WHEN search_text LIKE ? THEN 1 ELSE 0 END" for _ in tokens
        ]
        score_sql = " + ".join(score_terms) if score_terms else "0"
        match_sql = "WHERE relevance > 0" if tokens else ""
        parameters = [str(self.parquet_path), zip_code]
        parameters.extend(f"%{token}%" for token in tokens)
        parameters.append(max(1, min(int(limit), 1000)))

        query = f"""
            WITH zip_rows AS (
                SELECT *
                FROM read_parquet(?)
                WHERE zip_code = ?
            ), scored AS (
                SELECT
                    listing_id,
                    source,
                    provider_name,
                    zip_code,
                    city,
                    state,
                    service_type,
                    pet_types,
                    price_usd,
                    price_unit,
                    rating,
                    review_count,
                    description,
                    profile_url,
                    cast(collected_at AS VARCHAR) AS collected_at,
                    {score_sql} AS relevance
                FROM zip_rows
            )
            SELECT *
            FROM scored
            {match_sql}
            ORDER BY
                relevance DESC,
                rating DESC NULLS LAST,
                review_count DESC NULLS LAST,
                price_usd ASC NULLS LAST,
                provider_name,
                service_type
            LIMIT ?
        """

        with duckdb.connect() as connection:
            cursor = connection.execute(query, parameters)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
