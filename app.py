import os
from pathlib import Path

import re
from flask import Flask, jsonify, request, send_from_directory

from catalog import CatalogError, PetServiceCatalog, json_safe


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
                    "SELECT zip_code, (city || ', ' || state) as address, source, count(*) as count, string_agg(DISTINCT service_type, ', ') as services FROM read_parquet(?) GROUP BY zip_code, city, state, source ORDER BY zip_code, source",
                    [parquet_str]
                ).fetchdf()
                df = df.rename(columns={"source":"provider","count":"count"})
                # Drop separate city/state; keep combined address and provider/count
                for _, row in df.iterrows():
                    pass  # row objects already have correct fields
                # Build clean flat dict
                clean = []
                for _, row in df.iterrows():
                    adr = str(row.get("address") or "").replace(", CA , CA", ", CA").replace(", CA ", ", ").strip(", ")
                    clean.append({"zip_code": str(row.get("zip_code") or ""), "address": adr, "provider": str(row.get("provider") or ""), "count": int(row.get("count") or 0)})
                summary["zip_codes"] = clean
            finally:
                conn.close()
            summary["service_types"] = service_catalog.service_types()
            summary["sources"] = service_catalog.sources()
            return jsonify(json_safe(summary))
        except CatalogError as exc:
            return jsonify({"error": str(exc)}), 503
            return jsonify({"error": str(exc)}), 503

    @application.route("/api/search", methods=["POST"])
    def search():
        payload = request.get_json(force=True, silent=True) or {}
        zip_code = str(payload.get("zip_code", "")).strip()
        description = str(payload.get("description", "")).strip()
        service_type = str(payload.get("service_type", "")).strip()
        source = str(payload.get("source", "")).strip()
        max_price_raw = payload.get("max_price")

        max_price = None
        if max_price_raw not in (None, ""):
            try:
                max_price = float(max_price_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Maximum rate must be a number", "results": []}), 400
            if max_price < 0:
                return jsonify({"error": "Maximum rate cannot be negative", "results": []}), 400

        try:
            results = service_catalog.search(
                zip_code,
                description,
                limit=application.config["SEARCH_RESULT_LIMIT"],
                service_type=service_type or None,
                max_price=max_price,
                source=source or None,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "results": []}), 400
        except CatalogError as exc:
            return jsonify({"error": str(exc), "results": []}), 503

        response_payload = {
            "query": {
                "zip_code": zip_code,
                "description": description,
                "service_type": service_type or None,
                "max_price": max_price,
            },
            "count": len(results),
            "results": results,
        }
        return jsonify(json_safe(response_payload))

    return application


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=_integer_environment("APP_PORT", 5050, 1, 65535),
        debug=_boolean_environment("APP_DEBUG"),
    )
