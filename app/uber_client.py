from __future__ import annotations
# pyright: reportMissingImports=false

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable

from app.config import Settings
from app.fallback_estimator import estimate_fallback_fare
from app.screenshot_renderer import render_estimate_screenshot


PRICE_URL = "https://www.uber.com/global/en/price-estimate/"


def _extract_price_range(candidates: Iterable[str]) -> tuple[float, float] | None:
    range_pattern = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:-|to)\s*\$?\s*(\d+(?:\.\d{1,2})?)")
    single_pattern = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")

    for text in candidates:
        match = range_pattern.search(text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            return (min(low, high), max(low, high))

    for text in candidates:
        match = single_pattern.search(text)
        if match:
            value = float(match.group(1))
            return (value, value)

    return None


class UberClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _debug_screenshot_path(self, attempt: int) -> Path:
        debug_dir = self.settings.scraper_debug_dir
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return debug_dir / f"uber_attempt_{attempt}_{timestamp}.png"

    def _capture_failure_artifacts(self, page, attempt: int) -> str | None:
        image_path = self._debug_screenshot_path(attempt)
        html_path = image_path.with_suffix(".html")
        image_written = False
        try:
            page.screenshot(path=str(image_path), full_page=True)
            image_written = True
        except Exception:
            pass

        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        return image_path.name if image_written else None

    def _capture_success_screenshot(self, page, attempt: int) -> str | None:
        image_path = self._debug_screenshot_path(attempt)
        try:
            page.screenshot(path=str(image_path), full_page=True)
            return image_path.name
        except Exception:
            return None

    def _fill_first_available(self, page, selectors: list[str], value: str, timeout_ms: int) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(timeout=timeout_ms)
                locator.fill("")
                locator.fill(value)
                locator.press("Enter")
                return True
            except Exception:
                continue
        return False

    def _collect_candidate_texts(self, page) -> list[str]:
        texts: list[str] = []
        selectors = [
            "[class*='fare' i]",
            "[class*='price' i]",
            "[class*='estimate' i]",
            "[data-testid*='fare' i]",
            "[data-testid*='price' i]",
        ]
        for selector in selectors:
            try:
                texts.extend(page.locator(selector).all_inner_texts())
            except Exception:
                continue

        try:
            texts.append(page.inner_text("body"))
        except Exception:
            pass
        return texts

    def get_cost_estimate(self) -> dict:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is not installed. Run: python -m pip install -r requirements.txt") from exc

        last_error: Exception | None = None
        last_screenshot_name: str | None = None
        retries = max(1, self.settings.scraper_retries)

        for attempt in range(1, retries + 1):
            browser = None
            page = None
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        headless=self.settings.scraper_headless,
                        slow_mo=max(0, self.settings.scraper_slow_mo_ms),
                    )
                    page = browser.new_page()
                    page.goto(
                        PRICE_URL,
                        wait_until="domcontentloaded",
                        timeout=self.settings.scraper_timeout_ms,
                    )

                    from_ok = self._fill_first_available(
                        page,
                        [
                            "input[placeholder*='pickup' i]",
                            "input[aria-label*='pickup' i]",
                            "input[name*='pickup' i]",
                            "input[placeholder*='from' i]",
                            "input[aria-label*='from' i]",
                        ],
                        self.settings.source_address,
                        min(20000, self.settings.scraper_timeout_ms),
                    )
                    if not from_ok:
                        raise RuntimeError("Could not locate Uber pickup input")

                    to_ok = self._fill_first_available(
                        page,
                        [
                            "input[placeholder*='drop' i]",
                            "input[aria-label*='drop' i]",
                            "input[name*='destination' i]",
                            "input[placeholder*='destination' i]",
                            "input[placeholder*='to' i]",
                        ],
                        self.settings.destination_address,
                        min(20000, self.settings.scraper_timeout_ms),
                    )
                    if not to_ok:
                        raise RuntimeError("Could not locate Uber destination input")

                    page.wait_for_timeout(9000)
                    last_screenshot_name = self._capture_success_screenshot(page, attempt)
                    quote_blocks = self._collect_candidate_texts(page)
                    extracted = _extract_price_range(quote_blocks)
                    if not extracted:
                        raise RuntimeError("Unable to parse Uber price from estimate page")

                    low, high = extracted
                    return {
                        "ride_type": "web_estimate",
                        "low_estimate": round(float(low), 2),
                        "high_estimate": round(float(high), 2),
                        "currency": "USD",
                        "screenshot_path": last_screenshot_name
                        or render_estimate_screenshot(
                            settings=self.settings,
                            provider="uber",
                            low_estimate=round(float(low), 2),
                            high_estimate=round(float(high), 2),
                            ride_type="web_estimate",
                        ),
                    }
            except PlaywrightTimeoutError:
                last_error = RuntimeError("Uber web quote timed out while loading price estimate")
                if page is not None:
                    last_screenshot_name = self._capture_failure_artifacts(page, attempt)
            except Exception as exc:
                last_error = exc
                if page is not None:
                    last_screenshot_name = self._capture_failure_artifacts(page, attempt)
            finally:
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass

        if last_error is None:
            last_error = RuntimeError("Uber web quote failed for unknown reason")

        try:
            fallback = estimate_fallback_fare(self.settings, provider="uber")
            fallback["ride_type"] = f"{fallback['ride_type']} (fallback)"
            fallback["screenshot_path"] = last_screenshot_name or render_estimate_screenshot(
                settings=self.settings,
                provider="uber",
                low_estimate=float(fallback["low_estimate"]),
                high_estimate=float(fallback["high_estimate"]),
                ride_type=str(fallback["ride_type"]),
            )
            return fallback
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Uber web quote failed after {retries} attempt(s): {last_error}; fallback failed: {fallback_exc}"
            )
