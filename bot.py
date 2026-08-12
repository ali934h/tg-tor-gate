"""tg-tor-gate — Telegram bot that manages a local Tor SOCKS5 proxy.

Lets an authorised user switch the Tor exit country on demand, picking from
the list of countries that currently have active exit relays (fetched live
from the Tor Project's Onionoo API — see locations.py).
"""

from __future__ import annotations

import logging
import random
import subprocess
import time

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
import ip_check
import locations
import tor_control
from countries import country_name, flag_emoji, label

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("tg-tor-gate.bot")

_last_newnym: float = 0.0

COMMANDS = [
    BotCommand("start", "Show the welcome message"),
    BotCommand("help", "List all commands"),
    BotCommand("status", "Show current exit country and proxy info"),
    BotCommand("ip", "Check the current exit IP and country"),
    BotCommand("locations", "Browse and pick an exit country"),
    BotCommand("random", "Switch to a random exit country"),
    BotCommand("any", "Clear the country restriction (any exit)"),
    BotCommand("newip", "Request a new circuit (same country)"),
    BotCommand("refresh", "Refresh the live country list"),
    BotCommand("restart", "Restart the Tor service"),
]

HELP_TEXT = (
    "*tg-tor-gate*\n"
    "Manages a local Tor SOCKS5 proxy — one fixed port, switchable exit country.\n\n"
    f"SOCKS5 endpoint: `{config.TOR_SOCKS_HOST}:{config.TOR_SOCKS_PORT}`\n\n"
    "*Commands*\n"
    "/status — current exit country, proxy address, Tor status\n"
    "/ip — check the current exit IP and country (live, via Tor)\n"
    "/locations — browse countries with active exit relays and pick one\n"
    "/random — switch to a random exit country\n"
    "/any — remove the country restriction (any exit worldwide)\n"
    "/newip — new circuit, same country\n"
    "/refresh — force-refresh the live country list from Onionoo\n"
    "/restart — restart the Tor service\n"
    "/help — this message"
)


def _authorised(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in config.ALLOWED_USERS)


async def _guard(update: Update) -> bool:
    """Return True if the request may proceed. Unauthorised users get silence."""
    if _authorised(update):
        return True
    log.info("Ignored message from unauthorised user %s", update.effective_user)
    return False


# ---------------------------------------------------------------- keyboards

def _locations_keyboard(
    countries_list: list[tuple[str, int]], page: int
) -> InlineKeyboardMarkup:
    per_page = config.LOCATIONS_PER_PAGE
    start = page * per_page
    page_items = countries_list[start : start + per_page]

    rows = [
        [InlineKeyboardButton(label(code, count), callback_data=f"loc:set:{code}")]
        for code, count in page_items
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"loc:page:{page - 1}"))
    total_pages = max(1, -(-len(countries_list) // per_page))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="loc:noop"))
    if start + per_page < len(countries_list):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"loc:page:{page + 1}"))
    rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("🌍 Any country", callback_data="loc:any"),
            InlineKeyboardButton("🔄 Refresh", callback_data="loc:refresh"),
        ]
    )
    return InlineKeyboardMarkup(rows)


# ------------------------------------------------------------------ helpers

async def _apply_country(update: Update, code: str | None) -> str:
    """Set the exit country, wait for a new circuit, and return a status line."""
    tor_control.set_exit_country(code)
    time.sleep(config.CIRCUIT_BUILD_WAIT_SEC)
    where = f"{flag_emoji(code)} {country_name(code)}" if code else "🌍 any country"
    return f"Exit country set to *{where}*.\nUse /ip to confirm the new exit IP."


# ----------------------------------------------------------------- commands

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return

    alive = tor_control.is_alive()
    if not alive:
        await update.message.reply_text("⚠️ Tor ControlPort is not reachable.")
        return

    current = tor_control.get_current_exit_country()
    where = f"{flag_emoji(current)} {country_name(current)}" if current else "🌍 any country"
    age = locations.cache_age_minutes()
    age_txt = f"{age:.0f} min ago" if age is not None else "never fetched"

    text = (
        "*Tor status*\n"
        "Tor daemon: 🟢 running\n"
        f"Exit country: *{where}*\n"
        f"SOCKS5: `{config.TOR_SOCKS_HOST}:{config.TOR_SOCKS_PORT}`\n"
        f"Country list last refreshed: {age_txt}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.message.reply_text("Checking current exit IP through Tor…")
    try:
        info = ip_check.current_exit()
        text = (
            f"IP: `{info['ip']}`\n"
            f"Country: {flag_emoji(info['country_code'])} {info['country_name']}"
        )
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        log.exception("ip_check failed")
        await msg.edit_text(f"❌ Could not check the exit IP: {exc}")


async def locations_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.message.reply_text("Fetching live exit-country list…")
    try:
        countries_list = locations.get_exit_countries()
    except Exception as exc:
        log.exception("locations fetch failed")
        await msg.edit_text(f"❌ Could not fetch the country list: {exc}")
        return

    await msg.edit_text(
        f"*{len(countries_list)} countries* currently have active Tor exit relays.\n"
        "Tap one to switch:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_locations_keyboard(countries_list, page=0),
    )


async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    try:
        countries_list = locations.get_exit_countries()
        code = random.choice(countries_list)[0]
    except Exception as exc:
        await update.message.reply_text(f"❌ Could not fetch the country list: {exc}")
        return

    msg = await update.message.reply_text(f"Switching to a random country…")
    try:
        text = await _apply_country(update, code)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        log.exception("set_exit_country failed")
        await msg.edit_text(f"❌ Could not switch country: {exc}")


async def any_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.message.reply_text("Removing the country restriction…")
    try:
        text = await _apply_country(update, None)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        log.exception("set_exit_country failed")
        await msg.edit_text(f"❌ Could not clear the restriction: {exc}")


async def newip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_newnym
    if not await _guard(update):
        return

    now = time.time()
    remaining = config.NEWNYM_COOLDOWN_SEC - (now - _last_newnym)
    if remaining > 0:
        await update.message.reply_text(f"⏳ Please wait {remaining:.0f}s before requesting again.")
        return
    _last_newnym = now

    msg = await update.message.reply_text("Requesting a new circuit…")
    try:
        tor_control.new_identity()
        time.sleep(config.CIRCUIT_BUILD_WAIT_SEC)
        await msg.edit_text("New circuit ready. Use /ip to see the new exit IP.")
    except Exception as exc:
        log.exception("new_identity failed")
        await msg.edit_text(f"❌ Could not request a new circuit: {exc}")


async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.message.reply_text("Refreshing the country list from Onionoo…")
    try:
        countries_list = locations.get_exit_countries(force_refresh=True)
        await msg.edit_text(f"✅ Refreshed — {len(countries_list)} countries available.")
    except Exception as exc:
        log.exception("refresh failed")
        await msg.edit_text(f"❌ Refresh failed: {exc}")


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    msg = await update.message.reply_text("Restarting the Tor service…")
    try:
        subprocess.run(["systemctl", "restart", "tor"], check=True, timeout=30)
        time.sleep(3)
        alive = tor_control.is_alive()
        await msg.edit_text("✅ Tor restarted." if alive else "⚠️ Restarted, but ControlPort not yet reachable.")
    except Exception as exc:
        log.exception("restart failed")
        await msg.edit_text(f"❌ Restart failed: {exc}")


# ------------------------------------------------------------ callback query

async def locations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not query.from_user or query.from_user.id not in config.ALLOWED_USERS:
        await query.answer()
        return

    await query.answer()
    action = query.data.split(":", 2)

    if action[1] == "noop":
        return

    if action[1] == "page":
        page = int(action[2])
        countries_list = locations.get_exit_countries()
        await query.edit_message_reply_markup(
            reply_markup=_locations_keyboard(countries_list, page)
        )
        return

    if action[1] == "refresh":
        countries_list = locations.get_exit_countries(force_refresh=True)
        await query.edit_message_text(
            f"*{len(countries_list)} countries* currently have active Tor exit relays.\n"
            "Tap one to switch:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_locations_keyboard(countries_list, page=0),
        )
        return

    if action[1] == "any":
        try:
            text = await _apply_country(update, None)
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as exc:
            await query.edit_message_text(f"❌ Could not clear the restriction: {exc}")
        return

    if action[1] == "set":
        code = action[2]
        try:
            text = await _apply_country(update, code)
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as exc:
            await query.edit_message_text(f"❌ Could not switch country: {exc}")
        return


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(COMMANDS)
    log.info("Bot commands menu registered")


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set in config.py")
    if not config.ALLOWED_USERS:
        log.warning("ALLOWED_USERS is empty — no one will be able to use this bot")

    app = Application.builder().token(config.BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CommandHandler("locations", locations_cmd))
    app.add_handler(CommandHandler("random", random_cmd))
    app.add_handler(CommandHandler("any", any_cmd))
    app.add_handler(CommandHandler("newip", newip_cmd))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CallbackQueryHandler(locations_callback, pattern=r"^loc:"))

    log.info("tg-tor-gate starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
