Music Release Scout is a small Python tool that researches new music for you, attaches quick listening links, and sends a weekly digest to your phone by Telegram or email.

The current version has three discovery lanes:

core: new releases from your favorite artists
similar: new releases from artists adjacent to your taste graph
editorial: albums surfaced by trusted outlets such as NPR Music and Pitchfork
The digest tries to distribute picks across those lanes instead of letting one source dominate the whole week.

How it picks music
Each run:

checks your favorite artists for recent albums, EPs, and singles through MusicBrainz
expands outward through Last.fm similar-artist signals when a Last.fm API key is configured
scans trusted editorial pages:
NPR Music New Music Friday
Pitchfork Best New Albums
scores candidates by:
how close they are to your core artist list
whether they also appear in the similar-artist lane
whether an editorial outlet highlighted them
how recent they are
how strongly they match your genre/vibe keywords
whether they surfaced in multiple lanes at once
attaches Apple/iTunes and preview links plus a YouTube Music search fallback
If a week is otherwise quiet, it can resend a few especially strong recent picks instead of sending an empty digest.

Project layout
config.example.json
config.json
music_release_scout/main.py
music_release_scout/config.py
music_release_scout/discovery.py
music_release_scout/enrichment.py
music_release_scout/notifiers.py
music_release_scout/render.py
data/state.json
Setup
Edit config.json with your favorite artists and taste keywords.
Add either Telegram credentials or SMTP email credentials.
Add a Last.fm API key if you want the similar lane to work.
Run:
/Users/jamieilagan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m music_release_scout.main --config config.json
The run creates:

output/latest_digest.html
output/latest_digest.json
data/state.json
data/state.json remembers what has already been sent so the hosted workflow can avoid resending the same release every week.

Secrets and environment variables
For safer setups, especially hosted runs, keep secrets out of config.json and use environment variables instead.

Supported env vars:

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
LASTFM_API_KEY
config.json already points at these names by default.

Hosted weekly run with GitHub Actions
If you want the tool to run when your computer is off, use the included workflow in .github/workflows/weekly-release-scout.yml.

What it does:

runs on GitHub-hosted runners
checks the time in Australia/Sydney
sends the digest only when it is Friday at 9:00 AM Sydney time
stores recommendation memory in data/state.json
commits updated state back to the repo so future runs remember what was already sent
Setup steps:

Push this project to a GitHub repository.
In GitHub, open Settings -> Secrets and variables -> Actions.
Add these repository secrets:
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
LASTFM_API_KEY
Enable GitHub Actions for the repo.
GitHub cron schedules use UTC, not Sydney time. The workflow avoids daylight-savings mistakes by running at both possible UTC hours and checking actual Sydney time before sending.

Taste profile tips
The most important fields are:

favorite_artists: strongest core signal
genre_keywords: words you want rewarded in titles, categories, or editorial framing
bonus_catalog_artists: optional older favorites for a one-off older recommendation
allow_repeats_when_empty: resend a few strong picks when the week is otherwise quiet
editorial_outlets: which trusted editorial sources to scan
Notes
Music metadata comes from the official MusicBrainz API.
Similar-artist expansion uses the official Last.fm API.
Editorial coverage currently includes official NPR Music pages and Pitchfork Best New Albums pages:
NPR Music New Music Friday
Pitchfork Best New Albums
Link enrichment uses Apple’s iTunes Search API.
