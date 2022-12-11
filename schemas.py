from pydantic import BaseModel, PositiveFloat

class UserSchema(BaseModel):
    username: str
    password: str

class SwapSchema(BaseModel):
    currency: str
    value: PositiveFloat
