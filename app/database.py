from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS price_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL DEFAULT 'lyft',
    checked_at TEXT NOT NULL,
    source_address TEXT NOT NULL,
    destination_address TEXT NOT NULL,
    target_datetime TEXT NOT NULL,
    passengers INTEGER NOT NULL,
    ride_type TEXT,
    low_estimate REAL,
    high_estimate REAL,
    currency TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    alert_sent INTEGER NOT NULL DEFAULT 0,
    screenshot_path TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS tracker_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    source_address TEXT NOT NULL,
    destination_address TEXT NOT NULL,
    target_datetime TEXT NOT NULL,
    passengers INTEGER NOT NULL,
    price_threshold REAL NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path, default_config: dict[str, Any]) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(price_checks)").fetchall()
        }
        if "provider" not in columns:
            conn.execute(
                "ALTER TABLE price_checks ADD COLUMN provider TEXT NOT NULL DEFAULT 'lyft'"
            )
        if "screenshot_path" not in columns:
            conn.execute("ALTER TABLE price_checks ADD COLUMN screenshot_path TEXT")
        conn.execute(
            """
            INSERT INTO tracker_config (
                id,
                source_address,
                destination_address,
                target_datetime,
                passengers,
                price_threshold,
                updated_at
            )
            SELECT 1, ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM tracker_config WHERE id = 1)
            """,
            (
                default_config["source_address"],
                default_config["destination_address"],
                default_config["target_datetime"],
                default_config["passengers"],
                default_config["price_threshold"],
                default_config["updated_at"],
            ),
        )
        conn.commit()


def insert_check(db_path: Path, row: dict[str, Any]) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO price_checks (
                provider,
                checked_at,
                source_address,
                destination_address,
                target_datetime,
                passengers,
                ride_type,
                low_estimate,
                high_estimate,
                currency,
                success,
                alert_sent,
                screenshot_path,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["provider"],
                row["checked_at"],
                row["source_address"],
                row["destination_address"],
                row["target_datetime"],
                row["passengers"],
                row.get("ride_type"),
                row.get("low_estimate"),
                row.get("high_estimate"),
                row.get("currency"),
                row["success"],
                row["alert_sent"],
                row.get("screenshot_path"),
                row.get("error_message"),
            ),
        )
        conn.commit()


def get_recent_checks(db_path: Path, limit: int = 100) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM price_checks
            ORDER BY datetime(checked_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_successful_check(db_path: Path) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM price_checks
            WHERE success = 1
            ORDER BY datetime(checked_at) DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def get_latest_successful_check_by_provider(db_path: Path, provider: str) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM price_checks
            WHERE success = 1 AND provider = ?
            ORDER BY datetime(checked_at) DESC
            LIMIT 1
            """,
            (provider,),
        ).fetchone()
    return dict(row) if row else None


def get_tracker_config(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_address, destination_address, target_datetime, passengers, price_threshold, updated_at
            FROM tracker_config
            WHERE id = 1
            """
        ).fetchone()
    if not row:
        raise RuntimeError("Tracker config has not been initialized")
    return dict(row)


def upsert_tracker_config(db_path: Path, config: dict[str, Any]) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tracker_config (
                id,
                source_address,
                destination_address,
                target_datetime,
                passengers,
                price_threshold,
                updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_address = excluded.source_address,
                destination_address = excluded.destination_address,
                target_datetime = excluded.target_datetime,
                passengers = excluded.passengers,
                price_threshold = excluded.price_threshold,
                updated_at = excluded.updated_at
            """,
            (
                config["source_address"],
                config["destination_address"],
                config["target_datetime"],
                config["passengers"],
                config["price_threshold"],
                config["updated_at"],
            ),
        )
        conn.commit()
