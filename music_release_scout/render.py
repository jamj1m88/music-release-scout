from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .discovery import ReleaseCandidate


def render_html(profile_name: str, picks: list[ReleaseCandidate], output_path: Path) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards: list[str] = []
    for pick in picks:
        why = "".join(f"<li>{html.escape(reason)}</li>" for reason in pick.why)
        links: list[str] = []
        if pick.apple_music_url:
            links.append(f'<a href="{html.escape(pick.apple_music_url)}">Apple/iTunes</a>')
        if pick.apple_preview_url:
            links.append(f'<a href="{html.escape(pick.apple_preview_url)}">Preview clip</a>')
        if pick.youtube_music_url:
            links.append(f'<a href="{html.escape(pick.youtube_music_url)}">YouTube Music search</a>')
        link_html = " | ".join(links) if links else "No listening links found"
        cards.append(
            f"""
            <article class="card">
              <div class="meta">{html.escape(pick.bucket.title())} • {html.escape(pick.source_detail)} • {html.escape(pick.release_date or pick.release_type)}</div>
              <h2>{html.escape(pick.artist_name)} - {html.escape(pick.release_title)}</h2>
              <p class="links">{link_html}</p>
              <ul>{why}</ul>
            </article>
            """
        )

    body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Music Release Scout</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f6f2e8;
        --panel: #fffdf8;
        --ink: #1f1d1a;
        --muted: #6b655d;
        --line: #ded3c2;
        --accent: #c25b2a;
      }}
      body {{
        margin: 0;
        padding: 32px 18px 48px;
        background:
          radial-gradient(circle at top right, rgba(194, 91, 42, 0.10), transparent 28%),
          linear-gradient(180deg, #f8f4eb 0%, var(--bg) 100%);
        color: var(--ink);
        font: 16px/1.5 Georgia, serif;
      }}
      main {{
        max-width: 840px;
        margin: 0 auto;
      }}
      h1 {{
        font-size: clamp(2rem, 4vw, 3.4rem);
        margin-bottom: 0.4rem;
      }}
      .lede {{
        color: var(--muted);
        max-width: 60ch;
      }}
      .card {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px 18px 12px;
        margin-top: 16px;
        box-shadow: 0 10px 30px rgba(31, 29, 26, 0.05);
      }}
      .meta {{
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
      }}
      h2 {{
        margin: 0.4rem 0 0.75rem;
        font-size: 1.4rem;
      }}
      .links a {{
        color: var(--accent);
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Music Release Scout</h1>
      <p class="lede">Weekly picks for {html.escape(profile_name)} generated on {html.escape(timestamp)}.</p>
      {''.join(cards) if cards else '<p>No fresh matches this week.</p>'}
    </main>
  </body>
</html>
"""
    output_path.write_text(body, encoding="utf-8")


def write_json(picks: list[ReleaseCandidate], output_path: Path) -> None:
    payload = [pick.to_dict() for pick in picks]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
