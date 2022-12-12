from dotenv import load_dotenv
from os import environ

# Loads the variables of environments in the .env file
# of the current directory.
load_dotenv(environ.get("ENV_PATH", ".env"))

from services.redis import redis

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import sys
import api 

try:
    redis.ping()
except:
    logging.critical("Redis service unavailable.")
    logging.critical("Exit")
    sys.exit(0)

if __name__ == "__main__":
    api.start()