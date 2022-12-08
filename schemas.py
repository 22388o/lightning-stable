from pydantic import BaseModel

class UserSchema(BaseModel):
    username: str
    password: str

class SwapSchema(BaseModel):
    currency: str
    value: float
