from fastapi import Request, HTTPException, status
from jose import JWTError, jwt
from backend.utils.auth import is_token_revoked
import logging
from slowapi.util import get_remote_address

from config import get_settings
import logging
from datetime import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
UTC = timezone.utc


async def get_current_user(request: Request) -> dict:
    """Validate JWT token and return user data"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # jwt.decode will automatically check expiration
        payload = jwt.decode(
            token, 
            settings.secret_key, 
            algorithms=[settings.algorithm],
            options={"verify_exp": True}
        )
        
        # Check if token has been revoked
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_data = payload.get("user_data")
        if user_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_data
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )





