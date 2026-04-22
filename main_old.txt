from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .discovery import discover_bonus_catalog_pick, discover_recent_releases
from .enrichment import enrich_candidate
from .notifiers import send_email_digest, send_telegram_digest
from .render import render_html, write_json
from .state import candidate_key, load_seen_keys, write_state


def build_digest(config_path: Path, output_dir: Path, state_path: Path) -> tuple[list[dict], str]:
    config = load_config(config_path)
    output_dir.mkdir(exist_ok=True)
    state_path.parent.mkdir(exist_ok=True)
    html_path = output_dir / "latest_digest.html"
    json_path = output_dir / "latest_digest.json"
    seen_keys = load_seen_keys(state_path)

    fresh_candidates = [
        candidate
        for candidate in discover_recent_releases(config)
        if candidate_key(candidate) not in seen_keys
    ]
    picks = [enrich_candidate(candidate) for candidate in fresh_candidates]
    bonus = discover_bonus_catalog_pick(config)
    if bonus and candidate_key(bonus) not in seen_keys:
        picks.append(enrich_candidate(bonus))

    render_html(config.profile_name, picks, html_path)
    write_json(picks, json_path)
    seen_keys.update(candidate_key(pick) for pick in picks)
    write_state(
        state_path=state_path,
        profile_name=config.profile_name,
        recommendation_count=len(picks),
        html_path=html_path,
        json_path=json_path,
        seen_keys=seen_keys,
    )

    html_body = html_path.read_text(encoding="utf-8")
    send_telegram_digest(config, picks)
    send_email_digest(config, picks, html_body)
    return [pick.to_dict() for pick in picks], html_body


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
