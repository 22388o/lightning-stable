from fastapi import Request, HTTPException
from helpers import timestamp
from configs import API_JWT_SECRET

import jwt

def isAuthorization(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not (token):
        raise HTTPException(401)
    else:
        try:
            data = jwt.decode(token, API_JWT_SECRET, algorithms=["HS256"])
        except:
            raise HTTPException(401)
        
        if not (data):
            raise HTTPException(401)
        
        if (data.get("exp", 0) < timestamp()) or (data.get("username") == None):
            raise HTTPException(401)
        else:
            request.data = { "username": data["username"] }        
            return request