"""Live exit-country list, sourced from the Tor Project's Onionoo API.

Onionoo (https://onionoo.torproject.org) is the Tor Project's official
network-status API. We query the /details endpoint, filtered server-side to
currently running relays with the Exit flag, and ask only for the `country`
field to keep the response small. The result is cached to disk so we don't
hit the API on every button press.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from collections import Counter

import config

log = logging.getLogger("tg-tor-gate.locations")


def _cache_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, config.LOCATIONS_CACHE_FILE)


def _fetch_from_onionoo() -> list[tuple[str, int]]:
    """Query Onionoo for running exit relays and count them per country."""
    params = "type=relay&running=true&flag=Exit&fields=country"
    url = f"{config.ONIONOO_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "tg-tor-gate/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)

    counts: Counter[str] = Counter()
    for relay in data.get("relays", []):
        code = relay.get("country")
        if code:
            counts[code.upper()] += 1

    return sorted(
        ((code, n) for code, n in counts.items() if n >= config.MIN_EXIT_RELAYS),
        key=lambda item: (-item[1], item[0]),
    )


def get_exit_countries(force_refresh: bool = False) -> list[tuple[str, int]]:
    """Return [(country_code, exit_relay_count), ...], using the on-disk cache
    when it is fresh enough. Falls back to a stale cache if Onionoo is
    unreachable, and only raises if there is no cache at all.
    """
    path = _cache_path()
    ttl_sec = config.LOCATIONS_CACHE_TTL_HOURS * 3600

    if not force_refresh and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < ttl_sec:
            with open(path, encoding="utf-8") as f:
                return [tuple(item) for item in json.load(f)]

    try:
        countries = _fetch_from_onionoo()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(countries, f)
        return countries
    except Exception as exc:
        log.warning("Onionoo fetch failed (%s), falling back to cache if any", exc)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return [tuple(item) for item in json.load(f)]
        raise


def cache_age_minutes() -> float | None:
    path = _cache_path()
    if not os.path.exists(path):
        return None
    return (time.time() - os.path.getmtime(path)) / 60
