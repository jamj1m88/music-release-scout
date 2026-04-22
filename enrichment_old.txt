from __future__ import annotations

from urllib.parse import quote_plus

from .discovery import ReleaseCandidate
from .http import get_json


ITUNES_SEARCH_API = "https://itunes.apple.com/search"


def _find_album_match(artist_name: str, release_title: str) -> dict | None:
    payload = get_json(
        ITUNES_SEARCH_API,
        {
            "term": f"{artist_name} {release_title}",
            "entity": "album",
            "media": "music",
            "limit": 5,
        },
    )
    results = payload.get("results", [])
    if not results:
        return None

    lowered_artist = artist_name.lower()
    lowered_title = release_title.lower()
    for result in results:
        candidate_artist = str(result.get("artistName", "")).lower()
        candidate_title = str(result.get("collectionName", "")).lower()
        if lowered_artist in candidate_artist and lowered_title in candidate_title:
            return result
    return results[0]


def _find_preview(artist_name: str, release_title: str) -> str | None:
    payload = get_json(
        ITUNES_SEARCH_API,
        {
            "term": f"{artist_name} {release_title}",
            "entity": "song",
            "media": "music",
            "limit": 3,
        },
    )
    for result in payload.get("results", []):
        preview = result.get("previewUrl")
        if preview:
            return str(preview)
    return None


def enrich_candidate(candidate: ReleaseCandidate) -> ReleaseCandidate:
    album_match = _find_album_match(candidate.artist_name, candidate.release_title)
    if album_match:
        candidate.apple_music_url = album_match.get("collectionViewUrl")
    candidate.apple_preview_url = _find_preview(candidate.artist_name, candidate.release_title)
    candidate.youtube_music_url = (
        "https://music.youtube.com/search?q="
        + quote_plus(f"{candidate.artist_name} {candidate.release_title}")
    )
    return candidate
