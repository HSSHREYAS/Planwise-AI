"""
PlanWise AI - Live Places Provider

Fetches real hotels, restaurants, attractions and transport hubs around
any coordinates from OpenStreetMap (Nominatim category search - free, no
API key).

Results are normalized to the same record shape the bundled Cambridge
dataset uses (name / type / area / address / food / stars /
entrance_fee ...), ranked by notability and distance, and cached in
memory for an hour.
"""

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.geo import geocoder
from app.geo.geocoder import Place, haversine_km

logger = logging.getLogger(__name__)

DOMAINS = ("hotel", "restaurant", "attraction", "transport")

# domain → (search terms, max search radius in metres)
DOMAIN_QUERIES: Dict[str, Tuple[List[str], int]] = {
    "hotel": (["hotel"], 6000),
    "restaurant": (["restaurant"], 4000),
    "attraction": (["attraction", "museum", "castle"], 12000),
    "transport": (["railway station", "bus station", "airport"], 30000),
}

_HOTEL_TYPES = {"hotel", "guest_house", "hostel", "motel", "resort", "apartment", "chalet"}
_FOOD_TYPES = {"restaurant", "cafe", "fast_food", "food_court", "pub", "bar", "biergarten"}
_SIGHT_TYPES = {
    "attraction", "museum", "gallery", "viewpoint", "zoo", "theme_park",
    "aquarium", "artwork",
}

MIN_RESULTS = 3          # fewer than this → retry with a wider search area
WIDE_RADIUS_M = 25000

CACHE_TTL_SECONDS = 3600

# University / college dorms are mapped as "hostel" but are not for travellers
_STUDENT_HOUSING = re.compile(
    r"^\s*(?:block\s*[\w-]*|\d+\s*(?:st|nd|rd|th)?\s*block)\s*$"
    r"|\bblock\s*\d+\b|\b\d+(?:st|nd|rd|th)\s+block\b"
    r"|hall of residence|\bdorm(?:itory)?\b"
    r"|\b(?:boys|girls|ladies|gents|men'?s|women'?s|students?|college|university|pg)\b.*\bhostel\b"
    r"|\bhostel\b.*\b(?:boys|girls|ladies|gents|students?|college|university)\b",
    re.IGNORECASE,
)

_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


# ── Helpers ─────────────────────────────────────────────────────

def _viewbox(place: Place, radius_m: int) -> str:
    """Nominatim viewbox 'left,top,right,bottom' around the place centre."""
    dlat = radius_m / 111_000
    dlon = radius_m / (111_000 * max(math.cos(math.radians(place.lat)), 0.2))
    return f"{place.lon - dlon},{place.lat + dlat},{place.lon + dlon},{place.lat - dlat}"


def _classify(item: Dict[str, Any]) -> Optional[str]:
    category = item.get("category", "")
    kind = item.get("type", "")
    extratags = item.get("extratags") or {}
    if category == "tourism" and kind in _HOTEL_TYPES:
        return "hotel"
    if category == "amenity" and kind in _FOOD_TYPES:
        return "restaurant"
    if (
        (category == "railway" and kind in ("station", "halt"))
        or (category == "amenity" and kind == "bus_station")
        or (category == "aeroway" and kind == "aerodrome")
    ):
        return "transport"
    if (category == "tourism" and kind in _SIGHT_TYPES) or category == "historic":
        return "attraction"
    if category == "leisure" and kind in ("park", "garden", "nature_reserve"):
        return "attraction"
    if category == "building" and extratags.get("tourism") in _SIGHT_TYPES:
        return "attraction"
    return None


def _address(address: Dict[str, str]) -> str:
    street = " ".join(x for x in (address.get("house_number"), address.get("road")) if x)
    parts = [
        street,
        address.get("suburb") or address.get("neighbourhood") or address.get("quarter"),
        address.get("city") or address.get("town") or address.get("village"),
        address.get("postcode"),
    ]
    return ", ".join(p for p in parts if p)


def _normalize(item: Dict[str, Any], domain: str, place: Place) -> Optional[Dict[str, Any]]:
    name = (item.get("name") or "").strip()
    if not name:
        return None
    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    tags = item.get("extratags") or {}
    address = item.get("address") or {}
    kind = item.get("type", "")
    category = item.get("category", "")
    importance = float(item.get("importance") or 0)
    distance = round(haversine_km(place.lat, place.lon, lat, lon), 1)

    record: Dict[str, Any] = {
        "name": name,
        "area": (
            address.get("suburb") or address.get("neighbourhood") or address.get("quarter")
            or address.get("city") or address.get("town") or place.name
        ),
        "address": _address(address),
        "phone": tags.get("phone") or tags.get("contact:phone") or "",
        "website": tags.get("website") or tags.get("contact:website") or "",
        "opening_hours": tags.get("opening_hours", ""),
        "lat": lat,
        "lon": lon,
        "distance_km": distance,
        "map_url": f"https://www.openstreetmap.org/{item.get('osm_type', 'node')}/{item.get('osm_id', '')}",
        "source": "openstreetmap",
    }

    if domain == "hotel":
        if kind == "hostel" and _STUDENT_HOUSING.search(name):
            return None
        record["type"] = kind.replace("_", " ")
        stars = str(tags.get("stars", "")).strip()
        if stars[:1].isdigit():
            record["stars"] = stars[:1]
        if tags.get("internet_access") in ("wlan", "yes", "wifi"):
            record["internet"] = "yes"
    elif domain == "restaurant":
        record["type"] = kind.replace("_", " ")
        cuisine = tags.get("cuisine", "").replace(";", ", ").replace("_", " ")
        if cuisine:
            record["food"] = cuisine
        veg = tags.get("diet:vegetarian", "")
        lowered = name.lower()
        if veg in ("yes", "only") or "vegetarian" in cuisine or "vegetarian" in lowered or " veg" in f" {lowered} ":
            record["vegetarian"] = "only" if veg == "only" else "yes"
        if tags.get("diet:vegan") in ("yes", "only") or "vegan" in lowered:
            record["vegan"] = "yes"
    elif domain == "attraction":
        if category == "historic":
            record["type"] = "historic site" if kind in ("yes", "") else kind.replace("_", " ")
            if kind == "castle" and "palace" in name.lower():
                record["type"] = "palace"
        else:
            record["type"] = kind.replace("_", " ")
        fee = tags.get("fee", "")
        if fee == "no":
            record["entrance_fee"] = "free"
        elif tags.get("charge"):
            record["entrance_fee"] = tags["charge"]
        elif fee == "yes":
            record["entrance_fee"] = "ticketed"
        if tags.get("wikipedia"):
            record["wikipedia"] = tags["wikipedia"]
    elif domain == "transport":
        if category == "aeroway":
            record["type"] = "airport"
            if tags.get("iata"):
                record["code"] = tags["iata"]
        elif kind == "bus_station":
            record["type"] = "bus station"
        else:
            record["type"] = "metro station" if tags.get("station") == "subway" else "railway station"
        if tags.get("operator"):
            record["operator"] = tags["operator"]

    # Ranking: notability (Nominatim importance is derived from Wikipedia
    # link counts) first, then documentation quality, then proximity.
    score = importance * 25
    if tags.get("wikidata") or tags.get("wikipedia"):
        score += 3
    for key in ("website", "phone", "opening_hours", "cuisine", "stars"):
        if tags.get(key) or tags.get(f"contact:{key}"):
            score += 0.6
    if record.get("stars"):
        score += int(record["stars"]) * 0.4
    radius_km = DOMAIN_QUERIES[domain][1] / 1000
    score -= min(distance, radius_km) / radius_km * 3
    record["_score"] = round(score, 3)

    return {k: v for k, v in record.items() if v not in ("", None)}


# ── Public API ──────────────────────────────────────────────────

def _cache_key(domain: str, place: Place) -> str:
    return f"{domain}:{place.lat:.2f}:{place.lon:.2f}"


def _fetch_domain(domain: str, place: Place) -> Optional[List[Dict[str, Any]]]:
    terms, max_radius = DOMAIN_QUERIES[domain]
    if domain in ("hotel", "restaurant"):
        radius = min(max(place.radius_m, 2500), max_radius)
    else:
        radius = max_radius if domain == "transport" else min(max(place.radius_m, 6000), max_radius)
    found: Dict[str, Dict[str, Any]] = {}
    any_success = False

    def collect(search_radius: int) -> None:
        nonlocal any_success
        viewbox = _viewbox(place, search_radius)
        for term in terms:
            items = geocoder.category_search(term, viewbox, limit=40)
            if items is None:
                continue
            any_success = True
            for item in items:
                if _classify(item) != domain:
                    continue
                record = _normalize(item, domain, place)
                if record is None:
                    continue
                key = record["name"].lower()
                if key not in found or record["_score"] > found[key]["_score"]:
                    found[key] = record

    collect(radius)
    # Small towns and spread-out places: look further out before giving up
    if any_success and len(found) < MIN_RESULTS and radius < WIDE_RADIUS_M:
        collect(WIDE_RADIUS_M)

    if not any_success:
        return None
    return sorted(found.values(), key=lambda r: r["_score"], reverse=True)


def fetch_places(place: Place, domains: List[str]) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """
    Fetch live places for the given domains.

    Returns a dict domain → ranked records. A domain maps to None when the
    live service could not be reached (so callers can tell "nothing there"
    apart from "lookup failed").
    """
    result: Dict[str, Optional[List[Dict[str, Any]]]] = {}
    for domain in domains:
        if domain not in DOMAINS:
            continue
        key = _cache_key(domain, place)
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            result[domain] = cached[1]
            continue

        records = _fetch_domain(domain, place)
        if records is not None:
            _cache[key] = (time.time(), records)
            logger.info(f"Live places: {len(records)} {domain} records near {place.name}")
        else:
            logger.warning(f"Live places lookup failed for {domain} near {place.name}")
        result[domain] = records
    return result


def public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal ranking fields before a record leaves the backend."""
    return {k: v for k, v in record.items() if not k.startswith("_")}
