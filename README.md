# Lyft + Uber Price Tracker

This app checks both Lyft and Uber fare estimates every 4 hours by visiting their web estimate pages, stores a running log, displays results on a web page, and sends an email alert when the fare goes below your configured threshold.

## What it does

- Checks price on a schedule (default: every 4 hours)
- Checks both Lyft and Uber each cycle
- Uses a source, destination, target date/time, and passenger count from config
- Stores every check (success or failure) in SQLite
- Shows current + historical prices on a dashboard with provider separation
- Displays a line chart of low fare estimates over time
- Lets you download the full log as CSV
- Lets you update source, destination, datetime, passengers, and alert threshold from the web page
- Sends SMTP email alert when `low_estimate <= PRICE_THRESHOLD`

## Requirements

- Python 3.10+
- Lyft API credentials (`LYFT_CLIENT_ID`, `LYFT_CLIENT_SECRET`)
- Playwright browser runtime (Chromium)
- SMTP credentials for email alerts

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

Install the Playwright Chromium browser:

```bash
python -m playwright install chromium
```

3. Copy `.env.example` to `.env` and set your values.

4. Run the server:

```bash
uvicorn app.main:app --reload
```

5. Open:

- http://127.0.0.1:8000

6. Optional: export your price log CSV from:

- http://127.0.0.1:8000/export.csv

## Configuration

Set these in `.env`:

- `SOURCE_ADDRESS`, `DESTINATION_ADDRESS`
- `TARGET_DATETIME` (ISO format, e.g. `2026-04-15T09:30:00`)
- `PASSENGERS`
- `PRICE_THRESHOLD`
- `CHECK_INTERVAL_HOURS` (default `4`)
- SMTP settings: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`

Optional:

- `SOURCE_LAT`, `SOURCE_LNG`, `DEST_LAT`, `DEST_LNG` to skip geocoding

After startup, you can edit route/trip inputs directly in the dashboard. Those values are persisted in the app database and used by both scheduled checks and manual checks.

## Notes

- The app uses headless browser automation against Lyft/Uber public web estimate pages.
- Because this is web scraping, page markup changes can break extraction and produce failed checks until selectors are updated.
- On failures, screenshot artifacts are written to `SCRAPER_DEBUG_DIR` for debugging.

## Scraper Tuning

Set these optional values in `.env` to tune scraping behavior:

- `SCRAPER_HEADLESS=true|false`
- `SCRAPER_SLOW_MO_MS=0` (increase for slower, more human-like interactions)
- `SCRAPER_TIMEOUT_MS=60000`
- `SCRAPER_RETRIES=3`
- `SCRAPER_DEBUG_DIR=scrape_debug`
- The app performs one initial check a few seconds after startup, then follows the interval.

## Windows Auto-Start (Task Scheduler)

Use the provided scripts to run the server automatically at Windows startup.

Register task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1
```

Custom task name / host / port:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1 -TaskName "LyftPriceTracker" -Host "127.0.0.1" -Port 8000
```

Remove task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\unregister-task.ps1
```

Task details:

- Task triggers at system startup
- Task runs `scripts/run-server.ps1`, which launches `uvicorn app.main:app`
