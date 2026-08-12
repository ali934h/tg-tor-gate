"""Check the current Tor circuit's exit relay: IP and country.

Reading Tor's circuit list passively isn't enough: Tor doesn't proactively
rebuild a circuit just because the old one was closed or NEWNYM was
signalled — it only builds one when something actually asks to use the
SocksPort. So this opens a real (tiny) SOCKS5 connection first, to force
Tor to attach a genuine circuit, then reads that exact circuit's exit
relay and country from the ControlPort — Tor's own built-in GeoIP database,
not an external HTTP request.

The probe target is Tor Project's own check.torproject.org — infrastructure
built to handle exactly this kind of traffic from every Tor user, unlike
small third-party IP-lookup APIs (ipapi.co, ip-api.com, etc.) which
rate-limit by source IP and get hit constantly since a Tor exit IP is
shared by thousands of concurrent users.
"""

from __future__ import annotations

import logging

import socks

import config
from countries import country_name
from tor_control import _connect

log = logging.getLogger("tg-tor-gate.ip_check")

_PROBE_HOST = "check.torproject.org"
_PROBE_PORT = 443


def _open_probe_connection() -> socks.socksocket:
    """Open a bare TCP connection through the Tor SOCKS5 proxy, forcing Tor
    to attach a real circuit. No data is sent — the TCP handshake alone is
    enough to make Tor pick (and, if needed, build) an exit.
    """
    sock = socks.socksocket()
    sock.set_proxy(socks.SOCKS5, config.TOR_SOCKS_HOST, config.TOR_SOCKS_PORT, rdns=True)
    sock.settimeout(config.CIRCUIT_BUILD_WAIT_SEC + 10)
    sock.connect((_PROBE_HOST, _PROBE_PORT))
    return sock


def current_exit() -> dict:
    """Return {'ip': ..., 'country_code': ..., 'country_name': ...} for the
    circuit's exit relay, forcing a fresh circuit to exist if needed.
    """
    sock = None
    try:
        sock = _open_probe_connection()

        with _connect() as controller:
            streams = [s for s in controller.get_streams() if s.status == "SUCCEEDED"]
            if not streams:
                raise RuntimeError("Could not find the stream for this connection")

            circ_id = streams[-1].circ_id
            circuit = next((c for c in controller.get_circuits() if c.id == circ_id), None)
            if not circuit or not circuit.path:
                raise RuntimeError("Could not find the circuit for this connection")

            exit_fingerprint = circuit.path[-1][0]

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
    finally:
        if sock is not None:
            sock.close()

    return {
        "ip": address,
        "country_code": code,
        "country_name": country_name(code) if code != "?" else "?",
    }
