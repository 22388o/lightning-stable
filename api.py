from playhouse.shortcuts import model_to_dict
from services.lnmarkets import lnmarkets
from services.redis import redis
from services import lnbits
from secrets import token_hex

from fastapi import FastAPI, Body, HTTPException, Request, Depends
from configs import API_HOST, API_JWT_SECRET, API_PORT, SWAP_BTC_MAX, SWAP_BTC_MIN, SWAP_FIAT_MAX, SWAP_FIAT_MIN, TIME_DAY_IN_SECONDS
from helpers import percentage, timestamp
from schemas import DepositSchema, SwapSchema, UserSchema, WithdrawSchema
from json import dumps, loads
from re import sub

import middlewares
import database
import uvicorn
import bcrypt
import jwt

api = FastAPI()

@api.post("/api/v1/lnbits/webhook")
def lnbits_webhook(data: dict = Body(...)):
    payment_request = data.get("bolt11")
    if not (payment_request):
        raise HTTPException(400, "Payment request not found.")

    payment_hash = data.get("payment_hash")
    if (lnbits.lnbits.check_invoice_status(payment_hash) == False):
        raise HTTPException(500, "Invoice has not been paid.")

    decode_invoice = lnbits.lnbits.decode_invoice(payment_request)
    if (payment_hash != decode_invoice["payment_hash"]):
        raise HTTPException(500, "Payment hash invalid.")
    
    if (data["amount"] != decode_invoice["amount_msat"]):
        raise HTTPException(500, "Amount invalid.")
    
    tx = redis.get(f"stable.tx.{payment_hash}")
    if not (tx):
        raise HTTPException(500, "Transaction already processed.")
    else:
        tx = loads(tx)

    username = tx["username"]
    balance = database.Balance.select().where(
        (database.Balance.username == username) & 
        (database.Balance.currency == "BTC")
    )
    amount = int(decode_invoice["amount_msat"] / 1000)
    if (balance.exists() == False):
        database.Balance.create(username=username, currency="BTC", balance=amount)
    else:
        balance = balance.get()
        balance_current = balance.balance
        balance.balance = balance_current + amount
        balance.save()      
    
    database.Transaction.create(
        txid=payment_hash,
        username=username,
        destination=username, 
        currency="BTC",
        value=amount,
        status="settled",
        typeof="deposit"
    )
    
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
    fee_sat = 0
    if (value > lnmarkets_balance):
        fee_sat = round(percentage(value - lnmarkets_balance, 1))
        if ((value + fee_sat) > balance_in_asset_current):
            raise HTTPException(500, "You don't have enough balance.") 
        
        balance_in_asset.balance = balance_in_asset_current - (value + fee_sat)
        balance_in_asset.save()
        
        payment_request = loads(lnmarkets.deposit({ "amount": (value - lnmarkets_balance) }))["paymentRequest"]
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
    
    swap = lnmarkets.swap( { "in_asset": in_asset, "out_asset": currency, "in_amount": value } )
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
        txid=token_hex(32),
        username=username,
        destination=username,
        currency=in_asset,
        fee=fee_sat,
        value=value,
        status="settled",
        typeof="withdraw"
    )
    database.Transaction.create(
        txid=token_hex(32),
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
def get_list_transactions(offset: int = 0, limit: int = 10, request: Request = Depends(middlewares.isAuthorization)):
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

@api.post("/api/deposit")
def deposit(data: DepositSchema, request: Request = Depends(middlewares.isAuthorization)):
    value = data.value
    if (value < 1):
        raise HTTPException(500, "Value is invalid.")
    
    description = data.description
    if (len(description) > 64):
        raise HTTPException(500, "Description is greater than 64 characters.")
    
    payment_request = lnbits.create_invoice(value, description)
    if (payment_request.get("message")):
        raise HTTPException(500, payment_request["message"])

    payment_hash = payment_request["payment_hash"]
    username = request.data["username"]
    expiry = payment_request["expiry"]
    redis.set(f"stable.tx.{payment_hash}", dumps({
        "txid":      payment_hash,
        "username":  username,
        "currency":  "BTC",
        "status":    "pending",
        "type":      "deposit",
        "created_at": timestamp() 
    }))
    redis.expire(f"stable.tx.{payment_hash}", expiry)
    return payment_request

@api.post("/api/withdraw")
def withdraw(data: WithdrawSchema, request: Request = Depends(middlewares.isAuthorization)):
    payment_request = data.payment_request
    try:
        decode_invoice = lnbits.lnbits.decode_invoice(payment_request)
    except:
        raise HTTPException(500, "Invoice is invalid.")
    
    amount_sat = int(decode_invoice["amount_msat"] / 1000)
    if (amount_sat < 1):
        raise HTTPException(500, "Value must be greater than or equal to 1 sats.")
    
    username = request.data["username"]
    balance = database.Balance.select().where(
        (database.Balance.username == username) & 
        (database.Balance.currency == "BTC") & 
        (database.Balance.balance > amount_sat)
    )
    if (balance.exists() == False):
        raise HTTPException(500, "You don't have enough balance.")
    else:
        balance = balance.get()
    
    balance_current = balance.balance
    if (amount_sat > balance_current):
        raise HTTPException(500, "You don't have enough balance.")

    lnmarkets_balance = loads(lnmarkets.get_user())["balance"] 
    lnbits_balance = round(lnbits.lnbits.get_wallet()["balance"] / 1000)
    fee_sat = round(percentage(amount_sat, 1))
    if ((amount_sat + fee_sat) > balance_current):
        raise HTTPException(500, "You don't have enough balance.") 
    
    balance.balance = balance_current - (amount_sat + fee_sat)
    balance.save()

    if (lnbits_balance > amount_sat):
        pay = lnbits.lnbits.pay_invoice(payment_request)
        if not (pay):
            balance.balance = balance_current
            balance.save()
            raise HTTPException(500, "Unable to pay invoice.")

        payment_hash = pay.get("payment_hash")
    elif (lnmarkets_balance > amount_sat) and (amount_sat >= 1000):
        pay = lnmarkets.withdraw( { "invoice": payment_request } )
        if not (pay):
            balance.balance = balance_current
            balance.save()
            raise HTTPException(500, "Unable to pay invoice.")
        else:
            pay = loads(pay)
        
        payment_hash = pay.get("payment_hash")
    else:
        balance.balance = balance_current
        balance.save()
        raise HTTPException(500, "Unable to pay invoice.")
    
    if not (payment_hash):
        balance.balance = balance_current
        balance.save()
        raise HTTPException(500, "Unable to pay invoice.")
    
    tx = database.Transaction.create(
        txid=payment_hash,
        username=username,
        destination=username,
        currency="BTC",
        value=amount_sat,
        fee=fee_sat,
        status="settled",
        typeof="withdraw"
    )
    tx = model_to_dict(tx)
    tx["type"] = tx["typeof"]
    del tx["id"]
    del tx["typeof"]
    return tx

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