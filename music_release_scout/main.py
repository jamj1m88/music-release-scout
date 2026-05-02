from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .discovery import BUCKET_ORDER, ReleaseCandidate, discover_bonus_catalog_pick, discover_candidates_by_bucket
from .enrichment import enrich_candidate
from .notifiers import send_email_digest, send_telegram_digest
from .render import render_html, write_json
from .state import candidate_key, load_seen_keys, write_state


def _delivery_timezone() -> ZoneInfo:
    timezone_name = os.environ.get("MUSIC_SCOUT_TIMEZONE", "Australia/Sydney")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Australia/Sydney")


def _today_local_date() -> str:
    return datetime.now(_delivery_timezone()).date().isoformat()


def _normalize_artist_key(artist_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", artist_name)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower().strip()
    normalized = re.sub(r"^the\s+", "", normalized)
    normalized = re.sub(r"\s+(feat|featuring|with|x|and)\s+.*$", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def _has_artist(selected: list[ReleaseCandidate], artist_name: str) -> bool:
    artist_key = _normalize_artist_key(artist_name)
    return any(_normalize_artist_key(candidate.artist_name) == artist_key for candidate in selected)


def _boost_multi_lane_candidates(candidates_by_bucket: dict[str, list[ReleaseCandidate]]) -> None:
    support_map: dict[str, set[str]] = {}
    for bucket, candidates in candidates_by_bucket.items():
        for candidate in candidates:
            support_map.setdefault(candidate_key(candidate), set()).add(bucket)

    for candidates in candidates_by_bucket.values():
        for candidate in candidates:
            supports = support_map.get(candidate_key(candidate), set())
            if len(supports) > 1:
                candidate.score += 12 * (len(supports) - 1)
                candidate.significance += 6 * (len(supports) - 1)
                reason = "surfaced across multiple research lanes this week"
                if reason not in candidate.why:
                    candidate.why.insert(0, reason)


def _sort_candidates(candidates_by_bucket: dict[str, list[ReleaseCandidate]]) -> None:
    for candidates in candidates_by_bucket.values():
        candidates.sort(key=lambda item: (item.score, item.significance, item.release_date), reverse=True)


def _pick_balanced_candidates(
    candidates_by_bucket: dict[str, list[ReleaseCandidate]],
    seen_keys: set[str],
    max_count: int,
) -> list[ReleaseCandidate]:
    selected: list[ReleaseCandidate] = []
    chosen_keys: set[str] = set()
    chosen_artists: set[str] = set()
    pools = {bucket: list(candidates) for bucket, candidates in candidates_by_bucket.items()}

    while len(selected) < max_count:
        progress = False
        for bucket in BUCKET_ORDER:
            pool = pools.get(bucket, [])
            while pool:
                candidate = pool.pop(0)
                key = candidate_key(candidate)
                artist_key = _normalize_artist_key(candidate.artist_name)
                if key in seen_keys or key in chosen_keys or artist_key in chosen_artists:
                    continue
                selected.append(candidate)
                chosen_keys.add(key)
                chosen_artists.add(artist_key)
                progress = True
                break
            if len(selected) >= max_count:
                break
        if not progress:
            break

    if len(selected) >= max_count:
        return selected[:max_count]

    remaining = []
    for bucket in BUCKET_ORDER:
        remaining.extend(pools.get(bucket, []))
    remaining.sort(key=lambda item: (item.score, item.significance, item.release_date), reverse=True)

    for candidate in remaining:
        key = candidate_key(candidate)
        artist_key = _normalize_artist_key(candidate.artist_name)
        if key in seen_keys or key in chosen_keys or artist_key in chosen_artists:
            continue
        selected.append(candidate)
        chosen_keys.add(key)
        chosen_artists.add(artist_key)
        if len(selected) >= max_count:
            break

    return selected


def _prepare_repeat_candidates(
    target_count: int,
    candidates_by_bucket: dict[str, list[ReleaseCandidate]],
    existing: list[ReleaseCandidate] | None = None,
) -> list[ReleaseCandidate]:
    selected = list(existing or [])
    chosen_keys = {candidate_key(candidate) for candidate in selected}
    chosen_artists = {_normalize_artist_key(candidate.artist_name) for candidate in selected}
    pools = {bucket: list(candidates) for bucket, candidates in candidates_by_bucket.items()}

    while len(selected) < target_count:
        progress = False
        for bucket in BUCKET_ORDER:
            pool = pools.get(bucket, [])
            while pool:
                candidate = pool.pop(0)
                key = candidate_key(candidate)
                artist_key = _normalize_artist_key(candidate.artist_name)
                if key in chosen_keys or artist_key in chosen_artists:
                    continue
                reason = "was strong enough to repeat because this week was otherwise quiet"
                if reason not in candidate.why:
                    candidate.why.insert(0, reason)
                selected.append(candidate)
                chosen_keys.add(key)
                chosen_artists.add(artist_key)
                progress = True
                break
            if len(selected) >= target_count:
                break
        if not progress:
            break

    return selected


def build_digest(config_path: Path, output_dir: Path, state_path: Path) -> tuple[list[dict], str]:
    config = load_config(config_path)
    output_dir.mkdir(exist_ok=True)
    state_path.parent.mkdir(exist_ok=True)
    html_path = output_dir / "latest_digest.html"
    json_path = output_dir / "latest_digest.json"
    seen_keys = load_seen_keys(state_path)

    candidates_by_bucket = discover_candidates_by_bucket(config)
    _boost_multi_lane_candidates(candidates_by_bucket)
    _sort_candidates(candidates_by_bucket)

    picks = _pick_balanced_candidates(
        candidates_by_bucket=candidates_by_bucket,
        seen_keys=seen_keys,
        max_count=config.discovery.max_recommendations,
    )

    if config.discovery.allow_repeats_when_empty and len(picks) < config.discovery.max_recommendations:
        target_count = min(
            config.discovery.max_recommendations,
            max(config.discovery.max_repeat_recommendations, len(picks)),
        )
        picks = _prepare_repeat_candidates(
            target_count=target_count,
            candidates_by_bucket=candidates_by_bucket,
            existing=picks,
        )

    bonus = discover_bonus_catalog_pick(config)
    if (
        bonus
        and candidate_key(bonus) not in {candidate_key(pick) for pick in picks}
        and not _has_artist(picks, bonus.artist_name)
    ):
        if candidate_key(bonus) not in seen_keys or not picks:
            picks.append(bonus)

    enriched_picks = [enrich_candidate(candidate) for candidate in picks]

    render_html(config.profile_name, enriched_picks, html_path)
    write_json(enriched_picks, json_path)
    seen_keys.update(candidate_key(pick) for pick in enriched_picks)
    write_state(
        state_path=state_path,
        profile_name=config.profile_name,
        recommendation_count=len(enriched_picks),
        html_path=html_path,
        json_path=json_path,
        seen_keys=seen_keys,
        last_delivery_local_date=_today_local_date(),
    )

    html_body = html_path.read_text(encoding="utf-8")
    send_telegram_digest(config, enriched_picks)
    send_email_digest(config, enriched_picks, html_body)
    return [pick.to_dict() for pick in enriched_picks], html_body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send a music release digest.")
    parser.add_argument("--config", default="config.json", help="Path to the config JSON file.")
    parser.add_argument("--output-dir", default="output", help="Directory for generated digest files.")
    parser.add_argument(
        "--state-path",
        default="output/state.json",
        help="Path to the state JSON file used for deduping recommendations.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    picks, _ = build_digest(
        config_path=Path(args.config),
        output_dir=Path(args.output_dir),
        state_path=Path(args.state_path),
    )
    print(json.dumps({"recommendations": picks}, indent=2))


if __name__ == "__main__":
    main()
