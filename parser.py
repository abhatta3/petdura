"""
Natural-language query parser.

Turns a free-text request ("flights from Chicago to Denver next Friday for
2 people under $400") into a structured dict of search parameters plus a
leftover bag of generic keywords. Rule-based on purpose: a prototype has no
need for a model-backed NLU step, and regex keeps the whole pipeline
dependency-light and inspectable.
"""
import re
from datetime import datetime, timedelta

from dateutil import parser as dateparser

STOPWORDS = {
    "a", "an", "the", "for", "to", "from", "on", "in", "of", "and", "or",
    "with", "me", "please", "find", "show", "search", "i", "want", "need",
    "flights", "flight", "under", "less", "than", "around", "about",
    "people", "person", "passengers", "passenger", "adults", "adult",
    "next", "this", "tomorrow", "ticket", "tickets", "trip", "one", "way",
}

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

CITY_AIRPORTS = {
    "new york": "JFK", "nyc": "JFK", "chicago": "ORD", "denver": "DEN",
    "los angeles": "LAX", "la": "LAX", "san francisco": "SFO",
    "boston": "BOS", "seattle": "SEA", "miami": "MIA", "dallas": "DFW",
    "atlanta": "ATL", "houston": "IAH", "phoenix": "PHX",
    "las vegas": "LAS", "madison": "MSN", "minneapolis": "MSP",
    "washington": "DCA", "austin": "AUS", "portland": "PDX",
    "san diego": "SAN", "philadelphia": "PHL", "detroit": "DTW",
}


def _airport_code(city_name):
    city_name = city_name.strip().lower()
    return CITY_AIRPORTS.get(city_name, city_name.upper()[:3] if city_name else None)


def _extract_route(text):
    m = re.search(
        r"from\s+([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+(?:on|next|this|tomorrow|for|under|less|around|in)\b|[,.]|$)",
        text,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = re.search(r"([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+(?:on|next|this|tomorrow|for|under|less|around|in)\b|[,.]|$)", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return None, None


def _extract_date(text):
    """Returns (iso_date, matched_phrase) so the caller can strip the
    matched phrase out of the leftover-keywords bag."""
    today = datetime.now()

    m = re.search(r"next\s+(" + "|".join(WEEKDAYS) + r")", text)
    if m:
        target = WEEKDAYS[m.group(1)]
        days_ahead = (target - today.weekday() + 7) % 7
        days_ahead = days_ahead + 7 if days_ahead == 0 else days_ahead
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d"), m.group(0)

    m = re.search(r"this\s+(" + "|".join(WEEKDAYS) + r")", text)
    if m:
        target = WEEKDAYS[m.group(1)]
        days_ahead = (target - today.weekday() + 7) % 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d"), m.group(0)

    if "tomorrow" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d"), "tomorrow"

    m = re.search(r"in\s+(\d+)\s+days?", text)
    if m:
        return (today + timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d"), m.group(0)

    m = re.search(
        r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)\b",
        text,
    )
    if m:
        try:
            return dateparser.parse(m.group(1), fuzzy=True, default=today).strftime("%Y-%m-%d"), m.group(0)
        except (ValueError, OverflowError):
            pass

    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1), m.group(0)

    return None, None


def _extract_passengers(text):
    m = re.search(r"(\d+)\s*(?:people|passengers?|adults?|travell?ers?)", text)
    if m:
        return int(m.group(1))
    return 1


def _extract_max_price(text):
    m = re.search(r"(?:under|less than|below|cap(?:ped)? at|max(?:imum)? of)\s*\$?\s*(\d+)", text)
    if m:
        return int(m.group(1)), m.group(0)
    m = re.search(r"\$\s*(\d+)\s*(?:budget|or less|max)", text)
    if m:
        return int(m.group(1)), m.group(0)
    return None, None


def _extract_cabin_class(text):
    for cls in ("first", "business", "premium economy", "economy"):
        if cls in text:
            return cls
    return None


def _extract_keywords(text, consumed_spans):
    cleaned = text
    for span_text in consumed_spans:
        if span_text:
            cleaned = cleaned.replace(span_text.lower(), " ")
    tokens = re.findall(r"[a-z0-9]+", cleaned)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def parse_query(raw_text):
    text = (raw_text or "").strip().lower()

    origin_city, destination_city = _extract_route(text)
    date, date_phrase = _extract_date(text)
    passengers = _extract_passengers(text)
    max_price, price_phrase = _extract_max_price(text)
    cabin_class = _extract_cabin_class(text)

    keywords = _extract_keywords(
        text,
        [origin_city, destination_city, date_phrase, price_phrase, cabin_class],
    )

    return {
        "raw_text": raw_text,
        "origin_city": origin_city.title() if origin_city else None,
        "origin_code": _airport_code(origin_city) if origin_city else None,
        "destination_city": destination_city.title() if destination_city else None,
        "destination_code": _airport_code(destination_city) if destination_city else None,
        "date": date,
        "passengers": passengers,
        "max_price": max_price,
        "cabin_class": cabin_class,
        "keywords": keywords,
    }
