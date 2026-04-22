from __future__ import annotations

import json
from pathlib import Path

from .discovery import ReleaseCandidate


def load_seen_keys(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    seen = payload.get("seen_release_keys", [])
    return {str(item) for item in seen}


def candidate_key(candidate: ReleaseCandidate) -> str:
    return "|".join(
        [
            candidate.artist_name.strip().lower(),
            candidate.release_title.strip().lower(),
        ]
    )


def write_state(
    state_path: Path,
    profile_name: str,
    recommendation_count: int,
    html_path: Path,
    json_path: Path,
    seen_keys: set[str],
) -> None:
    state_path.write_text(
        json.dumps(
            {
                "profile_name": profile_name,
                "last_run_files": {
                    "html": str(html_path),
                    "json": str(json_path),
                },
                "recommendation_count": recommendation_count,
                "seen_release_keys": sorted(seen_keys),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
