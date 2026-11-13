import os
import tempfile
from pathlib import Path
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

class AuthCatalog:
    def __init__(self, users_path, services_path):
        self.users_path = Path(users_path)
        self.services_path = Path(services_path)

    def _init_table(self, path):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            schema = pa.schema([
                ("user_id", pa.string()),
                ("name", pa.string()),
                ("address", pa.string()),
                ("zip_code", pa.string()),
                ("contact", pa.string()),
                ("password", pa.string()),
                ("service_type", pa.string()),
                ("description", pa.string()),
                ("price_usd", pa.float64()),
            ])
            empty_table = pa.Table.from_batches([], schema=schema)
            pq.write_table(empty_table, path)

    def register(self, account_type, data):
        path = self.services_path if account_type == "service" else self.users_path
        self._init_table(path)

        user_id = str(data.get("user_id", "")).strip()
        name = str(data.get("name", "")).strip()
        address = str(data.get("address", "")).strip()
        zip_code = str(data.get("zip_code", "")).strip()
        contact = str(data.get("contact", "")).strip()
        password = str(data.get("password", "")).strip()

        if not user_id or not name or not password:
            raise ValueError("User ID, Name, and Password are required.")

        conn = duckdb.connect(":memory:")
        try:
            parquet_str = str(path)
            existing = conn.execute("SELECT count(*) FROM read_parquet(?) WHERE LOWER(TRIM(user_id)) = LOWER(TRIM(?))", [parquet_str, user_id]).fetchone()[0]
            if existing > 0:
                raise ValueError("User ID already exists. Please choose another or login.")

            new_row = {
                "user_id": user_id,
                "name": name,
                "address": address,
                "zip_code": zip_code,
                "contact": contact,
                "password": password,
                "service_type": str(data.get("service_type", "General Pet Care")),
                "description": str(data.get("description", "Registered local service provider")),
                "price_usd": float(data.get("price_usd", 50.0))
            }

            table = pq.read_table(path)
            new_table = pa.Table.from_pylist([new_row])
            combined = pa.concat_tables([table, new_table])
            pq.write_table(combined, path)

            return new_row
        finally:
            conn.close()

    def login(self, account_type, user_id, password):
        path = self.services_path if account_type == "service" else self.users_path
        self._init_table(path)

        conn = duckdb.connect(":memory:")
        try:
            parquet_str = str(path)
            res = conn.execute(
                "SELECT user_id, name, address, zip_code, contact, service_type, description, price_usd FROM read_parquet(?) WHERE LOWER(TRIM(user_id)) = LOWER(TRIM(?)) AND password = ?",
                [parquet_str, user_id, password]
            ).fetchone()
            if not res:
                raise ValueError("Invalid User ID or Password.")
            return {
                "user_id": res[0],
                "name": res[1],
                "address": res[2],
                "zip_code": res[3],
                "contact": res[4],
                "service_type": res[5],
                "description": res[6],
                "price_usd": res[7],
                "account_type": account_type
            }
        finally:
            conn.close()

    def reset_password(self, account_type, name, address, new_password):
        path = self.services_path if account_type == "service" else self.users_path
        self._init_table(path)

        conn = duckdb.connect(":memory:")
        try:
            parquet_str = str(path)
            res = conn.execute(
                "SELECT user_id FROM read_parquet(?) WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) AND LOWER(TRIM(address)) = LOWER(TRIM(?))",
                [parquet_str, name, address]
            ).fetchone()

            if not res:
                raise ValueError("No account found matching that Name and Address.")

            user_id = res[0]

            df = conn.execute("SELECT * FROM read_parquet(?)", [parquet_str]).fetchdf()
            df.loc[df["user_id"] == user_id, "password"] = new_password
            updated_table = pa.Table.from_pandas(df)
            pq.write_table(updated_table, path)

            return {"success": True, "user_id": user_id}
        finally:
            conn.close()

    def get_services_by_zip(self, zip_code):
        self._init_table(self.services_path)
        conn = duckdb.connect(":memory:")
        try:
            parquet_str = str(self.services_path)
            df = conn.execute(
                "SELECT user_id as listing_id, name as provider_name, address, zip_code, contact, service_type, description, price_usd FROM read_parquet(?) WHERE zip_code = ?",
                [parquet_str, zip_code]
            ).fetchdf()
            records = df.to_dict(orient="records")
            for r in records:
                r["source"] = "Registered Services"
                r["city"] = r["address"]
                r["state"] = "CA"
                r["rating"] = 5.0
                r["review_count"] = 1
                r["price_unit"] = "per service"
                r["profile_url"] = f"mailto:{r['contact']}"
            return records
        finally:
            conn.close()
