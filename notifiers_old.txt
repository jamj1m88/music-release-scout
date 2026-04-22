from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import AppConfig
from .discovery import ReleaseCandidate


def _telegram_message(picks: list[ReleaseCandidate]) -> str:
    if not picks:
        return "No fresh music matches this week."

    lines = ["Your weekly music picks:"]
    for index, pick in enumerate(picks, start=1):
        lines.append(f"{index}. {pick.artist_name} - {pick.release_title} ({pick.release_date})")
        if pick.apple_music_url:
            lines.append(f"   Apple/iTunes: {pick.apple_music_url}")
        if pick.apple_preview_url:
            lines.append(f"   Preview: {pick.apple_preview_url}")
        if pick.youtube_music_url:
            lines.append(f"   YouTube Music: {pick.youtube_music_url}")
    return "\n".join(lines)


def send_telegram_digest(config: AppConfig, picks: list[ReleaseCandidate]) -> None:
    telegram = config.delivery.telegram
    if not telegram.enabled:
        return

    payload = urlencode(
        {
            "chat_id": telegram.chat_id,
            "text": _telegram_message(picks),
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{telegram.bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=20):
        return


def send_email_digest(config: AppConfig, picks: list[ReleaseCandidate], html_body: str) -> None:
    email = config.delivery.email
    if not email.enabled:
        return

    text_body = _telegram_message(picks)
    message = EmailMessage()
    message["Subject"] = "Weekly music release picks"
    message["From"] = email.from_address
    message["To"] = email.to_address
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(email.smtp_host, email.smtp_port, timeout=20) as smtp:
        if email.use_tls:
            smtp.starttls()
        if email.username:
            smtp.login(email.username, email.password)
        smtp.send_message(message)
