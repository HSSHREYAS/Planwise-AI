"""
Unit tests for location handling: geocoder helpers, live-places
normalization/ranking, currency helpers and tool routing. No network access.
"""

import pytest

from app import money
from app.geo import geocoder, places
from app.geo.geocoder import Place
from app.tools import common
from app.tools.registry import execute_tool

MYSURU = Place(name="Mysuru", lat=12.3041, lon=76.6529, country="India",
               country_code="in", radius_m=8000)
CAMBRIDGE = Place(name="Cambridge", lat=52.1976, lon=0.1392, country="United Kingdom",
                  country_code="gb", radius_m=6000)


def nominatim_item(name, category, kind, lat=12.31, lon=76.65, importance=0.0, extratags=None, address=None):
    return {
        "name": name, "category": category, "type": kind,
        "lat": str(lat), "lon": str(lon), "importance": importance,
        "osm_type": "node", "osm_id": 42,
        "extratags": extratags or {},
        "address": address or {"road": "Palace Road", "suburb": "Agrahara", "city": "Mysuru"},
    }


class TestGeocoderHelpers:
    def test_to_place_reads_address_and_radius(self):
        place = geocoder._to_place({
            "name": "Mysuru", "lat": "12.30", "lon": "76.65",
            "display_name": "Mysuru, Karnataka, India", "addresstype": "city",
            "address": {"city": "Mysuru", "state": "Karnataka", "country": "India", "country_code": "IN"},
            "boundingbox": ["12.25", "12.36", "76.59", "76.71"],
        })
        assert place.name == "Mysuru"
        assert place.country_code == "in"
        assert place.label == "Mysuru, India"
        assert 2500 <= place.radius_m <= 15000

    def test_label_does_not_repeat_country(self):
        assert Place(name="India", lat=0, lon=0, country="India").label == "India"

    def test_is_cambridge_uk(self):
        assert geocoder.is_cambridge_uk(CAMBRIDGE) is True
        us_cambridge = Place(name="Cambridge", lat=42.37, lon=-71.11, country_code="us")
        assert geocoder.is_cambridge_uk(us_cambridge) is False
        assert geocoder.is_cambridge_uk(None) is False

    def test_remember_and_lookup(self):
        geocoder.remember(MYSURU)
        assert geocoder.lookup(12.30412, 76.65288).name == "Mysuru"
        assert geocoder.lookup(48.85, 2.35) is None or geocoder.lookup(48.85, 2.35).name != "Mysuru"

    def test_search_ignores_too_short_queries(self):
        assert geocoder.search("a") == []
        assert geocoder.search("") == []

    def test_haversine(self):
        assert geocoder.haversine_km(0, 0, 0, 0) == 0
        assert 110 < geocoder.haversine_km(0, 0, 1, 0) < 112


class TestMoney:
    @pytest.mark.parametrize("country,currency", [
        ("in", "INR"), ("gb", "GBP"), ("fr", "EUR"), ("de", "EUR"),
        ("us", "USD"), ("jp", "JPY"), ("zz", "USD"), (None, "USD"),
    ])
    def test_currency_for_country(self, country, currency):
        assert money.currency_for_country(country) == currency

    def test_format_money(self):
        assert money.format_money(12000, "INR") == "₹12,000"
        assert money.format_money(35.4, "GBP") == "£35"
        assert money.format_money(10, "SEK") == "SEK 10"
        assert money.format_money(None, "USD") == "-"

    @pytest.mark.parametrize("text,currency", [
        ("budget of 5000 rupees", "INR"), ("under ₹2000", "INR"), ("£200 weekend", "GBP"),
        ("300 dollars", "USD"), ("about 150 euros", "EUR"), ("plan a 2 day trip", None),
    ])
    def test_detect_currency(self, text, currency):
        assert money.detect_currency(text) == currency

    def test_estimates_scale_with_currency(self):
        assert money.estimate_meal_cost("cheap", "INR") > money.estimate_meal_cost("cheap", "GBP")
        assert money.estimate_meal_cost("expensive", "USD") > money.estimate_meal_cost("cheap", "USD")
        assert money.estimate_hotel_cost("moderate", "INR") > money.estimate_meal_cost("moderate", "INR")

    def test_tight_budget_threshold(self):
        assert money.tight_daily_budget(None) == 300.0
        assert money.tight_daily_budget("GBP") < money.tight_daily_budget("INR")


class TestPlacesNormalization:
    def test_classify(self):
        assert places._classify(nominatim_item("X", "tourism", "hotel")) == "hotel"
        assert places._classify(nominatim_item("X", "tourism", "guest_house")) == "hotel"
        assert places._classify(nominatim_item("X", "amenity", "restaurant")) == "restaurant"
        assert places._classify(nominatim_item("X", "amenity", "cafe")) == "restaurant"
        assert places._classify(nominatim_item("X", "tourism", "museum")) == "attraction"
        assert places._classify(nominatim_item("X", "historic", "castle")) == "attraction"
        assert places._classify(nominatim_item("X", "railway", "station")) == "transport"
        assert places._classify(nominatim_item("X", "aeroway", "aerodrome")) == "transport"
        assert places._classify(nominatim_item("X", "highway", "bus_stop")) is None
        assert places._classify(nominatim_item("X", "amenity", "parking")) is None

    def test_normalize_restaurant(self):
        item = nominatim_item(
            "Om Shanthi Vegetarian Restaurant", "amenity", "restaurant",
            extratags={"cuisine": "indian;south_indian", "phone": "+91 1", "website": "https://x.test",
                       "opening_hours": "Mo-Su 07:00-22:00"},
        )
        rec = places._normalize(item, "restaurant", MYSURU)
        assert rec["name"] == "Om Shanthi Vegetarian Restaurant"
        assert rec["food"] == "indian, south indian"
        assert rec["vegetarian"] == "yes"
        assert rec["address"] == "Palace Road, Agrahara, Mysuru"
        assert rec["area"] == "Agrahara"
        assert rec["source"] == "openstreetmap"
        assert rec["map_url"] == "https://www.openstreetmap.org/node/42"
        assert isinstance(rec["distance_km"], float)

    def test_normalize_hotel_and_attraction(self):
        hotel = places._normalize(
            nominatim_item("Grand", "tourism", "hotel", extratags={"stars": "4S", "internet_access": "wlan"}),
            "hotel", MYSURU)
        assert hotel["stars"] == "4" and hotel["internet"] == "yes" and hotel["type"] == "hotel"

        palace = places._normalize(
            nominatim_item("Mysore Palace", "historic", "castle", importance=0.4, extratags={"fee": "yes"}),
            "attraction", MYSURU)
        assert palace["type"] == "palace" and palace["entrance_fee"] == "ticketed"

        park = places._normalize(
            nominatim_item("City Museum", "tourism", "museum", extratags={"fee": "no"}), "attraction", MYSURU)
        assert park["entrance_fee"] == "free"

    def test_normalize_transport(self):
        airport = places._normalize(
            nominatim_item("Mysore Airport", "aeroway", "aerodrome", extratags={"iata": "MYQ"}),
            "transport", MYSURU)
        assert airport["type"] == "airport" and airport["code"] == "MYQ"
        metro = places._normalize(
            nominatim_item("Central", "railway", "station", extratags={"station": "subway"}),
            "transport", MYSURU)
        assert metro["type"] == "metro station"

    def test_normalize_rejects_unnamed_or_broken_items(self):
        assert places._normalize(nominatim_item("", "amenity", "restaurant"), "restaurant", MYSURU) is None
        broken = nominatim_item("X", "amenity", "restaurant")
        broken["lat"] = "not-a-number"
        assert places._normalize(broken, "restaurant", MYSURU) is None

    def test_notable_places_rank_first(self, monkeypatch):
        items = [
            nominatim_item("Tiny Gallery", "tourism", "gallery", importance=0.0),
            nominatim_item("Mysore Palace", "historic", "castle", importance=0.45,
                           extratags={"wikidata": "Q1"}),
            nominatim_item("A Bus Stop", "highway", "bus_stop"),
        ]
        monkeypatch.setattr(geocoder, "category_search", lambda term, viewbox, limit=40: items)
        monkeypatch.setattr(places, "_cache", {})
        result = places.fetch_places(MYSURU, ["attraction"])["attraction"]
        assert [r["name"] for r in result] == ["Mysore Palace", "Tiny Gallery"]

    def test_fetch_reports_service_failure_as_none(self, monkeypatch):
        monkeypatch.setattr(geocoder, "category_search", lambda term, viewbox, limit=40: None)
        monkeypatch.setattr(places, "_cache", {})
        assert places.fetch_places(MYSURU, ["hotel"]) == {"hotel": None}

    def test_fetch_uses_cache(self, monkeypatch):
        calls = []

        def fake_search(term, viewbox, limit=40):
            calls.append(term)
            return [nominatim_item("Cafe One", "amenity", "cafe")]

        monkeypatch.setattr(geocoder, "category_search", fake_search)
        monkeypatch.setattr(places, "_cache", {})
        places.fetch_places(MYSURU, ["restaurant"])
        places.fetch_places(MYSURU, ["restaurant"])
        assert calls == ["restaurant"]

    def test_public_record_hides_internal_fields(self):
        assert places.public_record({"name": "A", "_score": 3}) == {"name": "A"}

    def test_viewbox_is_left_top_right_bottom(self):
        left, top, right, bottom = (float(x) for x in places._viewbox(MYSURU, 5000).split(","))
        assert left < MYSURU.lon < right
        assert bottom < MYSURU.lat < top


class TestToolRouting:
    def test_helpers(self):
        assert common.as_list(None) == []
        assert common.as_list("veg") == ["veg"]
        assert common.as_list(["a", "", None, "b"]) == ["a", "b"]
        assert common.price_level("cheap") == "cheap"
        assert common.price_level(None, ["luxury"]) == "expensive"
        assert common.price_level(1000) == "moderate"
        assert common.price_level(None, []) is None
        assert common.local_area("the centre of Cambridge") == "centre"
        assert common.local_area("city center") == "centre"
        assert common.local_area("Northampton") is None
        assert common.strip_area_words("the centre of Cambridge") == "Cambridge"
        assert common.strip_area_words("Paris") == "Paris"

    def test_area_words_and_cambridge_use_bundled_dataset(self, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("the geocoder must not be called")

        monkeypatch.setattr(geocoder, "geocode", fail)
        assert common.resolve_place(None, None) == ("local", None)
        assert common.resolve_place("centre", None) == ("local", None)
        assert common.resolve_place("centre of Cambridge", None) == ("local", None)
        assert common.resolve_place("anywhere", CAMBRIDGE.model_dump()) == ("local", None)

    def test_other_places_use_live_data(self, monkeypatch):
        mode, place = common.resolve_place("Mysuru", MYSURU.model_dump())
        assert mode == "live" and place.name == "Mysuru"

        monkeypatch.setattr(geocoder, "geocode", lambda q: MYSURU)
        mode, place = common.resolve_place("Mysuru", None)
        assert mode == "live" and place.name == "Mysuru"

    def test_unknown_place_is_not_served_from_cambridge(self, monkeypatch):
        monkeypatch.setattr(geocoder, "geocode", lambda q: None)
        assert common.resolve_place("Atlantis", None) == ("unknown", None)
        result = execute_tool("hotel_search", {"location": "Atlantis"})
        assert result.success is False and result.results == []
        assert "Atlantis" in result.error

    def test_live_restaurant_search_prefers_vegetarian(self, monkeypatch):
        records = [
            {"name": "Steak Place", "type": "restaurant", "_score": 9},
            {"name": "Green Leaf", "type": "restaurant", "vegetarian": "yes", "_score": 1},
            {"name": "Pizza Roma", "type": "restaurant", "food": "italian, pizza", "_score": 5},
        ]
        monkeypatch.setattr(places, "fetch_places", lambda place, domains: {"restaurant": list(records)})
        result = execute_tool("restaurant_search", {
            "location": "Mysuru", "place": MYSURU.model_dump(), "preferences": ["vegetarian"],
        })
        assert result.success is True
        assert result.results[0]["name"] == "Green Leaf"
        assert all("_score" not in r for r in result.results)

        result = execute_tool("restaurant_search", {
            "location": "Mysuru", "place": MYSURU.model_dump(), "preferences": ["italian"],
        })
        assert result.results[0]["name"] == "Pizza Roma"

    def test_live_lookup_failure_is_reported(self, monkeypatch):
        monkeypatch.setattr(places, "fetch_places", lambda place, domains: {domains[0]: None})
        for tool in ("hotel_search", "restaurant_search", "attraction_search", "transport_search"):
            result = execute_tool(tool, {"location": "Mysuru", "place": MYSURU.model_dump()})
            assert result.success is False
            assert "unavailable" in result.error

    def test_cambridge_results_are_tagged_with_source(self):
        result = execute_tool("hotel_search", {"location": "centre", "budget": "cheap"})
        assert result.success and result.results
        assert all(r["source"] == "multiwoz" for r in result.results)
