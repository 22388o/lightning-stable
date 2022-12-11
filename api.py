from secrets import token_hex
from playhouse.shortcuts import model_to_dict
from services.lnmarkets import lnmarkets
from services import lnbits

from fastapi import FastAPI, HTTPException, Request, Depends
from configs import API_HOST, API_JWT_SECRET, API_PORT, SWAP_BTC_MAX, SWAP_BTC_MIN, SWAP_FIAT_MAX, SWAP_FIAT_MIN, TIME_DAY_IN_SECONDS
from helpers import percentage, timestamp
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
    if (len(username) < 8) or (len(password) > 64):
        raise HTTPException(400, "Username is invalid.")
    
    if (len(password) < 8) or (len(password) > 64):
        raise HTTPException(400, "Password is invalid.")

    if (database.User.select(database.User.username).where(database.User.username == username).exists() == True):
        raise HTTPException(401, "Unable to create account.")
    
    hashed_password = bcrypt.hashpw(password=password.encode(), salt=bcrypt.gensalt())
    database.User.create(username=username, password=hashed_password)
    return { "message": "User created successfully." }

@api.post("/api/auth")
def auth_user(data: UserSchema):
    username = sub("[^a-zA-Z0-9 \n\.]", "", data.username)
    password = data.password
    if (len(username) < 8) or (len(password) > 64):
        raise HTTPException(400, "Username is invalid.")
    
    if (len(password) < 8) or (len(password) > 64):
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
    if (value <= 0):
        raise HTTPException(500, f"Value is less than or equal to zero.")
    
    if (currency == "USD"):
        in_asset = "BTC"
        value = int(value)
        if (value > SWAP_BTC_MAX):
            raise HTTPException(500, f"Value is greater than {SWAP_BTC_MAX} sats.")
        
        if (value < SWAP_BTC_MIN):
            raise HTTPException(500, f"Value is less than {SWAP_BTC_MIN} sats.")
    else:
        in_asset = "USD"
        if (value < 0.01):
            raise HTTPException(500, "Value is invalid.")
        
        if (value > SWAP_FIAT_MAX):
            raise HTTPException(500, f"Value is greater than $ {SWAP_FIAT_MAX}.")
        
        if (value < SWAP_FIAT_MIN):
            raise HTTPException(500, f"Value is less than $ {SWAP_FIAT_MIN}.")
    
    username = request.data["username"]
    balance_in_asset = database.Balance.select().where((database.Balance.username == username) & (database.Balance.currency == in_asset))
    if (balance_in_asset.exists() == False):
        database.Balance.create(username=username, currency=in_asset)
        raise HTTPException(500, "You don't have enough balance.")
    else:
        balance_in_asset = balance_in_asset.get()

    balance_in_asset_current = balance_in_asset.balance
    if (value > balance_in_asset_current):
        raise HTTPException(500, "You don't have enough balance.") 

    lnmarkets_balance = loads(lnmarkets.get_user())["balance"] 
    if (value > lnmarkets_balance):
        fee_sat = round(percentage(value, 1))
        if ((value + fee_sat) > balance_in_asset_current):
            raise HTTPException(500, "You don't have enough balance.") 
        
        balance_in_asset.balance = balance_in_asset_current - (value + fee_sat)
        balance_in_asset.save()
        
        payment_request = loads(lnmarkets.deposit({ "amount": value }))["paymentRequest"]
        pay_invoice = lnbits.pay_invoice(payment_request)
        if (pay_invoice.get("message")):
            balance_in_asset.balance = balance_in_asset_current
            balance_in_asset.save()                
            raise HTTPException(500, "It was not possible to swap the exchange.")
        else:
            fee_sat = pay_invoice["fee_sat"]
            balance_in_asset.balance = balance_in_asset_current - (value + fee_sat)
            balance_in_asset.save()
    else:
        balance_in_asset.balance = balance_in_asset_current - value
        balance_in_asset.save()
    
    swap = lnmarkets.swap({"in_asset": in_asset, "out_asset": currency, "in_amount": value})
    if not (swap):
        balance_in_asset.balance = balance_in_asset_current
        balance_in_asset.save()
        raise HTTPException(500, "It was not possible to swap the exchange.")
    else:
        swap = loads(swap)
    
    if not (swap.get("exchange_rate")):
        balance_in_asset.balance = balance_in_asset_current
        balance_in_asset.save()
        raise HTTPException(500, "It was not possible to swap the exchange.")
    
    out_amount = float(swap["out_amount"])
    balance_out_asset = database.Balance.select().where((database.Balance.username == username) & (database.Balance.currency == currency))
    if (balance_out_asset.exists() == False):
        database.Balance.create(username=username, currency=currency, balance=out_amount)
    else:
        balance_out_asset = balance_out_asset.get()
        balance_out_asset.balance = balance_out_asset.balance + out_amount
        balance_out_asset.save()
    
    database.Transaction.create(
        txid=token_hex(16),
        username=username,
        destination=username,
        currency=in_asset,
        value=value,
        status="settled",
        typeof="withdraw"
    )
    database.Transaction.create(
        txid=token_hex(16),
        username=username,
        destination=username, 
        currency=currency,
        value=out_amount,
        status="settled",
        typeof="deposit"
    )
    return { "coins": out_amount, "currency": currency }

@api.get("/api/balance")
def get_balance(currency: str = "BTC", request: Request = Depends(middlewares.isAuthorization)):
    currency = currency.upper()
    if not (currency in ["USD", "BTC"]):
        raise HTTPException(500, "Currency is invalid.")
    
    username = request.data["username"]
    balance = database.Balance.select(database.Balance.balance).where((database.Balance.username == username) & (database.Balance.currency == currency))
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

@api.get("/api/transaction/{txid}")
def get_transaction(txid: str, request: Request = Depends(middlewares.isAuthorization)):
    username = request.data["username"]
    tx = database.Transaction.select().where((database.Transaction.username == username) & (database.Transaction.txid == txid))
    if (tx.exists() == False):
        raise HTTPException(500, "Tx does not exist.")
    else:
        tx = tx.get()
        tx = model_to_dict(tx)
        tx["type"] = tx["typeof"]
        del tx["id"]
        del tx["typeof"]
        return tx

@api.get("/api/transactions")
def get_list_transactions(offset: str = 0, limit = 10, request: Request = Depends(middlewares.isAuthorization)):
    username = request.data["username"]
    txs = []
    if (limit > 10):
        raise HTTPException(500, "The limit must be less than 10.")
    
    for tx in database.Transaction.select().order_by(database.Transaction.created_at).where((database.Transaction.username == username)).limit(limit).offset(offset):
        tx = model_to_dict(tx)
        tx["type"] = tx["typeof"]
        del tx["id"]
        del tx["typeof"]
        txs.append(tx)
    return txs
    
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