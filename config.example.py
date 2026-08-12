# tg-tor-gate configuration
# Copy this file to config.py and fill in your values.
# config.py is in .gitignore — never commit it.

# --- Telegram ---
BOT_TOKEN = ""            # from @BotFather
ALLOWED_USERS = []        # list of numeric Telegram user IDs, e.g. [123456789]

# --- Tor control ---
TOR_CONTROL_HOST = "127.0.0.1"
TOR_CONTROL_PORT = 9051
TOR_CONTROL_PASSWORD = ""     # set by install.sh (matches HashedControlPassword in torrc)
TOR_SOCKS_HOST = "127.0.0.1"
TOR_SOCKS_PORT = 9050

# --- Behaviour ---
DEFAULT_COUNTRY = ""          # ISO country code, e.g. "DE". Empty = no restriction (any exit)
NEWNYM_COOLDOWN_SEC = 10       # Tor enforces its own minimum; this just throttles button spam
CIRCUIT_BUILD_WAIT_SEC = 6    # seconds to wait after NEWNYM before reporting the new exit IP

# --- Onionoo (live Tor network data) ---
ONIONOO_URL = "https://onionoo.torproject.org/summary"
LOCATIONS_CACHE_FILE = "locations_cache.json"
LOCATIONS_CACHE_TTL_HOURS = 6
LOCATIONS_PER_PAGE = 8         # countries shown per page in the /locations keyboard
MIN_EXIT_RELAYS = 1            # hide countries with fewer active exit relays than this

# --- IP check ---
IP_CHECK_URL = "https://api.ipify.org?format=json"
IP_CHECK_TIMEOUT_SEC = 15
