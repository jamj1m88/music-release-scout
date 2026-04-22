from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "MusicReleaseScout/0.1 (personal music release digest)"


def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    final_url = url
    if params:
        final_url = f"{url}?{urlencode(params)}"
    request = Request(
        final_url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))
