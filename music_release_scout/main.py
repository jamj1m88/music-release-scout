from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .discovery import BUCKET_ORDER, ReleaseCandidate, discover_bonus_catalog_pick, discover_candidates_by_bucket
from .enrichment import enrich_candidate
from .notifiers import send_email_digest, send_telegram_digest
from .render import render_html, write_json
from .state import candidate_key, load_seen_keys, write_state


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
    pools = {bucket: list(candidates) for bucket, candidates in candidates_by_bucket.items()}

    while len(selected) < max_count:
        progress = False
        for bucket in BUCKET_ORDER:
            pool = pools.get(bucket, [])
            while pool:
                candidate = pool.pop(0)
                key = candidate_key(candidate)
                if key in seen_keys or key in chosen_keys:
                    continue
                selected.append(candidate)
                chosen_keys.add(key)
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
        if key in seen_keys or key in chosen_keys:
            continue
        selected.append(candidate)
        chosen_keys.add(key)
        if len(selected) >= max_count:
            break

    return selected


def _prepare_repeat_candidates(
    config_max: int,
    candidates_by_bucket: dict[str, list[ReleaseCandidate]],
) -> list[ReleaseCandidate]:
    selected: list[ReleaseCandidate] = []
    chosen_keys: set[str] = set()
    pools = {bucket: list(candidates) for bucket, candidates in candidates_by_bucket.items()}

    while len(selected) < config_max:
        progress = False
        for bucket in BUCKET_ORDER:
            pool = pools.get(bucket, [])
            while pool:
                candidate = pool.pop(0)
                key = candidate_key(candidate)
                if key in chosen_keys:
                    continue
