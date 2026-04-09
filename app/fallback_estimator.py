from __future__ import annotations

from typing import Any

import requests
from geopy.geocoders import Nominatim

from app.config import Settings


def _resolve_coordinates(settings: Settings) -> tuple[float, float, float, float]:
    if None not in (
        settings.source_lat,
        settings.source_lng,
        settings.dest_lat,
        settings.dest_lng,
    ):
        return (
            float(settings.source_lat),
            float(settings.source_lng),
            float(settings.dest_lat),
            float(settings.dest_lng),
        )

    geolocator = Nominatim(user_agent="ride-price-tracker")
    source = geolocator.geocode(settings.source_address)
    destination = geolocator.geocode(settings.destination_address)

    if source is None or destination is None:
        raise RuntimeError("Unable to geocode source or destination address")

    return (source.latitude, source.longitude, destination.latitude, destination.longitude)


def _route_metrics(start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> tuple[float, float]:
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{start_lng},{start_lat};{end_lng},{end_lat}?overview=false"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    payload = response.json()
    routes = payload.get("routes", [])
    if not routes:
        raise RuntimeError("Unable to calculate route for fallback estimate")

    route = routes[0]
    distance_miles = float(route.get("distance", 0.0)) / 1609.344
    duration_minutes = float(route.get("duration", 0.0)) / 60.0
    return (distance_miles, duration_minutes)


def _fare_range(base: float, per_mile: float, per_minute: float, booking_fee: float, minimum: float, miles: float, minutes: float) -> tuple[float, float]:
    estimate = base + booking_fee + (per_mile * miles) + (per_minute * minutes)
    estimate = max(minimum, estimate)

    low = max(minimum, estimate * 0.88)
    high = estimate * 1.18
    return (round(low, 2), round(high, 2))


def estimate_fallback_fare(settings: Settings, provider: str) -> dict[str, Any]:
    start_lat, start_lng, end_lat, end_lng = _resolve_coordinates(settings)
    miles, minutes = _route_metrics(start_lat, start_lng, end_lat, end_lng)

    provider_key = provider.lower()
    if provider_key == "lyft":
        if settings.passengers > 4:
            low, high = _fare_range(
                base=3.1,
                per_mile=2.2,
                per_minute=0.45,
                booking_fee=3.0,
                minimum=11.0,
                miles=miles,
                minutes=minutes,
            )
            ride_type = "lyft_xl_web_model"
        else:
            low, high = _fare_range(
                base=2.5,
                per_mile=1.35,
                per_minute=0.3,
                booking_fee=2.75,
                minimum=7.5,
                miles=miles,
                minutes=minutes,
            )
            ride_type = "lyft_web_model"
    elif provider_key == "uber":
        if settings.passengers > 4:
            low, high = _fare_range(
                base=3.0,
                per_mile=2.1,
                per_minute=0.42,
                booking_fee=3.0,
                minimum=10.5,
                miles=miles,
                minutes=minutes,
            )
            ride_type = "uberxl_web_model"
        else:
            low, high = _fare_range(
                base=1.5,
                per_mile=1.2,
                per_minute=0.28,
                booking_fee=2.85,
                minimum=7.0,
                miles=miles,
                minutes=minutes,
            )
            ride_type = "uberx_web_model"
    else:
        raise RuntimeError(f"Unsupported provider for fallback model: {provider}")

    return {
        "ride_type": ride_type,
        "low_estimate": low,
        "high_estimate": high,
        "currency": "USD",
    }
