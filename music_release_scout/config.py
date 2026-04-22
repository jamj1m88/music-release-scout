from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TelegramConfig:
    enabled: bool
    bot_token: str
    chat_id: str


@dataclass
class EmailConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_address: str
    to_address: str
    use_tls: bool


@dataclass
class DeliveryConfig:
    telegram: TelegramConfig
    email: EmailConfig


@dataclass
class DiscoveryConfig:
    days_back: int
    max_recommendations: int
    include_release_types: list[str]
    include_bonus_catalog_pick: bool
    allow_repeats_when_empty: bool
    max_repeat_recommendations: int
    enable_similar_artists: bool
    max_similar_artists_per_seed: int
    similar_artist_min_match: float
    lastfm_api_key: str
    editorial_outlets: list[str]


@dataclass
class AppConfig:
    profile_name: str
    favorite_artists: list[str]
    genre_keywords: list[str]
    avoid_keywords: list[str]
    bonus_catalog_artists: list[str]
    discovery: DiscoveryConfig
    delivery: DeliveryConfig


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_secret(raw: dict[str, Any], value_key: str, env_key: str) -> str:
    if raw.get(env_key):
        return os.environ.get(str(raw[env_key]), "").strip()
    return str(raw.get(value_key, "")).strip()


def load_config(path: str | Path) -> AppConfig:
    raw = _read_json(Path(path))
    telegram_raw = raw["delivery"]["telegram"]
    email_raw = raw["delivery"]["email"]
    discovery_raw = raw["discovery"]
    return AppConfig(
        profile_name=raw["profile_name"],
        favorite_artists=raw["favorite_artists"],
        genre_keywords=raw.get("genre_keywords", []),
        avoid_keywords=raw.get("avoid_keywords", []),
        bonus_catalog_artists=raw.get("bonus_catalog_artists", []),
        discovery=DiscoveryConfig(
            days_back=int(discovery_raw["days_back"]),
            max_recommendations=int(discovery_raw["max_recommendations"]),
            include_release_types=list(discovery_raw["include_release_types"]),
            include_bonus_catalog_pick=bool(discovery_raw["include_bonus_catalog_pick"]),
            allow_repeats_when_empty=bool(discovery_raw.get("allow_repeats_when_empty", True)),
            max_repeat_recommendations=int(discovery_raw.get("max_repeat_recommendations", 4)),
            enable_similar_artists=bool(discovery_raw.get("enable_similar_artists", True)),
            max_similar_artists_per_seed=int(discovery_raw.get("max_similar_artists_per_seed", 3)),
            similar_artist_min_match=float(discovery_raw.get("similar_artist_min_match", 0.5)),
            lastfm_api_key=_read_secret(discovery_raw, "lastfm_api_key", "lastfm_api_key_env"),
            editorial_outlets=list(
                discovery_raw.get("editorial_outlets", ["npr_music", "pitchfork_best_new_albums"])
            ),
        ),
        delivery=DeliveryConfig(
            telegram=TelegramConfig(
                enabled=bool(telegram_raw["enabled"]),
                bot_token=_read_secret(telegram_raw, "bot_token", "bot_token_env"),
                chat_id=_read_secret(telegram_raw, "chat_id", "chat_id_env"),
            ),
            email=EmailConfig(
                enabled=bool(email_raw["enabled"]),
                smtp_host=str(email_raw["smtp_host"]),
                smtp_port=int(email_raw["smtp_port"]),
                username=_read_secret(email_raw, "username", "username_env"),
                password=_read_secret(email_raw, "password", "password_env"),
                from_address=str(email_raw["from_address"]),
                to_address=str(email_raw["to_address"]),
                use_tls=bool(email_raw.get("use_tls", True)),
            ),
        ),
    )
