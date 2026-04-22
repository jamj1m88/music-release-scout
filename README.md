# Music Release Scout

`Music Release Scout` is a small Python tool that watches for new music releases that match your taste profile, enriches each pick with listen/preview links, and sends a weekly digest to your phone by Telegram or email.

The first version is intentionally simple:

- You describe your taste in a local JSON config file.
- The tool checks favorite artists for recent albums, EPs, and singles.
- It ranks results using your positive and negative signals.
- It attaches direct Apple/iTunes links and a quick search link for YouTube Music.
- It writes an HTML digest locally and can also send the digest through Telegram or email.

## Why this design

Your main friction is the gap between "I heard about this" and "I can listen right now."

So each recommendation includes:

- what released
- why it was chosen
- release date
- a direct Apple/iTunes link when available
- a preview clip link when available
- a YouTube Music search link as a fallback

## Project layout

- [config.example.json](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/config.example.json)
- [music_release_scout/main.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/main.py)
- [music_release_scout/config.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/config.py)
- [music_release_scout/discovery.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/discovery.py)
- [music_release_scout/enrichment.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/enrichment.py)
- [music_release_scout/notifiers.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/notifiers.py)
- [music_release_scout/render.py](/Users/jamieilagan/Documents/Codex/2026-04-22-i-want-a-tool-that-researches/music_release_scout/render.py)

## Setup

1. Edit `config.json` with your favorite artists and taste signals.
2. Add either Telegram credentials or SMTP email credentials.
3. Run:

```bash
/Users/jamieilagan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m music_release_scout.main --config config.json
```

The run creates:

- `output/latest_digest.html`
- `output/latest_digest.json`
- `output/state.json`

`state.json` remembers what has already been sent so you do not get the same release repeated every week.

## Secrets and environment variables

For local-only use, you can place credentials directly in `config.json`.

For safer setups, especially hosted runs, keep secrets out of the file and use environment variables instead. This project already supports that:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

`config.json` can point to those env vars with:

```json
"bot_token_env": "TELEGRAM_BOT_TOKEN",
"chat_id_env": "TELEGRAM_CHAT_ID"
```

## Scheduling weekly runs

This tool is designed to run once per week.

You can schedule it with:

- `cron`
- `launchd`
- a GitHub Action
- a Codex automation

## Hosted weekly run with GitHub Actions

If you want the tool to run even when your computer is off, use the included workflow in `.github/workflows/weekly-release-scout.yml`.

What it does:

- runs on GitHub-hosted runners
- checks the time in `Australia/Sydney`
- sends the digest only when it is Friday at 9:00 AM Sydney time
- stores recommendation memory in `data/state.json`
- commits updated state back to the repo so future runs do not resend the same release

Setup steps:

1. Push this project to a GitHub repository.
2. In GitHub, open `Settings -> Secrets and variables -> Actions`.
3. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Enable GitHub Actions for the repo.

GitHub cron schedules use UTC, not Sydney time. The workflow avoids daylight-savings mistakes by running at both possible UTC hours and checking the actual local Sydney time before sending.

## Taste profile tips

The most important fields are:

- `favorite_artists`: strongest signal
- `genre_keywords`: words you want rewarded in titles, genres, or editorial text
- `avoid_keywords`: words you want penalized
- `bonus_catalog_artists`: optional older favorites for a "one older recommendation" extra

This first version learns from rules you type in yourself. That keeps it transparent and easy to tune.

## Notification options

### Telegram

Create a bot with BotFather, then add:

- `telegram.bot_token` and `telegram.chat_id`, or preferably:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### Email

Use any SMTP provider by filling:

- `email.smtp_host`
- `email.smtp_port`
- `email.username`
- `email.password`
- `email.from_address`
- `email.to_address`

## Notes

- Discovery uses MusicBrainz metadata for recent releases.
- Link enrichment uses Apple's iTunes Search API for direct store and preview links.
- If Telegram or email is not configured, the local HTML digest still works as a weekly inbox.
