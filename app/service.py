from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone

from app.config import Settings
from app.database import insert_check
from app.emailer import can_send_email, send_alert_email
from app.lyft_client import LyftClient
from app.uber_client import UberClient


def _run_single_provider_check(
    settings: Settings,
    effective_settings: Settings,
    provider: str,
) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()

    row: dict = {
        "provider": provider,
        "checked_at": checked_at,
        "source_address": effective_settings.source_address,
        "destination_address": effective_settings.destination_address,
        "target_datetime": effective_settings.target_datetime,
        "passengers": effective_settings.passengers,
        "success": 0,
        "alert_sent": 0,
    }

    try:
        client = LyftClient(effective_settings) if provider == "lyft" else UberClient(effective_settings)
        result = client.get_cost_estimate()
        row.update(result)
        row["success"] = 1

        if result["low_estimate"] <= effective_settings.price_threshold and can_send_email(effective_settings):
            send_alert_email(
                settings=effective_settings,
                provider=provider,
                low_estimate=result["low_estimate"],
                high_estimate=result["high_estimate"],
                ride_type=result["ride_type"],
            )
            row["alert_sent"] = 1

    except Exception as exc:
        row["error_message"] = str(exc)

    insert_check(effective_settings.database_path, row)
    return row


def run_price_check(settings: Settings, tracker_config: dict | None = None) -> list[dict]:
    config = {
        "source_address": settings.source_address,
        "destination_address": settings.destination_address,
        "target_datetime": settings.target_datetime,
        "passengers": settings.passengers,
        "price_threshold": settings.price_threshold,
    }
    if tracker_config:
        config.update(tracker_config)

    effective_settings = replace(
        settings,
        source_address=str(config["source_address"]),
        destination_address=str(config["destination_address"]),
        target_datetime=str(config["target_datetime"]),
        passengers=int(config["passengers"]),
        price_threshold=float(config["price_threshold"]),
    )

    providers = ("lyft", "uber")
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(_run_single_provider_check, settings, effective_settings, provider): provider
            for provider in providers
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda row: str(row.get("provider", "")))
    return results
