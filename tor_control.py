"""Thin wrapper around Tor's ControlPort (via the `stem` library).

Everything here talks to the *local* Tor daemon that tg-tor-gate manages —
never to a remote host. The bot never touches Tor's traffic itself, only its
control protocol, so the SOCKS5 proxy Tor already exposes on
TOR_SOCKS_HOST:TOR_SOCKS_PORT is what applications should point at.
"""

from __future__ import annotations

import logging

from stem import Signal
from stem.control import Controller

import config

log = logging.getLogger("tg-tor-gate.tor_control")


class TorControlError(Exception):
    pass


def _connect() -> Controller:
    try:
        controller = Controller.from_port(
            address=config.TOR_CONTROL_HOST, port=config.TOR_CONTROL_PORT
        )
    except Exception as exc:
        raise TorControlError(f"Could not reach Tor ControlPort: {exc}") from exc

    try:
        if config.TOR_CONTROL_PASSWORD:
            controller.authenticate(password=config.TOR_CONTROL_PASSWORD)
        else:
            controller.authenticate()
    except Exception as exc:
        controller.close()
        raise TorControlError(f"Tor ControlPort authentication failed: {exc}") from exc

    return controller


def get_current_exit_country() -> str:
    """Return the currently configured ExitNodes country code, or '' for any."""
    with _connect() as controller:
        value = controller.get_conf("ExitNodes", default="")
    # ExitNodes is stored as e.g. "{de}" — strip the braces
    value = (value or "").strip()
    if value.startswith("{") and value.endswith("}"):
        return value[1:-1].upper()
    return ""


def set_exit_country(country_code: str | None) -> None:
    """Restrict (or clear, if None/'') the exit country and rebuild circuits."""
    with _connect() as controller:
        if country_code:
            controller.set_conf("ExitNodes", "{" + country_code.lower() + "}")
            controller.set_conf("StrictNodes", "1")
        else:
            controller.set_conf("ExitNodes", "")
            controller.set_conf("StrictNodes", "0")
        controller.signal(Signal.NEWNYM)


def new_identity() -> None:
    """Ask Tor for a fresh circuit (new exit IP) without changing the country."""
    with _connect() as controller:
        controller.signal(Signal.NEWNYM)


def is_alive() -> bool:
    try:
        with _connect() as controller:
            return controller.is_alive()
    except TorControlError:
        return False
