from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    source_address: str
    destination_address: str
    target_datetime: str
    passengers: int
    price_threshold: float
    check_interval_hours: int
    source_lat: float | None
    source_lng: float | None
    dest_lat: float | None
    dest_lng: float | None
    lyft_client_id: str
    lyft_client_secret: str
    uber_client_id: str
    uber_client_secret: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str
    database_path: Path
    scraper_headless: bool
    scraper_slow_mo_ms: int
    scraper_timeout_ms: int
    scraper_retries: int
    scraper_debug_dir: Path


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if not value:
        return None
    return float(value)


def load_settings() -> Settings:
    return Settings(
        source_address=os.getenv("SOURCE_ADDRESS", ""),
        destination_address=os.getenv("DESTINATION_ADDRESS", ""),
        target_datetime=os.getenv("TARGET_DATETIME", ""),
        passengers=int(os.getenv("PASSENGERS", "2")),
        price_threshold=float(os.getenv("PRICE_THRESHOLD", "20.0")),
        check_interval_hours=int(os.getenv("CHECK_INTERVAL_HOURS", "4")),
        source_lat=_get_optional_float("SOURCE_LAT"),
        source_lng=_get_optional_float("SOURCE_LNG"),
        dest_lat=_get_optional_float("DEST_LAT"),
        dest_lng=_get_optional_float("DEST_LNG"),
        lyft_client_id=os.getenv("LYFT_CLIENT_ID", ""),
        lyft_client_secret=os.getenv("LYFT_CLIENT_SECRET", ""),
        uber_client_id=os.getenv("UBER_CLIENT_ID", ""),
        uber_client_secret=os.getenv("UBER_CLIENT_SECRET", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        database_path=Path(os.getenv("DATABASE_PATH", "lyft_prices.db")),
        scraper_headless=_get_bool("SCRAPER_HEADLESS", True),
        scraper_slow_mo_ms=int(os.getenv("SCRAPER_SLOW_MO_MS", "0")),
        scraper_timeout_ms=int(os.getenv("SCRAPER_TIMEOUT_MS", "60000")),
        scraper_retries=int(os.getenv("SCRAPER_RETRIES", "3")),
        scraper_debug_dir=Path(os.getenv("SCRAPER_DEBUG_DIR", "scrape_debug")),
    )
