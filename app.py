import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from catalog import CatalogError, PetServiceCatalog


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG = BASE_DIR / "data" / "pet_services.parquet"


def _integer_environment(name, default, minimum, maximum):
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean_environment(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(catalog_path=None):
    application = Flask(__name__, static_folder="static", static_url_path="")
    application.config["MAX_CONTENT_LENGTH"] = 1_000_000
    application.config["SEARCH_RESULT_LIMIT"] = _integer_environment(
        "SEARCH_RESULT_LIMIT", 500, 1, 1000
    )

    selected_catalog = Path(
        catalog_path or os.environ.get("PET_SERVICE_PARQUET", DEFAULT_CATALOG)
    ).expanduser().resolve()
    service_catalog = PetServiceCatalog(selected_catalog)

    @application.route("/")
    def index():
        return send_from_directory(application.static_folder, "index.html")

    @application.route("/api/health", methods=["GET"])
    def health():
        try:
            summary = service_catalog.summary()
        except CatalogError:
            return jsonify({"status": "unavailable"}), 503
        return jsonify(
            {
                "status": "ok",
                "listing_count": summary["listing_count"],
                "zip_count": summary["zip_count"],
            }
        )

    @application.route("/api/catalog", methods=["GET"])
    def catalog_summary():
        try:
            summary = service_catalog.summary()
            conn = service_catalog._get_connection()
            try:
                parquet_str = str(service_catalog.catalog_path)
                df = conn.execute(
                    """
                    SELECT zip_code, city, state, count(*) as listing_count,
                           string_agg(DISTINCT service_type, ', ') as services
                    FROM read_parquet(?)
                    GROUP BY zip_code, city, state
                    ORDER BY zip_code
                    """,
                    [parquet_str],
                ).fetchdf()
                summary["zip_codes"] = df.to_dict(orient="records")
            finally:
                conn.close()
            return jsonify(summary)
        except CatalogError as exc:
            return jsonify({"error": str(exc)}), 503

    @application.route("/api/search", methods=["POST"])
    def search():
        payload = request.get_json(force=True, silent=True) or {}
        zip_code = str(payload.get("zip_code", "")).strip()
        description = str(payload.get("description", "")).strip()

        try:
            results = service_catalog.search(
                zip_code,
                description,
                limit=application.config["SEARCH_RESULT_LIMIT"],
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "results": []}), 400
        except CatalogError as exc:
            return jsonify({"error": str(exc), "results": []}), 503

        return jsonify(
            {
                "query": {"zip_code": zip_code, "description": description},
                "count": len(results),
                "results": results,
            }
        )

    return application


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=_integer_environment("APP_PORT", 5050, 1, 65535),
        debug=_boolean_environment("APP_DEBUG"),
    )
