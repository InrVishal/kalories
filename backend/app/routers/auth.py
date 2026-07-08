from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_user_by_username,
    create_user
)

router = APIRouter(prefix="/auth", tags=["auth"])

class UserAuthPayload(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str

@router.post("/register", response_model=TokenResponse)
async def register(payload: UserAuthPayload):
    username = payload.username.strip()
    password = payload.password
    
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password cannot be empty."
        )
        
    existing_user = await get_user_by_username(username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already registered."
        )
        
    hashed = hash_password(password)
    await create_user(username, hashed)
    
    access_token = create_access_token(data={"sub": username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": username
    }

@router.post("/login", response_model=TokenResponse)
async def login(payload: UserAuthPayload):
    username = payload.username.strip()
    password = payload.password
    
    user = await get_user_by_username(username)
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": username
    }
