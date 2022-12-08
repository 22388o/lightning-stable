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
SYNT_SWAP_MAX = environ.get("SYNT_SWAP_MAX", 1000)
SYNT_SWAP_MIN = environ.get("SYNT_SWAP_MIN", 0.01)