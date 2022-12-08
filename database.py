from configs import PATH
from peewee import SqliteDatabase, Model, TextField, FloatField, ForeignKeyField

database = SqliteDatabase(f"{PATH}/data/database.db")

class BaseModel(Model):
    class Meta:
        database = database

class User(BaseModel):
    username = TextField(unique=True)
    password = TextField()

class Balance(BaseModel):
    username = TextField()
    currency = TextField(choices=["BTC", "USD"])
    balance = FloatField(default=0)

database.create_tables([User, Balance])