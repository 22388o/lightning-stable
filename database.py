from datetime import datetime
from configs import PATH
from peewee import SqliteDatabase, Model, DateTimeField, TextField, FloatField

database = SqliteDatabase(f"{PATH}/data/database.db")

class BaseModel(Model):
    class Meta:
        database = database

class User(BaseModel):
    username = TextField(unique=True)
    password = TextField()

class Balance(BaseModel):
    username   = TextField()
    currency   = TextField(choices=["BTC", "USD"])
    balance    = FloatField(default=0)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

class Transaction(BaseModel):
    txid         = TextField()
    username     = TextField()
    destination  = TextField()
    currency     = TextField(choices=["BTC", "USD"])
    value        = FloatField(default=0)
    status       = TextField(choices=["settled", "pending", "canceled"])
    typeof       = TextField(column_name="type", choices=["withdraw", "deposit"])
    description  = TextField(null=True)
    created_at   = DateTimeField(default=datetime.now)
    updated_at   = DateTimeField(default=datetime.now)

database.create_tables([User, Balance, Transaction])