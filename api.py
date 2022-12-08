from services.lnmarkets import lnmarkets
from fastapi import FastAPI, HTTPException, Request, Depends
from configs import API_HOST, API_JWT_SECRET, API_PORT, SYNT_SWAP_MAX, SYNT_SWAP_MIN, TIME_DAY_IN_SECONDS
from helpers import timestamp
from schemas import SwapSchema, UserSchema
from json import loads
from re import sub

import middlewares
import database
import uvicorn
import logging
import bcrypt
import jwt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

api = FastAPI()

@api.post("/api/create")
def create_user(data: UserSchema):
    username = sub("[^a-zA-Z0-9 \n\.]", "", data.username)
    password = data.password
    if (len(username) < 8):
        raise HTTPException(400, "Username is invalid.")
    
    if (len(password) < 8):
        raise HTTPException(400, "Password is invalid.")

    if (database.User.select(database.User.username).where(database.User.username == username).exists() == True):
        raise HTTPException(401)
    
    hashed_password = bcrypt.hashpw(password=password.encode(), salt=bcrypt.gensalt())
    database.User.create(username=username, password=hashed_password)
    return { "message": "User created successfully." }

@api.post("/api/auth")
def auth_user(data: UserSchema):
    username = sub("[^a-zA-Z0-9 \n\.]", "", data.username)
    password = data.password
    if (len(username) < 8):
        raise HTTPException(400, "Username is invalid.")
    
    if (len(password) < 8):
        raise HTTPException(400, "Password is invalid.")
    
    user = database.User.select().where((database.User.username == username))
    if (user.exists() == False):
        raise HTTPException(401)
    else:
        user = user.get()

    hashed_password = user.password
    if (bcrypt.checkpw(password.encode(), hashed_password.encode()) == False):
        raise HTTPException(401)
    else:
        exp = timestamp() + TIME_DAY_IN_SECONDS
        token = jwt.encode(payload={ "username": username, "exp": exp }, key=API_JWT_SECRET, algorithm="HS256")
        return { "token": token, "exp": exp }    

@api.post("/api/swap")
def create_swap(data: SwapSchema, request: Request = Depends(middlewares.isAuthorization)):
    currency = data.currency
    if not (currency in ["USD", "BTC"]):
        raise HTTPException(500, "Currency is invalid.")
    
    value = data.value
    if (value < 0.01):
        raise HTTPException(500, "Value is invalid.")

    if (value > SYNT_SWAP_MAX):
        raise HTTPException(500, "Value is greater than allowed.")
    
    if (value < SYNT_SWAP_MIN):
        raise HTTPException(500, )

    username = request.data["username"]
    if (currency == "USD"):
        in_asset = "BTC"
        value = int(value)
    else:
        in_asset = "USD"
    
    balance_in_asset = database.Balance.select().where(
        (database.Balance.username == username) & 
        (database.Balance.currency == in_asset)
    )
    if (balance_in_asset.exists() == False):
        database.Balance.create(username=username, currency=in_asset)
        raise HTTPException(500, "Value is equal to zero.")
    else:
        balance_in_asset = balance_in_asset.get()
    
    balance_in_asset_current = balance_in_asset.balance
    if (value > balance_in_asset_current):
        raise HTTPException(500, "You don't have enough balance.") 
    else:
        balance_in_asset.balance = balance_in_asset_current - value
        balance_in_asset.save()
    
    swap = lnmarkets.swap({"in_asset": in_asset, "out_asset": currency, "in_amount": value})
    if not (swap):
        balance_in_asset.balance = balance_in_asset_current
        balance_in_asset.save()
        raise HTTPException(500, "Unable to swap.")
    else:
        swap = loads(swap)
    
    if not (swap.get("exchange_rate")):
        balance_in_asset.balance = balance_in_asset_current
        balance_in_asset.save()
        raise HTTPException(500, "It was not possible to swap the exchange.")
    
    out_amount = float(swap["out_amount"])

    balance_out_asset = database.Balance.select().where(
        (database.Balance.username == username) & 
        (database.Balance.currency == currency)
    )
    if (balance_out_asset.exists() == False):
        database.Balance.create(username=username, currency=currency, balance=out_amount)
    else:
        balance_out_asset = balance_out_asset.get()
        balance_out_asset.balance -= out_amount
        balance_out_asset.save()
    
    return { "coins": out_amount, "currency": currency }

@api.get("/api/balance")
def get_balance(currency: str = "BTC", request: Request = Depends(middlewares.isAuthorization)):
    currency = currency.upper()
    if not (currency in ["USD", "BTC"]):
        raise HTTPException(500, "Currency is invalid.")
    
    username = request.data["username"]
    balance = database.Balance.select(database.Balance.balance).where(
        (database.Balance.username == username) & (database.Balance.currency == currency))
    if (balance.exists() == False):
        return { "balance": 0 }
    else:
        balance = balance.get().balance
        return { "balance": balance }

@api.get("/api/balances")
def get_all_balances(request: Request = Depends(middlewares.isAuthorization)):
    username = request.data["username"]
    balances = {}
    for balance in database.Balance.select(database.Balance.balance, database.Balance.currency).where(database.Balance.username == username):
        balances[balance.currency] = balance.balance
    return balances

def start():
    uvicorn.run(api, host=API_HOST, port=API_PORT, log_config={
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(asctime)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",

            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "foo-logger": {"handlers": ["default"], "level": "DEBUG"},
        },
    })