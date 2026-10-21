#!/usr/bin/env python3
"""Care.com pet-sitter adapter (template — set URL/selector for your OC ZIPs)."""
# Copy pw_other_adapter.py / pw_collect.py; change URL and extract logic.
# Example URL pattern: https://www.care.com/pet-sitter?location=92694
# After collecting TSV, merge: python build_catalog.py --input data/care_sitters.tsv --output data/pet_services.parquet --mode upsert
from pathlib import Path
print("Care adapter template ready. Use Playwright, set URL/selector, output to data/care_sitters.tsv, then merge.")
