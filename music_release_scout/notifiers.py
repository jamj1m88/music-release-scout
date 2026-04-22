from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import AppConfig
from .discovery import ReleaseCandidate


def _blurb_for_pick(pick: ReleaseCandidate) -> str:
    release_type = pick.release_type.lower()
    primary_reason = pick.why[0] if pick.why else "matches your taste profile"
    if "repeat" in primary_reason.lower():
        return f"Worth another look this week: {primary_reason}."
    if pick.release_type == "Bonus catalog pick":
        return f"Older gem pick: {primary_reason}."
    if release_type == "album":
        return f"Start here for a full listen. It surfaced because it {primary_reason}."
    if release_type == "ep":
        return f"A shorter new release worth a quick spin. It surfaced because it {primary_reason}."
    if release_type == "single":
        return f"Easy one-track check-in. It surfaced because it {primary_reason}."
    return f"Fresh pick for this week. It surfaced because it {primary_reason}."


def _telegram_message(picks: list[ReleaseCandidate]) -> str:
    if not picks:
        return "No fresh music matches this week."

    lines = ["<b>Your weekly music picks</b>"]
    for index, pick in enumerate(picks, start=1):
        title = html.escape(f"{pick.artist_name} - {pick.release_title}")
        lines.append(f"{index}. <b>{title}</b>")
        lines.append(f"Released: {html.escape(pick.release_date)}")

        link_labels: list[str] = []
        if pick.apple_music_url:
            link_labels.append(f'<a href="{html.escape(pick.apple_music_url, quote=True)}">Apple</a>')
        if pick.apple_preview_url:
            link_labels.append(f'<a href="{html.escape(pick.apple_preview_url, quote=True)}">Preview</a>')
        if pick.youtube_music_url:
            link_labels.append(
                f'<a href="{html.escape(pick.youtube_music_url, quote=True)}">YouTube Music</a>'
            )
        if link_labels:
            lines.append("Listen: " + " | ".join(link_labels))
        lines.append("Note: " + html.escape(_blurb_for_pick(pick)))
        lines.append("")
    return "\n".join(lines)


def send_telegram_digest(config: AppConfig, picks: list[ReleaseCandidate]) -> None:
    telegram = config.delivery.telegram
    if not telegram.enabled:
        return

    payload = urlencode(
        {
            "chat_id": telegram.chat_id,
            "text": _telegram_message(picks),
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
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
