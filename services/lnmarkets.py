from lnmarkets.rest import LNMarketsRest
from configs import LNM_KEY, LNM_NETWORK, LNM_SECRET, LNM_PASSPHRASE

lnmarkets = LNMarketsRest(key=LNM_KEY, secret=LNM_SECRET, network=LNM_NETWORK, passphrase=LNM_PASSPHRASE)