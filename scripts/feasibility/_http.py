"""Polite sequential HTTP helper shared by the dev-only feasibility probes."""

import time
from typing import Any

import httpx

USER_AGENT = "opendata-atlas-feasibility/0"
DELAY_SECONDS = 0.2
TIMEOUT_SECONDS = 120.0
REGIONS = {"us": "https://api.us.socrata.com", "eu": "https://api.eu.socrata.com"}

_client = httpx.Client(
    headers={"User-Agent": USER_AGENT},
    timeout=TIMEOUT_SECONDS,
    follow_redirects=True,
)


def configure(user_agent: str, timeout: float = TIMEOUT_SECONDS) -> None:
    """Replace the shared client, e.g. so another dev script sends its own User-Agent."""
    global _client  # noqa: PLW0603
    _client.close()
    _client = httpx.Client(
        headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True
    )


def get_text(url: str, params: dict[str, Any] | None = None) -> tuple[int, str | None]:
    """GET `url` after a short sleep. Return (status, body text); status 0 on transport error."""
    time.sleep(DELAY_SECONDS)
    try:
        response = _client.get(url, params=params)
    except httpx.HTTPError:
        return 0, None
    return response.status_code, response.text


def get_detail(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET `url` after a short sleep and describe the outcome without raising.

    Keys: status (0 on transport error), json (parsed body or None), final_url (after
    redirects, None on transport error), error (exception class name or None), timeout (True
    when the exception is an httpx.TimeoutException).
    """
    time.sleep(DELAY_SECONDS)
    try:
        response = _client.get(url, params=params)
    except httpx.HTTPError as e:
        return {
            "status": 0,
            "json": None,
            "final_url": None,
            "error": type(e).__name__,
            "timeout": isinstance(e, httpx.TimeoutException),
        }
    try:
        body = response.json()
    except ValueError:
        body = None
    return {
        "status": response.status_code,
        "json": body,
        "final_url": str(response.url),
        "error": None,
        "timeout": False,
    }


def get(
    url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> tuple[int, Any]:
    """GET `url` after a short sleep. Return (status, JSON or None); status 0 on transport error."""
    time.sleep(DELAY_SECONDS)
    try:
        response = _client.get(url, params=params, headers=headers)
    except httpx.HTTPError:
        return 0, None
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None
