from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "MusicReleaseScout/0.1 (personal music release digest)"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


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
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in TRANSIENT_STATUS_CODES or attempt == 3:
                raise
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 3:
                raise
        time.sleep(1.5 * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch JSON for an unknown reason.")
