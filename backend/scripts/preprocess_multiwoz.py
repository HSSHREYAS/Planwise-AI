"""
PlanWise AI - MultiWOZ 2.2 Preprocessor

Reads raw MultiWOZ 2.2 dataset and extracts domain records.
Outputs normalized JSON files to data/processed/.

Usage:
    cd backend
    python -m scripts.preprocess_multiwoz

The script will look for the dataset in data/raw/ and handle
multiple possible directory structures.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"


def find_db_directory() -> Optional[Path]:
    """Find the db/ directory within the raw data folder."""
    # Check common MultiWOZ directory structures
    possible_paths = [
        RAW_DIR / "db",
        RAW_DIR / "MULTIWOZ2.2" / "db",
        RAW_DIR / "MultiWOZ_2.2" / "db",
        RAW_DIR / "multiwoz" / "db",
        RAW_DIR / "MultiWOZ2.2" / "db",
        RAW_DIR / "multi-woz-2.2" / "db",
    ]

    # Also check for any subdirectory containing a 'db' folder
    if RAW_DIR.exists():
        for child in RAW_DIR.iterdir():
            if child.is_dir():
                db_path = child / "db"
                if db_path.exists():
                    possible_paths.append(db_path)
                # Check one level deeper
                for grandchild in child.iterdir():
                    if grandchild.is_dir():
                        db_path = grandchild / "db"
                        if db_path.exists():
                            possible_paths.append(db_path)

    for path in possible_paths:
        if path.exists() and path.is_dir():
            logger.info(f"Found db directory: {path}")
            return path

    # Try to find individual db files directly in raw dir
    for child in RAW_DIR.rglob("hotel_db.json"):
        logger.info(f"Found hotel_db.json at: {child.parent}")
        return child.parent

    return None


def load_json_file(filepath: Path) -> Any:
    """Load a JSON file with error handling."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return None


def normalize_string(value: Any) -> str:
    """Normalize a string value."""
    if value is None:
        return ""
    return str(value).strip().lower()


def process_hotels(db_dir: Path) -> List[Dict]:
    """Process hotel records from MultiWOZ db."""
    filepath = db_dir / "hotel_db.json"
    raw = load_json_file(filepath)
    if raw is None:
        return []

    hotels = []
    for record in raw:
        hotel = {
            "name": record.get("name", ""),
            "area": normalize_string(record.get("area")),
            "pricerange": normalize_string(record.get("pricerange")),
            "type": normalize_string(record.get("type", "hotel")),
            "stars": record.get("stars", ""),
            "parking": normalize_string(record.get("parking")),
            "internet": normalize_string(record.get("internet")),
            "address": record.get("address", ""),
            "phone": record.get("phone", ""),
            "postcode": record.get("postcode", ""),
            "takesbookings": normalize_string(record.get("takesbookings")),
        }
        # Clean up: remove empty fields
        hotel = {k: v for k, v in hotel.items() if v != "" and v is not None}
        if hotel.get("name"):
            hotels.append(hotel)

    logger.info(f"Processed {len(hotels)} hotel records")
    return hotels


def process_restaurants(db_dir: Path) -> List[Dict]:
    """Process restaurant records from MultiWOZ db."""
    filepath = db_dir / "restaurant_db.json"
    raw = load_json_file(filepath)
    if raw is None:
        return []

    restaurants = []
    for record in raw:
        restaurant = {
            "name": record.get("name", ""),
            "area": normalize_string(record.get("area")),
            "food": normalize_string(record.get("food")),
            "pricerange": normalize_string(record.get("pricerange")),
            "address": record.get("address", ""),
            "phone": record.get("phone", ""),
            "postcode": record.get("postcode", ""),
        }
        restaurant = {k: v for k, v in restaurant.items() if v != "" and v is not None}
        if restaurant.get("name"):
            restaurants.append(restaurant)

    logger.info(f"Processed {len(restaurants)} restaurant records")
    return restaurants


def process_attractions(db_dir: Path) -> List[Dict]:
    """Process attraction records from MultiWOZ db."""
    filepath = db_dir / "attraction_db.json"
    raw = load_json_file(filepath)
    if raw is None:
        return []

    attractions = []
    for record in raw:
        attraction = {
            "name": record.get("name", ""),
            "area": normalize_string(record.get("area")),
            "type": normalize_string(record.get("type")),
            "entrance_fee": record.get("entrance fee", record.get("entrancefee", "")),
            "address": record.get("address", ""),
            "phone": record.get("phone", ""),
            "postcode": record.get("postcode", ""),
            "openhours": record.get("openhours", ""),
        }
        attraction = {k: v for k, v in attraction.items() if v != "" and v is not None}
        if attraction.get("name"):
            attractions.append(attraction)

    logger.info(f"Processed {len(attractions)} attraction records")
    return attractions


def process_transport(db_dir: Path) -> List[Dict]:
    """Process train records from MultiWOZ db."""
    filepath = db_dir / "train_db.json"
    raw = load_json_file(filepath)
    if raw is None:
        # Try alternative name
        filepath = db_dir / "train-db.json"
        raw = load_json_file(filepath)
    if raw is None:
        return []

    transport = []
    for record in raw:
        entry = {
            "name": f"Train: {record.get('departure', '?')} → {record.get('destination', '?')}",
            "type": "train",
            "departure": record.get("departure", ""),
            "destination": record.get("destination", ""),
            "day": record.get("day", ""),
            "leaveAt": record.get("leaveAt", record.get("leaveat", "")),
            "arriveBy": record.get("arriveBy", record.get("arriveby", "")),
            "price": record.get("price", ""),
            "duration": record.get("duration", ""),
            "trainID": record.get("trainID", record.get("trainid", "")),
        }
        entry = {k: v for k, v in entry.items() if v != "" and v is not None}
        if entry.get("departure") or entry.get("destination"):
            transport.append(entry)

    logger.info(f"Processed {len(transport)} transport records")
    return transport


def save_processed(data: List[Dict], filename: str) -> None:
    """Save processed data to JSON file."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PROCESSED_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(data)} records to {filepath}")


def main():
    """Main preprocessing pipeline."""
    logger.info("=" * 60)
    logger.info("PlanWise AI - MultiWOZ 2.2 Preprocessor")
    logger.info("=" * 60)
    logger.info(f"Raw data directory: {RAW_DIR}")

    if not RAW_DIR.exists():
        logger.error(f"Raw data directory does not exist: {RAW_DIR}")
        logger.info("Please place the MultiWOZ 2.2 dataset in:")
        logger.info(f"  {RAW_DIR}")
        sys.exit(1)

    db_dir = find_db_directory()
    if db_dir is None:
        logger.error("Could not find the MultiWOZ db/ directory")
        logger.info("Please ensure the dataset contains a 'db' folder with:")
        logger.info("  hotel_db.json, restaurant_db.json, attraction_db.json, train_db.json")
        logger.info(f"Expected location: {RAW_DIR}/<dataset_folder>/db/")
        sys.exit(1)

    logger.info(f"\nUsing db directory: {db_dir}")
    logger.info("-" * 40)

    # Process each domain
    hotels = process_hotels(db_dir)
    restaurants = process_restaurants(db_dir)
    attractions = process_attractions(db_dir)
    transport = process_transport(db_dir)

    # Save
    save_processed(hotels, "hotels.json")
    save_processed(restaurants, "restaurants.json")
    save_processed(attractions, "attractions.json")
    save_processed(transport, "transport.json")

    # Summary
    logger.info("-" * 40)
    logger.info("Preprocessing complete!")
    logger.info(f"  Hotels:      {len(hotels)}")
    logger.info(f"  Restaurants: {len(restaurants)}")
    logger.info(f"  Attractions: {len(attractions)}")
    logger.info(f"  Transport:   {len(transport)}")
    logger.info(f"  Output dir:  {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
