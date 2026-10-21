"""
Mock flight-search connectors.

These simulate what four independent vendor sites would return for the same
parsed query. They are synthetic-data generators, not scrapers: hitting real
flight sites (Google Flights, Kayak, airline sites, ...) programmatically
generally violates their terms of service and requires per-site agreements
or paid APIs, which is out of scope for a local prototype. The random
generation is seeded from the query so repeat searches are stable, and each
vendor is biased differently (budget carrier vs. premium, more/fewer stops)
so the sort/filter UI has something real to do.

To point this at real data later, implement BaseConnector.search() against
a real API (e.g. Amadeus, Duffel, Skyscanner's partner API) or an
authorized scraper, and register it in connectors/__init__.py — nothing
else in the app needs to change.
"""
import hashlib
import random
from datetime import datetime, timedelta

from .base import BaseConnector

AIRLINES = [
    "AeroLine", "ValueJet", "NorthWind Air", "CoastalWings",
    "Summit Airways", "BlueHarbor Air", "Prairie Express",
]


def _seed_for(vendor_name, parsed_query):
    key = "|".join([
        vendor_name,
        str(parsed_query.get("origin_code")),
        str(parsed_query.get("destination_code")),
        str(parsed_query.get("date")),
    ])
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _fake_time(rng, base_hour_range=(5, 22)):
    hour = rng.randint(*base_hour_range)
    minute = rng.choice([0, 15, 20, 30, 45])
    return f"{hour:02d}:{minute:02d}"


def _generate_offers(vendor_name, parsed_query, count, price_range, stop_bias, booking_domain):
    rng = random.Random(_seed_for(vendor_name, parsed_query))
    origin = parsed_query.get("origin_code") or "???"
    destination = parsed_query.get("destination_code") or "???"
    date = parsed_query.get("date") or datetime.now().strftime("%Y-%m-%d")

    offers = []
    for _ in range(count):
        price = rng.randint(*price_range)
        stops = rng.choices([0, 1, 2], weights=stop_bias, k=1)[0]
        duration_minutes = 90 + stops * rng.randint(45, 90) + rng.randint(-20, 40)
        depart = _fake_time(rng)
        depart_dt = datetime.strptime(depart, "%H:%M")
        arrive_dt = depart_dt + timedelta(minutes=duration_minutes)
        airline = rng.choice(AIRLINES)

        offers.append({
            "vendor": vendor_name,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            "date": date,
            "depart_time": depart,
            "arrive_time": arrive_dt.strftime("%H:%M"),
            "duration_minutes": duration_minutes,
            "stops": stops,
            "price": price,
            "currency": "USD",
            "cabin_class": parsed_query.get("cabin_class") or "economy",
            "booking_url": f"https://{booking_domain}/book?{origin}-{destination}-{date}",
        })

    offers.sort(key=lambda o: o["price"])
    return offers


class SkyPathMock(BaseConnector):
    name = "SkyPath"

    def search(self, parsed_query):
        return _generate_offers(
            self.name, parsed_query, count=5,
            price_range=(120, 420), stop_bias=[5, 3, 1],
            booking_domain="skypath.example",
        )


class CloudHopperMock(BaseConnector):
    name = "CloudHopper"

    def search(self, parsed_query):
        return _generate_offers(
            self.name, parsed_query, count=4,
            price_range=(90, 380), stop_bias=[2, 5, 2],
            booking_domain="cloudhopper.example",
        )


class BudgetWingsMock(BaseConnector):
    name = "BudgetWings"

    def search(self, parsed_query):
        return _generate_offers(
            self.name, parsed_query, count=6,
            price_range=(70, 260), stop_bias=[1, 4, 4],
            booking_domain="budgetwings.example",
        )


class NorthStarAirMock(BaseConnector):
    name = "NorthStarAir"

    def search(self, parsed_query):
        return _generate_offers(
            self.name, parsed_query, count=4,
            price_range=(180, 520), stop_bias=[7, 2, 0],
            booking_domain="northstarair.example",
        )
