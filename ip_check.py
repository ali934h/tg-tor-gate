"""Check the current Tor exit IP and its country.

The request is made *through* Tor's own SOCKS5 proxy, so the result reflects
exactly what any application using that proxy would see.
"""

from __future__ import annotations

import logging

import requests

import config

log = logging.getLogger("tg-tor-gate.ip_check")


def _socks_proxies() -> dict:
    proxy_url = f"socks5h://{config.TOR_SOCKS_HOST}:{config.TOR_SOCKS_PORT}"
    return {"http": proxy_url, "https": proxy_url}


def current_exit() -> dict:
    """Return {'ip': ..., 'country_code': ..., 'country_name': ...} for the
    current Tor exit, or raise on failure.
    """
    resp = requests.get(
        "https://ipapi.co/json/",
        proxies=_socks_proxies(),
        timeout=config.IP_CHECK_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(data.get("reason", "ipapi.co returned an error"))

    return {
        "ip": data.get("ip", "?"),
        "country_code": (data.get("country_code") or data.get("country") or "?").upper(),
        "country_name": data.get("country_name", "?"),
    }
