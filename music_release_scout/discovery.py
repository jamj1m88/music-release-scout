from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError

from .config import AppConfig
from .http import get_json, get_text


MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
NPR_NEWMUSICFRIDAY_SECTION = "https://www.npr.org/sections/allsongs/606254804/new-music-friday/"
PITCHFORK_BEST_NEW_ALBUMS = "https://pitchfork.com/reviews/best/albums/"
BUCKET_ORDER = ("core", "similar", "editorial")


@dataclass
class ReleaseCandidate:
    artist_name: str
    release_title: str
    release_date: str
    release_type: str
    primary_type: str
    source: str
    score: int
    why: list[str]
    bucket: str
    source_detail: str
    significance: int = 0
    apple_music_url: str | None = None
    apple_preview_url: str | None = None
    youtube_music_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArtistWatch:
    artist_name: str
    bucket: str
    source_detail: str
    seed_artist: str | None = None
    similarity: float = 0.0


def _safe_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y":
                return date(parsed.year, 1, 1)
            if fmt == "%Y-%m":
                return date(parsed.year, parsed.month, 1)
            return parsed.date()
        except ValueError:
            continue
    return None


def _recentness_bonus(release_date: str) -> int:
    parsed = _safe_date(release_date)
    if not parsed:
        return 0
    days_old = (date.today() - parsed).days
    if days_old <= 7:
        return 14
    if days_old <= 14:
        return 9
    if days_old <= 21:
        return 4
    return 0


def _text_blob(*parts: str) -> str:
    return " ".join(part for part in parts if part).lower()


def _keyword_score(config: AppConfig, blob: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for keyword in config.genre_keywords:
        if keyword.lower() in blob:
            score += 8
            reasons.append(f'matches your taste keyword "{keyword}"')
    for keyword in config.avoid_keywords:
        if keyword.lower() in blob:
            score -= 20
            reasons.append(f'penalized for avoid keyword "{keyword}"')
    return score, reasons


def search_artist(artist_name: str) -> dict[str, Any] | None:
    payload = get_json(
