from os.path import expanduser
from secrets import token_hex
from os import environ, makedirs

PATH = expanduser("~/.ln-stable")

makedirs(f"{PATH}/data", exist_ok=True)

# API configuration.
API_HOST = environ.get("API_HOST", "0.0.0.0")
API_PORT = environ.get("API_PORT", 2631)
API_JWT_SECRET = environ["API_JWT_SECRET"]

# Time configuration.
TIME_HOUR_IN_SECONDS = (60 * 60)
TIME_DAY_IN_SECONDS = (TIME_HOUR_IN_SECONDS * 24) 

# LN Markets configuration.
LNM_KEY = environ["LNM_KEY"]
LNM_SECRET = environ["LNM_SECRET"]
LNM_NETWORK = environ.get("LNM_NETWORK", "mainnet")
LNM_PASSPHRASE = environ["LNM_PASSPHRASE"]

# Swap synthetic configuration.
SWAP_BTC_MAX = environ.get("SYNT_SWAP_BTC_MAX", 10000000)
SWAP_BTC_MIN = environ.get("SYNT_SWAP_BTC_MIN", 500)

SWAP_FIAT_MAX = environ.get("SYNT_SWAP_FIAT_MAX", 1000)
SWAP_FIAT_MIN = environ.get("SYNT_SWAP_FIAT_MAX", 0.01)

# Redis configuration.
REDIS_HOST = environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = environ.get("REDIS_PORT", 6379)
REDIS_PASS = environ.get("REDIS_PASS", "")

# Lnbits configuration.
LNBITS_HOST = environ.get("LNBITS_HOST", "https://legend.lnbits.com/api")
LNBITS_BASE_URL = environ.get("LNBITS_BASE_URL", "https://www.lnbits.com")
LNBITS_WEBHOOK_URL = environ.get("LNBITS_WEBHOOK_URL", f"http://127.0.0.1:{API_PORT}/api/v1/lnbits/webhook")
LNBITS_WALLET_ADMIN_KEY = environ["LNBITS_WALLET_ADMIN_KEY"]
LNBITS_WALLET_INVOICE_KEY = environ["LNBITS_WALLET_INVOICE_KEY"]