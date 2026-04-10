from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings, load_settings
from app.database import (
    get_latest_check_by_provider,
    get_latest_failed_check_by_provider,
    get_latest_successful_check_by_provider,
    get_recent_checks,
    get_tracker_config,
    init_db,
    upsert_tracker_config,
)
from app.service import run_price_check


app = FastAPI(title="Lyft + Uber Price Tracker")
templates = Jinja2Templates(directory="app/templates")
settings: Settings = load_settings()
scheduler = BackgroundScheduler(timezone="UTC")
app.mount("/screenshots", StaticFiles(directory=str(settings.scraper_debug_dir)), name="screenshots")


def _format_est(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    eastern = dt.astimezone(ZoneInfo("America/New_York"))
    return eastern.strftime("%Y-%m-%d %I:%M:%S %p %Z")


def _format_est_compact(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    eastern = dt.astimezone(ZoneInfo("America/New_York"))
    return eastern.strftime("%m/%d %I:%M %p")


def _extract_error_code(error_message: str | None) -> str | None:
    if not error_message:
        return None
    message = error_message.strip()
    if message.startswith("[") and "]" in message:
        return message[1 : message.index("]")].strip()
    return None


def _default_tracker_config() -> dict:
    return {
        "source_address": settings.source_address,
        "destination_address": settings.destination_address,
        "target_datetime": settings.target_datetime,
        "passengers": settings.passengers,
        "price_threshold": settings.price_threshold,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def scheduled_check() -> None:
    tracker_config = get_tracker_config(settings.database_path)
    run_price_check(settings, tracker_config=tracker_config)


@app.on_event("startup")
def on_startup() -> None:
    settings.scraper_debug_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path, default_config=_default_tracker_config())

    if not scheduler.running:
        scheduler.add_job(
            scheduled_check,
            trigger="interval",
            hours=settings.check_interval_hours,
            id="lyft-price-check",
            replace_existing=True,
        )
        scheduler.add_job(
            scheduled_check,
            trigger="date",
            run_date=datetime.utcnow() + timedelta(seconds=5),
            id="lyft-price-check-initial",
            replace_existing=True,
        )
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/")
def dashboard(request: Request):
    checks = get_recent_checks(settings.database_path, limit=200)
    latest_lyft = get_latest_successful_check_by_provider(settings.database_path, "lyft")
    latest_uber = get_latest_successful_check_by_provider(settings.database_path, "uber")
    latest_lyft_check = get_latest_check_by_provider(settings.database_path, "lyft")
    latest_uber_check = get_latest_check_by_provider(settings.database_path, "uber")
    latest_failed_lyft = get_latest_failed_check_by_provider(settings.database_path, "lyft")
    latest_failed_uber = get_latest_failed_check_by_provider(settings.database_path, "uber")
    tracker_config = get_tracker_config(settings.database_path)
    checks_display = []
    for row in checks:
        row_copy = dict(row)
        row_copy["checked_at_est"] = _format_est(str(row.get("checked_at", "")))
        row_copy["error_code"] = _extract_error_code(row_copy.get("error_message"))
        screenshot_name = row_copy.get("screenshot_path")
        row_copy["screenshot_url"] = f"/screenshots/{screenshot_name}" if screenshot_name else None
        checks_display.append(row_copy)

    latest_lyft_display = dict(latest_lyft) if latest_lyft else None
    if latest_lyft_display:
        latest_lyft_display["checked_at_est"] = _format_est(str(latest_lyft_display.get("checked_at", "")))
        screenshot_name = latest_lyft_display.get("screenshot_path")
        latest_lyft_display["screenshot_url"] = f"/screenshots/{screenshot_name}" if screenshot_name else None

    latest_uber_display = dict(latest_uber) if latest_uber else None
    if latest_uber_display:
        latest_uber_display["checked_at_est"] = _format_est(str(latest_uber_display.get("checked_at", "")))
        screenshot_name = latest_uber_display.get("screenshot_path")
        latest_uber_display["screenshot_url"] = f"/screenshots/{screenshot_name}" if screenshot_name else None

    latest_lyft_check_display = dict(latest_lyft_check) if latest_lyft_check else None
    if latest_lyft_check_display:
        latest_lyft_check_display["checked_at_est"] = _format_est(str(latest_lyft_check_display.get("checked_at", "")))
        latest_lyft_check_display["error_code"] = _extract_error_code(latest_lyft_check_display.get("error_message"))

    latest_uber_check_display = dict(latest_uber_check) if latest_uber_check else None
    if latest_uber_check_display:
        latest_uber_check_display["checked_at_est"] = _format_est(str(latest_uber_check_display.get("checked_at", "")))
        latest_uber_check_display["error_code"] = _extract_error_code(latest_uber_check_display.get("error_message"))

    latest_failed_lyft_display = dict(latest_failed_lyft) if latest_failed_lyft else None
    if latest_failed_lyft_display:
        latest_failed_lyft_display["checked_at_est"] = _format_est(str(latest_failed_lyft_display.get("checked_at", "")))
        latest_failed_lyft_display["error_code"] = _extract_error_code(latest_failed_lyft_display.get("error_message"))

    latest_failed_uber_display = dict(latest_failed_uber) if latest_failed_uber else None
    if latest_failed_uber_display:
        latest_failed_uber_display["checked_at_est"] = _format_est(str(latest_failed_uber_display.get("checked_at", "")))
        latest_failed_uber_display["error_code"] = _extract_error_code(latest_failed_uber_display.get("error_message"))

    lyft_rows = [
        row
        for row in reversed(checks_display)
        if row.get("provider") == "lyft" and row.get("success") and row.get("low_estimate") is not None
    ]
    uber_rows = [
        row
        for row in reversed(checks_display)
        if row.get("provider") == "uber" and row.get("success") and row.get("low_estimate") is not None
    ]

    lyft_by_label = {
        _format_est_compact(str(row["checked_at"])): float(row["low_estimate"]) for row in lyft_rows
    }
    uber_by_label = {
        _format_est_compact(str(row["checked_at"])): float(row["low_estimate"]) for row in uber_rows
    }
    chart_labels = sorted(
        set(lyft_by_label.keys()) | set(uber_by_label.keys()),
        key=lambda value: datetime.strptime(value, "%m/%d %I:%M %p"),
    )
    lyft_chart_values = [lyft_by_label.get(label) for label in chart_labels]
    uber_chart_values = [uber_by_label.get(label) for label in chart_labels]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "checks": checks_display,
            "latest_lyft": latest_lyft_display,
            "latest_uber": latest_uber_display,
            "latest_lyft_check": latest_lyft_check_display,
            "latest_uber_check": latest_uber_check_display,
            "latest_failed_lyft": latest_failed_lyft_display,
            "latest_failed_uber": latest_failed_uber_display,
            "chart_labels": chart_labels,
            "lyft_chart_values": lyft_chart_values,
            "uber_chart_values": uber_chart_values,
            "tracker": tracker_config,
            "settings": settings,
            "now": _format_est(datetime.now(timezone.utc).isoformat()),
        },
    )


@app.post("/run-check")
def manual_run_check() -> RedirectResponse:
    tracker_config = get_tracker_config(settings.database_path)
    run_price_check(settings, tracker_config=tracker_config)
    return RedirectResponse(url="/", status_code=303)


@app.post("/settings")
def update_settings(
    source_address: str = Form(...),
    destination_address: str = Form(...),
    target_datetime: str = Form(...),
    passengers: int = Form(...),
    price_threshold: float = Form(...),
) -> RedirectResponse:
    sanitized_source = source_address.strip()
    sanitized_destination = destination_address.strip()
    sanitized_datetime = target_datetime.strip()
    sanitized_passengers = max(1, int(passengers))
    sanitized_threshold = max(0.0, float(price_threshold))

    upsert_tracker_config(
        settings.database_path,
        {
            "source_address": sanitized_source,
            "destination_address": sanitized_destination,
            "target_datetime": sanitized_datetime,
            "passengers": sanitized_passengers,
            "price_threshold": sanitized_threshold,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return RedirectResponse(url="/", status_code=303)


@app.get("/export.csv")
def export_csv() -> StreamingResponse:
    checks = get_recent_checks(settings.database_path, limit=2000)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "checked_at",
            "provider",
            "source_address",
            "destination_address",
            "target_datetime",
            "passengers",
            "ride_type",
            "low_estimate",
            "high_estimate",
            "currency",
            "success",
            "alert_sent",
            "screenshot_path",
            "error_message",
        ]
    )

    for row in reversed(checks):
        writer.writerow(
            [
                row.get("checked_at"),
                row.get("provider"),
                row.get("source_address"),
                row.get("destination_address"),
                row.get("target_datetime"),
                row.get("passengers"),
                row.get("ride_type"),
                row.get("low_estimate"),
                row.get("high_estimate"),
                row.get("currency"),
                row.get("success"),
                row.get("alert_sent"),
                row.get("screenshot_path"),
                row.get("error_message"),
            ]
        )

    output.seek(0)
    filename = f"ride_price_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)
