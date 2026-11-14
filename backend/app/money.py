"""
PlanWise AI - Currency helpers

Currency by country, symbols, formatting and rough price-level
estimates used when a data source carries no explicit prices.
All budget arithmetic stays deterministic (never delegated to the LLM).
"""

import re
from typing import Optional

_CURRENCY_BY_COUNTRY = {
    "in": "INR", "gb": "GBP", "us": "USD", "ca": "CAD", "au": "AUD", "nz": "NZD",
    "jp": "JPY", "cn": "CNY", "sg": "SGD", "ae": "AED", "ch": "CHF", "th": "THB",
    "my": "MYR", "id": "IDR", "lk": "LKR", "np": "NPR", "bd": "BDT", "pk": "PKR",
    "kr": "KRW", "vn": "VND", "ph": "PHP", "tr": "TRY", "eg": "EGP", "za": "ZAR",
    "br": "BRL", "mx": "MXN", "ru": "RUB", "se": "SEK", "no": "NOK", "dk": "DKK",
    "pl": "PLN", "cz": "CZK", "hu": "HUF", "sa": "SAR", "qa": "QAR", "hk": "HKD",
    "mv": "MVR", "bt": "BTN", "il": "ILS", "ke": "KES", "ng": "NGN", "ar": "ARS",
}
_EURO_COUNTRIES = {
    "fr", "de", "it", "es", "pt", "nl", "be", "at", "ie", "fi", "gr", "lu",
    "mt", "cy", "sk", "si", "ee", "lv", "lt", "hr", "mc", "sm", "va", "ad",
}

CURRENCY_SYMBOLS = {
    "INR": "₹", "GBP": "£", "USD": "$", "EUR": "€", "JPY": "¥", "CNY": "¥",
    "AUD": "A$", "CAD": "C$", "SGD": "S$", "NZD": "NZ$", "HKD": "HK$",
    "THB": "฿", "KRW": "₩", "VND": "₫", "PHP": "₱", "TRY": "₺", "ILS": "₪",
}

# Very rough units of local currency per 1 USD - used only to scale
# default price estimates, never shown as an exchange rate.
_UNITS_PER_USD = {
    "USD": 1, "EUR": 0.9, "GBP": 0.8, "CHF": 0.9, "CAD": 1.4, "AUD": 1.5,
    "NZD": 1.7, "SGD": 1.3, "AED": 3.7, "SAR": 3.75, "QAR": 3.6, "JPY": 150,
    "CNY": 7.2, "HKD": 7.8, "KRW": 1350, "THB": 35, "MYR": 4.5, "IDR": 16000,
    "VND": 25000, "PHP": 57, "INR": 30, "LKR": 110, "NPR": 50, "BDT": 45,
    "PKR": 100, "BTN": 30, "MVR": 15, "TRY": 20, "EGP": 25, "ZAR": 12,
    "BRL": 4, "MXN": 14, "RUB": 60, "SEK": 10.5, "NOK": 10.5, "DKK": 6.8,
    "PLN": 3.5, "CZK": 20, "HUF": 300, "ILS": 3.6, "KES": 80, "NGN": 700,
    "ARS": 600,
}

# Baseline per-person estimates in USD by price level
_MEAL_USD = {"cheap": 7.0, "moderate": 17.0, "expensive": 40.0}
_HOTEL_USD = {"cheap": 40.0, "moderate": 95.0, "expensive": 220.0}


def currency_for_country(country_code: Optional[str]) -> str:
    code = (country_code or "").lower()
    if code in _EURO_COUNTRIES:
        return "EUR"
    return _CURRENCY_BY_COUNTRY.get(code, "USD")


def currency_symbol(currency: Optional[str]) -> str:
    if not currency:
        return ""
    code = currency.upper()
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def format_money(amount: Optional[float], currency: Optional[str]) -> str:
    if amount is None:
        return "-"
    return f"{currency_symbol(currency)}{amount:,.0f}"


def detect_currency(text: str) -> Optional[str]:
    """Currency explicitly mentioned in a user message, if any."""
    lowered = text.lower()
    if "₹" in text or re.search(r"\b(rupees?|inr|rs\.?)\b", lowered):
        return "INR"
    if "£" in text or re.search(r"\b(pounds?|gbp|quid)\b", lowered):
        return "GBP"
    if "€" in text or re.search(r"\b(euros?|eur)\b", lowered):
        return "EUR"
    if "¥" in text or re.search(r"\b(yen|jpy)\b", lowered):
        return "JPY"
    if "$" in text or re.search(r"\b(dollars?|usd|bucks)\b", lowered):
        return "USD"
    return None


def _scale(usd: float, currency: Optional[str]) -> float:
    units = _UNITS_PER_USD.get((currency or "USD").upper(), 1)
    value = usd * units
    # Round to a "natural" figure for the currency's magnitude
    if value >= 10000:
        return round(value, -3)
    if value >= 1000:
        return round(value, -2)
    if value >= 100:
        return round(value, -1)
    return float(round(value))


def estimate_meal_cost(pricerange: Optional[str], currency: Optional[str]) -> float:
    return _scale(_MEAL_USD.get((pricerange or "moderate").lower(), _MEAL_USD["moderate"]), currency)


def estimate_hotel_cost(pricerange: Optional[str], currency: Optional[str]) -> float:
    return _scale(_HOTEL_USD.get((pricerange or "moderate").lower(), _HOTEL_USD["moderate"]), currency)


# ── Group cost sharing ──────────────────────────────────────────
#
# Activity costs in a plan are stored PER PERSON, except hotels, which are
# stored PER ROOM PER NIGHT (two travellers share a room). These helpers
# turn them into what the whole group pays and what each person pays.

MAX_TRAVELERS = 50


def clamp_travelers(value) -> int:
    try:
        return max(1, min(int(value), MAX_TRAVELERS))
    except (TypeError, ValueError):
        return 1


def rooms_needed(travelers: int) -> int:
    """Hotel rooms for a group, assuming two people per room."""
    return max(1, -(-clamp_travelers(travelers) // 2))


def group_cost(activity_type: Optional[str], cost: Optional[float], travelers: int) -> float:
    """What the whole group pays for one activity."""
    if not cost:
        return 0.0
    if (activity_type or "").lower() == "hotel":
        return float(cost) * rooms_needed(travelers)
    return float(cost) * clamp_travelers(travelers)


def split_evenly(total: Optional[float], travelers: int) -> Optional[float]:
    """Each person's share of a group amount."""
    if total is None:
        return None
    return round(float(total) / clamp_travelers(travelers), 2)


def tight_daily_budget(currency: Optional[str]) -> float:
    """Below this per-day amount a complete plan is unrealistic."""
    if not currency:
        return 300.0  # legacy default (rupee-scale amounts)
    return estimate_meal_cost("cheap", currency) * 1.5
