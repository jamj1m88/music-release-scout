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


def _score_release_group(
    config: AppConfig,
    watch: ArtistWatch,
    release_group: dict[str, Any],
) -> tuple[int, int, list[str]]:
    score = 0
    significance = 0
    reasons: list[str] = []

    if watch.bucket == "core":
        score += 88
        significance += 24
        reasons.append(f"new release from favorite artist {watch.artist_name}")
    elif watch.bucket == "similar":
        score += 62
        significance += 14
        if watch.seed_artist:
            reasons.append(f"similar artist lane matched from {watch.seed_artist}")
        if watch.similarity:
            score += int(watch.similarity * 24)
            significance += int(watch.similarity * 10)
            reasons.append(f"similarity signal scored {watch.similarity:.2f}")

    primary_type = (release_group.get("primary-type") or "Other").title()
    if primary_type == "Album":
        score += 12
        significance += 10
        reasons.append("album gets the highest priority boost")
    elif primary_type == "EP":
        score += 7
        significance += 6
        reasons.append("EP gets a medium priority boost")
    elif primary_type == "Single":
        score += 3
        significance += 3
        reasons.append("single gets a quick-check boost")

    tags = release_group.get("tags", [])
    tag_names = [
        str(tag.get("name", ""))
        for tag in tags
        if isinstance(tag, dict) and tag.get("name")
    ]
    blob = _text_blob(
        release_group.get("title", ""),
        release_group.get("disambiguation", ""),
        " ".join(tag_names),
    )
    keyword_score, keyword_reasons = _keyword_score(config, blob)
    score += keyword_score
    reasons.extend(keyword_reasons)

    release_date = release_group.get("first-release-date", "")
    recent_bonus = _recentness_bonus(release_date)
    score += recent_bonus
    significance += recent_bonus
    if recent_bonus:
        reasons.append("very recent release timing boosted the score")

    return score, significance, reasons


def discover_recent_releases_for_watchlist(
    config: AppConfig,
    watchlist: list[ArtistWatch],
) -> list[ReleaseCandidate]:
    cutoff = date.today() - timedelta(days=config.discovery.days_back)
    releases: list[ReleaseCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    for watch in watchlist:
        try:
            artist = search_artist(watch.artist_name)
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

                dedupe_key = (
                    watch.bucket,
                    watch.artist_name.lower(),
                    group.get("title", "").lower(),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                score, significance, reasons = _score_release_group(config, watch, group)
                releases.append(
                    ReleaseCandidate(
                        artist_name=watch.artist_name,
                        release_title=group.get("title", "Unknown title"),
                        release_date=group.get("first-release-date", ""),
                        release_type=primary_type,
                        primary_type=primary_type,
                        source="musicbrainz",
                        score=score,
                        why=reasons,
                        bucket=watch.bucket,
                        source_detail=watch.source_detail,
                        significance=significance,
                    )
                )

            offset += len(groups)
            if offset >= int(payload.get("release-group-count", 0)):
                break

    releases.sort(key=lambda item: (item.score, item.release_date), reverse=True)
    return releases


def discover_similar_watchlist(config: AppConfig) -> tuple[list[ArtistWatch], set[str]]:
    api_key = config.discovery.lastfm_api_key
    if not config.discovery.enable_similar_artists or not api_key:
        return [], set()

    similar_watchlist: list[ArtistWatch] = []
    similar_names: set[str] = set()
    seen: set[str] = set()

    for artist_name in config.favorite_artists:
        try:
            payload = get_json(
                LASTFM_API,
                {
                    "method": "artist.getSimilar",
                    "artist": artist_name,
                    "api_key": api_key,
                    "format": "json",
                    "limit": config.discovery.max_similar_artists_per_seed,
                    "autocorrect": 1,
                },
            )
        except (HTTPError, URLError, TimeoutError):
            continue

        for artist in payload.get("similarartists", {}).get("artist", []):
            similar_name = str(artist.get("name", "")).strip()
            if not similar_name:
                continue
            lowered = similar_name.lower()
            if lowered in seen or lowered in {item.lower() for item in config.favorite_artists}:
                continue
            try:
                match = float(artist.get("match", 0))
            except (TypeError, ValueError):
                match = 0.0
            if match < config.discovery.similar_artist_min_match:
                continue

            seen.add(lowered)
            similar_names.add(lowered)
            similar_watchlist.append(
                ArtistWatch(
                    artist_name=similar_name,
                    bucket="similar",
                    source_detail="Last.fm similar artists",
                    seed_artist=artist_name,
                    similarity=match,
                )
            )

    return similar_watchlist, similar_names


def _html_to_text(raw_html: str) -> str:
    without_scripts = re.sub(r"<(script|style).*?>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    with_breaks = re.sub(r"</(p|div|li|h1|h2|h3|h4|br|section|article)>", "\n", without_scripts, flags=re.I)
    no_tags = re.sub(r"<[^>]+>", " ", with_breaks)
    return unescape(no_tags)


def _extract_unique_article_links(section_html: str) -> list[str]:
    links = re.findall(
        r"https://www\.npr\.org/\d{4}/\d{2}/\d{2}/\d+/new-music-friday[^\"'<>\s]*",
        section_html,
    )
    unique: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        unique.append(link)
    return unique[:2]


def _parse_artist_title_entry(entry: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"^[•\-\s]+", "", entry).strip()
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*$", "", cleaned).strip()
    if not cleaned:
        return None

    quoted_match = re.match(r"(.+?),\s*[\"'“](.+?)[\"'”]\s*$", cleaned)
    if quoted_match:
        return quoted_match.group(1).strip(), quoted_match.group(2).strip()

    colon_match = re.match(r"(.+?):\s+(.+)$", cleaned)
    if colon_match:
        return colon_match.group(1).strip(), colon_match.group(2).strip()

    if "," in cleaned:
        artist_name, release_title = cleaned.split(",", 1)
        return artist_name.strip(), release_title.strip()

    return None


def _extract_bullets(section_text: str) -> list[str]:
    return [line.strip() for line in section_text.splitlines() if line.strip().startswith("•")]


def _score_editorial_pick(
    config: AppConfig,
    artist_name: str,
    release_title: str,
    base_score: int,
    significance: int,
    source_detail: str,
    favorite_names: set[str],
    similar_names: set[str],
    extra_blob: str = "",
) -> tuple[int, int, list[str]]:
    score = base_score
    reasons = [f"highlighted by {source_detail}"]
    lowered_artist = artist_name.lower()
    if lowered_artist in favorite_names:
        score += 35
        significance += 14
        reasons.append("editorial pick also comes from your core artist list")
    elif lowered_artist in similar_names:
        score += 22
        significance += 9
        reasons.append("editorial pick overlaps with your similar-artist lane")

    keyword_score, keyword_reasons = _keyword_score(
        config,
        _text_blob(artist_name, release_title, source_detail, extra_blob),
    )
    score += keyword_score
    reasons.extend(keyword_reasons)
    return score, significance, reasons


def discover_npr_editorial_candidates(
    config: AppConfig,
    favorite_names: set[str],
    similar_names: set[str],
) -> list[ReleaseCandidate]:
    try:
        section_html = get_text(NPR_NEWMUSICFRIDAY_SECTION)
    except (HTTPError, URLError, TimeoutError):
        return []

    candidates: list[ReleaseCandidate] = []
    for article_url in _extract_unique_article_links(section_html):
        try:
            article_text = _html_to_text(get_text(article_url))
        except (HTTPError, URLError, TimeoutError):
            continue

        article_date_match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", article_text)
        article_date = article_date_match.group(1) if article_date_match else ""

        featured_match = re.search(
            r"(Featured Albums|The Starting 5)(.*?)(Other notable albums out|Stream The Playlist)",
            article_text,
            flags=re.S,
        )
        other_match = re.search(
            r"Other notable albums out.*?(?=Stream The Playlist|Sponsor Message|$)",
            article_text,
            flags=re.S,
        )

        sections = []
        if featured_match:
            sections.append((featured_match.group(2), 82, 34, "NPR Music New Music Friday featured"))
        if other_match:
            sections.append((other_match.group(0), 68, 22, "NPR Music New Music Friday"))

        for block, base_score, significance, source_detail in sections:
            for entry in _extract_bullets(block):
                parsed = _parse_artist_title_entry(entry)
                if not parsed:
                    continue
                artist_name, release_title = parsed
                score, tuned_significance, reasons = _score_editorial_pick(
                    config,
                    artist_name,
                    release_title,
                    base_score=base_score,
                    significance=significance,
                    source_detail=source_detail,
                    favorite_names=favorite_names,
                    similar_names=similar_names,
                    extra_blob="npr music new music friday",
                )
                candidates.append(
                    ReleaseCandidate(
                        artist_name=artist_name,
                        release_title=release_title,
                        release_date=article_date,
                        release_type="Editorial pick",
                        primary_type="Album",
                        source="npr",
                        score=score,
                        why=reasons,
                        bucket="editorial",
                        source_detail=source_detail,
                        significance=tuned_significance,
                    )
                )

    return candidates


def discover_pitchfork_editorial_candidates(
    config: AppConfig,
    favorite_names: set[str],
    similar_names: set[str],
) -> list[ReleaseCandidate]:
    try:
        page_text = _html_to_text(get_text(PITCHFORK_BEST_NEW_ALBUMS))
    except (HTTPError, URLError, TimeoutError):
        return []

    cutoff = date.today() - timedelta(days=config.discovery.days_back * 3)
    matches = re.finditer(
        r"([A-Za-z/&+]+)\s+(.+?)\s+(.+?)\s+By\s+.+?\s+([A-Z][a-z]+ \d{1,2}, \d{4})",
        page_text,
        flags=re.S,
    )
    candidates: list[ReleaseCandidate] = []
    seen: set[tuple[str, str]] = set()
    for match in matches:
        category = " ".join(match.group(1).split())
        release_title = " ".join(match.group(2).split())
        artist_name = " ".join(match.group(3).split())
        review_date = " ".join(match.group(4).split())
        parsed_date = _safe_date(review_date)
        if not parsed_date or parsed_date < cutoff:
            continue
        dedupe_key = (artist_name.lower(), release_title.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        score, significance, reasons = _score_editorial_pick(
            config,
            artist_name,
            release_title,
            base_score=84,
            significance=38,
            source_detail="Pitchfork Best New Albums",
            favorite_names=favorite_names,
            similar_names=similar_names,
            extra_blob=category,
        )
        reasons.append(f"genre framing from Pitchfork was {category}")
        candidates.append(
            ReleaseCandidate(
                artist_name=artist_name,
                release_title=release_title,
                release_date=review_date,
                release_type="Editorial pick",
                primary_type="Album",
                source="pitchfork",
                score=score,
                why=reasons,
                bucket="editorial",
                source_detail="Pitchfork Best New Albums",
                significance=significance,
            )
        )

    return candidates


def discover_candidates_by_bucket(config: AppConfig) -> dict[str, list[ReleaseCandidate]]:
    favorite_names = {artist.lower() for artist in config.favorite_artists}
    core_watchlist = [
        ArtistWatch(
            artist_name=artist_name,
            bucket="core",
            source_detail="Your core artist list",
        )
        for artist_name in config.favorite_artists
    ]
    core_candidates = discover_recent_releases_for_watchlist(config, core_watchlist)

    similar_watchlist, similar_names = discover_similar_watchlist(config)
    similar_candidates = discover_recent_releases_for_watchlist(config, similar_watchlist)

    editorial_candidates: list[ReleaseCandidate] = []
    if "npr_music" in config.discovery.editorial_outlets:
        editorial_candidates.extend(
            discover_npr_editorial_candidates(config, favorite_names=favorite_names, similar_names=similar_names)
        )
    if "pitchfork_best_new_albums" in config.discovery.editorial_outlets:
        editorial_candidates.extend(
            discover_pitchfork_editorial_candidates(
                config,
                favorite_names=favorite_names,
                similar_names=similar_names,
            )
        )

    editorial_candidates.sort(key=lambda item: (item.score, item.significance), reverse=True)
    return {
        "core": core_candidates,
        "similar": similar_candidates,
        "editorial": editorial_candidates,
    }


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
        score=18,
        why=[f"bonus older recommendation from {artist_name}"],
        bucket="editorial",
        source_detail="Bonus catalog fallback",
        significance=6,
    )
