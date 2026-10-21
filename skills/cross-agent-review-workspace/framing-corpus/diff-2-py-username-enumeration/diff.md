# api/routes/auth.py (new file)

from fastapi import APIRouter, HTTPException
from api.db import db
from api.auth import verify_password, issue_token
from api.schemas import LoginBody

router = APIRouter()


@router.post('/auth/login')
async def login(body: LoginBody):
    user = await db.users.find_one({'email': body.email})
    if not user:
        raise HTTPException(status_code=404, detail='No user with that email')
    if not verify_password(body.password, user['password_hash']):
        raise HTTPException(status_code=401, detail='Incorrect password')
    return {'token': issue_token(user)}
