from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError

from .config import AppConfig
from .http import get_json


MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"


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
    apple_music_url: str | None = None
    apple_preview_url: str | None = None
    youtube_music_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def search_artist(artist_name: str) -> dict[str, Any] | None:
    payload = get_json(
        f"{MUSICBRAINZ_API}/artist",
        {
            "query": f'artist:"{artist_name}"',
            "fmt": "json",
            "limit": 5,
        },
    )
    artists = payload.get("artists", [])
    if not artists:
        return None
    exact = [item for item in artists if item.get("name", "").lower() == artist_name.lower()]
    return (exact or artists)[0]


def browse_release_groups(artist_mbid: str, offset: int = 0) -> dict[str, Any]:
    return get_json(
        f"{MUSICBRAINZ_API}/release-group",
        {
            "artist": artist_mbid,
            "fmt": "json",
            "limit": 100,
            "offset": offset,
        },
    )


def score_release(config: AppConfig, favorite_artist: str, release_group: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    score += 60
    reasons.append(f"new release from favorite artist {favorite_artist}")
    tags = release_group.get("tags", [])
    tag_names = [
        str(tag.get("name", ""))
        for tag in tags
        if isinstance(tag, dict) and tag.get("name")
    ]

    title_blob = " ".join(
        filter(
            None,
            [
                release_group.get("title", ""),
                release_group.get("disambiguation", ""),
                " ".join(tag_names),
            ],
        )
    ).lower()

    for keyword in config.genre_keywords:
        if keyword.lower() in title_blob:
            score += 10
            reasons.append(f'matches taste keyword "{keyword}"')

    for keyword in config.avoid_keywords:
        if keyword.lower() in title_blob:
            score -= 20
            reasons.append(f'penalized for avoid keyword "{keyword}"')

    primary_type = (release_group.get("primary-type") or "Other").title()
    if primary_type == "Album":
        score += 8
        reasons.append("album gets a small priority boost")
    elif primary_type == "EP":
        score += 5
        reasons.append("EP gets a moderate priority boost")
    elif primary_type == "Single":
        score += 2
        reasons.append("single gets a small priority boost")

    return score, reasons


def discover_recent_releases(config: AppConfig) -> list[ReleaseCandidate]:
    cutoff = date.today() - timedelta(days=config.discovery.days_back)
    releases: list[ReleaseCandidate] = []
    seen: set[tuple[str, str]] = set()

    for artist_name in config.favorite_artists:
        try:
            artist = search_artist(artist_name)
        except (HTTPError, URLError, TimeoutError):
            continue
        if not artist:
            continue

        offset = 0
        while True:
            try:
                payload = browse_release_groups(artist["id"], offset=offset)
            except (HTTPError, URLError, TimeoutError):
                break
            groups = payload.get("release-groups", [])
            if not groups:
                break

            for group in groups:
                primary_type = (group.get("primary-type") or "Other").title()
                if primary_type not in config.discovery.include_release_types:
                    continue

                first_release_date = _safe_date(group.get("first-release-date"))
                if not first_release_date or first_release_date < cutoff:
                    continue

                dedupe_key = (artist_name.lower(), group.get("title", "").lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                score, reasons = score_release(config, artist_name, group)
                releases.append(
                    ReleaseCandidate(
                        artist_name=artist_name,
                        release_title=group.get("title", "Unknown title"),
                        release_date=group.get("first-release-date", ""),
                        release_type=primary_type,
                        primary_type=primary_type,
                        source="musicbrainz",
                        score=score,
                        why=reasons,
                    )
                )

            offset += len(groups)
            if offset >= int(payload.get("release-group-count", 0)):
                break

    releases.sort(key=lambda item: (item.score, item.release_date), reverse=True)
    return releases[: config.discovery.max_recommendations]


def discover_bonus_catalog_pick(config: AppConfig) -> ReleaseCandidate | None:
    if not config.discovery.include_bonus_catalog_pick or not config.bonus_catalog_artists:
        return None

    artist_name = config.bonus_catalog_artists[0]
    try:
        artist = search_artist(artist_name)
    except (HTTPError, URLError, TimeoutError):
        return None
    if not artist:
        return None

    try:
        payload = browse_release_groups(artist["id"], offset=0)
    except (HTTPError, URLError, TimeoutError):
        return None
    groups = payload.get("release-groups", [])
    groups = [group for group in groups if (group.get("primary-type") or "Other").title() == "Album"]
    if not groups:
        return None

    groups.sort(key=lambda item: item.get("first-release-date", ""))
    pick = groups[0]
    return ReleaseCandidate(
        artist_name=artist_name,
        release_title=pick.get("title", "Unknown title"),
        release_date=pick.get("first-release-date", ""),
        release_type="Bonus catalog pick",
        primary_type="Album",
        source="musicbrainz",
        score=15,
        why=[f"bonus older recommendation from {artist_name}"],
    )
