from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings


def can_send_email(settings: Settings) -> bool:
    required = [
        settings.smtp_host,
        settings.smtp_username,
        settings.smtp_password,
        settings.email_from,
        settings.email_to,
    ]
    return all(required)


def send_alert_email(
    settings: Settings,
    provider: str,
    low_estimate: float,
    high_estimate: float,
    ride_type: str,
) -> None:
    message = EmailMessage()
    title_provider = provider.upper()
    message["Subject"] = f"{title_provider} fare alert: price is below your threshold"
    message["From"] = settings.email_from
    message["To"] = settings.email_to

    body = (
        f"Route: {settings.source_address} -> {settings.destination_address}\n"
        f"Provider: {title_provider}\n"
        f"For datetime: {settings.target_datetime}\n"
        f"Passengers: {settings.passengers}\n"
        f"Ride type: {ride_type}\n"
        f"Current estimate: ${low_estimate:.2f} - ${high_estimate:.2f}\n"
        f"Your threshold: ${settings.price_threshold:.2f}\n"
    )
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
