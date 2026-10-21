import csv
import tempfile
import unittest
from pathlib import Path

from build_catalog import build_catalog
from catalog import PetServiceCatalog


PROJECT_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DATA = PROJECT_DIR / "data" / "sample_pet_services.csv"


class PetServiceCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.parquet_path = Path(cls.temp_dir.name) / "catalog.parquet"
        build_catalog(SAMPLE_DATA, cls.parquet_path)
        cls.catalog = PetServiceCatalog(cls.parquet_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_blank_description_returns_all_services_in_zip(self):
        results = self.catalog.search("92101", "")
        self.assertEqual(len(results), 5)

    def test_description_ranks_matching_services(self):
        results = self.catalog.search("92101", "large anxious dog")
        self.assertEqual(results[0]["listing_id"], "sample-001")

    def test_search_does_not_cross_zip_codes(self):
        results = self.catalog.search("92101", "boarding")
        self.assertEqual(results, [])

    def test_invalid_zip_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid ZIP code format"):
            self.catalog.search("9210", "dog walk")

    def test_summary_reports_catalog_shape(self):
        summary = self.catalog.summary()
        self.assertEqual(summary["listing_count"], 15)
        self.assertEqual(summary["zip_count"], 8)

    def test_tab_separated_input_with_only_required_columns(self):
        path = Path(self.temp_dir.name) / "minimal.tsv"
        output = Path(self.temp_dir.name) / "minimal.parquet"
        fields = [
            "listing_id", "source", "provider_name", "zip_code", "city",
            "state", "service_type", "description",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerow(
                {
                    "listing_id": "tsv-001",
                    "source": "Lab-maintained TSV",
                    "provider_name": "Sample Provider TSV",
                    "zip_code": "92102",
                    "city": "San Diego",
                    "state": "CA",
                    "service_type": "Dog Walking",
                    "description": "Morning walks for energetic dogs",
                }
            )

        report = build_catalog(path, output)
        results = PetServiceCatalog(output).search("92102", "morning walk")
        self.assertEqual(report["final_count"], 1)
        self.assertEqual(results[0]["listing_id"], "tsv-001")
        self.assertEqual(results[0]["pet_types"], "")

    def test_multiple_mixed_delimited_inputs(self):
        fieldnames = [
            "listing_id", "source", "provider_name", "zip_code", "city",
            "state", "service_type", "description",
        ]
        csv_path = Path(self.temp_dir.name) / "one.csv"
        tsv_path = Path(self.temp_dir.name) / "two.tsv"
        output = Path(self.temp_dir.name) / "mixed.parquet"
        rows = [
            {
                "listing_id": "mixed-001", "source": "CSV", "provider_name": "One",
                "zip_code": "92103", "city": "San Diego", "state": "CA",
                "service_type": "Boarding", "description": "Small dog boarding",
            },
            {
                "listing_id": "mixed-002", "source": "TSV", "provider_name": "Two",
                "zip_code": "92104", "city": "San Diego", "state": "CA",
                "service_type": "Drop-In Visits", "description": "Cat visits",
            },
        ]
        for path, delimiter, row in (
            (csv_path, ",", rows[0]),
            (tsv_path, "\t", rows[1]),
        ):
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
                writer.writeheader()
                writer.writerow(row)

        report = build_catalog([csv_path, tsv_path], output)
        self.assertEqual(report["incoming_count"], 2)
        self.assertEqual(PetServiceCatalog(output).summary()["zip_count"], 2)

    def test_upsert_replaces_existing_listing_id(self):
        output = Path(self.temp_dir.name) / "upsert.parquet"
        update_path = Path(self.temp_dir.name) / "update.tsv"
        build_catalog(SAMPLE_DATA, output)
        fields = [
            "listing_id", "source", "provider_name", "zip_code", "city",
            "state", "service_type", "description", "price_usd",
        ]
        with update_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerow(
                {
                    "listing_id": "sample-001",
                    "source": "Updated authorized feed",
                    "provider_name": "Sample Provider 01",
                    "zip_code": "92101",
                    "city": "San Diego",
                    "state": "CA",
                    "service_type": "Dog Walking",
                    "description": "Updated walking description",
                    "price_usd": "31",
                }
            )

        report = build_catalog(update_path, output, mode="upsert")
        rows = PetServiceCatalog(output).search("92101", "")
        updated = next(row for row in rows if row["listing_id"] == "sample-001")
        self.assertEqual(report["replaced_count"], 1)
        self.assertEqual(report["final_count"], 15)
        self.assertEqual(updated["price_usd"], 31)
        self.assertEqual(updated["source"], "Updated authorized feed")


if __name__ == "__main__":
    unittest.main()
