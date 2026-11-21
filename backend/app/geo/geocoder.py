"""
PlanWise AI - Geocoder

Turns place names into coordinates using Photon, with Open-Meteo as a
search fallback. Nominatim is only a last-resort reverse-geocoding provider;
it is not used for autocomplete or POI searches.
"""

import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel

from app import config

logger = logging.getLogger(__name__)


class Place(BaseModel):
    """A resolved geographic place."""
    name: str
    display_name: str = ""
    lat: float
    lon: float
    country: str = ""
    country_code: str = ""
    state: str = ""
    kind: str = ""            # city, town, suburb, point ...
    radius_m: int = 6000      # sensible search radius around the centre

    @property
    def label(self) -> str:
        """Short human label, e.g. 'Mysuru, India'."""
        if self.country and self.country.lower() not in self.name.lower():
            return f"{self.name}, {self.country}"
        return self.name


# ── Nominatim access ────────────────────────────────────────────

_cache: Dict[str, Any] = {}
_known_places: Dict[str, "Place"] = {}
_lock = threading.Lock()


def _coord_key(lat: float, lon: float) -> str:
    return f"{float(lat):.3f}:{float(lon):.3f}"


def remember(place: "Place") -> None:
    """Memoize a resolved place so its coordinates can be recognised later."""
    _known_places[_coord_key(place.lat, place.lon)] = place


def lookup(lat: float, lon: float) -> Optional["Place"]:
    """A previously resolved place at (roughly) these coordinates, if any."""
    return _known_places.get(_coord_key(lat, lon))
_last_request_at = 0.0
_last_request_ok = True


def _request(path: str, params: Dict[str, Any], timeout: Optional[int] = None) -> Any:
    """Throttled GET against Nominatim."""
    global _last_request_at, _last_request_ok
    with _lock:
        wait = 1.05 - (time.time() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(
                f"{config.NOMINATIM_URL}{path}",
                params={**params, "format": "jsonv2", "addressdetails": 1, "accept-language": "en"},
                headers={"User-Agent": config.GEO_USER_AGENT},
                timeout=timeout if timeout is not None else config.GEO_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            _last_request_ok = True
            return data
        except Exception:
            _last_request_ok = False
            raise
        finally:
            _last_request_at = time.time()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _to_place(item: Dict[str, Any]) -> Place:
    address = item.get("address") or {}
    lat = float(item["lat"])
    lon = float(item["lon"])

    name = (
        item.get("name")
        or address.get("city") or address.get("town") or address.get("village")
        or address.get("suburb") or address.get("county") or address.get("state")
        or (item.get("display_name") or "").split(",")[0]
    )
    # Councils / boundaries ("Jaipur Municipal Corporation") carry the plain
    # city name in the address - use that so people see "Jaipur".
    kind = item.get("addresstype") or item.get("type") or ""
    city = address.get("city") or address.get("town") or address.get("village")
    if kind in ("local_authority", "administrative", "boundary", "municipality") and city \
            and city.lower() in str(name).lower():
        name = city

    # Search radius from the bounding box (half diagonal), clamped
    radius_m = 6000
    bbox = item.get("boundingbox")
    if bbox and len(bbox) == 4:
        try:
            south, north, west, east = (float(x) for x in bbox)
            diagonal_km = haversine_km(south, west, north, east)
            radius_m = int(max(2500, min(diagonal_km * 1000 / 2, 15000)))
        except (TypeError, ValueError):
            pass

    return Place(
        name=str(name).strip(),
        display_name=item.get("display_name", ""),
        lat=lat,
        lon=lon,
        country=address.get("country", ""),
        country_code=(address.get("country_code") or "").lower(),
        state=address.get("state", ""),
        kind=item.get("addresstype") or item.get("type") or "",
        radius_m=radius_m,
    )


def search(query: str, limit: int = 5) -> List[Place]:
    """Free-text place search (used for geocoding and autocomplete)."""
    global _last_request_ok
    query = (query or "").strip()
    if len(query) < 2:
        return []
    key = f"search:{query.lower()}:{limit}"
    if key in _cache:
        return _cache[key]

    places = _photon_search(query, limit=max(limit, 8))
    photon_available = _last_request_ok
    index_by_key: Dict[Any, int] = {}
    deduped: List[Place] = []
    for place in places:
        dedupe_key = (place.name.lower(), place.state.lower(), place.country_code)
        if dedupe_key in index_by_key:
            # Same name twice (e.g. "Udupi" the district and "Udupi" the city):
            # keep the actual settlement - a district's centre can be far from town.
            existing = deduped[index_by_key[dedupe_key]]
            if place.kind in SETTLEMENT_KINDS and existing.kind not in SETTLEMENT_KINDS:
                deduped[index_by_key[dedupe_key]] = place
            continue
        index_by_key[dedupe_key] = len(deduped)
        deduped.append(place)

    places = deduped
    if not places:
        places = _openmeteo_search(query, limit=limit)
        if photon_available:
            # Photon was reachable and returned no match; an unrelated
            # Open-Meteo outage must not turn a genuine no-match into AI fallback.
            _last_request_ok = True

    places = places[:limit]
    for place in places:
        remember(place)
    _cache[key] = places
    return places


SETTLEMENT_KINDS = {
    "city", "town", "village", "municipality", "hamlet", "suburb", "city_district",
    "borough", "neighbourhood", "quarter", "local_authority", "current_location",
}


def geocode(query: str) -> Optional[Place]:
    """Best match for a place name, or None."""
    results = search(query, limit=3)
    return results[0] if results else None


def reverse(lat: float, lon: float) -> Optional[Place]:
    """Coordinates → nearest named locality (city / town / suburb)."""
    global _last_request_ok
    key = f"reverse:{lat:.3f}:{lon:.3f}"
    if key in _cache:
        return _cache[key]

    # Photon is the primary reverse service; unlike the Nominatim public
    # endpoint it is not constrained by Nominatim's 1 request/second policy.
    place = _photon_reverse(lat, lon, timeout=6)
    photon_available = _last_request_ok
    if place is not None:
        _cache[key] = place
        remember(place)
        return place

    # Keep Nominatim as a low-volume fallback if Photon is unavailable.
    timeout = max(1, min(config.GEO_TIMEOUT, 6))
    try:
        item = _request("/reverse", {"lat": lat, "lon": lon, "zoom": 12}, timeout=timeout)
        if isinstance(item, dict) and "lat" in item:
            address = item.get("address") or {}
            locality = (
                address.get("city") or address.get("town") or address.get("village")
                or address.get("municipality") or address.get("suburb")
                or address.get("county") or item.get("name")
            )
            result = _to_place(item)
            place = result.model_copy(update={
                "name": str(locality or result.name).strip(),
                "lat": float(lat),
                "lon": float(lon),
                "kind": "current_location",
                "radius_m": 5000,
            })
        else:
            place = None
    except Exception as exc:
        logger.warning("Nominatim reverse fallback failed for %s,%s: %s", lat, lon, exc)
        place = None
        if photon_available:
            _last_request_ok = True
    if place is not None:
        _cache[key] = place
        remember(place)
        return place

    # Fallback 3: Return a sensible coordinate-based place so caller never receives None
    fallback = Place(
        name="Current location",
        display_name=f"{lat:.4f}, {lon:.4f}",
        lat=float(lat),
        lon=float(lon),
        kind="current_location",
        radius_m=5000,
    )
    _cache[key] = fallback
    remember(fallback)
    return fallback


def _photon_search(query: str, limit: int = 8, timeout: int = 6) -> List[Place]:
    """Search place names with Photon and adapt its GeoJSON to Place records."""
    global _last_request_ok
    try:
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": limit, "lang": "en"},
            headers={"User-Agent": config.GEO_USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        _last_request_ok = True
        features = (response.json() or {}).get("features") or []
        places: List[Place] = []
        for feature in features:
            try:
                properties = feature.get("properties") or {}
                coordinates = (feature.get("geometry") or {}).get("coordinates") or []
                if len(coordinates) < 2:
                    continue
                name = properties.get("name") or properties.get("city") or ""
                address = {
                    key: properties.get(key, "")
                    for key in (
                        "city", "town", "village", "municipality", "suburb",
                        "district", "county", "state", "country",
                    )
                }
                address["country_code"] = properties.get("countrycode", "")
                extent = properties.get("extent") or []
                boundingbox = (
                    [extent[1], extent[3], extent[0], extent[2]] if len(extent) == 4 else None
                )
                item = {
                    "name": name,
                    "display_name": ", ".join(
                        str(value) for value in (
                            name, properties.get("street"), properties.get("city")
                            or properties.get("town"), properties.get("state"), properties.get("country")
                        ) if value
                    ),
                    "lat": coordinates[1],
                    "lon": coordinates[0],
                    "addresstype": properties.get("type", ""),
                    "address": address,
                    "boundingbox": boundingbox,
                }
                places.append(_to_place(item))
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
        return places
    except Exception as e:
        _last_request_ok = False
        logger.warning("Photon search failed for '%s': %s", query, e)
        return []


def _openmeteo_search(query: str, limit: int = 8, timeout: int = 5) -> List[Place]:
    """Open-Meteo geocoding fallback for autocomplete/search."""
    global _last_request_ok
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": limit, "language": "en", "format": "json"},
            headers={"User-Agent": config.GEO_USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        _last_request_ok = True
        results = (response.json() or {}).get("results") or []
        places: List[Place] = []
        for item in results:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            country = str(item.get("country") or "")
            state = str(item.get("admin1") or "")
            places.append(Place(
                name=name,
                display_name=", ".join(part for part in (name, state, country) if part),
                lat=float(item["latitude"]),
                lon=float(item["longitude"]),
                country=country,
                country_code=str(item.get("country_code") or "").lower(),
                state=state,
                kind="city",
                radius_m=6000,
            ))
        return places
    except Exception as e:
        _last_request_ok = False
        logger.warning(f"Open-Meteo search failed for '{query}': {e}")
        return []


def _photon_reverse(lat: float, lon: float, timeout: int) -> Optional[Place]:
    """Try Photon when Nominatim is unavailable or has no matching result."""
    global _last_request_ok
    try:
        response = requests.get(
            "https://photon.komoot.io/reverse",
            params={"lat": lat, "lon": lon, "lang": "en", "limit": 1},
            headers={"User-Agent": config.GEO_USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        _last_request_ok = True
        features = (response.json() or {}).get("features") or []
        if not features or not isinstance(features[0], dict):
            return None
        properties = features[0].get("properties") or {}
        locality = (
            properties.get("city") or properties.get("town") or properties.get("village")
            or properties.get("municipality") or properties.get("suburb")
            or properties.get("district") or properties.get("county")
            or properties.get("state") or properties.get("name") or properties.get("country")
        )
        if not locality:
            return None
        country = str(properties.get("country") or "")
        state = str(properties.get("state") or "")
        name = str(locality).strip()
        return Place(
            name=name,
            display_name=", ".join(part for part in (name, state, country) if part),
            lat=float(lat),
            lon=float(lon),
            country=country,
            country_code=str(properties.get("countrycode") or "").lower(),
            state=state,
            kind="current_location",
            radius_m=5000,
        )
    except Exception as e:
        _last_request_ok = False
        logger.warning(f"Photon reverse geocoding failed for {lat},{lon}: {e}")
        return None


def service_ok() -> bool:
    """False when the most recent Nominatim request failed (service/network down)."""
    return _last_request_ok


def is_cambridge_uk(place: Optional[Place]) -> bool:
    """The bundled MultiWOZ dataset covers Cambridge, England only."""
    if place is None:
        return False
    return place.country_code == "gb" and place.name.strip().lower() == "cambridge"
