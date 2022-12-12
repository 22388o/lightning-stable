from pydantic import BaseModel, PositiveFloat, PositiveInt
from typing import Optional

class UserSchema(BaseModel):
    username: str
    password: str

class SwapSchema(BaseModel):
    currency: str
    value: PositiveFloat

class DepositSchema(BaseModel):
    value: PositiveInt
    description: Optional[str] = ""

class WithdrawSchema(BaseModel):
    payment_request: str