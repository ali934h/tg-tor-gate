# AI handoff — tg-tor-gate

Technical briefing for an AI assistant picking up this project.

## Purpose

Single-user (or small allow-listed group) Telegram bot that manages **one**
local Tor daemon and exposes it as a fixed SOCKS5 proxy. The exit country is
switchable at runtime through Telegram, without editing files or restarting
by hand. This is a personal-use proxy manager, not a multi-tenant or
public-facing service.

## Architecture

```
Telegram ──▶ bot.py ──▶ tor_control.py ──(ControlPort, stem)──▶ tor (systemd)
                │                                                   │
                └──▶ locations.py ──(HTTPS)──▶ onionoo.torproject.org
                │
                └──▶ ip_check.py ──(SOCKS5, through tor)──▶ ipapi.co
```

- **One** Tor instance, **one** SocksPort. We never run multiple Tor
  processes — country switching is done by changing `ExitNodes` on the same
  instance and forcing a new circuit with `NEWNYM`. This keeps RAM usage low
  (a single Tor process, not N of them) which matters for small VPS
  deployments.
- `tor_control.py` opens a fresh `stem.control.Controller` connection per
  call rather than holding one open — simpler lifecycle, avoids stale
  connection issues across a long-running bot process.
- `locations.py` hits Onionoo's `/details` endpoint with
  `fields=country&flag=Exit&running=true` — server-side filtering keeps the
  response small (country codes only, not full relay objects). Cached to
  `locations_cache.json` next to the code, TTL-based (`LOCATIONS_CACHE_TTL_HOURS`).
- `countries.py` generates flag emoji algorithmically from ISO codes
  (Regional Indicator Symbols) rather than storing emoji per country —
  avoids a large lookup table and encoding issues.
- `ip_check.py` verifies the exit by making a real request *through* the
  Tor SOCKS5 proxy (not by querying Tor's internal state), so what the user
  sees matches what any application using the proxy would see.

## Key design decisions

- **Silent rejection of unauthorised users** — matches `tg-xui-manager` and
  `tg-hub` convention. No error message, no "you are not allowed" — the bot
  simply doesn't respond, so its existence isn't confirmed to strangers.
- **`StrictNodes 1`** is always set alongside `ExitNodes` — without it, Tor
  falls back to any exit if the requested country has no usable path at that
  moment, silently defeating the country selection.
- **No multi-instance Tor.** This was a deliberate simplification from an
  earlier design (10 parallel Tor processes for 10 fixed proxies) — a single
  instance with dynamic `ExitNodes` gives the same practical outcome (any
  country, on demand) at a fraction of the RAM.
- **Onionoo over a static country list** — the set of countries with active
  exit relays changes over time (relays go up/down); a hardcoded list would
  drift from reality and let users pick dead-end countries.

## Known limitations

- `ExitNodes` country selection depends on Tor actually having a usable exit
  in that country *right now*; very small countries can occasionally have
  zero usable exits despite Onionoo showing 1+ (e.g. one relay that just
  went offline between cache refreshes).
- The bot's systemd service runs as root, matching `tg-xui-manager`'s
  pattern, since it needs to run `systemctl restart tor`.
- No rate limiting beyond `/newip`'s cooldown — `/random` and `/locations`
  selections aren't throttled. Acceptable for single-user use; would need
  hardening for a shared bot.

## Planned features (not yet implemented)

- Optional per-country "favourites" shortcut list, configurable via a bot
  command instead of only browsing the full `/locations` list.
- Bandwidth/latency probe alongside `/ip` to help pick a fast exit, not just
  a working one.
