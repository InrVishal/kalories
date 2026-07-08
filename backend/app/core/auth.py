import logging
import hashlib
import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
from app.core.db import db

logger = logging.getLogger("kalories.auth")

# FastAPI OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# In-memory user database fallback (for when MongoDB is offline)
MOCK_USERS_DB = {}

def hash_password(password: str) -> str:
    """Hash password using PBKDF2 with a random salt."""
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + hashed.hex()

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify standard password against the stored salt + hash."""
    try:
        salt_hex, hashed_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        hashed = bytes.fromhex(hashed_hex)
        new_hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return new_hashed == hashed
    except Exception as e:
        logger.error(f"Error verifying password hash: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a JWT token with expiration timestamp."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_user_by_username(username: str) -> Optional[dict]:
    """Look up a user in MongoDB or the mock database if MongoDB is disconnected."""
    if db is not None:
        try:
            user = await db.users.find_one({"username": username})
            if user:
                return user
        except Exception as e:
            logger.error(f"Failed to lookup user '{username}' in MongoDB: {e}")
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=503, detail="Database connection error")
    
    if settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=503, detail="Database is offline")
    # Fallback to local memory mock database
    return MOCK_USERS_DB.get(username)

async def create_user(username: str, password_hash: str) -> dict:
    """Create a new user in MongoDB or the mock database."""
    user_doc = {
        "username": username,
        "hashed_password": password_hash,
        "created_at": datetime.utcnow()
    }
    if db is not None:
        try:
            await db.users.insert_one(user_doc)
            return user_doc
        except Exception as e:
            logger.error(f"Failed to save user '{username}' to MongoDB: {e}")
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=503, detail="Database connection error")
    
    if settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=503, detail="Database is offline")
    # Fallback
    MOCK_USERS_DB[username] = user_doc
    return user_doc

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency to protect endpoints.
    Verifies JWT token and retrieves the corresponding user document.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Allow fallback if no token provided for a smoother local dev experience,
    # or enforce strictly depending on token presence
    if not token:
        # Check if auth header is passed manually as standard Authorization header
        # (in case OAuth2 scheme misses it or it's formatted differently in WebSocket/fetch requests)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = await get_user_by_username(username)
    if user is None:
        raise credentials_exception
        
    return user
