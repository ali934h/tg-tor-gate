"""Check the current Tor circuit's exit relay: IP and country.

This is read directly from Tor's own ControlPort — the exit relay of the
most recently built circuit, plus Tor's built-in GeoIP database — instead
of making an external HTTP request.

External IP-lookup services (ipapi.co, ip-api.com, etc.) rate-limit by
source IP, and a Tor exit IP is shared by thousands of concurrent Tor
users, so those services return 429 Too Many Requests very often. Tor
already knows the exit relay's address and country locally, so there is no
need to leave the network for this at all.
"""

from __future__ import annotations

import logging

from countries import country_name
from tor_control import _connect

log = logging.getLogger("tg-tor-gate.ip_check")


def current_exit() -> dict:
    """Return {'ip': ..., 'country_code': ..., 'country_name': ...} for the
    exit relay of the most recently built circuit, or raise if none exists
    yet (e.g. called immediately after switching country).
    """
    with _connect() as controller:
        circuits = [
            c
            for c in controller.get_circuits()
            if c.purpose == "GENERAL" and c.status == "BUILT"
        ]
        if not circuits:
            raise RuntimeError("No circuit is built yet — try again in a few seconds")

        exit_fingerprint = circuits[-1].path[-1][0]

        address = "?"
        try:
            desc = controller.get_network_status(exit_fingerprint)
            if desc:
                address = desc.address
        except Exception as exc:
            log.warning("Could not resolve exit relay descriptor: %s", exc)

        code = "?"
        if address != "?":
            try:
                result = controller.get_info(f"ip-to-country/{address}", default="?")
                code = (result or "?").upper()
            except Exception as exc:
                log.warning("Could not resolve exit relay country: %s", exc)

    return {
        "ip": address,
        "country_code": code,
        "country_name": country_name(code) if code != "?" else "?",
    }
