from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone

from app.config import Settings
from app.database import insert_check
from app.emailer import can_send_email, send_alert_email
from app.fallback_estimator import estimate_fallback_fare
from app.lyft_client import LyftClient
from app.uber_client import UberClient


def _run_provider_client(effective_settings: Settings, provider: str) -> dict:
    client = LyftClient(effective_settings) if provider == "lyft" else UberClient(effective_settings)
    return client.get_cost_estimate()


def _build_recovery_settings(effective_settings: Settings) -> Settings:
    return replace(
        effective_settings,
        scraper_timeout_ms=max(90000, effective_settings.scraper_timeout_ms * 2),
        scraper_retries=max(2, effective_settings.scraper_retries + 1),
        scraper_slow_mo_ms=max(100, effective_settings.scraper_slow_mo_ms),
    )


def _classify_error_message(message: str) -> str:
    text = message.lower()
    if "playwright is not installed" in text:
        return "PLAYWRIGHT_MISSING"
    if "could not locate" in text and "input" in text:
        return "SCRAPE_INPUT_NOT_FOUND"
    if "unable to parse" in text:
        return "SCRAPE_PARSE_FAILED"
    if "timed out" in text:
        return "TIMEOUT"
    if "router.project-osrm.org" in text:
        return "ROUTING_API_UNAVAILABLE"
    if "geocode" in text:
        return "GEOCODE_FAILED"
    if "username and password not accepted" in text or "5.7.8" in text:
        return "SMTP_AUTH_FAILED"
    return "UNKNOWN"


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
        result = _run_provider_client(effective_settings, provider)
        row.update(result)
        row["success"] = 1

        if result["low_estimate"] <= effective_settings.price_threshold and can_send_email(effective_settings):
            try:
                send_alert_email(
                    settings=effective_settings,
                    provider=provider,
                    low_estimate=result["low_estimate"],
                    high_estimate=result["high_estimate"],
                    ride_type=result["ride_type"],
                )
                row["alert_sent"] = 1
            except Exception as email_exc:
                row["error_message"] = f"[SMTP_ALERT_FAILED] alert email failed: {email_exc}"

    except Exception as exc:
        recovery_notes = [f"initial check failed: {exc}"]

        try:
            recovery_settings = _build_recovery_settings(effective_settings)
            recovered = _run_provider_client(recovery_settings, provider)
            recovered_ride_type = str(recovered.get("ride_type") or "web_estimate")
            recovered["ride_type"] = f"{recovered_ride_type} (auto-recovered)"
            row.update(recovered)
            row["success"] = 1
            row["error_message"] = None
        except Exception as retry_exc:
            recovery_notes.append(f"extended-timeout retry failed: {retry_exc}")
            try:
                fallback = estimate_fallback_fare(effective_settings, provider=provider)
                fallback_ride_type = str(fallback.get("ride_type") or "fallback")
                fallback["ride_type"] = f"{fallback_ride_type} (auto-fix fallback)"
                row.update(fallback)
                row["success"] = 1
                row["error_message"] = None
            except Exception as fallback_exc:
                recovery_notes.append(f"fallback fare model failed: {fallback_exc}")
                full_message = " | ".join(recovery_notes)
                row["error_message"] = f"[{_classify_error_message(full_message)}] {full_message}"

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
