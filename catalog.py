import datetime
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


class CatalogError(Exception):
    """Raised when there is an