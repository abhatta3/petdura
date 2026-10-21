import tempfile
import unittest
from pathlib import Path

from app import create_app
from build_catalog import build_catalog


PROJECT_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DATA = PROJECT_DIR / "data" / "sample_pet_services.csv"


class ApplicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.parquet_path = Path(cls.temp_dir.name) / "catalog.parquet"
        build_catalog(SAMPLE_DATA, cls.parquet_path)
        cls.client = create_app(cls.parquet_path).test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_health_reports_ready_catalog(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "ok", "listing_count": 15, "zip_count": 8},
        )

    def test_search_uses_selected_catalog(self):
        response = self.client.post(
            "/api/search",
            json={"zip_code": "92101", "description": "large anxious dog"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"][0]["listing_id"], "sample-001")

    def test_missing_catalog_health_does_not_expose_server_path(self):
        missing = Path(self.temp_dir.name) / "private" / "missing.parquet"
        response = create_app(missing).test_client().get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(missing), response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
