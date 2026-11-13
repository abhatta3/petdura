import os
from pathlib import Path
import re
from flask import Flask, jsonify, request, send_from_directory

from catalog import CatalogError, PetServiceCatalog, json_safe
from auth_catalog import AuthCatalog


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG = BASE_DIR / "data" / "pet_services.parquet"
USERS_CATALOG = BASE_DIR / "data" / "users.parquet"
SERVICES_CATALOG = BASE_DIR / "data" / "services.parquet"


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


def create_app(catalog_path=None, users_path=None, services_path=None):
    application = Flask(__name__, static_folder="static", static_url_path="")
    application.config["MAX_CONTENT_LENGTH"] = 1_000_000
    application.config["SEARCH_RESULT_LIMIT"] = _integer_environment(
        "SEARCH_RESULT_LIMIT", 500, 1, 1000
    )

    selected_catalog = Path(
        catalog_path or os.environ.get("PET_SERVICE_PARQUET", DEFAULT_CATALOG)
    ).expanduser().resolve()
    service_catalog = PetServiceCatalog(selected_catalog)

    selected_users = Path(users_path or USERS_CATALOG).expanduser().resolve()
    selected_services = Path(services_path or SERVICES_CATALOG).expanduser().resolve()
    auth_catalog = AuthCatalog(selected_users, selected_services)

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

    @application.route("/api/auth/register", methods=["POST"])
    def api_register():
        payload = request.get_json(force=True, silent=True) or {}
        account_type = str(payload.get("account_type", "user")).strip()
        try:
            res = auth_catalog.register(account_type, payload)
            # Hide password in response
            res.pop("password", None)
            return jsonify({"success": True, "account": res})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @application.route("/api/auth/login", methods=["POST"])
    def api_login():
        payload = request.get_json(force=True, silent=True) or {}
        account_type = str(payload.get("account_type", "user")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        password = str(payload.get("password", "")).strip()
        try:
            user_data = auth_catalog.login(account_type, user_id, password)
            user_data.pop("password", None)
            return jsonify({"success": True, "user": user_data})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @application.route("/api/auth/reset-password", methods=["POST"])
    def api_reset_password():
        payload = request.get_json(force=True, silent=True) or {}
        account_type = str(payload.get("account_type", "user")).strip()
        name = str(payload.get("name", "")).strip()
        address = str(payload.get("address", "")).strip()
        new_password = str(payload.get("new_password", "")).strip()
        try:
            res = auth_catalog.reset_password(account_type, name, address, new_password)
            return jsonify(res)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @application.route("/api/catalog", methods=["GET"])
    def catalog_summary():
        try:
            summary = service_catalog.summary()
            conn = service_catalog._get_connection()
            try:
                parquet_str = str(service_catalog.catalog_path)
                df = conn.execute(
                    "SELECT zip_code, MIN(COALESCE(city,'') || ', ' || COALESCE(state,'')) as address, source, count(*) as count, string_agg(DISTINCT service_type, ', ') as services FROM read_parquet(?) GROUP BY zip_code, source ORDER BY zip_code, source",
                    [parquet_str]
                ).fetchdf()
                clean = []
                seen = set()
                for _, row in df.iterrows():
                    adr_raw = str(row.get("address") or "").strip()
                    zip_code = str(row.get("zip_code") or "").strip()
                    adr = adr_raw.replace(", CA , CA", ", CA").replace(", CA ", ", ").strip(", ")
                    if zip_code and zip_code not in adr:
                        adr = f"{adr}, {zip_code}".strip(", ")
                    key = (zip_code, str(row.get("provider") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    clean.append({"zip_code": zip_code, "address": adr, "provider": str(row.get("provider") or ""), "count": int(row.get("count") or 0)})
                summary["zip_codes"] = clean
            finally:
                conn.close()
            summary["service_types"] = service_catalog.service_types()
            summary["sources"] = service_catalog.sources()
            return jsonify(json_safe(summary))
        except CatalogError as exc:
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

        # Check registered services first for this zip code
        results = []
        if zip_code:
            try:
                results = auth_catalog.get_services_by_zip(zip_code)
            except Exception:
                pass

        if not results:
            # Fall back to public catalog
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
