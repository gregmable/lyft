from __future__ import annotations

import math
from typing import Any

import requests
from geopy.geocoders import Nominatim

from app.config import Settings


def _haversine_miles(start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> float:
    earth_radius_miles = 3958.7613
    lat1 = math.radians(start_lat)
    lon1 = math.radians(start_lng)
    lat2 = math.radians(end_lat)
    lon2 = math.radians(end_lng)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return earth_radius_miles * c


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


def _route_metrics(start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> tuple[float, float, str]:
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{start_lng},{start_lat};{end_lng},{end_lat}?overview=false"
    )
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        payload = response.json()
        routes = payload.get("routes", [])
        if not routes:
            raise RuntimeError("No route candidates returned")

        route = routes[0]
        distance_miles = float(route.get("distance", 0.0)) / 1609.344
        duration_minutes = float(route.get("duration", 0.0)) / 60.0
        if distance_miles <= 0.0 or duration_minutes <= 0.0:
            raise RuntimeError("Route response did not include positive distance/duration")
        return (distance_miles, duration_minutes, "osrm")
    except Exception:
        direct_miles = max(0.5, _haversine_miles(start_lat, start_lng, end_lat, end_lng))
        # Approximate road distance and duration when routing API is unavailable.
        road_miles = direct_miles * 1.3
        avg_city_speed_mph = 22.0
        minutes = max(8.0, (road_miles / avg_city_speed_mph) * 60.0)
        return (road_miles, minutes, "haversine")


def _fare_range(base: float, per_mile: float, per_minute: float, booking_fee: float, minimum: float, miles: float, minutes: float) -> tuple[float, float]:
    estimate = base + booking_fee + (per_mile * miles) + (per_minute * minutes)
    estimate = max(minimum, estimate)

    low = max(minimum, estimate * 0.88)
    high = estimate * 1.18
    return (round(low, 2), round(high, 2))


def estimate_fallback_fare(settings: Settings, provider: str) -> dict[str, Any]:
    start_lat, start_lng, end_lat, end_lng = _resolve_coordinates(settings)
    miles, minutes, model_source = _route_metrics(start_lat, start_lng, end_lat, end_lng)

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
        "model_source": model_source,
    }
