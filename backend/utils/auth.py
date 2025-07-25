from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
import uuid
import json
import redis
import ssl
import logging
import time
import sys
from urllib.parse import urlparse
import asyncio

from shared_variables import (redis_client)

from config import get_settings
import logging
from datetime import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
UTC = timezone.utc




# State management functions
def store_state(state: str, data: dict):
    """Store auth state in Redis with expiration"""
    key = f"auth_state:{state}"
    redis_client.setex(key, 600, json.dumps(data))  # 10 minutes expiration

def get_state(state: str) -> Optional[dict]:
    """Retrieve auth state from Redis"""
    key = f"auth_state:{state}"
    data = redis_client.get(key)
    return json.loads(data) if data else None

def delete_state(state: str):
    """Delete auth state from Redis"""
    key = f"auth_state:{state}"
    redis_client.delete(key)

def store_refresh_token(user_id: str, refresh_token: str):
    """Store refresh token in Redis with expiration"""
    key = f"refresh_token:{user_id}"
    expiration = settings.refresh_token_expire_days * 86400  # Convert days to seconds
    redis_client.setex(key, expiration, refresh_token)

def get_refresh_token(user_id: str) -> Optional[str]:
    """Retrieve refresh token from Redis"""
    key = f"refresh_token:{user_id}"
    return redis_client.get(key)

def delete_refresh_token(user_id: str):
    """Delete refresh token from Redis"""
    key = f"refresh_token:{user_id}"
    redis_client.delete(key)

# Token revocation for Logouts
def revoke_access_token(jti: str):
    """Add JWT ID to revocation list"""
    key = f"access_token:revoked:{jti}"
    # Store until token would have expired anyway
    redis_client.setex(key, settings.access_token_expire_minutes * 60, "1")

def is_token_revoked(jti: str) -> bool:
    """Check if JWT ID is in revocation list"""
    key = f"access_token:revoked:{jti}"
    return redis_client.exists(key) > 0

# JWT token creation and validation
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    
    # Add JWT ID for revocation support
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": jti
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt



